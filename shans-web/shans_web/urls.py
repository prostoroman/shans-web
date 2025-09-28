from __future__ import annotations

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("", include("apps.core.urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.markets.urls")),
    path("", include("apps.portfolio.urls")),
    path("", include("apps.activity.urls")),
    path("api/", include("apps.markets.api")),
    path("api/", include("apps.portfolio.api")),
]

