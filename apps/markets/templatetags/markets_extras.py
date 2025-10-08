"""
Custom template filters for markets app.
"""

from django import template

register = template.Library()


@register.filter
def lookup(dictionary, key):
    """Lookup a key in a dictionary."""
    if not isinstance(dictionary, dict):
        return None
    return dictionary.get(key)


@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary."""
    if not isinstance(dictionary, dict):
        return None
    return dictionary.get(key)


@register.filter
def format_market_cap(value, currency='USD'):
    """Format market cap with currency symbol and abbreviations."""
    if not value or value == 0:
        return 'N/A'
    
    # Convert to float if it's a string
    try:
        value = float(value)
    except (ValueError, TypeError):
        return 'N/A'
    
    # Add currency symbol
    currency_symbol = '$' if currency == 'USD' else currency
    
    # Format with abbreviations
    if value >= 1e12:  # Trillions
        return f"{currency_symbol}{value/1e12:.1f}T"
    elif value >= 1e9:  # Billions
        return f"{currency_symbol}{value/1e9:.1f}B"
    elif value >= 1e6:  # Millions
        return f"{currency_symbol}{value/1e6:.1f}M"
    elif value >= 1e3:  # Thousands
        return f"{currency_symbol}{value/1e3:.1f}K"
    else:
        # Format with thousands separators using spaces
        formatted = f"{value:,.0f}".replace(',', ' ')
        return f"{currency_symbol}{formatted}"


@register.filter
def format_price(value, currency='USD'):
    """Format price with currency symbol and thousands separators."""
    if not value:
        return 'N/A'
    
    try:
        value = float(value)
    except (ValueError, TypeError):
        return 'N/A'
    
    # Add currency symbol
    currency_symbol = '$' if currency == 'USD' else currency
    
    # Format with thousands separators using spaces
    formatted = f"{value:,.2f}".replace(',', ' ')
    return f"{currency_symbol}{formatted}"


@register.filter
def format_market_cap_no_currency(value, currency='USD'):
    """Format market cap with abbreviations but without currency symbol."""
    if not value or value == 0:
        return 'N/A'
    
    # Convert to float if it's a string
    try:
        value = float(value)
    except (ValueError, TypeError):
        return 'N/A'
    
    # Format with abbreviations (no currency symbol)
    if value >= 1e12:  # Trillions
        return f"{value/1e12:.1f}T"
    elif value >= 1e9:  # Billions
        return f"{value/1e9:.1f}B"
    elif value >= 1e6:  # Millions
        return f"{value/1e6:.1f}M"
    elif value >= 1e3:  # Thousands
        return f"{value/1e3:.1f}K"
    else:
        # Format with thousands separators using spaces
        formatted = f"{value:,.0f}".replace(',', ' ')
        return formatted


@register.filter
def format_price_no_currency(value, currency='USD'):
    """Format price with thousands separators but without currency symbol."""
    if not value:
        return 'N/A'
    
    try:
        value = float(value)
    except (ValueError, TypeError):
        return 'N/A'
    
    # Format with thousands separators using spaces (no currency symbol)
    formatted = f"{value:,.2f}".replace(',', ' ')
    return formatted


@register.filter
def mul(value, arg):
    """Multiply value by arg."""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def get_index(list_or_tuple, index):
    """Get an item from a list or tuple by index."""
    try:
        index = int(index)
        if isinstance(list_or_tuple, (list, tuple)) and 0 <= index < len(list_or_tuple):
            return list_or_tuple[index]
        return None
    except (ValueError, TypeError, IndexError):
        return None