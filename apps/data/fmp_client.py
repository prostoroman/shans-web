"""
Financial Modeling Prep client wrapper.

Priority: use the official `fmp_python` client if available, with robust
retry/backoff and aggressive Django cache. Fallback to direct HTTP if needed.
"""

import os
import time
import logging
from typing import Dict, List, Optional, Any, Callable, Tuple
from datetime import datetime, date

import requests

try:
    # Official client
    from fmp_python import FMP  # type: ignore
except Exception:  # pragma: no cover - optional dependency import guard
    FMP = None  # type: ignore

logger = logging.getLogger(__name__)

# FMP API configuration
BASE_URL = "https://financialmodelingprep.com/api/v3"


def _get_settings():
    """Safe access to Django settings inside functions."""
    try:
        from django.conf import settings
        return settings
    except Exception:  # pragma: no cover
        class _S:
            DEFAULT_RF = 0.03
            CACHE_TTL_EOD = 60 * 60
            CACHE_TTL_RATIOS = 45 * 60
            CACHE_TTL_INTRADAY = 8 * 60
            FMP_API_KEY = os.getenv("FMP_API_KEY", "")

        return _S()


def _get_api_key() -> str:
    settings = _get_settings()
    return getattr(settings, "FMP_API_KEY", "") or os.getenv("FMP_API_KEY", "")


def _get_cache():
    try:
        from django.core.cache import cache
        return cache
    except Exception:  # pragma: no cover - cache may not be available in some contexts
        return None


def _retry_with_backoff(func: Callable[[], Any], attempts: int = 3, base_delay: float = 0.5) -> Any:
    """Retry a callable with exponential backoff."""
    last_exc: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(base_delay * (2 ** attempt))
    if last_exc:
        raise last_exc
    return None


def _cached_call(cache_key: str, ttl: int, loader: Callable[[], Any]) -> Any:
    cache = _get_cache()
    if cache is not None:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    value = _retry_with_backoff(loader)
    if cache is not None and value is not None:
        cache.set(cache_key, value, ttl)
    return value


def _http_get_json(endpoint: str, params: Optional[Dict[str, Any]] = None, timeout: int = 8) -> Any:
    api_key = _get_api_key()
    if not api_key:
        logger.error("FMP_API_KEY not configured")
        return None
    url = f"{BASE_URL}/{endpoint}"
    query = dict(params or {})
    query["apikey"] = api_key
    resp = requests.get(url, params=query, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data


_fmp_client: Optional[Any] = None


def _get_fmp() -> Optional[Any]:
    global _fmp_client
    if _fmp_client is not None:
        return _fmp_client
    api_key = _get_api_key()
    if not api_key or FMP is None:
        return None
    try:
        _fmp_client = FMP(apikey=api_key)  # type: ignore[arg-type]
        return _fmp_client
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"Failed to init fmp_python client, will use HTTP fallback: {exc}")
        return None


def get_profile(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Get company profile for a symbol.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        Company profile data or None if error
    """
    settings = _get_settings()
    cache_key = f"fmp:profile:{symbol.upper()}"
    ttl = settings.CACHE_TTL_EOD

    def loader():
        client = _get_fmp()
        if client is not None:
            # fmp_python method names may vary; try common ones
            for method_name in ("company_profile", "profile"):
                if hasattr(client, method_name):
                    data = getattr(client, method_name)(symbol)
                    if isinstance(data, list):
                        return data[0] if data else None
                    return data
        data = _http_get_json(f"profile/{symbol}")
        if isinstance(data, list):
            return data[0] if data else None
        return data

    try:
        return _cached_call(cache_key, ttl, loader)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting profile for {symbol}: {e}")
        return None


def get_price_series(symbol: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get historical price data for a symbol.
    
    Args:
        symbol: Stock symbol
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        
    Returns:
        List of price data
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_EOD
    cache_key = f"fmp:hist:{symbol.upper()}:{start_date or ''}:{end_date or ''}"

    def loader():
        client = _get_fmp()
        if client is not None and hasattr(client, "historical_price_full"):
            data = client.historical_price_full(symbol, _from=start_date, to=end_date)  # type: ignore[call-arg]
            # client may return dict with 'historical'
            if isinstance(data, dict) and "historical" in data:
                return data.get("historical", [])
            if isinstance(data, list) and data and isinstance(data[0], dict) and "historical" in data[0]:
                return data[0]["historical"]
            return data or []
        params: Dict[str, Any] = {}
        if start_date:
            params["from"] = start_date
        if end_date:
            params["to"] = end_date
        data = _http_get_json(f"historical-price-full/{symbol}", params)
        if isinstance(data, list) and data and "historical" in data[0]:
            return data[0]["historical"]
        if isinstance(data, dict) and "historical" in data:
            return data.get("historical", [])
        return []

    try:
        result = _cached_call(cache_key, ttl, loader)
        return result or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting price series for {symbol}: {e}")
        return []


def get_key_metrics(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Get key metrics for a symbol.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        Key metrics data or None if error
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_RATIOS
    cache_key = f"fmp:key_metrics:{symbol.upper()}"

    def loader():
        client = _get_fmp()
        if client is not None:
            for method_name in ("key_metrics", "key_metrics_ttm"):
                if hasattr(client, method_name):
                    data = getattr(client, method_name)(symbol, limit=1)
                    if isinstance(data, list):
                        if data:
                            return data[0]
                    elif isinstance(data, dict):
                        return data
        data = _http_get_json(f"key-metrics/{symbol}", {"limit": 1})
        if isinstance(data, list) and data:
            return data[0]
        if not data:
            data = _http_get_json(f"ratios/{symbol}", {"limit": 1})
            if isinstance(data, list) and data:
                return data[0]
        return None

    try:
        return _cached_call(cache_key, ttl, loader)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting key metrics for {symbol}: {e}")
        return None


def get_financial_ratios(symbol: str) -> List[Dict[str, Any]]:
    """
    Get financial ratios for a symbol.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        List of financial ratios
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_RATIOS
    cache_key = f"fmp:ratios:{symbol.upper()}"

    def loader():
        client = _get_fmp()
        if client is not None and hasattr(client, "ratios"):
            data = client.ratios(symbol)
            return data or []
        data = _http_get_json(f"ratios/{symbol}")
        return data or []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting financial ratios for {symbol}: {e}")
        return []


def get_income_statement(symbol: str, limit: int = 1) -> List[Dict[str, Any]]:
    """
    Get income statement for a symbol.
    
    Args:
        symbol: Stock symbol
        limit: Number of periods to return
        
    Returns:
        List of income statements
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_RATIOS
    cache_key = f"fmp:income:{symbol.upper()}:{limit}"

    def loader():
        client = _get_fmp()
        if client is not None and hasattr(client, "income_statement"):
            data = client.income_statement(symbol, limit=limit)
            return data or []
        data = _http_get_json(f"income-statement/{symbol}", {"limit": limit})
        return data or []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting income statement for {symbol}: {e}")
        return []


def get_balance_sheet(symbol: str, limit: int = 1) -> List[Dict[str, Any]]:
    """
    Get balance sheet for a symbol.
    
    Args:
        symbol: Stock symbol
        limit: Number of periods to return
        
    Returns:
        List of balance sheets
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_RATIOS
    cache_key = f"fmp:balance:{symbol.upper()}:{limit}"

    def loader():
        client = _get_fmp()
        if client is not None and hasattr(client, "balance_sheet_statement"):
            data = client.balance_sheet_statement(symbol, limit=limit)
            return data or []
        data = _http_get_json(f"balance-sheet-statement/{symbol}", {"limit": limit})
        return data or []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting balance sheet for {symbol}: {e}")
        return []


def get_cash_flow(symbol: str, limit: int = 1) -> List[Dict[str, Any]]:
    """
    Get cash flow statement for a symbol.
    
    Args:
        symbol: Stock symbol
        limit: Number of periods to return
        
    Returns:
        List of cash flow statements
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_RATIOS
    cache_key = f"fmp:cashflow:{symbol.upper()}:{limit}"

    def loader():
        client = _get_fmp()
        if client is not None and hasattr(client, "cash_flow_statement"):
            data = client.cash_flow_statement(symbol, limit=limit)
            return data or []
        data = _http_get_json(f"cash-flow-statement/{symbol}", {"limit": limit})
        return data or []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting cash flow for {symbol}: {e}")
        return []


def get_quote(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Get real-time quote for a symbol.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        Quote data or None if error
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_INTRADAY
    cache_key = f"fmp:quote:{symbol.upper()}"

    def loader():
        client = _get_fmp()
        if client is not None and hasattr(client, "quote"):
            data = client.quote(symbol)
            if isinstance(data, list):
                return data[0] if data else None
            return data
        data = _http_get_json(f"quote/{symbol}")
        if isinstance(data, list):
            return data[0] if data else None
        return data

    try:
        return _cached_call(cache_key, ttl, loader)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting quote for {symbol}: {e}")
        return None


def search_symbols(query: str) -> List[Dict[str, Any]]:
    """
    Search for symbols by company name or symbol.
    
    Args:
        query: Search query
        
    Returns:
        List of matching symbols
    """
    settings = _get_settings()
    ttl = 24 * 60 * 60  # search can be cached longer
    cache_key = f"fmp:search:{query.strip().lower()}"

    def loader():
        client = _get_fmp()
        if client is not None and hasattr(client, "search"):
            data = client.search(query)
            return data or []
        data = _http_get_json("search", {"query": query})
        return data or []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error searching symbols for {query}: {e}")
        return []


def get_market_cap(symbol: str) -> Optional[float]:
    """
    Get market capitalization for a symbol.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        Market cap value or None if error
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_EOD
    cache_key = f"fmp:marketcap:{symbol.upper()}"

    def loader():
        # Client may not expose; fallback to HTTP
        data = _http_get_json(f"market-capitalization/{symbol}")
        if isinstance(data, list) and data:
            return data[0].get("marketCap")
        if isinstance(data, dict):
            return data.get("marketCap")
        return None

    try:
        return _cached_call(cache_key, ttl, loader)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting market cap for {symbol}: {e}")
        return None


def get_dividend_history(symbol: str) -> List[Dict[str, Any]]:
    """
    Get dividend history for a symbol.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        List of dividend payments
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_EOD
    cache_key = f"fmp:dividends:{symbol.upper()}"

    def loader():
        # HTTP fallback because client method may not exist
        data = _http_get_json(f"historical-price-full/stock_dividend/{symbol}")
        return data or []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting dividend history for {symbol}: {e}")
        return []


def get_earnings_calendar(symbol: str) -> List[Dict[str, Any]]:
    """
    Get earnings calendar for a symbol.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        List of earnings dates
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_EOD
    cache_key = f"fmp:earnings_cal:{symbol.upper()}"

    def loader():
        data = _http_get_json("earning_calendar", {"symbol": symbol})
        return data or []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting earnings calendar for {symbol}: {e}")
        return []


# Additional endpoints required by the app

def get_peers(symbol: str) -> List[str]:
    """Return peer symbols for a given symbol (for Compare auto-populate)."""
    settings = _get_settings()
    ttl = 24 * 60 * 60
    cache_key = f"fmp:peers:{symbol.upper()}"

    def loader():
        data = _http_get_json(f"stock/peers", {"symbol": symbol})
        if isinstance(data, dict) and "peersList" in data:
            return data.get("peersList", [])
        if isinstance(data, list):
            # sometimes returns list of symbols
            return data
        return []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting peers for {symbol}: {e}")
        return []


def get_dcf_premium_discount(symbol: str) -> Optional[float]:
    """Return premium/discount percentage vs market from DCF endpoint."""
    settings = _get_settings()
    ttl = settings.CACHE_TTL_RATIOS
    cache_key = f"fmp:dcf:{symbol.upper()}"

    def loader():
        data = _http_get_json(f"discounted-cash-flow/{symbol}")
        # DCF endpoint may return { 'symbol': 'AAPL', 'dcf': 155, 'Stock Price': 170 }
        if isinstance(data, list) and data:
            item = data[0]
        elif isinstance(data, dict):
            item = data
        else:
            return None
        try:
            dcf = float(item.get("dcf"))
            price = float(item.get("Stock Price") or item.get("price") or 0)
            if price > 0:
                return (dcf - price) / price
        except Exception:  # noqa: BLE001
            return None
        return None

    try:
        return _cached_call(cache_key, ttl, loader)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting DCF premium/discount for {symbol}: {e}")
        return None


def get_etf_holdings(symbol: str) -> Dict[str, Any]:
    """Top-10 holdings + sector/country weights and summary metrics for ETF."""
    settings = _get_settings()
    ttl = settings.CACHE_TTL_EOD
    cache_key = f"fmp:etf:{symbol.upper()}:holdings"

    def loader():
        top10 = _http_get_json(f"etf/holdings/{symbol}") or []
        sector_weights = _http_get_json(f"etf-sector-weightings/{symbol}") or []
        country_weights = _http_get_json(f"etf-country-weightings/{symbol}") or []
        summary_list = _http_get_json(f"profile/{symbol}") or []
        summary = summary_list[0] if isinstance(summary_list, list) and summary_list else {}
        return {
            "top10": top10[:10] if isinstance(top10, list) else [],
            "sector_weights": sector_weights,
            "country_weights": country_weights,
            "summary": {
                "expense_ratio": summary.get("expenseRatio"),
                "dividend_yield": summary.get("lastDiv"),
            },
        }

    try:
        return _cached_call(cache_key, ttl, loader) or {"top10": [], "sector_weights": [], "country_weights": [], "summary": {}}
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting ETF holdings for {symbol}: {e}")
        return {"top10": [], "sector_weights": [], "country_weights": [], "summary": {}}


def get_risk_free_yield(tenor: str = "3m") -> Optional[float]:
    """Fetch latest UST yield for tenor in {3m, 6m, 2y}. Returns annual decimal."""
    tenor_map = {"3m": "3month", "6m": "6month", "2y": "2year"}
    period = tenor_map.get(tenor.lower(), "3month")
    try:
        # v4 treasury endpoint
        data = requests.get(
            "https://financialmodelingprep.com/api/v4/treasury",
            params={"apikey": _get_api_key(), "period": period, "from": (date.today().replace(year=date.today().year - 1)).isoformat(), "to": date.today().isoformat()},
            timeout=8,
        ).json()
        if isinstance(data, list) and data:
            # take last non-null
            for row in reversed(data):
                try:
                    v = float(row.get("value"))
                    return v / 100.0
                except Exception:  # noqa: BLE001
                    continue
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Risk-free yield fetch failed, falling back to DEFAULT_RF: {e}")
    settings = _get_settings()
    return getattr(settings, "DEFAULT_RF", 0.03)


def quote_short(symbols: List[str]) -> List[Dict[str, Any]]:
    """Lightweight quotes for lists of symbols."""
    try:
        data = _http_get_json("quote-short/{}".format(",".join(symbols)))
        return data or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting quote_short for {symbols}: {e}")
        return []


def available_exchanges() -> List[str]:
    try:
        data = _http_get_json("available-exchanges")
        if isinstance(data, list):
            return [d.get("exchangeShortName") or d.get("name") for d in data if isinstance(d, dict)]
        return []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting available exchanges: {e}")
        return []


def index_list() -> List[Dict[str, Any]]:
    try:
        data = _http_get_json("quotes/index")
        return data or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting index list: {e}")
        return []