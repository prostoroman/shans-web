from __future__ import annotations

from typing import Dict


def plan_status(request) -> Dict[str, str | None]:
    if not request.user.is_authenticated:
        return {"plan_status": None}
    profile = getattr(request.user, "userprofile", None)
    return {"plan_status": getattr(profile, "status", None)}

