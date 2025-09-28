from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from .forms import ProfileForm
from .models import UserProfile


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    profile = UserProfile.objects.get(user=request.user)
    context = {
        "title": _("Dashboard"),
        "profile": profile,
    }
    return render(request, "accounts/dashboard.html", context)


@login_required
def profile_edit(request: HttpRequest) -> HttpResponse:
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            return redirect("dashboard")
    else:
        form = ProfileForm(instance=profile)
    return render(request, "accounts/profile.html", {"form": form})

