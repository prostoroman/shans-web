from __future__ import annotations

from typing import List

import pandas as pd
from django.conf import settings
from django.http import JsonResponse
from django.urls import path
from rest_framework.decorators import api_view

from apps.data.services import ensure_fundamentals, ensure_prices
from .metrics import compute_cagr, compute_sharpe, compute_volatility


@api_view(["GET"])
def api_info(request):
    symbol = request.GET.get("symbol", "").upper()
    if not symbol:
        return JsonResponse({"error": "symbol required"}, status=400)
    inst, rows = ensure_prices(symbol, days=365 * 5)
    ensure_fundamentals(symbol)
    df = pd.DataFrame(
        {"date": [r.date for r in rows], "close": [r.close for r in rows]}
    ).set_index("date").sort_index()
    rets = df["close"].pct_change().dropna()
    out = {
        "symbol": inst.symbol,
        "name": inst.name,
        "currency": inst.currency,
        "metrics": {
            "cagr": compute_cagr(df["close"]),
            "volatility": compute_volatility(rets),
            "sharpe": compute_sharpe(rets, risk_free=float(settings.DEFAULT_RF)),
        },
        "series": df.tail(252).reset_index().to_dict(orient="records"),
    }
    return JsonResponse(out)


@api_view(["GET"])
def api_compare(request):
    symbols = request.GET.get("symbols", "").upper()
    if not symbols:
        return JsonResponse({"error": "symbols required"}, status=400)
    syms: List[str] = [s.strip() for s in symbols.split(",") if s.strip()]
    frames = {}
    for s in syms:
        inst, rows = ensure_prices(s, days=365 * 5)
        df = pd.DataFrame(
            {"date": [r.date for r in rows], s: [r.close for r in rows]}
        ).set_index("date").sort_index()
        frames[s] = df
    combined = pd.concat(frames.values(), axis=1, join="inner").dropna()
    returns = combined.pct_change().dropna()
    metrics = {
        s: {
            "cagr": compute_cagr(combined[s]),
            "volatility": compute_volatility(returns[s]),
            "sharpe": compute_sharpe(returns[s], risk_free=float(settings.DEFAULT_RF)),
        }
        for s in syms
    }
    corr = returns.corr().round(4).to_dict()
    out = {"metrics": metrics, "correlations": corr}
    return JsonResponse(out)


urlpatterns = [
    path("info", api_info, name="api_info"),
    path("compare", api_compare, name="api_compare"),
]

