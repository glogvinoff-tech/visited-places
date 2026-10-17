from datetime import date, datetime

from django import template
from django.utils import formats, timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.templatetags.static import static

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


@register.filter
def place_image(place):
    place = dict(place)
    if place.get("image_url"):
        return place["image_url"]
    photos = {
        ("красная площадь", "москва"): "red-square.jpg",
        ("парк горького", "москва"): "gorky-park.jpg",
        ("эрмитаж", "санкт-петербург"): "hermitage.jpg",
        ("невский проспект", "санкт-петербург"): "nevsky.jpg",
        ("галатская башня", "стамбул"): "galata.jpg",
        ("казанский кремль", "казань"): "kazan.jpg",
    }
    name = place.get("place_name", place.get("name", ""))
    filename = photos.get((name.casefold(), place.get("city", "").casefold()))
    return static(f"visited_places/images/{filename}") if filename else ""
