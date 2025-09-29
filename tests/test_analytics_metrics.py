import math
from apps.analytics.metrics import (
    cagr,
    vol_annual,
    max_drawdown,
    sharpe,
    sortino,
    rolling_ytd_return,
    diversification_score,
)


def test_cagr_basic():
    prices = [100, 110, 121]
    # 2 years, 10% annual
    assert abs(cagr(prices, 2.0) - 0.10) < 1e-6


def test_vol_and_sharpe_sortino():
    # synthetic small returns
    returns = [0.01, -0.005, 0.02, -0.01, 0.015]
    v = vol_annual(returns)
    assert v >= 0
    s = sharpe(returns, 0.03)
    so = sortino(returns, 0.03)
    assert isinstance(s, float)
    assert isinstance(so, float)


def test_max_drawdown():
    prices = [100, 120, 90, 130, 80]
    mdd = max_drawdown(prices)
    assert 0.0 <= mdd <= 1.0


def test_rolling_ytd():
    prices = list(range(1, 260))
    ytd = rolling_ytd_return(prices)
    assert ytd >= 0.0


def test_diversification_score():
    corr = [
        [1.0, 0.5, 0.2],
        [0.5, 1.0, 0.1],
        [0.2, 0.1, 1.0],
    ]
    score = diversification_score(corr)
    assert 0.0 <= score <= 100.0

