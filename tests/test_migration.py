import json
import sqlite3
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

import main
from visited_places.database import JournalDatabase
from visited_places.migration import migrate_legacy_records
from visited_places.storage import journal_from_records, load_journal, save_json


@pytest.fixture
def legacy_records():
    return {
        "users": [
            {"id": 1, "name": "Alex", "email": "alex@example.com"},
            {"id": 2, "name": "Maria", "email": "maria@example.com"},
        ],
        "places": [
            {"id": 1, "name": "Square", "city": "Moscow",
             "country": "Russia", "category": "Landmark"},
            {"id": 2, "name": "Park", "city": "Moscow",
             "country": "Russia", "category": "Park"},
            {"id": 3, "name": "Museum", "city": "Petersburg",
             "country": "Russia", "category": "Museum"},
        ],
        "trips": [
            {"id": 1, "user_id": 1, "name": "Weekend",
             "start_date": "2026-06-10", "end_date": "2026-06-12"},
            {"id": 2, "user_id": 2, "name": "August",
             "start_date": "2026-08-15", "end_date": "2026-08-17"},
        ],
        "visits": [
            {"id": 1, "user_id": 1, "place_id": 1, "trip_id": 1,
             "visited_at": "2026-06-10 12:00", "rating": 5, "note": "Память"},
            {"id": 2, "user_id": 1, "place_id": 2, "trip_id": 1,
             "visited_at": "2026-06-11 12:00", "rating": 4, "note": "Park note"},
            {"id": 3, "user_id": 2, "place_id": 3, "trip_id": 2,
             "visited_at": "2026-08-16 12:00", "rating": None, "note": "Museum"},
            {"id": 4, "user_id": 2, "place_id": 3, "trip_id": None,
             "visited_at": "2026-09-05 14:00", "rating": 3, "note": "No trip"},
        ],
    }


def create_legacy_database(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = Path(__file__).parent / "fixtures" / "schema_v1.sql"
    with sqlite3.connect(path) as connection:
        connection.executescript(schema.read_text(encoding="utf-8"))
        for table, items in records.items():
            if not items:
                continue
            columns = ", ".join(items[0])
            values = ", ".join(f":{key}" for key in items[0])
            connection.executemany(
                f"INSERT INTO {table} ({columns}) VALUES ({values})", items
            )


def read_records(path):
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        return {
            table: [dict(row) for row in connection.execute(
                f"SELECT * FROM {table} ORDER BY id"
            )]
            for table in ("users", "places", "trips", "visits")
        }


def assert_old_visit_details_preserved(journal, records):
    assert [user.to_data() for user in journal.users] == records["users"]
    assert [place.to_data() for place in journal.places] == records["places"]
    assert len(journal.visits) == len(records["visits"])
    for old, visit in zip(records["visits"], journal.visits):
        for field in ("id", "user_id", "visited_at", "rating", "note"):
            assert visit.to_data()[field] == old[field]
        assert visit.trip.place_id == old["place_id"]


def test_converter_splits_multi_place_trips_without_mutating_source(legacy_records):
    before = deepcopy(legacy_records)
    converted = migrate_legacy_records(legacy_records)
    assert legacy_records == before
    journal = journal_from_records(converted)
    assert_old_visit_details_preserved(journal, legacy_records)
    assert len(journal.trips) == 4
    assert [visit.trip_id for visit in journal.visits] == [1, 3, 2, 4]
    assert journal.trips[3].start_date == "2026-09-05"
    assert journal.trips[3].end_date == "2026-09-05"
    assert all("user_id" not in item for item in converted["trips"])
    assert all("place_id" not in item for item in converted["visits"])


def test_sqlite_upgrade_preserves_data_and_creates_a_restorable_backup(
    tmp_path, legacy_records,
):
    path = tmp_path / "journal.sqlite3"
    create_legacy_database(path, legacy_records)
    database = JournalDatabase(path)
    restored = database.load()
    assert_old_visit_details_preserved(restored, legacy_records)
    assert database.last_backup_path is not None
    assert read_records(database.last_backup_path) == legacy_records
    with sqlite3.connect(database.last_backup_path) as backup:
        assert backup.execute("PRAGMA user_version").fetchone() == (1,)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (2,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    database.save(restored)
    reopened = JournalDatabase(path)
    assert_old_visit_details_preserved(reopened.load(), legacy_records)
    assert reopened.last_backup_path is None
    assert len(list(tmp_path.glob("journal.v1-backup-*.sqlite3"))) == 1


def test_failed_migration_rolls_back_schema_version_and_every_record(
    tmp_path, legacy_records, monkeypatch,
):
    path = tmp_path / "journal.sqlite3"
    create_legacy_database(path, legacy_records)

    def fail_write(connection, journal):
        raise sqlite3.IntegrityError("Simulated migration failure")

    monkeypatch.setattr(JournalDatabase, "_write", staticmethod(fail_write))
    with pytest.raises(sqlite3.IntegrityError, match="Simulated"):
        JournalDatabase(path).load()
    assert read_records(path) == legacy_records
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_unused_legacy_trip_without_a_known_place_is_not_guessed_or_deleted(
    tmp_path, legacy_records,
):
    legacy_records["trips"].append({
        "id": 20, "user_id": 1, "name": "Unknown destination",
        "start_date": "2026-10-01", "end_date": "2026-10-02",
    })
    path = tmp_path / "journal.sqlite3"
    create_legacy_database(path, legacy_records)
    with pytest.raises(ValueError, match="Cannot infer the place"):
        JournalDatabase(path).load()
    assert read_records(path) == legacy_records
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)


@pytest.mark.parametrize("changes", [
    {"user_id": 999}, {"user_id": 2}, {"place_id": 999},
    {"trip_id": 999}, {"place_id": 0},
])
def test_converter_rejects_invalid_legacy_links(legacy_records, changes):
    legacy_records["visits"][0].update(changes)
    with pytest.raises(ValueError):
        migrate_legacy_records(legacy_records)


def test_duplicate_legacy_ids_are_rejected_without_dropping_records(legacy_records):
    legacy_records["trips"].append(dict(legacy_records["trips"][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        migrate_legacy_records(legacy_records)


def test_empty_version_one_database_is_upgraded(tmp_path):
    path = tmp_path / "journal.sqlite3"
    create_legacy_database(
        path, {key: [] for key in ("users", "places", "trips", "visits")}
    )
    assert not JournalDatabase(path).load().users
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (2,)


def test_old_json_import_is_converted_without_overwriting_files(
    tmp_path, legacy_records,
):
    for table, records in legacy_records.items():
        save_json(tmp_path / f"{table}.json", records)
    assert_old_visit_details_preserved(load_journal(tmp_path), legacy_records)
    for table, records in legacy_records.items():
        content = (tmp_path / f"{table}.json").read_text(encoding="utf-8")
        assert json.loads(content) == records


def test_missing_old_json_fields_have_a_useful_error(tmp_path, legacy_records):
    del legacy_records["visits"][0]["visited_at"]
    legacy_records["visits"][0]["trip_id"] = None
    for table, records in legacy_records.items():
        save_json(tmp_path / f"{table}.json", records)
    with pytest.raises(ValueError, match="Missing legacy journal field"):
        load_journal(tmp_path)


def test_terminal_can_restart_after_upgrading_legacy_database(tmp_path, legacy_records):
    create_legacy_database(tmp_path / "journal.sqlite3", legacy_records)
    command = [
        sys.executable, str(Path(main.__file__).resolve()), "--data-dir", str(tmp_path),
    ]
    first = subprocess.run(
        command, input="1\n0\n", capture_output=True,
        text=True, encoding="utf-8", timeout=10,
    )
    assert first.returncode == 0, first.stderr
    assert "База обновлена" in first.stdout
    assert "Память" in first.stdout
    second = subprocess.run(
        command, input="1\n0\n", capture_output=True,
        text=True, encoding="utf-8", timeout=10,
    )
    assert second.returncode == 0, second.stderr
    assert "База обновлена" not in second.stdout
    assert "Память" in second.stdout
