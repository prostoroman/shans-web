from __future__ import annotations

from typing import List

import pandas as pd
from django.conf import settings
from django.http import JsonResponse
from django.urls import path
from rest_framework.decorators import api_view

from apps.data.services import ensure_prices
from .mpt import compute_mean_cov, min_variance_portfolio, tangency_portfolio


@api_view(["POST"])
def api_portfolio_analyze(request):
    symbols = request.data.get("symbols", "")
    syms: List[str] = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not syms:
        return JsonResponse({"error": "symbols required"}, status=400)
    frames = {}
    for s in syms:
        inst, rows = ensure_prices(s, days=365 * 5)
        df = pd.DataFrame(
            {"date": [r.date for r in rows], s: [r.close for r in rows]}
        ).set_index("date").sort_index()
        frames[s] = df
    prices = pd.concat(frames.values(), axis=1, join="inner").dropna()
    mu, sigma = compute_mean_cov(prices)
    w_min = min_variance_portfolio(mu, sigma)
    w_tan = tangency_portfolio(mu, sigma, rf=float(settings.DEFAULT_RF))
    out = {
        "weights_min": {k: float(v) for k, v in w_min.items()},
        "weights_tan": {k: float(v) for k, v in w_tan.items()},
    }
    return JsonResponse(out)


urlpatterns = [
    path("portfolio/analyze", api_portfolio_analyze, name="api_portfolio_analyze"),
]

