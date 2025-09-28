from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TierLimits:
    max_saved_portfolios: int
    max_compare_symbols: int
    history_days: int


def get_user_status(user) -> str:
    if not getattr(user, "is_authenticated", False):
        return "basic"
    profile = getattr(user, "userprofile", None)
    return getattr(profile, "status", "basic")


def get_limits_for_status(status: str) -> TierLimits:
    if status == "pro":
        return TierLimits(max_saved_portfolios=50, max_compare_symbols=12, history_days=365)
    return TierLimits(max_saved_portfolios=3, max_compare_symbols=4, history_days=30)

