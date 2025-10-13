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


@register.filter
def lookup(dictionary, key):
    """Lookup a key in a dictionary."""
    if not isinstance(dictionary, dict):
        return None
    return dictionary.get(key)


@register.filter
def format_market_cap_no_currency(value, currency='USD'):
    """
    Format market cap with proper abbreviation but without currency symbol.
    
    Args:
        value: The market cap value
        currency: The currency code (for future use, currently not used)
    
    Returns:
        Formatted market cap string without currency symbol
    """
    if value is None:
        return '-'
    
    try:
        num_value = float(value)
    except (ValueError, TypeError):
        return '-'
    
    if num_value >= 1e12:
        return f"{num_value/1e12:.1f}T"
    elif num_value >= 1e9:
        return f"{num_value/1e9:.1f}B"
    elif num_value >= 1e6:
        return f"{num_value/1e6:.1f}M"
    elif num_value >= 1e3:
        return f"{num_value/1e3:.1f}K"
    else:
        return f"{num_value:,.0f}"


@register.filter
def mul(value, arg):
    """
    Multiply the value by the argument.
    
    Args:
        value: The value to multiply
        arg: The multiplier
    
    Returns:
        The result of multiplication
    """
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def get_index(value, index):
    """
    Get an element from a list by index.
    
    Args:
        value: The list or sequence
        index: The index to retrieve
    
    Returns:
        The element at the specified index, or None if index is out of range
    """
    try:
        index = int(index)
        if hasattr(value, '__getitem__') and hasattr(value, '__len__'):
            if 0 <= index < len(value):
                return value[index]
    except (ValueError, TypeError, IndexError):
        pass
    return None