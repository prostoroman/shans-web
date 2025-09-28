from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    STATUS_BASIC = "basic"
    STATUS_PRO = "pro"
    STATUS_CHOICES = [
        (STATUS_BASIC, "basic"),
        (STATUS_PRO, "pro"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_BASIC)
    locale = models.CharField(max_length=8, default="en")
    marketing_opt_in = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Profile<{self.user_id}:{self.status}>"

