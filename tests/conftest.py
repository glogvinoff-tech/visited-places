import pytest

from visited_places.database import JournalDatabase
from visited_places.service import TravelJournal


@pytest.fixture
def journal():
    journal = TravelJournal()
    journal.add_user("Alex", "alex@example.com")
    journal.add_user("Maria", "maria@example.com")
    journal.add_place("Red Square", "Moscow", "Russia", "Landmark")
    journal.add_place("Hermitage", "Saint Petersburg", "Russia", "Museum")
    journal.add_place("Galata Tower", "Istanbul", "Turkey", "Landmark")
    journal.add_trip(1, "Moscow weekend", "2026-06-10", "2026-06-12")
    journal.add_trip(2, "Istanbul", "2026-08-15", "2026-08-17")
    return journal


@pytest.fixture
def journal_database(tmp_path, journal):
    database = JournalDatabase(tmp_path / "journal.sqlite3")
    database.initialize(journal)
    return database
