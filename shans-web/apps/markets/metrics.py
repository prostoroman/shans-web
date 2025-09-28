from __future__ import annotations

import numpy as np
import pandas as pd


def compute_cagr(prices: pd.Series) -> float:
    if prices.empty or prices.iloc[0] <= 0:
        return 0.0
    years = (prices.index[-1] - prices.index[0]).days / 365.25
    if years <= 0:
        return 0.0
    return (prices.iloc[-1] / prices.iloc[0]) ** (1 / years) - 1


def compute_volatility(returns: pd.Series, periods_per_year: int = 252) -> float:
    return float(returns.std(ddof=1) * np.sqrt(periods_per_year)) if len(returns) > 1 else 0.0


def compute_sharpe(returns: pd.Series, risk_free: float = 0.03, periods_per_year: int = 252) -> float:
    if returns.empty:
        return 0.0
    excess = returns - (risk_free / periods_per_year)
    denom = excess.std(ddof=1)
    if denom == 0 or np.isnan(denom):
        return 0.0
    return float(excess.mean() / denom * np.sqrt(periods_per_year))

