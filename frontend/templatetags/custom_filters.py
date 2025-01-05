from django import template
from decimal import Decimal

register = template.Library()

@register.filter
def sub(value, arg):
    """Subtract the arg from the value."""
    try:
        return value - arg
    except (ValueError, TypeError):
        try:
            return value
        except (ValueError, TypeError):
            return ''

@register.filter(name='discount_percentage')
def discount_percentage(original_price, current_price):
    """Calculate the discount percentage"""
    try:
        original = Decimal(str(original_price))
        current = Decimal(str(current_price))
        if original > 0:
            discount = ((original - current) / original) * 100
            return int(discount)
        return 0
    except (ValueError, TypeError, ZeroDivisionError):
        return 0
