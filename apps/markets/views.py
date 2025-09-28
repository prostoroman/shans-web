from __future__ import annotations

import base64
import io
from typing import List

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from apps.data.services import ensure_fundamentals, ensure_prices
from apps.accounts.utils import get_limits_for_status, get_user_status
from apps.activity.models import ViewEvent, SavedSet
from .metrics import compute_cagr, compute_sharpe, compute_volatility


matplotlib.use("Agg")


def _plot_series(df: pd.DataFrame, cols: List[str]) -> str:
    fig, ax = plt.subplots(figsize=(6, 3))
    for c in cols:
        df[c].plot(ax=ax, label=c)
    ax.legend()
    ax.set_title("Prices")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def info_page(request: HttpRequest, symbol: str | None = None) -> HttpResponse:
    symbol = symbol or request.GET.get("symbol", "").upper()
    if not symbol:
        return redirect("home")
    inst, rows = ensure_prices(symbol, days=365 * 5)
    ensure_fundamentals(symbol)
    df = pd.DataFrame(
        {"date": [r.date for r in rows], "close": [r.close for r in rows]}
    ).set_index("date").sort_index()
    rets = df["close"].pct_change().dropna()
    metrics = {
        "cagr": compute_cagr(df["close"]),
        "volatility": compute_volatility(rets),
        "sharpe": compute_sharpe(rets, risk_free=float(settings.DEFAULT_RF)),
    }
    chart_data_url = "data:image/png;base64," + _plot_series(df, ["close"])
    # Log view event for authenticated users
    if request.user.is_authenticated:
        ViewEvent.objects.create(user=request.user, symbol=inst.symbol)

    context = {
        "inst": inst,
        "metrics": metrics,
        "chart_data_url": chart_data_url,
    }
    return render(request, "markets/info.html", context)


def compare_page(request: HttpRequest, symbols: str | None = None) -> HttpResponse:
    symbols = symbols or request.GET.get("symbols", "").upper()
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    status = get_user_status(request.user)
    limits = get_limits_for_status(status)
    if len(syms) > limits.max_compare_symbols:
        syms = syms[: limits.max_compare_symbols]
    if not syms:
        return redirect("home")
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
    chart_data_url = "data:image/png;base64," + _plot_series(combined, syms)
    context = {"symbols": syms, "metrics": metrics, "chart_data_url": chart_data_url}
    return render(request, "markets/compare.html", context)

