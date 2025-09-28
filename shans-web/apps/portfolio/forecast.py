from __future__ import annotations

import pandas as pd


def ewma_forecast(series: pd.Series, span: int = 30, horizon: int = 30) -> pd.Series:
    ema = series.ewm(span=span, adjust=False).mean()
    last = ema.iloc[-1] if not ema.empty else 0.0
    idx = pd.RangeIndex(1, horizon + 1)
    return pd.Series([last] * horizon, index=idx)

