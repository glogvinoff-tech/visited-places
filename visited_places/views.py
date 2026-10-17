import sqlite3
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from db.database import execute, fetch_all, fetch_one
from .auth import login_required, staff_required
from .forms import (
    LoginForm,
    PlaceForm,
    ProfileForm,
    RegistrationForm,
    TripForm,
    VisitForm,
)

VISIT_SELECT = """
    SELECT v.*, t.name AS trip_name, t.start_date, t.end_date, p.id AS place_id,
           p.name AS place_name, p.city, p.country, p.category, p.image_url,
           u.name AS user_name
    FROM visits AS v JOIN trips AS t ON t.id = v.trip_id
    JOIN places AS p ON p.id = t.place_id
    JOIN users AS u ON u.id = v.user_id
"""
TRIP_SELECT = """
    SELECT t.*, p.name AS place_name, p.city, p.country, p.category, p.image_url
    FROM trips AS t JOIN places AS p ON p.id = t.place_id
"""


def pagination(request, total):
    try:
        number = int(request.GET.get("page", 1))
    except ValueError:
        number = 1
    pages = max(1, (total + 11) // 12)
    number = min(max(1, number), pages)
    return {
        "number": number,
        "pages": pages,
        "total": total,
        "previous": number - 1,
        "next": number + 1,
        "offset": (number - 1) * 12,
    }


def get_record(sql, parameters):
    record = fetch_one(sql, parameters)
    if record is None:
        raise Http404("Запись не найдена")
    return record


def login_view(request):
    if request.user:
        return redirect("visited_places:journal")
    form = LoginForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = fetch_one(
            "SELECT * FROM users WHERE casefold(username) = casefold(?) "
            "AND is_active = 1",
            (form.cleaned_data["username"],),
        )
        password = form.cleaned_data["password"]
        if user and check_password(password, user["password"]):
            request.session.cycle_key()
            request.session["user_id"] = user["id"]
            return redirect("visited_places:journal")
        if not user:
            make_password(password)
        form.add_error(None, "Неверный логин или пароль.")
    return render(request, "visited_places/login.html", {"form": form, "title": "Вход"})


def register(request):
    if request.user:
        return redirect("visited_places:journal")
    form = RegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            user_id = execute(
                "INSERT INTO users(username, name, email, password) "
                "VALUES (?, ?, ?, ?)",
                (
                    data["username"],
                    data["name"],
                    data["email"],
                    make_password(data["password1"]),
                ),
            )
        except sqlite3.IntegrityError:
            form.add_error(None, "Логин или email уже используется.")
        else:
            request.session.cycle_key()
            request.session["user_id"] = user_id
            return redirect("visited_places:journal")
    return render(
        request, "visited_places/register.html", {"form": form, "title": "Регистрация"}
    )


@require_POST
def logout_view(request):
    request.session.flush()
    return redirect("visited_places:login")


@login_required
def profile(request):
    form = ProfileForm(
        request.POST if request.method == "POST" else None,
        initial=dict(request.user),
        user_id=request.user["id"],
    )
    if request.method == "POST" and form.is_valid():
        try:
            execute(
                "UPDATE users SET name = ?, email = ? WHERE id = ?",
                (
                    form.cleaned_data["name"],
                    form.cleaned_data["email"],
                    request.user["id"],
                ),
            )
        except sqlite3.IntegrityError:
            form.add_error("email", "Этот email уже используется.")
        else:
            messages.success(request, "Профиль сохранён.")
            return redirect("visited_places:profile")
    return render(
        request,
        "visited_places/form.html",
        {
            "form": form,
            "title": "Мой профиль",
            "cancel_url": "visited_places:journal",
        },
    )


@login_required
def place_list(request):
    query = request.GET.get("q", "").strip()
    unvisited = request.GET.get("unvisited") == "1"
    where = """ WHERE instr(
        casefold(p.name || ' ' || p.city || ' ' || p.country || ' ' || p.category),
        casefold(?)) > 0
        AND (? = 0 OR NOT EXISTS (
            SELECT 1 FROM visits v JOIN trips t ON t.id = v.trip_id
            WHERE v.user_id = ? AND t.place_id = p.id
        )) """
    parameters = (query, int(unvisited), request.user["id"])
    total = fetch_one("SELECT COUNT(*) FROM places p" + where, parameters)[0]
    page = pagination(request, total)
    places = fetch_all(
        "SELECT p.* FROM places p" + where + "ORDER BY p.name, p.id LIMIT ? OFFSET ?",
        (*parameters, 12, page["offset"]),
    )
    return render(
        request,
        "visited_places/places.html",
        {
            "title": "Места",
            "places": places,
            "q": query,
            "unvisited": unvisited,
            "page": page,
            "section": "places",
        },
    )


@login_required
def trip_list(request):
    query, date = request.GET.get("q", "").strip(), request.GET.get("date", "")
    where = """ WHERE instr(
        casefold(t.name || ' ' || p.name || ' ' || p.city), casefold(?)) > 0
        AND (? = '' OR (t.start_date <= ? AND t.end_date >= ?)) """
    parameters = (query, date, date, date)
    total = fetch_one(
        "SELECT COUNT(*) FROM trips t JOIN places p ON p.id = t.place_id" + where,
        parameters,
    )[0]
    page = pagination(request, total)
    trips = fetch_all(
        TRIP_SELECT + where + "ORDER BY t.start_date DESC, t.id DESC LIMIT ? OFFSET ?",
        (*parameters, 12, page["offset"]),
    )
    return render(
        request,
        "visited_places/trips.html",
        {
            "title": "Поездки",
            "trips": trips,
            "q": query,
            "date": date,
            "page": page,
            "section": "trips",
        },
    )


@login_required
def visit_list(request):
    query = request.GET.get("q", "").strip()
    start, end = request.GET.get("from", ""), request.GET.get("to", "")
    trip = request.GET.get("trip", "")
    where = """ WHERE v.user_id = ?
        AND instr(casefold(p.name || ' ' || t.name || ' ' || v.note), casefold(?)) > 0
        AND substr(v.visited_at, 1, 10) BETWEEN ? AND ?
        AND (? = '' OR v.trip_id = ?) """
    parameters = (
        request.user["id"],
        query,
        start or "0000-01-01",
        end or "9999-12-31",
        trip,
        trip,
    )
    total = fetch_one(
        "SELECT COUNT(*) FROM visits v JOIN trips t ON t.id = v.trip_id "
        "JOIN places p ON p.id = t.place_id" + where,
        parameters,
    )[0]
    page = pagination(request, total)
    visits = fetch_all(
        VISIT_SELECT + where + "ORDER BY v.visited_at DESC, v.id DESC LIMIT ? OFFSET ?",
        (*parameters, 12, page["offset"]),
    )
    return render(
        request,
        "visited_places/visits.html",
        {
            "title": "Журнал посещений",
            "visits": visits,
            "q": query,
            "from": start,
            "to": end,
            "selected_trip": trip,
            "trips": fetch_all("SELECT id, name FROM trips ORDER BY name"),
            "page": page,
            "section": "visits",
        },
    )


@login_required
def statistics(request):
    try:
        minimum = min(1000000, max(1, int(request.GET.get("minimum", 1))))
    except ValueError:
        minimum = 1
    summary = fetch_one(
        """
        SELECT COUNT(v.id) AS visits, COUNT(DISTINCT t.place_id) AS places,
               COUNT(DISTINCT p.country) AS countries, ROUND(AVG(v.rating), 2) AS rating
        FROM visits v JOIN trips t ON t.id = v.trip_id
        JOIN places p ON p.id = t.place_id
        WHERE v.user_id = ?
    """,
        (request.user["id"],),
    )
    by_place = fetch_all(
        """
        SELECT p.id, p.name, p.city, COUNT(v.id) AS total
        FROM visits v JOIN trips t ON t.id = v.trip_id
        JOIN places p ON p.id = t.place_id
        WHERE v.user_id = ? GROUP BY p.id, p.name, p.city HAVING COUNT(v.id) >= ?
        ORDER BY total DESC, p.name
    """,
        (request.user["id"], minimum),
    )
    by_country = fetch_all(
        """
        SELECT p.country, COUNT(v.id) AS total
        FROM visits v JOIN trips t ON t.id = v.trip_id
        JOIN places p ON p.id = t.place_id
        WHERE v.user_id = ? GROUP BY p.country ORDER BY total DESC, p.country
    """,
        (request.user["id"],),
    )
    return render(
        request,
        "visited_places/statistics.html",
        {
            "title": "Статистика",
            "summary": summary,
            "by_place": by_place,
            "by_country": by_country,
            "minimum": minimum,
            "section": "statistics",
        },
    )


@login_required
def place_detail(request, pk):
    place = get_record("SELECT * FROM places WHERE id = ?", (pk,))
    return render(
        request,
        "visited_places/place_detail.html",
        {
            "title": place["name"],
            "place": place,
            "section": "places",
        },
    )


@login_required
def trip_detail(request, pk):
    trip = get_record(TRIP_SELECT + " WHERE t.id = ?", (pk,))
    visits = fetch_all(
        "SELECT id, visited_at, rating FROM visits WHERE trip_id = ? AND user_id = ? "
        "ORDER BY visited_at DESC",
        (pk, request.user["id"]),
    )
    return render(
        request,
        "visited_places/trip_detail.html",
        {
            "title": trip["name"],
            "trip": trip,
            "visits": visits,
            "section": "trips",
        },
    )


@login_required
def visit_detail(request, pk):
    visit = get_record(
        VISIT_SELECT + " WHERE v.id = ? AND v.user_id = ?", (pk, request.user["id"])
    )
    return render(
        request,
        "visited_places/visit_detail.html",
        {
            "title": visit["place_name"],
            "visit": visit,
            "section": "visits",
        },
    )


@login_required
def place_edit(request, pk=None):
    if pk is not None and not request.user["is_staff"]:
        return access_denied(request)
    place = get_record("SELECT * FROM places WHERE id = ?", (pk,)) if pk else None
    form = PlaceForm(
        request.POST if request.method == "POST" else None,
        initial=dict(place) if place else None,
        record_id=pk or 0,
    )
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        values = (
            data["name"],
            data["city"],
            data["country"],
            data["category"],
            data["image_url"],
        )
        try:
            if pk:
                execute(
                    "UPDATE places SET name=?, city=?, country=?, category=?, "
                    "image_url=? WHERE id=?",
                    (*values, pk),
                )
            else:
                pk = execute(
                    "INSERT INTO places(name, city, country, category, image_url) "
                    "VALUES (?, ?, ?, ?, ?)",
                    values,
                )
        except sqlite3.IntegrityError:
            form.add_error(None, "Такое место уже существует.")
        else:
            messages.success(request, "Место сохранено.")
            return redirect("visited_places:place-detail", pk=pk)
    return render(
        request,
        "visited_places/form.html",
        {
            "title": "Изменить место" if place else "Добавить место",
            "form": form,
            "cancel_url": "visited_places:places",
            "section": "places",
        },
    )


@login_required
def trip_edit(request, pk=None):
    if pk is not None and not request.user["is_staff"]:
        return access_denied(request)
    trip = get_record("SELECT * FROM trips WHERE id = ?", (pk,)) if pk else None
    form = TripForm(
        request.POST if request.method == "POST" else None,
        initial=dict(trip) if trip else None,
        record_id=pk or 0,
    )
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        values = (
            data["name"],
            data["place_id"],
            data["start_date"].isoformat(),
            data["end_date"].isoformat(),
        )
        try:
            if pk:
                execute(
                    "UPDATE trips SET name=?, place_id=?, start_date=?, end_date=? "
                    "WHERE id=?",
                    (*values, pk),
                )
            else:
                pk = execute(
                    "INSERT INTO trips(name, place_id, start_date, end_date) "
                    "VALUES (?, ?, ?, ?)",
                    values,
                )
        except sqlite3.IntegrityError:
            form.add_error(None, "Место больше не существует. Обновите страницу.")
        else:
            messages.success(request, "Поездка сохранена.")
            return redirect("visited_places:trip-detail", pk=pk)
    return render(
        request,
        "visited_places/form.html",
        {
            "title": "Изменить поездку" if trip else "Добавить поездку",
            "form": form,
            "cancel_url": "visited_places:trips",
            "section": "trips",
        },
    )


@login_required
def visit_edit(request, pk=None):
    visit = (
        get_record(
            "SELECT * FROM visits WHERE id = ? AND user_id = ?",
            (pk, request.user["id"]),
        )
        if pk
        else None
    )
    initial = dict(visit) if visit else {}
    if visit:
        initial["visited_at"] = datetime.strptime(visit["visited_at"], "%Y-%m-%d %H:%M")
    form = VisitForm(
        request.POST if request.method == "POST" else None,
        initial=initial,
        user_id=request.user["id"],
        record_id=pk or 0,
    )
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        values = (
            data["trip_id"],
            data["visited_at"].strftime("%Y-%m-%d %H:%M"),
            data["rating"],
            data["note"],
        )
        try:
            if pk:
                execute(
                    "UPDATE visits SET trip_id=?, visited_at=?, rating=?, note=? "
                    "WHERE id=? AND user_id=?",
                    (*values, pk, request.user["id"]),
                )
            else:
                pk = execute(
                    "INSERT INTO visits(trip_id, visited_at, rating, note, user_id) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (*values, request.user["id"]),
                )
        except sqlite3.IntegrityError:
            form.add_error(None, "Проверьте поездку и отсутствие повторного посещения.")
        else:
            messages.success(request, "Посещение сохранено.")
            return redirect("visited_places:visit-detail", pk=pk)
    return render(
        request,
        "visited_places/form.html",
        {
            "title": "Изменить посещение" if visit else "Добавить посещение",
            "form": form,
            "cancel_url": "visited_places:journal",
            "section": "visits",
        },
    )


def confirm_delete(request, record, sql, parameters, cancel_url):
    error = ""
    if request.method == "POST":
        try:
            execute(sql, parameters)
        except sqlite3.IntegrityError:
            error = "Сначала удалите или измените связанные поездки и посещения."
        else:
            messages.success(request, "Запись удалена.")
            return redirect(cancel_url)
    return render(
        request,
        "visited_places/confirm_delete.html",
        {
            "title": "Удалить запись?",
            "record": record,
            "error": error,
            "cancel_url": cancel_url,
        },
        status=409 if error else 200,
    )


@staff_required
def place_delete(request, pk):
    place = get_record("SELECT * FROM places WHERE id = ?", (pk,))
    return confirm_delete(
        request,
        place,
        "DELETE FROM places WHERE id = ?",
        (pk,),
        "visited_places:places",
    )


@staff_required
def trip_delete(request, pk):
    trip = get_record("SELECT * FROM trips WHERE id = ?", (pk,))
    return confirm_delete(
        request, trip, "DELETE FROM trips WHERE id = ?", (pk,), "visited_places:trips"
    )


@login_required
def visit_delete(request, pk):
    visit = get_record(
        VISIT_SELECT + " WHERE v.id = ? AND v.user_id = ?", (pk, request.user["id"])
    )
    return confirm_delete(
        request,
        visit,
        "DELETE FROM visits WHERE id = ? AND user_id = ?",
        (pk, request.user["id"]),
        "visited_places:journal",
    )


def access_denied(request):
    return render(
        request,
        "visited_places/error.html",
        {
            "title": "Доступ запрещён",
            "message": "Изменять каталог может администратор.",
        },
        status=403,
    )


def page_not_found(request, exception=None):
    return render(
        request,
        "visited_places/error.html",
        {
            "title": "Страница не найдена",
            "message": "Запись или страница не найдена.",
        },
        status=404,
    )


def csrf_failure(request, reason=""):
    return render(
        request,
        "visited_places/error.html",
        {
            "title": "Действие не выполнено",
            "message": "Обновите страницу и повторите действие.",
        },
        status=403,
    )
