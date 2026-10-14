import json
from datetime import date, datetime
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from visited_places.models import Place, Trip, User, Visit


def timestamp(day=10, hour=12):
    return timezone.make_aware(datetime(2026, 6, day, hour))


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class WebFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            "admin",
            "admin@example.com",
            "Test-Password-731!",
            name="Администратор",
            is_staff=True,
        )
        cls.user = User.objects.create_user(
            "traveller",
            "user@example.com",
            "Test-Password-731!",
            name="Путешественник",
        )
        cls.other = User.objects.create_user(
            "other",
            "other@example.com",
            "Test-Password-731!",
            name="Другой пользователь",
        )
        cls.place = Place.objects.create(
            name="Красная площадь",
            city="Москва",
            country="Россия",
            category="Площадь",
        )
        cls.trip = Trip.objects.create(
            place=cls.place,
            name="Москва в июне",
            start_date=date(2026, 6, 10),
            end_date=date(2026, 6, 12),
        )
        cls.visit = Visit.objects.create(
            user=cls.user,
            trip=cls.trip,
            visited_at=timestamp(),
            rating=4,
            note="Моя заметка",
        )
        cls.foreign_visit = Visit.objects.create(
            user=cls.other,
            trip=cls.trip,
            visited_at=timestamp(),
            rating=5,
            note="Чужая заметка",
        )

    def setUp(self):
        caches["default"].clear()
        caches["statistics"].clear()
        self.client.force_login(self.user)

    def send(self, method, url, payload):
        return getattr(self.client, method)(
            url,
            json.dumps(payload),
            content_type="application/json",
        )


class ModelTests(WebFixture):
    def test_relations_are_user_visit_trip_place(self):
        self.assertNotIn("user", [field.name for field in Trip._meta.fields])
        self.assertIn("place", [field.name for field in Trip._meta.fields])
        self.assertNotIn("place", [field.name for field in Visit._meta.fields])
        self.assertEqual(self.visit.trip.place, self.place)

    def test_unicode_place_duplicates_are_rejected(self):
        with self.assertRaises(ValidationError):
            Place.objects.create(
                name=" красная ПЛОЩАДЬ ",
                city="МОСКВА",
                country="россия",
                category="Парк",
            )

    def test_rating_range_is_enforced_by_model_and_database(self):
        with self.assertRaises(ValidationError):
            Visit.objects.create(
                user=self.user, trip=self.trip, visited_at=timestamp(11), rating=6
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Visit.objects.filter(pk=self.visit.pk).update(rating=0)

    def test_trip_dates_are_enforced_by_model_and_database(self):
        self.trip.end_date = date(2026, 6, 9)
        with self.assertRaises(ValidationError):
            self.trip.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Trip.objects.filter(pk=self.trip.pk).update(end_date=date(2026, 6, 9))

    def test_visit_local_date_must_fit_trip(self):
        with self.assertRaises(ValidationError):
            Visit.objects.create(
                user=self.user, trip=self.trip, visited_at=timestamp(13)
            )
        visit = Visit.objects.create(
            user=self.user, trip=self.trip, visited_at=timestamp(10, 0)
        )
        self.assertEqual(
            timezone.localtime(visit.visited_at).date(), self.trip.start_date
        )

    def test_trip_cannot_exclude_existing_visits(self):
        self.trip.start_date = date(2026, 6, 11)
        with self.assertRaises(ValidationError):
            self.trip.save()
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.start_date, date(2026, 6, 10))

    def test_place_and_trip_deletion_are_protected(self):
        with self.assertRaises(ProtectedError):
            self.place.delete()
        with self.assertRaises(ProtectedError):
            self.trip.delete()
        self.assertEqual(Visit.objects.count(), 2)

    def test_user_deletion_preserves_shared_resources_and_other_visits(self):
        self.user.delete()
        self.assertEqual(Place.objects.count(), 1)
        self.assertEqual(Trip.objects.count(), 1)
        self.assertEqual(Visit.objects.count(), 1)

    def test_password_is_hashed_and_email_is_normalized(self):
        user = User.objects.create_user(
            "fresh", " FRESH@EXAMPLE.COM ", "Strong-Password-781!", name="Имя"
        )
        self.assertEqual(user.email, "fresh@example.com")
        self.assertNotEqual(user.password, "Strong-Password-781!")
        self.assertTrue(user.check_password("Strong-Password-781!"))

    def test_unsafe_image_scheme_is_rejected(self):
        self.place.image_url = "javascript:alert(1)"
        with self.assertRaises(ValidationError):
            self.place.save()


class ApiTests(WebFixture):
    def test_anonymous_requests_are_denied(self):
        self.client.logout()
        for url in (
            "/api/me/",
            "/api/places/",
            "/api/trips/",
            "/api/visits/",
            "/api/statistics/",
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 401)

    def test_private_visit_list_does_not_include_other_user_data(self):
        data = self.client.get("/api/visits/").json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["note"], "Моя заметка")
        self.assertNotIn("Чужая заметка", json.dumps(data, ensure_ascii=False))

    def test_foreign_visit_cannot_be_read_changed_or_deleted(self):
        url = f"/api/visits/{self.foreign_visit.pk}/"
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.send("patch", url, {"note": "Взлом"}).status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.foreign_visit.refresh_from_db()
        self.assertEqual(self.foreign_visit.note, "Чужая заметка")

    def test_unicode_note_search_is_case_insensitive_and_private(self):
        data = self.client.get("/api/visits/", {"q": "моя ЗАМЕТКА"}).json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["id"], self.visit.pk)
        foreign = self.client.get("/api/visits/", {"q": "чужая"}).json()
        self.assertEqual(foreign["count"], 0)

    def test_staff_api_still_only_returns_own_visits(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get("/api/visits/").json()["count"], 0)
        self.assertEqual(
            self.client.get(f"/api/visits/{self.visit.pk}/").status_code, 404
        )

    def test_client_cannot_choose_visit_owner(self):
        response = self.send(
            "post",
            "/api/visits/",
            {
                "user": self.other.pk,
                "trip": self.trip.pk,
                "visited_at": "2026-06-11T12:00",
                "rating": 5,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Visit.objects.count(), 2)

    def test_visit_create_patch_delete_and_statistics_invalidation(self):
        self.assertEqual(self.client.get("/api/statistics/").json()["visits"], 1)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.send(
                "post",
                "/api/visits/",
                {
                    "trip": self.trip.pk,
                    "visited_at": "2026-06-11T12:00",
                    "rating": 5,
                    "note": "Новая заметка",
                },
            )
        self.assertEqual(response.status_code, 201)
        url = f"/api/visits/{response.json()['id']}/"
        totals = self.client.get("/api/statistics/").json()
        self.assertEqual(totals["visits"], 2)
        self.assertEqual(totals["average_rating"], 4.5)
        with self.captureOnCommitCallbacks(execute=True):
            changed = self.send("patch", url, {"rating": None, "note": "Изменено"})
        self.assertEqual(changed.json()["rating"], None)
        self.assertEqual(changed.json()["note"], "Изменено")
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.delete(url).status_code, 200)
        self.assertEqual(self.client.get("/api/statistics/").json()["visits"], 1)

    def test_duplicate_visit_is_rejected(self):
        response = self.send(
            "post",
            "/api/visits/",
            {
                "trip": self.trip.pk,
                "visited_at": "2026-06-10T12:00",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_date_does_not_change_an_existing_visit(self):
        response = self.send(
            "patch",
            f"/api/visits/{self.visit.pk}/",
            {
                "visited_at": "2026-06-13T12:00",
                "note": "Неверная дата",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.note, "Моя заметка")

    def test_invalid_json_and_typed_values_have_400_responses(self):
        self.assertEqual(
            self.client.post(
                "/api/places/", "{", content_type="application/json"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/places/", "[]", content_type="application/json"
            ).status_code,
            400,
        )
        self.assertEqual(self.client.post("/api/places/", {}).status_code, 400)
        for payload in (
            {"visited_at": 1},
            {"trip": True},
            {"rating": True},
            {"note": {"a": 1}},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.send(
                        "patch", f"/api/visits/{self.visit.pk}/", payload
                    ).status_code,
                    400,
                )

    def test_csrf_is_required_on_api_writes(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(
            client.post(
                "/api/places/", "{}", content_type="application/json"
            ).status_code,
            403,
        )

    def test_regular_user_cannot_edit_or_delete_shared_catalog(self):
        for resource, record in (("places", self.place), ("trips", self.trip)):
            url = f"/api/{resource}/{record.pk}/"
            with self.subTest(resource=resource):
                self.assertEqual(
                    self.send("patch", url, {"name": "Нельзя"}).status_code, 403
                )
                self.assertEqual(self.client.delete(url).status_code, 403)

    def test_staff_can_edit_catalog_but_cannot_delete_used_resources(self):
        self.client.force_login(self.staff)
        url = f"/api/places/{self.place.pk}/"
        self.assertEqual(
            self.send("patch", url, {"name": "Новая площадь"}).status_code, 200
        )
        self.assertEqual(self.client.delete(url).status_code, 409)
        self.assertEqual(
            self.client.delete(f"/api/trips/{self.trip.pk}/").status_code, 409
        )

    def test_regular_user_can_create_place_and_trip_without_an_owner_field(self):
        place = self.send(
            "post",
            "/api/places/",
            {
                "name": "Музей",
                "city": "Казань",
                "country": "Россия",
                "category": "Музей",
            },
        )
        self.assertEqual(place.status_code, 201)
        trip = self.send(
            "post",
            "/api/trips/",
            {
                "place": place.json()["id"],
                "name": "Казань",
                "start_date": "2026-07-01",
                "end_date": "2026-07-03",
            },
        )
        self.assertEqual(trip.status_code, 201)
        self.assertNotIn("user", trip.json())

    def test_unicode_search_and_pagination(self):
        response = self.client.get("/api/places/", {"q": "МОСКВА", "page_size": 1})
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(
            self.client.get("/api/trips/", {"q": "москва"}).json()["count"], 1
        )
        self.assertEqual(
            self.client.get("/api/places/", {"page_size": 201}).status_code, 400
        )
        self.assertEqual(self.client.get("/api/places/", {"page": -1}).status_code, 400)
        self.assertEqual(
            self.client.get("/api/places/", {"q": "' OR 1=1 --"}).json()["count"], 0
        )

    def test_trip_pagination_has_stable_newest_first_order(self):
        newer = Trip.objects.create(
            place=self.place,
            name="Поздняя поездка",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 3),
        )
        first = self.client.get("/api/trips/", {"page_size": 1}).json()
        second = self.client.get("/api/trips/", {"page_size": 1, "page": 2}).json()
        self.assertEqual(first["results"][0]["id"], newer.pk)
        self.assertEqual(second["results"][0]["id"], self.trip.pk)

    def test_private_statistics_cache_is_not_shared_between_users(self):
        self.assertEqual(
            self.client.get("/api/statistics/").json()["average_rating"], 4
        )
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.get("/api/statistics/").json()["average_rating"], 5
        )

    def test_statistics_cache_reduces_queries(self):
        self.client.get("/api/statistics/")
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/api/statistics/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            any("visited_places_visit" in entry["sql"] for entry in queries)
        )

    def test_statistics_normalizes_countries_and_keeps_distinct_places(self):
        for name, country in (
            ("Смотровая", "РОССИЯ"),
            (self.place.name, "Другая страна"),
        ):
            place = Place.objects.create(
                name=name, city=self.place.city, country=country, category="Площадь"
            )
            trip = Trip.objects.create(
                place=place,
                name=name,
                start_date=self.trip.start_date,
                end_date=self.trip.end_date,
            )
            Visit.objects.create(user=self.user, trip=trip, visited_at=timestamp())
        data = self.client.get("/api/statistics/").json()
        self.assertEqual(data["countries"], 2)
        countries = {
            item["name"].casefold(): item["count"] for item in data["by_country"]
        }
        self.assertEqual(countries, {"россия": 2, "другая страна": 1})
        self.assertEqual(len(data["top_places"]), 3)
        self.assertTrue(all(item["count"] == 1 for item in data["top_places"]))

    def test_visit_list_does_not_make_queries_per_row(self):
        for hour in range(1, 12):
            Visit.objects.create(
                user=self.user, trip=self.trip, visited_at=timestamp(11, hour)
            )
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/api/visits/", {"page_size": 20})
        self.assertEqual(response.json()["count"], 12)
        self.assertLessEqual(len(queries), 5)

    def test_user_cannot_change_privileges_through_profile(self):
        response = self.send("patch", "/api/me/", {"is_staff": True})
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)

    def test_profile_updates_name_and_email(self):
        response = self.send(
            "patch", "/api/me/", {"name": "Новое имя", "email": " NEW@EXAMPLE.COM "}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "new@example.com")

    def test_date_filters_and_bad_parameters(self):
        self.assertEqual(
            self.client.get("/api/visits/", {"from": "2026-06-11"}).json()["count"], 0
        )
        self.assertEqual(
            self.client.get("/api/visits/", {"from": "bad-date"}).status_code, 400
        )
        self.assertEqual(
            self.client.get("/api/visits/", {"trip": "bad-id"}).status_code, 400
        )


class AuthTests(WebFixture):
    def test_anonymous_pages_redirect_to_login(self):
        self.client.logout()
        for url in ("/", "/places/", "/trips/", "/statistics/"):
            self.assertEqual(self.client.get(url).status_code, 302)

    def test_login_and_post_logout(self):
        self.client.logout()
        response = self.client.post(
            "/login/", {"username": "traveller", "password": "Test-Password-731!"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/api/me/").status_code, 200)
        self.assertEqual(self.client.get("/logout/").status_code, 405)
        self.assertEqual(self.client.post("/logout/").status_code, 302)
        self.assertEqual(self.client.get("/api/me/").status_code, 401)

    def test_registration_uses_hashes_and_does_not_grant_staff_permissions(self):
        self.client.logout()
        response = self.client.post(
            "/register/",
            {
                "username": "newcomer",
                "name": "Новичок",
                "email": "newcomer@example.com",
                "password1": "Unique-Password-721!",
                "password2": "Unique-Password-721!",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="newcomer")
        self.assertTrue(user.check_password("Unique-Password-721!"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_repeated_failed_logins_are_throttled(self):
        self.client.logout()
        for _ in range(10):
            self.client.post("/login/", {"username": "missing", "password": "wrong"})
        response = self.client.post(
            "/login/", {"username": "missing", "password": "wrong"}
        )
        self.assertEqual(response.status_code, 429)

    def test_all_app_pages_render_without_exposing_foreign_notes(self):
        for url in ("/", "/places/", "/trips/", "/statistics/"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "Чужая заметка")

    def test_login_redirect_cannot_leave_the_application(self):
        self.client.logout()
        response = self.client.post(
            "/login/?next=https://example.com/",
            {
                "username": "traveller",
                "password": "Test-Password-731!",
            },
        )
        self.assertEqual(response.url, "/")


class TemplateTests(WebFixture):
    def test_journal_contains_private_records_in_initial_html(self):
        response = self.client.get("/")
        self.assertContains(response, "Моя заметка")
        self.assertNotContains(response, "Чужая заметка")
        self.assertContains(response, 'aria-busy="false"')
        self.assertEqual(response.context["initial_data"]["count"], 1)

    def test_pages_use_base_and_individual_content_templates(self):
        for url, name in (
            ("/", "visits"),
            ("/places/", "places"),
            ("/trips/", "trips"),
            ("/statistics/", "statistics"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertTemplateUsed(response, "visited_places/base.html")
                self.assertTemplateUsed(response, "visited_places/app.html")
                self.assertTemplateUsed(
                    response, f"visited_places/partials/{name}.html"
                )

    def test_html_and_api_share_unicode_search_results(self):
        for page, api, query in (
            ("/", "/api/visits/", "моя ЗАМЕТКА"),
            ("/places/", "/api/places/", "МОСКВА"),
            ("/trips/", "/api/trips/", "москва"),
        ):
            with self.subTest(page=page):
                html = self.client.get(page, {"q": query})
                data = self.client.get(api, {"q": query}).json()
                self.assertEqual(html.context["initial_data"], data)

    def test_server_pagination_preserves_page_size(self):
        for hour in range(1, 14):
            Visit.objects.create(
                user=self.user, trip=self.trip, visited_at=timestamp(11, hour)
            )
        parameters = {"page": 2, "page_size": 1}
        response = self.client.get("/", parameters)
        self.assertEqual(
            response.context["initial_data"],
            self.client.get("/api/visits/", parameters).json(),
        )
        self.assertEqual(len(response.context["records"]), 1)
        self.assertContains(response, 'name="page_size" value="1"')
        self.assertContains(response, 'form="filters-form" name="page" value="3"')

    def test_invalid_parameters_show_error_instead_of_a_server_exception(self):
        for parameters in (
            {"page": "bad"},
            {"page_size": 0},
            {"from": "bad-date"},
            {"trip": "bad-id"},
        ):
            with self.subTest(parameters=parameters):
                response = self.client.get("/", parameters)
                self.assertEqual(response.status_code, 400)
                self.assertTrue(response.context["initial_data"]["error"])
                self.assertEqual(response.context["records"], [])

    def test_regular_user_does_not_see_shared_catalog_edit_buttons(self):
        for url in ("/places/", "/trips/"):
            response = self.client.get(url)
            self.assertNotContains(response, 'data-record-action="edit"')
            self.assertNotContains(response, 'data-record-action="delete"')

    def test_staff_sees_shared_catalog_edit_buttons(self):
        self.client.force_login(self.staff)
        for url in ("/places/", "/trips/"):
            response = self.client.get(url)
            self.assertContains(response, 'data-record-action="edit"')
            self.assertContains(response, 'data-record-action="delete"')

    def test_own_visit_edit_buttons_exist_in_initial_html(self):
        response = self.client.get("/")
        self.assertContains(response, 'data-resource="visits"')
        self.assertContains(response, f'data-record-id="{self.visit.pk}"')
        self.assertNotContains(response, f'data-record-id="{self.foreign_visit.pk}"')

    def test_html_escapes_untrusted_notes_and_place_names(self):
        attack = '<script>alert("test")</script>'
        self.visit.note = attack
        self.visit.save()
        self.place.name = attack
        self.place.save()
        for url in ("/", "/places/"):
            response = self.client.get(url)
            self.assertNotContains(response, attack)
            self.assertContains(response, "&lt;script&gt;")

    def test_json_script_does_not_allow_notes_to_close_the_script(self):
        self.visit.note = "</script><script>alert(1)</script>"
        self.visit.save()
        response = self.client.get("/")
        self.assertNotContains(response, "</script><script>alert(1)")
        self.assertContains(response, "\\u003C/script\\u003E")
        self.assertEqual(
            response.context["initial_data"]["results"][0]["note"], self.visit.note
        )

    def test_empty_catalog_uses_empty_templates(self):
        Visit.objects.all().delete()
        Trip.objects.all().delete()
        Place.objects.all().delete()
        for url in ("/places/", "/trips/"):
            response = self.client.get(url)
            self.assertContains(response, "Записей не найдено")
            self.assertTemplateUsed(response, "visited_places/partials/empty.html")

    def test_empty_own_statistics_does_not_include_foreign_visits(self):
        Visit.objects.filter(user=self.user).delete()
        response = self.client.get("/statistics/")
        self.assertContains(response, "Посещений пока нет")
        self.assertEqual(response.context["stats"]["visits"], 0)

    def test_statistics_and_rating_are_present_in_initial_html(self):
        response = self.client.get("/statistics/")
        self.assertContains(response, "Посещения по странам")
        self.assertContains(response, "Красная площадь")
        self.assertContains(response, 'data-metric="average_rating">4.00</strong>')
        self.assertEqual(response.context["stats"]["visits"], 1)

    def test_html_does_not_make_queries_for_each_record(self):
        for hour in range(1, 12):
            Visit.objects.create(
                user=self.user, trip=self.trip, visited_at=timestamp(11, hour)
            )
        self.client.get("/api/statistics/")
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["records"]), 12)
        self.assertLessEqual(len(queries), 6)

    def test_date_and_trip_filters_remain_selected_in_html(self):
        parameters = {
            "trip": str(self.trip.pk),
            "from": "2026-06-10",
            "to": "2026-06-10",
        }
        response = self.client.get("/", parameters)
        self.assertEqual(response.context["initial_data"]["count"], 1)
        self.assertContains(response, 'value="2026-06-10"')
        self.assertContains(response, f'value="{self.trip.pk}" selected')


class DetailPageTests(WebFixture):
    def test_named_urls_have_application_namespace(self):
        self.assertEqual(reverse("visited_places:journal"), "/")
        self.assertEqual(reverse("visited_places:places"), "/places/")
        self.assertEqual(
            reverse("visited_places:visit-detail", args=[self.visit.pk]),
            f"/visits/{self.visit.pk}/",
        )

    def test_detail_pages_show_real_records_and_links(self):
        for resource, record in (
            ("places", self.place),
            ("trips", self.trip),
            ("visits", self.visit),
        ):
            with self.subTest(resource=resource):
                response = self.client.get(f"/{resource}/{record.pk}/")
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "visited_places/partials/detail.html")
                self.assertTemplateUsed(
                    response, "visited_places/partials/navigation.html"
                )
                self.assertEqual(response.context["record"]["id"], record.pk)
                self.assertTrue(response.context["initial_data"]["detail"])

    def test_api_returns_links_to_detail_pages(self):
        for resource, record in (
            ("places", self.place),
            ("trips", self.trip),
            ("visits", self.visit),
        ):
            response = self.client.get(f"/api/{resource}/{record.pk}/")
            self.assertEqual(response.json()["url"], f"/{resource}/{record.pk}/")

    def test_foreign_visit_detail_is_private_even_for_staff(self):
        for user in (self.user, self.staff):
            self.client.force_login(user)
            response = self.client.get(f"/visits/{self.foreign_visit.pk}/")
            self.assertEqual(response.status_code, 404)
            self.assertNotContains(response, "Чужая заметка", status_code=404)

    def test_missing_detail_page_shows_custom_404(self):
        for resource in ("places", "trips", "visits"):
            response = self.client.get(f"/{resource}/99999/")
            self.assertContains(response, "Страница не найдена", status_code=404)
            self.assertTemplateUsed(response, "visited_places/error.html")

    def test_anonymous_user_cannot_open_detail_pages(self):
        self.client.logout()
        for resource, record in (
            ("places", self.place),
            ("trips", self.trip),
            ("visits", self.visit),
        ):
            self.assertEqual(
                self.client.get(f"/{resource}/{record.pk}/").status_code, 302
            )

    def test_trip_detail_counts_visits_according_to_role(self):
        url = f"/trips/{self.trip.pk}/"
        self.assertEqual(self.client.get(url).context["record"]["visit_count"], 1)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(url).context["record"]["visit_count"], 2)

    def test_detail_note_is_escaped_and_not_truncated(self):
        self.visit.note = "<script>alert(1)</script>" + "a" * 1500
        self.visit.save()
        response = self.client.get(f"/visits/{self.visit.pk}/")
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "a" * 1500)
        self.assertContains(response, "&lt;script&gt;")

    @override_settings(DEBUG=False, SECURE_SSL_REDIRECT=False)
    def test_unmatched_url_uses_custom_404_in_production(self):
        response = self.client.get("/page-does-not-exist/")
        self.assertContains(response, "Страница не найдена", status_code=404)


class TemplateFilterTests(SimpleTestCase):
    def test_dates_and_times_are_formatted_in_moscow_timezone(self):
        from visited_places.templatetags.journal_display import (
            journal_date,
            journal_time,
        )

        self.assertEqual(journal_date("2026-06-10"), "10.06.2026")
        self.assertEqual(journal_date("2026-06-09T23:40:00Z"), "10.06.2026")
        self.assertEqual(journal_time("2026-06-09T23:40:00Z"), "02:40")

    def test_missing_or_invalid_dates_do_not_break_templates(self):
        from visited_places.templatetags.journal_display import (
            journal_date,
            journal_time,
        )

        for value in (None, "", "bad-date", "2026-02-30", 123):
            with self.subTest(value=value):
                self.assertEqual(journal_date(value), "")
                self.assertEqual(journal_time(value), "")


class ImportTests(TestCase):
    def test_console_import_preserves_source_and_is_idempotent(self):
        from visited_places.service import TravelJournal
        from visited_places.storage import save_journal

        journal = TravelJournal()
        user = journal.add_user("Логвинов Глеб Дмитриевич", "gleb@example.com")
        place = journal.add_place("Музей", "Москва", "Россия", "Музей")
        trip = journal.add_trip(place.id, "Выходные", "2026-06-10", "2026-06-12")
        journal.add_visit(user.id, trip.id, "2026-06-10 12:00", 5, "Память")
        with TemporaryDirectory() as directory:
            source = Path(directory)
            save_journal(source, journal)
            before = {file.name: file.read_bytes() for file in source.iterdir()}
            call_command("import_journal", source=source, stdout=StringIO())
            call_command("import_journal", source=source, stdout=StringIO())
            self.assertEqual(Visit.objects.count(), 1)
            self.assertEqual(Visit.objects.get().note, "Память")
            self.assertEqual(Visit.objects.get().trip.place.name, "Музей")
            self.assertFalse(User.objects.get().has_usable_password())
            self.assertEqual(
                before, {file.name: file.read_bytes() for file in source.iterdir()}
            )
