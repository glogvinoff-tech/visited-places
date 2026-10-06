import builtins
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

import main
from visited_places.cli import ConsoleApplication
from visited_places.database import JournalDatabase
from visited_places.service import TravelJournal


def run_session(journal, database, commands, monkeypatch):
    answers = iter(commands)

    def read_input(prompt):
        try:
            return next(answers)
        except StopIteration as error:
            raise EOFError from error

    monkeypatch.setattr(builtins, "input", read_input)
    application = ConsoleApplication(journal, database)
    assert application.run() == 0
    return application


def test_terminal_workflow_persists_and_restores_all_new_entities(
    tmp_path, monkeypatch,
):
    database = JournalDatabase(tmp_path / "journal.sqlite3")
    database.initialize(TravelJournal())
    run_session(database.load(), database, [
        "Alex", "alex@example.com",
        "4", "Museum", "Moscow", "Russia", "Museum",
        "5", "Weekend", "2026-06-10", "2026-06-12",
        "6", "1", "2026-06-10 12:00", "1", "5", "A memory",
        "0",
    ], monkeypatch)
    restored = database.load()
    assert restored.users[0].name == "Alex"
    assert restored.places[0].name == "Museum"
    assert restored.trips[0].name == "Weekend"
    assert restored.visits[0].note == "A memory"
    assert restored.visits[0].trip is restored.trips[0]


def test_edit_and_delete_visit_are_persisted(journal, journal_database, monkeypatch):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00", 4, "Original", 1)
    journal_database.save(journal)
    run_session(journal, journal_database, [
        "7", str(visit.id), "5", "Updated", "0",
    ], monkeypatch)
    restored = journal_database.load()
    assert restored.visits[0].rating == 5
    assert restored.visits[0].note == "Updated"
    run_session(restored, journal_database, [
        "8", str(visit.id), "yes", "0",
    ], monkeypatch)
    assert not journal_database.load().visits


def test_delete_cancellation_keeps_visit(journal, journal_database, monkeypatch):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00")
    journal_database.save(journal)
    run_session(journal, journal_database, ["8", str(visit.id), "no", "0"], monkeypatch)
    assert len(journal_database.load().visits) == 1


def test_profiles_can_be_added_and_switched(journal, journal_database, monkeypatch):
    application = run_session(journal, journal_database, [
        "11", "Anna", "anna@example.com", "10", "2", "0",
    ], monkeypatch)
    assert application.user.name == "Maria"
    assert journal_database.load().users[-1].name == "Anna"


def test_input_errors_do_not_exit_menu_or_change_saved_state(
    journal, journal_database, monkeypatch, capsys,
):
    run_session(journal, journal_database, [
        "unknown", "6", "not-an-id",
        "6", "1", "2026-06-10 12:00", "1", "9", "Invalid rating",
        "6", "1", "2026-06-10 12:00", "1", "5", "Valid visit", "0",
    ], monkeypatch)
    restored = journal_database.load()
    assert len(restored.visits) == 1
    assert restored.visits[0].rating == 5
    assert "Ошибка" in capsys.readouterr().out


def test_database_failure_does_not_publish_unsaved_memory_state(
    journal, journal_database, monkeypatch, capsys,
):
    def fail_save(candidate):
        raise sqlite3.OperationalError("Read-only database")

    monkeypatch.setattr(journal_database, "save", fail_save)
    application = run_session(journal, journal_database, [
        "4", "Unsaved", "Moscow", "Russia", "Museum", "0",
    ], monkeypatch)
    assert len(application.journal.places) == len(journal.places)
    assert "Read-only database" in capsys.readouterr().out


def test_trip_edit_and_delete_keep_visit_in_history(
    journal, journal_database, monkeypatch,
):
    journal.add_visit(1, 1, "2026-06-10 12:00", 5, trip_id=1)
    journal_database.save(journal)
    application = run_session(journal, journal_database, [
        "12", "1", "New name", "2026-06-09", "2026-06-13", "0",
    ], monkeypatch)
    assert journal_database.load().trips[0].name == "New name"
    run_session(application.journal, journal_database, [
        "13", "1", "yes", "0",
    ], monkeypatch)
    restored = journal_database.load()
    assert len(restored.visits) == 1
    assert restored.visits[0].trip is None


def test_history_catalog_and_statistics_use_selected_profile(
    journal, journal_database, monkeypatch, capsys,
):
    journal.add_visit(1, 1, "2026-06-10 12:00", 5, "Alex note", 1)
    journal.add_visit(2, 3, "2026-08-16 12:00", 1, "Maria note", 2)
    journal_database.save(journal)
    run_session(journal, journal_database, [
        "2", "mOsCoW", "1", "1", "9", "0",
    ], monkeypatch)
    output = capsys.readouterr().out
    assert "Red Square" in output
    assert "Alex note" in output
    assert "Maria note" not in output
    assert "5.00/5" in output


@pytest.mark.parametrize("exception", [EOFError, KeyboardInterrupt])
def test_end_of_input_exits_cleanly(journal, journal_database, monkeypatch, exception):
    def interrupted_input(prompt):
        raise exception

    monkeypatch.setattr(builtins, "input", interrupted_input)
    assert ConsoleApplication(journal, journal_database).run() == 0


def test_separate_process_restarts_from_sqlite_instead_of_reimporting_seed(tmp_path):
    data_dir = tmp_path / "data"
    shutil.copytree(
        main.DATA_DIR, data_dir, ignore=shutil.ignore_patterns("*.sqlite3*")
    )
    command = [
        sys.executable, str(Path(main.__file__).resolve()), "--data-dir", str(data_dir),
    ]
    first = subprocess.run(
        command, input="4\nMy museum\nMy city\nMy country\nMuseum\n0\n",
        capture_output=True, text=True, encoding="utf-8", timeout=10,
    )
    assert first.returncode == 0, first.stderr
    for path in data_dir.glob("*.json"):
        path.unlink()
    second = subprocess.run(
        command, input="2\nMy museum\n0\n",
        capture_output=True, text=True, encoding="utf-8", timeout=10,
    )
    assert second.returncode == 0, second.stderr
    assert "My museum" in second.stdout
    assert len(JournalDatabase(data_dir / "journal.sqlite3").load().places) == 7
