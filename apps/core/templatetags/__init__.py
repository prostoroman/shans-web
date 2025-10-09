from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter
def format_currency(value, currency='USD'):
    """
    Format a number as currency with proper symbol and formatting.
    
    Args:
        value: The numeric value to format
        currency: The currency code (USD, EUR, GBP, etc.)
    
    Returns:
        Formatted currency string
    """
    if value is None:
        return '-'
    
    try:
        num_value = float(value)
    except (ValueError, TypeError):
        return '-'
    
    # Currency symbols and formatting
    currency_map = {
        'USD': ('$', 2),
        'EUR': ('€', 2),
        'GBP': ('£', 2),
        'JPY': ('¥', 0),
        'CAD': ('C$', 2),
        'AUD': ('A$', 2),
        'NZD': ('NZ$', 2),
        'CHF': ('CHF ', 2),
        'CNY': ('¥', 2),
        'KRW': ('₩', 0),
        'INR': ('₹', 2),
        'RUB': ('₽', 2),
        'HKD': ('HK$', 2),
    }
    
    symbol, decimals = currency_map.get(currency.upper(), ('$', 2))
    
    # Format the number
    if num_value >= 1e12:
        formatted = f"{symbol}{num_value/1e12:.1f}T"
    elif num_value >= 1e9:
        formatted = f"{symbol}{num_value/1e9:.1f}B"
    elif num_value >= 1e6:
        formatted = f"{symbol}{num_value/1e6:.1f}M"
    elif num_value >= 1e3:
        formatted = f"{symbol}{num_value/1e3:.1f}K"
    else:
        formatted = f"{symbol}{num_value:,.{decimals}f}"
    
    return mark_safe(formatted)

@register.filter
def format_percentage(value):
    """
    Format a number as percentage with proper sign and color.
    
    Args:
        value: The numeric value to format as percentage
    
    Returns:
        Formatted percentage string with HTML
    """
    if value is None:
        return '-'
    
    try:
        num_value = float(value)
    except (ValueError, TypeError):
        return '-'
    
    # Determine color class
    if num_value > 0:
        color_class = 'text-success'
        sign = '+'
    elif num_value < 0:
        color_class = 'text-danger'
        sign = ''
    else:
        color_class = 'text-muted'
        sign = ''
    
    formatted = f"{sign}{num_value:.2f}%"
    return mark_safe(f'<span class="{color_class}">{formatted}</span>')

@register.filter
def format_market_cap(value):
    """
    Format market cap with proper abbreviation.
    
    Args:
        value: The market cap value
    
    Returns:
        Formatted market cap string
    """
    if value is None:
        return '-'
    
    try:
        num_value = float(value)
    except (ValueError, TypeError):
        return '-'
    
    if num_value >= 1e12:
        return f"${num_value/1e12:.1f}T"
    elif num_value >= 1e9:
        return f"${num_value/1e9:.1f}B"
    elif num_value >= 1e6:
        return f"${num_value/1e6:.1f}M"
    elif num_value >= 1e3:
        return f"${num_value/1e3:.1f}K"
    else:
        return f"${num_value:,.0f}"
