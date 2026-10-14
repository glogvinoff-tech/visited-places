import json
from datetime import date
from functools import wraps
from pathlib import Path

from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, Paginator
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Min, Q
from django.db.models.deletion import ProtectedError
from django.forms.models import model_to_dict
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone

from .forms import PlaceForm, ProfileForm, TripForm, VisitForm
from .models import Place, Trip, Visit

PHOTOS = {
    ("красная площадь", "москва"): "red-square.jpg",
    ("парк горького", "москва"): "gorky-park.jpg",
    ("эрмитаж", "санкт-петербург"): "hermitage.jpg",
    ("невский проспект", "санкт-петербург"): "nevsky.jpg",
    ("галатская башня", "стамбул"): "galata.jpg",
    ("казанский кремль", "казань"): "kazan.jpg",
}
PHOTO_CREDITS = json.loads(
    (
        Path(__file__).parent / "static" / "visited_places" / "images" / "credits.json"
    ).read_text(encoding="utf-8")
)


def error(message, status=400, fields=None):
    payload = {"error": message}
    if fields:
        payload["errors"] = fields
    return JsonResponse(payload, status=status)


def api_view(methods):
    def decorate(view):
        @wraps(view)
        def dispatch(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return error("Войдите в аккаунт.", 401)
            if request.method not in methods:
                response = error("Метод не поддерживается.", 405)
                response["Allow"] = ", ".join(methods)
                return response
            try:
                return view(request, *args, **kwargs)
            except Http404:
                return error("Запись не найдена.", 404)
            except ValidationError as exc:
                fields = exc.message_dict if hasattr(exc, "message_dict") else None
                return error("Проверьте поля формы.", fields=fields)
            except ProtectedError:
                return error("Сначала удалите или перенесите связанные записи.", 409)
            except IntegrityError:
                return error(
                    "Такая запись уже существует или нарушает ограничения.", 409
                )
            except (ValueError, json.JSONDecodeError) as exc:
                return error(str(exc))

        return dispatch

    return decorate


def body(request):
    if request.content_type != "application/json":
        raise ValueError("Ожидается JSON (Content-Type: application/json).")
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Некорректный JSON.") from exc
    if not isinstance(data, dict):
        raise ValueError("Ожидается JSON-объект.")
    return data


def save_form(form_class, data, instance=None, user=None):
    unknown = set(data) - set(form_class.base_fields)
    if unknown:
        raise ValidationError({"__all__": "Форма содержит недоступные поля."})
    for field, value in data.items():
        if field in {"place", "trip", "rating"}:
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int)
            ):
                raise ValidationError({field: "Укажите целое число."})
        elif value is not None and not isinstance(value, str):
            raise ValidationError({field: "Укажите текстовое значение."})
    values = model_to_dict(instance, fields=form_class.Meta.fields) if instance else {}
    values.update(data)
    form = form_class(values, instance=instance)
    if user is not None:
        form.instance.user = user
    if not form.is_valid():
        raise ValidationError(form.errors.as_data())
    return form.save()


def page_data(request, records, serialize):
    try:
        size = int(request.GET.get("page_size", 12))
        number = int(request.GET.get("page", 1))
    except ValueError as exc:
        raise ValueError("Номер и размер страницы должны быть целыми числами.") from exc
    if not 1 <= size <= 200 or number < 1:
        raise ValueError("Недопустимые параметры страницы.")
    paginator = Paginator(records, size)
    try:
        page = paginator.page(number)
    except EmptyPage as exc:
        raise ValueError("Страница не найдена.") from exc
    return {
        "results": [serialize(item) for item in page],
        "count": paginator.count,
        "page": page.number,
        "pages": paginator.num_pages,
        "page_size": size,
    }


def page_response(request, records, serialize):
    return JsonResponse(page_data(request, records, serialize))


def place_data(place):
    image = place.image_url
    filename = PHOTOS.get((place.name_key, place.city_key))
    if not image and filename:
        image = static(f"visited_places/images/{filename}")
    return {
        "id": place.pk,
        "url": reverse("visited_places:place-detail", args=[place.pk]),
        "name": place.name,
        "city": place.city,
        "country": place.country,
        "category": place.category,
        "image_url": place.image_url,
        "image": image,
        "credit": PHOTO_CREDITS.get(filename) if not place.image_url else None,
    }


def trip_data(trip):
    return {
        "id": trip.pk,
        "url": reverse("visited_places:trip-detail", args=[trip.pk]),
        "name": trip.name,
        "place": place_data(trip.place),
        "start_date": trip.start_date.isoformat(),
        "end_date": trip.end_date.isoformat(),
        "visit_count": getattr(trip, "visit_count", 0),
    }


def visit_data(visit):
    timestamp = timezone.localtime(visit.visited_at)
    return {
        "id": visit.pk,
        "url": reverse("visited_places:visit-detail", args=[visit.pk]),
        "trip": trip_data(visit.trip),
        "visited_at": timestamp.strftime("%Y-%m-%dT%H:%M"),
        "rating": visit.rating,
        "note": visit.note,
    }


def user_data(user):
    return {
        "id": user.pk,
        "username": user.username,
        "name": user.get_full_name(),
        "email": user.email,
        "is_staff": user.is_staff,
    }


def require_staff(request):
    return None if request.user.is_staff else error("Нужны права администратора.", 403)


def place_records(request):
    query = request.GET.get("q", "").strip().casefold()
    records = Place.objects.all()
    if query:
        records = records.filter(
            Q(name_key__contains=query)
            | Q(city_key__contains=query)
            | Q(country_key__contains=query)
            | Q(category_key__contains=query)
        )
    return records


def trip_queryset(user):
    return (
        Trip.objects.select_related("place")
        .annotate(
            visit_count=Count(
                "visits",
                filter=None if user.is_staff else Q(visits__user=user),
            )
        )
        .order_by("-start_date", "-id")
    )


def trip_records(request):
    records = trip_queryset(request.user)
    query = request.GET.get("q", "").strip().casefold()
    if query:
        records = [
            trip
            for trip in records
            if any(
                query in value
                for value in (
                    trip.name.casefold(),
                    trip.place.name_key,
                    trip.place.city_key,
                )
            )
        ]
    return records


def visit_records(request):
    records = Visit.objects.filter(user=request.user).select_related("trip__place")
    query = request.GET.get("q", "").strip().casefold()
    trip_id = request.GET.get("trip")
    if trip_id:
        try:
            records = records.filter(trip_id=int(trip_id))
        except ValueError as exc:
            raise ValueError("Неверный идентификатор поездки.") from exc
    for parameter, lookup in (("from", "gte"), ("to", "lte")):
        value = request.GET.get(parameter)
        if value:
            try:
                day = date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("Дата должна иметь формат YYYY-MM-DD.") from exc
            records = records.filter(**{f"visited_at__date__{lookup}": day})
    if query:
        records = [
            visit
            for visit in records
            if any(
                query in value.casefold()
                for value in (
                    visit.trip.place.name,
                    visit.trip.place.city,
                    visit.trip.name,
                    visit.note,
                )
            )
        ]
    return records


@api_view(["GET", "POST"])
def places(request):
    if request.method == "GET":
        return page_response(request, place_records(request), place_data)
    with transaction.atomic():
        place = save_form(PlaceForm, body(request))
    return JsonResponse(place_data(place), status=201)


@api_view(["GET", "PATCH", "DELETE"])
def place_detail(request, pk):
    place = get_object_or_404(Place, pk=pk)
    if request.method == "GET":
        return JsonResponse(place_data(place))
    denied = require_staff(request)
    if denied is not None:
        return denied
    with transaction.atomic():
        if request.method == "DELETE":
            place.delete()
            return JsonResponse({"deleted": True})
        place = save_form(PlaceForm, body(request), instance=place)
    return JsonResponse(place_data(place))


@api_view(["GET", "POST"])
def trips(request):
    if request.method == "GET":
        return page_response(request, trip_records(request), trip_data)
    with transaction.atomic():
        trip = save_form(TripForm, body(request))
    return JsonResponse(trip_data(trip), status=201)


@api_view(["GET", "PATCH", "DELETE"])
def trip_detail(request, pk):
    trip = get_object_or_404(trip_queryset(request.user), pk=pk)
    if request.method == "GET":
        return JsonResponse(trip_data(trip))
    denied = require_staff(request)
    if denied is not None:
        return denied
    with transaction.atomic():
        if request.method == "DELETE":
            trip.delete()
            return JsonResponse({"deleted": True})
        trip = save_form(TripForm, body(request), instance=trip)
    return JsonResponse(trip_data(trip))


@api_view(["GET", "POST"])
def visits(request):
    if request.method == "GET":
        return page_response(request, visit_records(request), visit_data)
    with transaction.atomic():
        visit = save_form(VisitForm, body(request), user=request.user)
    return JsonResponse(visit_data(visit), status=201)


@api_view(["GET", "PATCH", "DELETE"])
def visit_detail(request, pk):
    visit = get_object_or_404(
        Visit.objects.filter(user=request.user).select_related("trip__place"),
        pk=pk,
    )
    if request.method == "GET":
        return JsonResponse(visit_data(visit))
    with transaction.atomic():
        if request.method == "DELETE":
            visit.delete()
            return JsonResponse({"deleted": True})
        visit = save_form(VisitForm, body(request), instance=visit, user=request.user)
    return JsonResponse(visit_data(visit))


@api_view(["GET", "PATCH"])
def me(request):
    if request.method == "PATCH":
        with transaction.atomic():
            save_form(ProfileForm, body(request), instance=request.user)
    return JsonResponse(user_data(request.user))


def statistics_data(user):
    cache = caches["statistics"]
    key = f"user:{user.pk}"
    payload = cache.get(key)
    if payload is None:
        records = Visit.objects.filter(user=user)
        totals = records.aggregate(
            visits=Count("id"),
            visited_places=Count("trip__place", distinct=True),
            countries=Count("trip__place__country_key", distinct=True),
            trips=Count("trip", distinct=True),
            average_rating=Avg("rating"),
        )
        totals["average_rating"] = (
            round(totals["average_rating"], 2)
            if totals["average_rating"] is not None
            else None
        )
        totals["cities"] = (
            records.values(
                "trip__place__city_key",
                "trip__place__country_key",
            )
            .distinct()
            .count()
        )
        countries = (
            records.values("trip__place__country_key")
            .annotate(
                count=Count("id"),
                name=Min("trip__place__country"),
            )
            .order_by("-count", "name")
        )
        top = (
            records.values(
                "trip__place_id",
                "trip__place__name",
                "trip__place__city",
                "trip__place__country",
            )
            .annotate(
                count=Count("id"),
            )
            .order_by("-count", "trip__place__name", "trip__place_id")[:5]
        )
        payload = {
            **totals,
            "by_country": [
                {"name": row["name"], "count": row["count"]} for row in countries
            ],
            "top_places": [
                {
                    "name": row["trip__place__name"],
                    "city": row["trip__place__city"],
                    "country": row["trip__place__country"],
                    "count": row["count"],
                }
                for row in top
            ],
        }
        cache.set(key, payload, timeout=60)
    return payload


@api_view(["GET"])
def statistics(request):
    return JsonResponse(statistics_data(request.user))
