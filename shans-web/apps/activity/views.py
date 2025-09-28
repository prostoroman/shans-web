from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from .models import SavedSet, ViewEvent


@login_required
def history(request: HttpRequest) -> HttpResponse:
    qs = ViewEvent.objects.filter(user=request.user).order_by("-viewed_at")
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(request, "activity/history.html", {"page": page})


@login_required
def saved(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        type_ = request.POST.get("type", "compare")
        name = request.POST.get("name", "Compare set")
        payload = {}
        if type_ == "compare":
            payload = {"symbols": request.POST.get("symbols", "")}
        SavedSet.objects.create(user=request.user, type=type_, name=name, payload=payload)
        return redirect("saved")
    qs = SavedSet.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "activity/saved.html", {"items": qs})

