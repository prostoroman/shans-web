"""
Template tags and filters for markets app.
"""

from django import template
from django.urls import reverse, NoReverseMatch

register = template.Library()


@register.filter
def get_asset_type_url(symbol):
    """
    Determine the appropriate URL for a symbol based on its type.
    Returns the URL name for the appropriate asset type route.
    """
    symbol_upper = symbol.upper()
    
    # Known asset type mappings
    if symbol_upper in ['GCUSD', 'SILUSD', 'CLUSD', 'NGUSD', 'HGUSD', 'PLUSD', 'PAUSD']:
        return 'markets:commodity_info'
    elif symbol_upper in ['BTCUSD', 'ETHUSD', 'ADAUSD', 'DOTUSD', 'LINKUSD', 'LTCUSD', 'XRPUSD']:
        return 'markets:crypto_info'
    elif symbol_upper in ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'NZDUSD']:
        return 'markets:forex_info'
    elif symbol_upper.startswith('^') or symbol_upper in ['GSPC', 'NDX', 'DJI', 'RUT', 'VIX']:
        return 'markets:index_info'
    elif symbol_upper in ['SPY', 'QQQ', 'IWM', 'VTI', 'VEA', 'VWO', 'AGG', 'TLT', 'GLD', 'SLV']:
        return 'markets:etf_info'
    else:
        # Default to stock
        return 'markets:stock_info'


@register.simple_tag
def asset_info_url(symbol):
    """
    Generate the appropriate URL for a symbol based on its type.
    """
    url_name = get_asset_type_url(symbol)
    try:
        return reverse(url_name, kwargs={'symbol': symbol})
    except NoReverseMatch:
        # Fallback to stock route
        return reverse('markets:stock_info', kwargs={'symbol': symbol})