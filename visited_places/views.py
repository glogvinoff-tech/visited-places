from hashlib import sha256

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.core.cache import cache
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie

from . import api
from .forms import RegistrationForm
from .models import Place, Trip, Visit


class JournalLoginView(LoginView):
    template_name = "visited_places/login.html"
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        identity = request.POST.get("username", "").casefold()
        address = request.META.get("REMOTE_ADDR", "")
        self.attempt_key = (
            "login:" + sha256(f"{address}:{identity}".encode()).hexdigest()
        )
        if request.method == "POST" and cache.get(self.attempt_key, 0) >= 10:
            form = self.get_form()
            form.add_error(None, "Слишком много попыток. Повторите через 5 минут.")
            return self.render_to_response(self.get_context_data(form=form), status=429)
        return super().dispatch(request, *args, **kwargs)

    def form_invalid(self, form):
        cache.add(self.attempt_key, 0, timeout=300)
        cache.incr(self.attempt_key)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(self.attempt_key)
        return super().form_valid(form)


class JournalLogoutView(LogoutView):
    pass


def register(request):
    if request.user.is_authenticated:
        return redirect("visited_places:journal")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save()
        login(request, user)
        return redirect("visited_places:journal")
    return render(request, "visited_places/register.html", {"form": form})


def application_context(request, view):
    return {
        "view": view,
        "profile": {
            "name": request.user.name,
            "is_staff": request.user.is_staff,
            "login_url": reverse("visited_places:login"),
            "admin_url": reverse("admin:index"),
        },
        "stats": api.statistics_data(request.user),
        "content_template": f"visited_places/partials/{view}.html",
        "filters": {
            "q": request.GET.get("q", ""),
            "trip": request.GET.get("trip", ""),
            "from": request.GET.get("from", ""),
            "to": request.GET.get("to", ""),
        },
        "trip_choices": Trip.objects.values("id", "name") if view == "visits" else [],
    }


@login_required
@ensure_csrf_cookie
def application(request, view="visits"):
    titles = {
        "visits": "Журнал посещений",
        "places": "Каталог мест",
        "trips": "Поездки",
        "statistics": "Статистика",
    }
    context = application_context(request, view)
    context["title"] = titles[view]
    payload = {"results": [], "count": 0, "page": 1, "pages": 1, "page_size": 12}
    status = 200
    if view != "statistics":
        selectors = {
            "visits": (api.visit_records, api.visit_data),
            "places": (api.place_records, api.place_data),
            "trips": (api.trip_records, api.trip_data),
        }
        select, serialize = selectors[view]
        try:
            payload = api.page_data(request, select(request), serialize)
        except ValueError as exc:
            payload["error"] = str(exc)
            status = 400
    context.update({"initial_data": payload, "records": payload["results"]})
    return render(request, "visited_places/app.html", context, status=status)


@login_required
@ensure_csrf_cookie
def detail(request, pk, view):
    sources = {
        "places": (Place.objects.all(), api.place_data),
        "trips": (api.trip_queryset(request.user), api.trip_data),
        "visits": (
            Visit.objects.filter(user=request.user).select_related("trip__place"),
            api.visit_data,
        ),
    }
    records, serialize = sources[view]
    try:
        record = serialize(get_object_or_404(records, pk=pk))
    except Http404 as exc:
        return page_not_found(request, exc)
    context = application_context(request, view)
    list_name = "journal" if view == "visits" else view
    list_url = reverse(f"visited_places:{list_name}")
    context.update(
        {
            "title": (
                record["trip"]["place"]["name"] if view == "visits" else record["name"]
            ),
            "content_template": "visited_places/partials/detail.html",
            "detail_record": record,
            "record": record,
            "list_url": list_url,
            "initial_data": {
                "results": [record],
                "count": 1,
                "page": 1,
                "pages": 1,
                "page_size": 12,
                "detail": True,
                "list_url": list_url,
            },
        }
    )
    return render(request, "visited_places/app.html", context)


def page_not_found(request, exception):
    return render(
        request,
        "visited_places/error.html",
        {"title": "Страница не найдена", "message": "Запись или страница не найдена."},
        status=404,
    )


def csrf_failure(request, reason=""):
    if request.path.startswith("/api/"):
        return JsonResponse(
            {"error": "Обновите страницу и повторите действие."}, status=403
        )
    return render(
        request,
        "visited_places/error.html",
        {
            "message": "Проверка безопасности не пройдена. Обновите страницу.",
        },
        status=403,
    )
