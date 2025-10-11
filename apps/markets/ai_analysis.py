"""
AI analysis builder for single-asset summary using Financial Modeling Prep data.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import date

from django.conf import settings
from django.core.cache import cache

from apps.data import fmp_client
from apps.markets.metrics import calculate_metrics

logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def identify_asset_class(symbol: str) -> Tuple[str, Dict[str, Any]]:
    """
    Determine asset class: equity, etf, crypto, forex, commodity (fallback if detected elsewhere).
    Returns (asset_class, profile_like_dict).
    """
    sym = symbol.upper()
    profile = fmp_client.get_profile(sym)
    if profile:
        # FMP fields vary; check hints
        is_etf = bool(profile.get("isEtf") or profile.get("isFund") or (profile.get("type") == "etf"))
        if is_etf:
            return "etf", profile
        return "equity", profile

    # Heuristics
    if len(sym) == 6 and sym.isalpha():
        # Likely forex like EURUSD
        return "forex", {"symbol": sym}
    if sym.endswith("USD") or sym.endswith("BTC"):
        return "crypto", {"symbol": sym}

    # Try commodity quick quote to detect commodity
    comq = fmp_client.get_commodities_quote(sym)
    if comq:
        return "commodity", comq

    return "equity", {"symbol": sym}


def _fetch_history(symbol: str, asset_class: str, days: int = 3650) -> Dict[str, Any]:
    # 10 years default
    if asset_class == "commodity":
        series = fmp_client.get_commodities_price_history(symbol, days=days)
        return {"series": _normalize_series(series, price_keys=["price", "close", "adjClose"]) , "dividends": [], "splits": []}
    if asset_class == "crypto":
        series = fmp_client.get_cryptocurrency_price_history(symbol, days=days)
        return {"series": _normalize_series(series, price_keys=["price", "close", "adjClose"]) , "dividends": [], "splits": []}
    if asset_class == "forex":
        series = fmp_client.get_forex_price_history(symbol, days=days)
        return {"series": _normalize_series(series, price_keys=["price", "close", "adjClose"]) , "dividends": [], "splits": []}

    # equity/etf
    series = fmp_client.get_price_series(symbol)
    dividends = fmp_client.get_dividend_history(symbol)
    splits = fmp_client.get_stock_splits(symbol)
    return {
        "series": _normalize_series(series, price_keys=["close", "adjClose", "price"]) ,
        "dividends": [{"date": d.get("date"), "amount": _safe_float(d.get("adjDividend") or d.get("dividend"))} for d in (dividends or []) if d.get("date")],
        "splits": [{"date": s.get("date"), "ratio": s.get("label") or s.get("numerator")} for s in (splits or []) if s.get("date")],
    }


def _normalize_series(series: List[Dict[str, Any]], price_keys: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in series or []:
        d = p.get("date") or p.get("timestamp") or p.get("Date")
        price: Optional[float] = None
        for k in price_keys:
            if k in p and p[k] is not None:
                price = _safe_float(p[k])
                if price is not None:
                    break
        if d and price is not None:
            out.append({"date": str(d)[:10], "close": price})
    # ensure ascending by date
    try:
        out.sort(key=lambda x: x["date"])  # type: ignore[arg-type]
    except Exception:
        pass
    return out


def _compute_calculations(history_series: List[Dict[str, Any]], rf_annual: float) -> Dict[str, Any]:
    # Extract price list
    prices = [float(x["close"]) for x in history_series if x.get("close") is not None]
    if len(prices) < 2:
        return {"returns": {}, "volatility": None, "maxDD": None, "sharpe": None}

    # Rolling returns windows
    def window_days(years: float) -> int:
        return int(round(252 * years))

    def trailing_return(window: int) -> Optional[float]:
        if len(prices) < window + 1:
            return None
        start = prices[-window-1]
        end = prices[-1]
        return (end / start) - 1 if start > 0 else None

    returns = {
        "1M": trailing_return(window_days(1/12)),
        "3M": trailing_return(window_days(0.25)),
        "YTD": None,  # compute from first trading day of year if data present
        "1Y": trailing_return(window_days(1)),
        "3Y": trailing_return(window_days(3)),
        "5Y": trailing_return(window_days(5)),
        "10Y": trailing_return(window_days(10)),
    }

    # YTD calculation
    try:
        current_year = date.today().year
        first_idx = next((i for i, pt in enumerate(history_series) if str(pt.get("date", "")).startswith(str(current_year))), None)
        if first_idx is not None and first_idx < len(prices):
            start = prices[first_idx]
            end = prices[-1]
            returns["YTD"] = (end / start) - 1 if start > 0 else None
    except Exception:
        pass

    # Volatility, Sharpe, MaxDD
    metrics = calculate_metrics(prices, risk_free_rate=rf_annual, years=5.0)
    return {
        "returns": {k: (round(v, 6) if isinstance(v, float) and v is not None else None) for k, v in returns.items()},
        "volatility": round(metrics.get("volatility", 0.0), 6) if metrics else None,
        "maxDD": round(metrics.get("max_drawdown", 0.0), 6) if metrics else None,
        "sharpe": round(metrics.get("sharpe_ratio", 0.0), 6) if metrics else None,
    }


def build_data_contract(symbol: str) -> Dict[str, Any]:
    """Fetch, transform and assemble complete analysis JSON for a symbol."""
    sym = symbol.upper()

    asset_class, profile_or_meta = identify_asset_class(sym)

    # price/quote
    if asset_class == "commodity":
        quote = fmp_client.get_commodities_quote(sym) or {}
    elif asset_class == "crypto":
        quote = fmp_client.get_cryptocurrency_quote(sym) or {}
    elif asset_class == "forex":
        quote = fmp_client.get_forex_quote(sym) or {}
    else:
        quote = fmp_client.get_quote(sym) or {}

    # history
    history = _fetch_history(sym, asset_class)

    # fundamentals (equities/etfs)
    fundamentals: Dict[str, Any] = {}
    consensus: Dict[str, Any] = {}
    etf: Dict[str, Any] = {}
    if asset_class in ("equity", "etf"):
        # financials
        is_list = fmp_client.get_income_statement(sym, limit=5)
        bs_list = fmp_client.get_balance_sheet(sym, limit=5)
        cf_list = fmp_client.get_cash_flow(sym, limit=5)
        ratios_list = fmp_client.get_financial_ratios(sym)
        key_metrics = fmp_client.get_key_metrics(sym) or {}
        fundamentals = {
            "ttm": key_metrics,
            "ratios": ratios_list[:5] if isinstance(ratios_list, list) else [],
            "income": is_list,
            "balance": bs_list,
            "cashflow": cf_list,
        }
        # consensus
        consensus = {
            "analyst": fmp_client.get_analyst_estimates(sym),
            "targets": fmp_client.get_price_targets(sym),
            "rating": fmp_client.get_company_rating(sym),
        }
        # ETF specifics
        if asset_class == "etf":
            etf = fmp_client.get_etf_holdings(sym)

    # crypto/forex specifics already covered via quote/history
    crypto: Dict[str, Any] = quote if asset_class == "crypto" else {}
    forex: Dict[str, Any] = quote if asset_class == "forex" else {}

    # macro
    rf = fmp_client.get_risk_free_yield("3m") or settings.DEFAULT_RF
    mrp = fmp_client.get_market_risk_premium("US")

    # news
    news = fmp_client.get_stock_news(sym, limit=10)

    # calculations
    calc = _compute_calculations(history.get("series", []), rf)

    # valuation compact
    pe = None
    ev_ebitda = None
    div_yield = None
    if asset_class in ("equity", "etf"):
        pe = _safe_float((fmp_client.get_key_metrics(sym) or {}).get("peRatio"))
        # FMP fields variety - try multiple keys
        km = fmp_client.get_key_metrics(sym) or {}
        for k in ("enterpriseValueOverEBITDA", "evToEbitda", "evEbitda"):
            ev_ebitda = _safe_float(km.get(k)) if ev_ebitda is None else ev_ebitda
        div_yield = _safe_float(km.get("dividendYield"))

    # meta
    name = profile_or_meta.get("companyName") or profile_or_meta.get("name") or sym
    currency = profile_or_meta.get("currency") or quote.get("currency") or "USD"
    exchange = profile_or_meta.get("exchange") or quote.get("exchange") or ""
    sector = profile_or_meta.get("sector") or ""

    data = {
        "meta": {
            "symbol": sym,
            "assetClass": asset_class,
            "name": name,
            "currency": currency,
            "exchange": exchange,
            "sector": sector,
        },
        "price": {
            "last": _safe_float(quote.get("price") or quote.get("c")),
            "changePct": _safe_float(quote.get("changePercentage") or quote.get("changesPercentage")),
            "volume": _safe_float(quote.get("volume")),
            "beta": _safe_float((fmp_client.get_key_metrics(sym) or {}).get("beta")) if asset_class in ("equity", "etf") else None,
        },
        "history": history,
        "fundamentals": fundamentals,
        "consensus": consensus,
        "etf": etf,
        "crypto": {"quote": crypto, "history": history.get("series") if asset_class == "crypto" else []},
        "forex": {"quote": forex, "history": history.get("series") if asset_class == "forex" else []},
        "macro": {"riskFree": rf, "marketRiskPremium": mrp},
        "news": news,
        "calc": {
            **calc,
            "valuation": {"pe": pe, "evEbitda": ev_ebitda, "divYield": div_yield},
        },
    }

    return data


