import sqlite3
from copy import deepcopy

import pytest

from visited_places.database import JournalDatabase
from visited_places.service import TravelJournal


def test_database_round_trip_preserves_unicode_notes_and_object_links(
    journal, journal_database,
):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00", 5, "Памятное посещение", 1)
    journal_database.save(journal)
    restored = journal_database.load()
    assert restored.visits[0].to_data() == visit.to_data()
    assert restored.visits[0].user is restored.users[0]
    assert restored.visits[0].place is restored.places[0]
    assert restored.visits[0].trip is restored.trips[0]
    assert restored.trips[0].user is restored.users[0]


def test_database_can_persist_an_empty_journal(tmp_path):
    database = JournalDatabase(tmp_path / "nested" / "journal.sqlite3")
    database.initialize(TravelJournal())
    assert not database.load().users


def test_initialization_never_replaces_an_existing_database(journal, journal_database):
    with pytest.raises(FileExistsError):
        journal_database.initialize(TravelJournal())
    assert len(journal_database.load().users) == len(journal.users)


def test_failed_save_rolls_back_the_whole_snapshot(journal, journal_database):
    with sqlite3.connect(journal_database.path) as connection:
        connection.executescript(
            "CREATE TRIGGER simulate_failure BEFORE INSERT ON visits "
            "BEGIN SELECT RAISE(ABORT, 'Simulated write failure'); END;"
        )
    candidate = deepcopy(journal)
    candidate.users[0].name = "Changed name"
    candidate.add_visit(1, 1, "2026-06-10 12:00", 5)
    with pytest.raises(sqlite3.IntegrityError, match="Simulated"):
        journal_database.save(candidate)
    restored = journal_database.load()
    assert restored.users[0].name == journal.users[0].name
    assert len(restored.places) == len(journal.places)
    assert not restored.visits


def test_invalid_snapshot_is_rejected_without_changing_database(
    journal, journal_database,
):
    candidate = deepcopy(journal)
    candidate.trips[0].end_date = "2026-06-01"
    with pytest.raises(ValueError):
        journal_database.save(candidate)
    assert journal_database.load().trips[0].end_date == "2026-06-12"


def test_database_persists_visit_edits_and_trip_removal(journal, journal_database):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00", 4, "Original", 1)
    journal_database.save(journal)
    journal.update_visit(1, visit.id, rating=5, note="Updated")
    journal.remove_trip(1, 1)
    journal_database.save(journal)
    restored = JournalDatabase(journal_database.path).load()
    assert restored.visits[0].rating == 5
    assert restored.visits[0].note == "Updated"
    assert restored.visits[0].trip is None
    journal.remove_visit(1, visit.id)
    journal_database.save(journal)
    assert not journal_database.load().visits


def test_missing_database_is_not_created_by_load_or_save(tmp_path):
    database = JournalDatabase(tmp_path / "missing.sqlite3")
    with pytest.raises(FileNotFoundError):
        database.load()
    with pytest.raises(FileNotFoundError):
        database.save(TravelJournal())
    assert not database.exists


def test_unknown_schema_version_is_rejected(journal_database):
    with sqlite3.connect(journal_database.path) as connection:
        connection.execute("PRAGMA user_version = 99")
    with pytest.raises(ValueError, match="schema version"):
        journal_database.load()
