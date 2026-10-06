import sqlite3
from pathlib import Path

import pytest

from visited_places.storage import load_journal


PROJECT_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def database():
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(
            (PROJECT_DIR / "database" / "schema.sql").read_text(encoding="utf-8")
        )
        journal = load_journal(PROJECT_DIR / "data")
        for table in ("users", "places", "trips", "visits"):
            records = [item.to_data() for item in getattr(journal, table)]
            columns = ", ".join(records[0])
            parameters = ", ".join(f":{name}" for name in records[0])
            connection.executemany(
                f"INSERT INTO {table} ({columns}) VALUES ({parameters})", records
            )
        connection.commit()
        yield connection
    finally:
        connection.close()


def insert_visit(database, **changes):
    record = {
        "id": 20, "user_id": 1, "place_id": 1, "trip_id": 1,
        "visited_at": "2026-06-12 12:00", "rating": 5, "note": "New visit",
    }
    record.update(changes)
    database.execute(
        "INSERT INTO visits "
        "(id, user_id, place_id, trip_id, visited_at, rating, note) "
        "VALUES (:id, :user_id, :place_id, :trip_id, :visited_at, :rating, :note)",
        record,
    )


def test_schema_accepts_the_journals_demo_records(database):
    assert database.execute("PRAGMA foreign_keys").fetchone() == (1,)
    assert database.execute("PRAGMA foreign_key_check").fetchall() == []
    assert database.execute("SELECT COUNT(*) FROM visits").fetchone() == (6,)


@pytest.mark.parametrize("changes", [
    {"user_id": 999, "trip_id": None}, {"place_id": 999}, {"trip_id": 999},
    {"user_id": 2}, {"visited_at": "2026-06-13 00:00"}, {"rating": 0},
    {"rating": 6}, {"rating": 4.5}, {"note": None},
    {"visited_at": "2026-02-30 12:00", "trip_id": None},
    {"visited_at": "not-a-valid-date", "trip_id": None},
    {"visited_at": "2026-06-10 12:00"},
])
def test_schema_rejects_invalid_visits(database, changes):
    with pytest.raises(sqlite3.IntegrityError):
        insert_visit(database, **changes)


def test_schema_allows_visits_without_trip_or_rating(database):
    insert_visit(database, trip_id=None, rating=None)
    assert database.execute(
        "SELECT trip_id, rating FROM visits WHERE id = 20"
    ).fetchone() == (None, None)


@pytest.mark.parametrize("start,end", [
    ("2026-06-12", "2026-06-10"), ("2026-02-30", "2026-03-02"),
    ("2026-6-10", "2026-06-12"), ("invalid", "2026-06-12"),
])
def test_schema_rejects_invalid_trip_dates(database, start, end):
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "INSERT INTO trips (id, user_id, name, start_date, end_date) "
            "VALUES (20, 1, 'Invalid trip', ?, ?)", (start, end),
        )


@pytest.mark.parametrize("statement", [
    "UPDATE visits SET user_id = 2 WHERE id = 1",
    "UPDATE visits SET visited_at = '2026-06-13 12:00' WHERE id = 1",
    "UPDATE trips SET user_id = 2 WHERE id = 1",
    "UPDATE trips SET start_date = '2026-06-11' WHERE id = 1",
])
def test_schema_prevents_updates_that_break_trip_visit_links(database, statement):
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(statement)


def test_deleting_trip_preserves_its_marks_without_trip_link(database):
    database.execute("DELETE FROM trips WHERE id = 1")
    assert database.execute(
        "SELECT trip_id FROM visits WHERE id IN (1, 2)"
    ).fetchall() == [(None,), (None,)]


def test_deleting_used_place_is_restricted(database):
    with pytest.raises(sqlite3.IntegrityError):
        database.execute("DELETE FROM places WHERE id = 1")


def test_deleting_user_removes_only_their_private_data(database):
    database.execute("DELETE FROM users WHERE id = 1")
    assert database.execute("SELECT COUNT(*) FROM visits").fetchone() == (2,)
    assert database.execute("SELECT COUNT(*) FROM trips").fetchone() == (1,)
    assert database.execute("SELECT COUNT(*) FROM places").fetchone() == (6,)


def test_schema_enforces_unique_email(database):
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "INSERT INTO users (id, name, email) VALUES (20, 'Other', ?)",
            ("ALEXEY@EXAMPLE.COM",),
        )
