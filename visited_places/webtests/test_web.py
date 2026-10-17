import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.hashers import check_password, make_password
from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse

from db.database import execute, fetch_all, fetch_one
from db.import_json import import_json


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class WebTests(SimpleTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        environment = patch.dict(
            os.environ,
            {
                "VISITED_PLACES_DB": str(Path(directory.name) / "test.sqlite3"),
            },
        )
        environment.start()
        self.addCleanup(environment.stop)
        import_json()
        execute(
            "UPDATE users SET password = ?, is_staff = 1 WHERE id = 1",
            (make_password("Test-Travel-2026!"),),
        )
        execute(
            "UPDATE users SET password = ? WHERE id = 2",
            (make_password("Test-Travel-2026!"),),
        )
        self.client = Client()
        self.login()

    def login(self, username="gleb", client=None):
        client = client or self.client
        client.post("/logout/")
        return client.post(
            reverse("visited_places:login"),
            {
                "username": username,
                "password": "Test-Travel-2026!",
            },
        )

    def test_anonymous_redirect(self):
        client = Client()
        for url in ["/", "/places/", "/trips/", "/statistics/", "/visits/1/"]:
            self.assertRedirects(
                client.get(url), "/login/", fetch_redirect_response=False
            )

    def test_login_and_wrong_password(self):
        client = Client()
        response = client.post("/login/", {"username": "gleb", "password": "wrong"})
        self.assertContains(response, "Неверный логин или пароль")
        self.assertNotIn("user_id", client.session)
        self.login(client=client)
        self.assertEqual(client.session["user_id"], 1)

    def test_unknown_login(self):
        response = Client().post(
            "/login/", {"username": "missing", "password": "wrong"}
        )
        self.assertContains(response, "Неверный логин или пароль")

    def test_registration(self):
        client = Client()
        response = client.post(
            "/register/",
            {
                "username": "new_user",
                "name": "Новый пользователь",
                "email": "NEW@example.com",
                "password1": "New-Travel-2026!",
                "password2": "New-Travel-2026!",
                "is_staff": 1,
            },
        )
        self.assertEqual(response.status_code, 302)
        user = fetch_one("SELECT * FROM users WHERE username = ?", ("new_user",))
        self.assertTrue(check_password("New-Travel-2026!", user["password"]))
        self.assertEqual(user["email"], "new@example.com")
        self.assertEqual(user["is_staff"], 0)
        self.assertEqual(client.session["user_id"], user["id"])

    def test_duplicate_registration(self):
        response = Client().post(
            "/register/",
            {
                "username": "GLEB",
                "name": "Name",
                "email": "ALEXEY@EXAMPLE.COM",
                "password1": "New-Travel-2026!",
                "password2": "New-Travel-2026!",
            },
        )
        self.assertContains(response, "уже используется")
        self.assertEqual(fetch_one("SELECT COUNT(*) FROM users")[0], 3)

    def test_weak_password(self):
        response = Client().post(
            "/register/",
            {
                "username": "new",
                "name": "Name",
                "email": "new@example.com",
                "password1": "123",
                "password2": "123",
            },
        )
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(fetch_one("SELECT COUNT(*) FROM users")[0], 3)

    def test_profile(self):
        response = self.client.post(
            "/profile/", {"name": "Глеб", "email": "gleb@example.com"}
        )
        self.assertRedirects(response, "/profile/")
        self.assertEqual(fetch_one("SELECT name FROM users WHERE id = 1")[0], "Глеб")

    def test_logout_only_post(self):
        self.assertEqual(self.client.get("/logout/").status_code, 405)
        self.assertRedirects(self.client.post("/logout/"), "/login/")
        self.assertNotIn("user_id", self.client.session)

    def test_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.get("/login/")
        self.assertEqual(client.post("/login/", {"username": "gleb"}).status_code, 403)

    def test_session_tampering(self):
        self.client.cookies["visited_places_session"] = "forged-user-id-1"
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_inactive_account(self):
        execute("UPDATE users SET is_active = 0 WHERE id = 1")
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_lists_contain_database_records(self):
        response = self.client.get("/")
        self.assertEqual(len(response.context["visits"]), 4)
        self.assertContains(response, "Журнал посещений")
        self.assertEqual(len(self.client.get("/places/").context["places"]), 6)
        self.assertEqual(len(self.client.get("/trips/").context["trips"]), 6)

    def test_unicode_search_and_sql_injection(self):
        response = self.client.get("/places/", {"q": "МОСКВА"})
        self.assertEqual(len(response.context["places"]), 2)
        response = self.client.get("/places/", {"q": "' OR 1=1 --"})
        self.assertEqual(len(response.context["places"]), 0)

    def test_unvisited_places(self):
        response = self.client.get("/places/", {"unvisited": "1"})
        self.assertEqual({p["id"] for p in response.context["places"]}, {5, 6})

    def test_trip_date_filter(self):
        response = self.client.get("/trips/", {"date": "2026-06-11"})
        self.assertEqual({t["id"] for t in response.context["trips"]}, {1, 4})

    def test_visit_filters(self):
        response = self.client.get("/", {"from": "2026-07-01", "to": "2026-07-01"})
        self.assertEqual([v["id"] for v in response.context["visits"]], [3])
        self.assertEqual(len(self.client.get("/", {"trip": "1"}).context["visits"]), 1)

    def test_pagination(self):
        for number in range(15):
            execute(
                "INSERT INTO places(name, city, country, category) VALUES (?, ?, ?, ?)",
                (f"Test {number}", "City", "Country", "Test"),
            )
        response = self.client.get("/places/", {"q": "Test", "page": 2})
        self.assertEqual(len(response.context["places"]), 3)
        self.assertEqual(response.context["page"]["total"], 15)
        self.assertContains(response, "q=Test&amp;page=1")
        self.assertEqual(self.client.get("/places/", {"page": "bad"}).status_code, 200)

    def test_detail_pages(self):
        for url, text in [
            ("/places/1/", "Красная площадь"),
            ("/trips/1/", "Выходные в Москве"),
            ("/visits/1/", "Прогулка по историческому центру."),
        ]:
            self.assertContains(self.client.get(url), text)

    def test_private_visits_even_for_staff(self):
        for url in ["/visits/5/", "/visits/5/edit/", "/visits/5/delete/"]:
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, {}).status_code, 404)

    @override_settings(DEBUG=False)
    def test_custom_404(self):
        for url in ["/places/999999/", "/places/abc/", "/unknown/"]:
            self.assertContains(
                self.client.get(url), "Страница не найдена", status_code=404
            )

    def test_place_create_edit_delete(self):
        data = {
            "name": "Новое место",
            "city": "Москва",
            "country": "Россия",
            "category": "Парк",
        }
        response = self.client.post("/places/new/", data)
        pk = fetch_one("SELECT id FROM places WHERE name = ?", (data["name"],))[0]
        self.assertRedirects(response, f"/places/{pk}/")
        data["category"] = "Музей"
        self.client.post(f"/places/{pk}/edit/", data)
        self.assertEqual(
            fetch_one("SELECT category FROM places WHERE id = ?", (pk,))[0], "Музей"
        )
        self.assertEqual(self.client.get(f"/places/{pk}/delete/").status_code, 200)
        self.assertIsNotNone(fetch_one("SELECT id FROM places WHERE id = ?", (pk,)))
        self.assertEqual(self.client.post(f"/places/{pk}/delete/").status_code, 302)
        self.assertIsNone(fetch_one("SELECT id FROM places WHERE id = ?", (pk,)))

    def test_regular_user_catalog_permissions(self):
        self.login("journal_2")
        for url in [
            "/places/1/edit/",
            "/places/1/delete/",
            "/trips/1/edit/",
            "/trips/1/delete/",
        ]:
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.assertEqual(
            self.client.post(
                "/places/new/",
                {
                    "name": "User place",
                    "city": "City",
                    "country": "Country",
                    "category": "Test",
                },
            ).status_code,
            302,
        )

    def test_unicode_duplicate_place(self):
        response = self.client.post(
            "/places/new/",
            {
                "name": "КРАСНАЯ ПЛОЩАДЬ",
                "city": "МОСКВА",
                "country": "РОССИЯ",
                "category": "Test",
            },
        )
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(fetch_one("SELECT COUNT(*) FROM places")[0], 6)

    def test_unsafe_image(self):
        response = self.client.post(
            "/places/new/",
            {
                "name": "Test",
                "city": "City",
                "country": "Country",
                "category": "Test",
                "image_url": "javascript:alert(1)",
            },
        )
        self.assertIn("image_url", response.context["form"].errors)

    def test_trip_create_edit_delete(self):
        data = {
            "name": "New trip",
            "place_id": 1,
            "start_date": "2026-10-17",
            "end_date": "2026-10-18",
        }
        self.assertEqual(self.client.post("/trips/new/", data).status_code, 302)
        pk = fetch_one("SELECT id FROM trips WHERE name = 'New trip'")[0]
        data["name"] = "Edited trip"
        self.assertEqual(self.client.post(f"/trips/{pk}/edit/", data).status_code, 302)
        self.assertEqual(self.client.post(f"/trips/{pk}/delete/").status_code, 302)

    def test_invalid_trip_dates(self):
        response = self.client.post(
            "/trips/new/",
            {
                "name": "Bad",
                "place_id": 1,
                "start_date": "2026-10-18",
                "end_date": "2026-10-17",
            },
        )
        self.assertIn("end_date", response.context["form"].errors)

    def test_trip_dates_preserve_existing_visits(self):
        response = self.client.post(
            "/trips/1/edit/",
            {
                "name": "Trip",
                "place_id": 1,
                "start_date": "2026-06-11",
                "end_date": "2026-06-12",
            },
        )
        self.assertIn("start_date", response.context["form"].errors)

    def test_visit_create_edit_delete(self):
        data = {
            "trip_id": 1,
            "visited_at": "2026-06-12T12:00",
            "rating": 3,
            "note": "New note",
            "user_id": 2,
            "place_id": 6,
        }
        self.assertEqual(self.client.post("/visits/new/", data).status_code, 302)
        visit = fetch_one("SELECT * FROM visits WHERE note = 'New note'")
        self.assertEqual(visit["user_id"], 1)
        data.update(note="Edited note", rating="", trip_id=4)
        self.assertEqual(
            self.client.post(f"/visits/{visit['id']}/edit/", data).status_code, 302
        )
        updated = fetch_one("SELECT * FROM visits WHERE id = ?", (visit["id"],))
        self.assertEqual(updated["trip_id"], 4)
        self.assertIsNone(updated["rating"])
        self.assertEqual(
            self.client.post(f"/visits/{visit['id']}/delete/").status_code, 302
        )

    def test_bad_visit(self):
        for data in [
            {"trip_id": 1, "visited_at": "2026-10-17T12:00", "rating": 4},
            {"trip_id": 1, "visited_at": "2026-06-12T12:00", "rating": 6},
            {"trip_id": 1, "visited_at": "2026-06-10T12:00", "rating": 4},
        ]:
            response = self.client.post("/visits/new/", data)
            self.assertTrue(response.context["form"].errors)

    def test_escaped_note(self):
        execute(
            "UPDATE visits SET note = ? WHERE id = 1", ("<script>alert(1)</script>",)
        )
        response = self.client.get("/visits/1/")
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_protected_deletion(self):
        self.assertEqual(self.client.post("/places/1/delete/").status_code, 409)
        self.assertEqual(self.client.post("/trips/1/delete/").status_code, 409)

    def test_statistics(self):
        response = self.client.get("/statistics/")
        self.assertEqual(response.context["summary"]["visits"], 4)
        self.assertEqual(response.context["summary"]["places"], 4)
        self.assertEqual(response.context["summary"]["rating"], 4.67)
        self.assertEqual(len(response.context["by_place"]), 4)
        self.assertEqual(len(response.context["by_country"]), 1)

    def test_having_filter(self):
        response = self.client.get("/statistics/", {"minimum": 2})
        self.assertEqual(len(response.context["by_place"]), 0)

    def test_extreme_having_threshold(self):
        response = self.client.get("/statistics/", {"minimum": "9" * 100})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["by_place"]), 0)

    @override_settings(
        PASSWORD_HASHERS=["django.contrib.auth.hashers.PBKDF2PasswordHasher"]
    )
    def test_standard_password_hash(self):
        execute(
            "UPDATE users SET password = ? WHERE id = 1",
            (make_password("Test-Travel-2026!"),),
        )
        self.login()
        self.assertEqual(self.client.session["user_id"], 1)

    def test_sql_changes_are_visible(self):
        execute("UPDATE places SET name = ? WHERE id = 1", ("Название из SQLite",))
        self.assertContains(self.client.get("/places/1/"), "Название из SQLite")

    def test_forms_and_templates(self):
        response = self.client.get("/visits/1/edit/")
        self.assertTemplateUsed(response, "visited_places/base.html")
        self.assertTemplateUsed(response, "visited_places/partials/navigation.html")
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertNotIn("place_id", response.context["form"].fields)
        self.assertNotIn("user_id", response.context["form"].fields)
        initial = response.context["form"].initial["visited_at"]
        self.assertEqual(initial, datetime(2026, 6, 10, 12, 0))

    def test_removed_api(self):
        self.assertEqual(self.client.get("/api/places/").status_code, 404)

    def test_missing_trailing_slash(self):
        self.assertRedirects(self.client.get("/places"), "/places/", status_code=301)

    def test_private_trip_visits(self):
        response = self.client.get("/trips/3/")
        self.assertEqual(len(response.context["visits"]), 0)
        self.assertEqual(len(fetch_all("SELECT * FROM visits WHERE trip_id = 3")), 1)
