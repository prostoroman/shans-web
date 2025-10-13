"""
Core views for home, health check, and SEO pages.
"""

from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.conf import settings
import logging

from apps.data.fmp_client import (
    get_most_searched_stocks,
    index_list,
    get_cryptocurrency_list,
    search_commodities,
    get_forex_list,
    search_etfs,
)

logger = logging.getLogger(__name__)


def home(request):
    """Home page view."""
    # Get symbols from query parameters (for pre-populating the search form)
    symbols = []
    symbols_param = request.GET.get('symbols', '')
    if symbols_param:
        symbols = [s.strip() for s in symbols_param.split(',') if s.strip()]
    
    # Build Most Searched payload for dropdown (approximation across types)
    most_searched_stocks = []
    most_searched_etfs = []
    most_searched_indexes = []
    most_searched_crypto = []
    most_searched_commodities = []
    most_searched_forex = []
    most_searched_all = []
    try:
        # Stocks
        stocks = get_most_searched_stocks(min_market_cap=0) or []
        most_searched_stocks = [
            {
                'symbol': s.get('symbol'),
                'name': s.get('name') or s.get('companyName') or s.get('symbol'),
                'exchange': s.get('exchangeShortName') or s.get('exchange') or '',
                'type': 'stock',
            }
            for s in stocks[:20]
            if isinstance(s, dict) and s.get('symbol')
        ]
        # ETFs
        etfs = search_etfs('') or []
        most_searched_etfs = [
            {
                'symbol': e.get('symbol'),
                'name': e.get('name') or e.get('symbol'),
                'exchange': e.get('exchange') or 'ETF',
                'type': 'etf',
            }
            for e in etfs[:15]
            if isinstance(e, dict) and e.get('symbol')
        ]
        # Indexes
        indexes = index_list() or []
        most_searched_indexes = [
            {
                'symbol': i.get('symbol'),
                'name': i.get('name') or i.get('symbol'),
                'exchange': 'INDEX',
                'type': 'index',
            }
            for i in indexes[:15]
            if isinstance(i, dict) and i.get('symbol')
        ]
        # Crypto
        cryptos = get_cryptocurrency_list() or []
        # Prefer BTCUSD/ETHUSD first
        cryptos.sort(key=lambda x: 0 if str(x.get('symbol','')).upper() in ['BTCUSD','ETHUSD'] else 1)
        most_searched_crypto = [
            {
                'symbol': c.get('symbol'),
                'name': c.get('name') or c.get('symbol'),
                'exchange': c.get('exchange') or 'CRYPTO',
                'type': 'cryptocurrency',
            }
            for c in cryptos[:15]
            if isinstance(c, dict) and c.get('symbol')
        ]
        # Commodities
        commodities = search_commodities('') or []
        most_searched_commodities = [
            {
                'symbol': c.get('symbol'),
                'name': c.get('name') or c.get('symbol'),
                'exchange': 'COMMODITY',
                'type': 'commodity',
            }
            for c in commodities[:15]
            if isinstance(c, dict) and c.get('symbol')
        ]
        # Forex (limit to majors if present)
        forex = get_forex_list() or []
        majors = {
            'EURUSD','GBPUSD','USDJPY','USDCHF','AUDUSD','USDCAD','NZDUSD','EURGBP','EURJPY','GBPJPY'
        }
        forex.sort(key=lambda x: 0 if str(x.get('symbol','')).upper() in majors else 1)
        most_searched_forex = [
            {
                'symbol': f.get('symbol'),
                'name': f.get('name') or f.get('symbol'),
                'exchange': 'FOREX',
                'type': 'forex',
            }
            for f in forex[:15]
            if isinstance(f, dict) and f.get('symbol')
        ]
        # Merge
        most_searched_all = (
            most_searched_stocks + most_searched_etfs + most_searched_indexes +
            most_searched_crypto + most_searched_commodities + most_searched_forex
        )
    except Exception as e:
        logger.error(f"Error building most searched payload: {e}")
    
    context = {
        'title': _('shans.ai - Financial Analysis Platform'),
        'description': _('Professional financial analysis, portfolio optimization, and market insights.'),
        # Legacy key no longer used in template, kept for safety
        'most_searched_stocks': most_searched_stocks,
        # New payload for dropdown rendering
        'most_searched_payload': {
            'stocks': most_searched_stocks,
            'etf': most_searched_etfs,
            'indexes': most_searched_indexes,
            'crypto': most_searched_crypto,
            'commodities': most_searched_commodities,
            'forex': most_searched_forex,
            'all': most_searched_all,
        },
        'symbols': symbols,
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


def sitemap_xml(request):
    """Sitemap.xml for SEO with absolute, canonical URLs to public routes."""

    # Only include non-redirecting, public pages
    route_names = [
        'core:home',
    ]

    # Prefer Django Sites framework domain in production; fallback to request host
    try:
        from django.contrib.sites.models import Site
        site_domain = Site.objects.get_current().domain
    except Exception:
        site_domain = ''

    host = site_domain or request.get_host()

    # Normalize host (strip protocol if accidentally stored)
    if host.startswith('http://'):
        host = host[len('http://'):]
    if host.startswith('https://'):
        host = host[len('https://'):]

    base_url = f"https://{host}"

    urls = [base_url + reverse(name) for name in route_names]

    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
"""

    for loc in urls:
        xml_content += f"""  <url>
    <loc>{loc}</loc>
  </url>
"""

    xml_content += "</urlset>"

    return HttpResponse(xml_content, content_type='application/xml')