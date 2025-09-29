from __future__ import annotations

from typing import Optional
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle


class PlanRateThrottle(UserRateThrottle):
    """Throttle per user plan. Falls back to basic for anonymous users."""

    scope = "basic"

    def get_rate(self) -> Optional[str]:
        request = getattr(self, "request", None)
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False) and hasattr(user, "profile"):
            return self.THROTTLE_RATES.get("pro" if user.profile.is_pro else "basic")
        # anonymous -> basic
        return self.THROTTLE_RATES.get("basic")


class BasicAnonThrottle(AnonRateThrottle):
    scope = "basic"

