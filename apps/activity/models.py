from __future__ import annotations

from django.conf import settings
from django.db import models


class ViewEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    symbol = models.CharField(max_length=20)
    viewed_at = models.DateTimeField(auto_now_add=True)


class SavedSet(models.Model):
    TYPE_CHOICES = [("compare", "compare"), ("watchlist", "watchlist")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    name = models.CharField(max_length=200)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

