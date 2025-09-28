from __future__ import annotations

import datetime as dt
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext as _


def home(request: HttpRequest) -> HttpResponse:
    context = {
        "title": _("Shans Web"),
    }
    return render(request, "core/home.html", context)


def healthz(request: HttpRequest) -> HttpResponse:
    return HttpResponse("ok", content_type="text/plain")


def robots_txt(request: HttpRequest) -> HttpResponse:
    lines = [
        "User-agent: *",
        "Disallow:",
        "Sitemap: /sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


def sitemap_xml(request: HttpRequest) -> HttpResponse:
    # Minimal static sitemap
    updated = dt.datetime.utcnow().date().isoformat()
    urls = [
        ("/", updated),
        ("/portfolio", updated),
    ]
    items = "".join(
        f"<url><loc>{request.build_absolute_uri(path)}</loc><lastmod>{lastmod}</lastmod></url>"
        for path, lastmod in urls
    )
    xml = f"<?xml version='1.0' encoding='UTF-8'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>{items}</urlset>"
    return HttpResponse(xml, content_type="application/xml")

