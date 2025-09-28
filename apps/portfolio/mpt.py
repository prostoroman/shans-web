from __future__ import annotations

import numpy as np
import pandas as pd


def compute_mean_cov(price_frame: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    returns = price_frame.pct_change().dropna()
    mu = returns.mean()
    sigma = returns.cov()
    return mu, sigma


def min_variance_portfolio(mu: pd.Series, sigma: pd.DataFrame) -> pd.Series:
    inv = np.linalg.pinv(sigma.values)
    ones = np.ones(len(mu))
    w = inv @ ones
    w = w / w.sum()
    return pd.Series(w, index=mu.index)


def tangency_portfolio(mu: pd.Series, sigma: pd.DataFrame, rf: float = 0.0, periods: int = 252) -> pd.Series:
    excess = mu * periods - rf
    inv = np.linalg.pinv(sigma.values)
    w = inv @ excess.values
    w = w / w.sum()
    return pd.Series(w, index=mu.index)

