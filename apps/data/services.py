from __future__ import annotations

import datetime as dt
from typing import List, Tuple

import pandas as pd

from .fmp_client import FMPClient
from .models import CachedWindow, Fundamentals, Instrument, PriceOHLC


def ensure_instrument(symbol: str) -> Instrument:
    symbol = symbol.upper()
    inst, _ = Instrument.objects.get_or_create(symbol=symbol)
    if not inst.name:
        profile = FMPClient().get_json(f"/profile/{symbol}")
        if isinstance(profile, list) and profile:
            p = profile[0]
            inst.name = p.get("companyName", "")
            inst.exchange = p.get("exchangeShortName", "")
            inst.currency = p.get("currency", "")
            inst.country = p.get("country", "")
            inst.save()
    return inst


def ensure_prices(symbol: str, days: int = 1825) -> Tuple[Instrument, List[PriceOHLC]]:
    inst = ensure_instrument(symbol)
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    data = FMPClient().get_json(
        f"/historical-price-full/{inst.symbol}",
        {"from": since, "serietype": "line"},
    )
    hist = data.get("historical", []) if isinstance(data, dict) else []
    created = []
    for row in hist:
        o = PriceOHLC.objects.update_or_create(
            instrument=inst,
            date=row.get("date"),
            defaults={
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "adj_close": row.get("adjClose"),
                "volume": row.get("volume"),
            },
        )
        created.append(o[0])
    return inst, created


def ensure_fundamentals(symbol: str) -> Fundamentals:
    inst = ensure_instrument(symbol)
    data = FMPClient().get_json(f"/key-metrics-ttm/{inst.symbol}")
    item = data[0] if isinstance(data, list) and data else {}
    fund, _ = Fundamentals.objects.update_or_create(
        instrument=inst,
        period="ttm",
        defaults={
            "pe": item.get("peRatioTTM"),
            "pb": item.get("pbRatioTTM"),
            "dividend_yield": item.get("dividendYieldTTM"),
        },
    )
    return fund

