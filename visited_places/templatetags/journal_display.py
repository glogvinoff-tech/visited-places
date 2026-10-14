from datetime import date, datetime

from django import template
from django.utils import formats, timezone
from django.utils.dateparse import parse_date, parse_datetime

register = template.Library()


def parsed_date(value):
    if isinstance(value, str):
        try:
            value = parse_date(value) or parse_datetime(value)
        except ValueError:
            return None
    if isinstance(value, datetime) and timezone.is_aware(value):
        value = timezone.localtime(value)
    return value if isinstance(value, (date, datetime)) else None


@register.filter
def journal_date(value):
    value = parsed_date(value)
    return formats.date_format(value, "d.m.Y") if value else ""


@register.filter
def journal_time(value):
    value = parsed_date(value)
    return formats.time_format(value, "H:i") if isinstance(value, datetime) else ""
