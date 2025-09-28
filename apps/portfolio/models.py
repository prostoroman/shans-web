from __future__ import annotations

from django.conf import settings
from django.db import models


class Portfolio(models.Model):
    VIS_CHOICES = [("private", "private"), ("unlisted", "unlisted"), ("public", "public")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    base_currency = models.CharField(max_length=8, default="USD")
    visibility = models.CharField(max_length=16, choices=VIS_CHOICES, default="private")
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class PortfolioPosition(models.Model):
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="positions")
    symbol = models.CharField(max_length=20)
    weight = models.FloatField(null=True)
    quantity = models.FloatField(null=True)

