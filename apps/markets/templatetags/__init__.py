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
