from __future__ import annotations

from django.db import models


class Instrument(models.Model):
    symbol = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200, blank=True)
    exchange = models.CharField(max_length=64, blank=True)
    asset_class = models.CharField(max_length=32, blank=True)
    currency = models.CharField(max_length=8, blank=True)
    country = models.CharField(max_length=64, blank=True)

    def __str__(self) -> str:  # pragma: no cover
        return self.symbol


class PriceOHLC(models.Model):
    instrument = models.ForeignKey(Instrument, on_delete=models.CASCADE)
    date = models.DateField()
    open = models.FloatField(null=True)
    high = models.FloatField(null=True)
    low = models.FloatField(null=True)
    close = models.FloatField()
    adj_close = models.FloatField(null=True)
    volume = models.BigIntegerField(null=True)

    class Meta:
        unique_together = ("instrument", "date")
        ordering = ["instrument_id", "date"]


class Fundamentals(models.Model):
    PERIOD_CHOICES = [("annual", "annual"), ("ttm", "ttm"), ("q", "q")]
    instrument = models.ForeignKey(Instrument, on_delete=models.CASCADE)
    period = models.CharField(max_length=10, choices=PERIOD_CHOICES, default="ttm")
    revenue = models.FloatField(null=True)
    ebitda = models.FloatField(null=True)
    net_income = models.FloatField(null=True)
    equity = models.FloatField(null=True)
    pe = models.FloatField(null=True)
    pb = models.FloatField(null=True)
    dividend_yield = models.FloatField(null=True)
    updated_at = models.DateTimeField(auto_now=True)


class CachedWindow(models.Model):
    instrument = models.ForeignKey(Instrument, on_delete=models.CASCADE)
    kind = models.CharField(max_length=32)  # e.g., prices:1825d
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("instrument", "kind")

