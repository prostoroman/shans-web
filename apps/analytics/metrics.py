"""
Pure analytics functions for price-based KPIs and correlations.
These functions are intentionally framework-agnostic and easy to unit test.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Tuple
import math


def _to_list_floats(values: Iterable[float]) -> List[float]:
    return [float(v) for v in values]


def cagr(series_or_prices: Iterable[float], years: float) -> float:
    prices = _to_list_floats(series_or_prices)
    if years <= 0 or len(prices) < 2:
        return 0.0
    start = prices[0]
    end = prices[-1]
    if start <= 0:
        return 0.0
    return (end / start) ** (1.0 / years) - 1.0


def _daily_returns_from_prices(prices: List[float]) -> List[float]:
    returns: List[float] = []
    for i in range(1, len(prices)):
        prev = prices[i - 1]
        curr = prices[i]
        if prev == 0:
            continue
        returns.append((curr - prev) / prev)
    return returns


def vol_annual(returns: Iterable[float]) -> float:
    r = _to_list_floats(returns)
    if len(r) < 2:
        return 0.0
    mean = sum(r) / len(r)
    var = sum((x - mean) ** 2 for x in r) / max(len(r) - 1, 1)
    return math.sqrt(var) * math.sqrt(252.0)


def max_drawdown(prices: Iterable[float]) -> float:
    p = _to_list_floats(prices)
    if len(p) < 2:
        return 0.0
    peak = p[0]
    mdd = 0.0
    for price in p:
        if price > peak:
            peak = price
        draw = (peak - price) / peak if peak > 0 else 0.0
        if draw > mdd:
            mdd = draw
    return mdd


def sharpe(returns: Iterable[float], rf_annual: float) -> float:
    r = _to_list_floats(returns)
    if len(r) < 2:
        return 0.0
    rf_daily = rf_annual / 252.0
    excess = [x - rf_daily for x in r]
    mean = sum(excess) / len(excess)
    sigma = vol_annual(r) / math.sqrt(252.0)
    if sigma == 0:
        return 0.0
    return (mean * 252.0) / (sigma * math.sqrt(252.0))


def sortino(returns: Iterable[float], rf_annual: float) -> float:
    r = _to_list_floats(returns)
    if len(r) < 2:
        return 0.0
    rf_daily = rf_annual / 252.0
    excess = [x - rf_daily for x in r]
    mean = sum(excess) / len(excess)
    downs = [x for x in excess if x < 0]
    if not downs:
        return float("inf") if mean > 0 else 0.0
    down_std = vol_annual(downs) / math.sqrt(252.0)
    if down_std == 0:
        return 0.0
    return (mean * 252.0) / (down_std * math.sqrt(252.0))


def rolling_ytd_return(prices: Iterable[float]) -> float:
    p = _to_list_floats(prices)
    if not p:
        return 0.0
    # Approx YTD as last ~252 trading days start
    window = min(len(p) - 1, 252)
    if window <= 0:
        return 0.0
    start = p[-(window + 1)]
    end = p[-1]
    return (end / start) - 1.0 if start > 0 else 0.0


def corr_matrix(price_df) -> List[List[float]]:  # price_df can be pandas-like or list of lists
    # Accept a duck-typed object with .values if pandas, else assume list of lists
    import math as _math
    try:
        matrix = price_df.values  # type: ignore[attr-defined]
    except Exception:
        matrix = price_df
    # Convert to log returns and align by index
    series_returns: List[List[float]] = []
    for col in matrix:
        prices = _to_list_floats(col)
        if len(prices) < 3:
            series_returns.append([])
            continue
        rets: List[float] = []
        for i in range(1, len(prices)):
            prev = prices[i - 1]
            curr = prices[i]
            if prev <= 0 or curr <= 0:
                continue
            rets.append(math.log(curr / prev))
        series_returns.append(rets)
    n = len(series_returns)
    corr: List[List[float]] = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            a = series_returns[i]
            b = series_returns[j]
            m = min(len(a), len(b))
            if m < 2:
                rho = 0.0
            else:
                a2 = a[-m:]
                b2 = b[-m:]
                mean_a = sum(a2) / m
                mean_b = sum(b2) / m
                cov = sum((a2[k] - mean_a) * (b2[k] - mean_b) for k in range(m)) / max(m - 1, 1)
                std_a = math.sqrt(sum((x - mean_a) ** 2 for x in a2) / max(m - 1, 1))
                std_b = math.sqrt(sum((x - mean_b) ** 2 for x in b2) / max(m - 1, 1))
                rho = cov / (std_a * std_b) if std_a > 0 and std_b > 0 else 0.0
            corr[i][j] = corr[j][i] = rho
    return corr


def diversification_score(corr: List[List[float]]) -> float:
    n = len(corr)
    if n <= 1:
        return 0.0
    offdiag: List[float] = []
    for i in range(n):
        for j in range(n):
            if i != j:
                offdiag.append(corr[i][j])
    mean_off = sum(offdiag) / len(offdiag) if offdiag else 1.0
    return round(100.0 * (1.0 - mean_off), 1)

