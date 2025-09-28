from __future__ import annotations

from functools import wraps
from typing import Callable

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect


def require_pro(view_func: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not request.user.is_authenticated:
            return redirect("account_login")
        profile = getattr(request.user, "userprofile", None)
        if not profile or profile.status != "pro":
            messages.warning(request, "This feature requires a Pro plan.")
            return redirect("dashboard")
        return view_func(request, *args, **kwargs)

    return _wrapped

