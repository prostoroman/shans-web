from __future__ import annotations

from typing import List

import pandas as pd
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from apps.accounts.utils import get_limits_for_status, get_user_status
from apps.data.services import ensure_prices
from .models import Portfolio, PortfolioPosition
from .mpt import compute_mean_cov, min_variance_portfolio, tangency_portfolio


def portfolio_form(request: HttpRequest) -> HttpResponse:
    return render(request, "portfolio/form.html")


def portfolio_analyze(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return redirect("portfolio_form")
    symbols = request.POST.get("symbols", "").upper()
    syms: List[str] = [s.strip() for s in symbols.split(",") if s.strip()]
    if not syms:
        return redirect("portfolio_form")
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
    context = {
        "symbols": syms,
        "weights_min": w_min.round(4).to_dict(),
        "weights_tan": w_tan.round(4).to_dict(),
    }
    if request.user.is_authenticated and request.POST.get("save"):
        status = get_user_status(request.user)
        limits = get_limits_for_status(status)
        if Portfolio.objects.filter(user=request.user).count() >= limits.max_saved_portfolios:
            return render(request, "portfolio/result.html", {**context, "error": "Portfolio save limit reached for your plan."})
        p = Portfolio.objects.create(user=request.user, name="My Portfolio")
        for sym in syms:
            PortfolioPosition.objects.create(portfolio=p, symbol=sym, weight=float(w_tan.get(sym, 0)))
        context["saved_id"] = p.id
    return render(request, "portfolio/result.html", context)


urlpatterns = []

