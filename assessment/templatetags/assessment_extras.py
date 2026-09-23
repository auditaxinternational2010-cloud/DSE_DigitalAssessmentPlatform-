from django import template

register = template.Library()

@register.filter
def subtract(value, arg):
    """Subtract arg from value"""
    try:
        return int(value) - int(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def multiply(value, arg):
    """Multiply value by arg"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def get_numeric_value(numeric_data, field_name):
    """Return numeric_data[field_name] or empty string."""
    if not numeric_data:
        return ''
    return numeric_data.get(field_name, '')
