"""
Core views for home, health check, and SEO pages.
"""

from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext_lazy as _
from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def home(request):
    """Home page view."""
    context = {
        'title': _('shans.ai - Financial Analysis Platform'),
        'description': _('Professional financial analysis, portfolio optimization, and market insights.'),
    }
    return render(request, 'core/home.html', context)


@require_http_methods(["GET"])
def healthz(request):
    """Health check endpoint for monitoring."""
    return JsonResponse({
        'status': 'healthy',
        'version': '1.0.0',
        'debug': settings.DEBUG
    })


@cache_page(60 * 60 * 24)  # Cache for 24 hours
def robots_txt(request):
    """Robots.txt file for SEO."""
    content = """User-agent: *
Allow: /

Sitemap: https://{}/sitemap.xml
""".format(request.get_host())
    
    return HttpResponse(content, content_type='text/plain')


@cache_page(60 * 60 * 24)  # Cache for 24 hours
def sitemap_xml(request):
    """Sitemap.xml for SEO."""
    from django.contrib.sitemaps import Sitemap
    from django.urls import reverse
    
    class StaticViewSitemap(Sitemap):
        priority = 0.5
        changefreq = 'daily'
        
        def items(self):
            return [
                'core:home',
                'portfolio:form',
                'markets:info',
                'markets:compare',
            ]
        
        def location(self, item):
            return reverse(item)
    
    sitemap = StaticViewSitemap()
    content = sitemap.get_urls()
    
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
"""
    
    for url in content:
        xml_content += f"""  <url>
    <loc>{url['location']}</loc>
    <lastmod>{url['lastmod']}</lastmod>
    <changefreq>{url['changefreq']}</changefreq>
    <priority>{url['priority']}</priority>
  </url>
"""
    
    xml_content += "</urlset>"
    
    return HttpResponse(xml_content, content_type='application/xml')