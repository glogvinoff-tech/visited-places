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
    assert list(answers) == []
    return application


def test_terminal_workflow_persists_all_new_entities(tmp_path, monkeypatch):
    database = JournalDatabase(tmp_path / "journal.sqlite3")
    database.initialize(TravelJournal())
    run_session(database.load(), database, [
        "Alex", "alex@example.com",
        "4", "Museum", "Moscow", "Russia", "Museum",
        "5", "1", "Weekend", "2026-06-10", "2026-06-12",
        "6", "1", "2026-06-10 12:00", "5", "A memory", "0",
    ], monkeypatch)
    restored = database.load()
    assert restored.users[0].name == "Alex"
    assert restored.trips[0].place is restored.places[0]
    assert restored.visits[0].trip is restored.trips[0]
    assert restored.visits[0].note == "A memory"
    assert not hasattr(restored.visits[0], "place")


def test_edit_and_delete_visit_are_persisted(journal, journal_database, monkeypatch):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00", 4, "Original")
    journal_database.save(journal)
    run_session(journal, journal_database, [
        "7", str(visit.id), "", "", "5", "Updated", "0",
    ], monkeypatch)
    restored = journal_database.load()
    assert restored.visits[0].rating == 5
    assert restored.visits[0].note == "Updated"
    run_session(
        restored, journal_database, ["8", str(visit.id), "yes", "0"], monkeypatch
    )
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


def test_input_errors_do_not_exit_or_change_saved_state(
    journal, journal_database, monkeypatch, capsys,
):
    run_session(journal, journal_database, [
        "unknown", "6", "not-an-id",
        "6", "1", "2026-06-10 12:00", "9", "Invalid rating",
        "6", "1", "2026-06-10 12:00", "5", "Valid visit", "0",
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


def test_trip_edit_and_restricted_deletion_keep_visits(
    journal, journal_database, monkeypatch, capsys,
):
    journal.add_visit(1, 1, "2026-06-10 12:00", 5)
    journal_database.save(journal)
    run_session(journal, journal_database, [
        "12", "1", "New name", "2", "2026-06-09", "2026-06-13",
        "13", "1", "yes", "0",
    ], monkeypatch)
    restored = journal_database.load()
    assert restored.trips[0].name == "New name"
    assert restored.visits[0].trip.place is restored.places[1]
    assert "посещения этой поездки" in capsys.readouterr().out
    run_session(restored, journal_database, [
        "8", "1", "yes", "13", "1", "yes", "0",
    ], monkeypatch)
    assert len(journal_database.load().trips) == 2


def test_history_search_and_statistics_are_personal_but_trips_are_shared(
    journal, journal_database, monkeypatch, capsys,
):
    journal.add_visit(1, 1, "2026-06-10 12:00", 5, "Alex note")
    journal.add_visit(2, 1, "2026-06-11 12:00", 1, "Maria note")
    journal_database.save(journal)
    run_session(journal, journal_database, [
        "14", "mOsCoW", "15", "1", "3", "9", "0",
    ], monkeypatch)
    output = capsys.readouterr().out
    assert "Red Square" in output
    assert "Alex note" in output
    assert "Maria note" not in output
    assert "Istanbul" in output
    assert "5.00/5" in output


@pytest.mark.parametrize("command, expected", [
    ("1", "A visible visit"), ("2", "Red Square, Moscow, Russia"),
    ("3", "Moscow weekend: Red Square"),
])
def test_lists_are_printed_without_extra_input_or_repeating_menu(
    journal, journal_database, monkeypatch, capsys, command, expected,
):
    journal.add_visit(1, 1, "2026-06-10 12:00", note="A visible visit")
    journal_database.save(journal)
    run_session(journal, journal_database, [command, "0"], monkeypatch)
    output = capsys.readouterr().out
    assert expected in output
    assert output.count("0. Выход") == 1
    assert "Неизвестная команда" not in output


@pytest.mark.parametrize("command, expected", [
    ("1", "Посещений нет"), ("2", "Места не найдены"), ("3", "Поездок нет"),
])
def test_empty_lists_show_a_result_without_extra_input(
    tmp_path, monkeypatch, capsys, command, expected,
):
    journal = TravelJournal()
    journal.add_user("Alex", "alex@example.com")
    database = JournalDatabase(tmp_path / "journal.sqlite3")
    database.initialize(journal)
    run_session(journal, database, [command, "0"], monkeypatch)
    assert expected in capsys.readouterr().out


def test_menu_can_be_requested_after_showing_a_result(
    journal, journal_database, monkeypatch, capsys,
):
    run_session(journal, journal_database, ["3", "м", "0"], monkeypatch)
    assert capsys.readouterr().out.count("0. Выход") == 2


def test_all_editable_fields_are_persisted_through_the_new_links(
    journal, journal_database, monkeypatch, capsys,
):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00", 3, "Original")
    journal_database.save(journal)
    run_session(journal, journal_database, [
        "7", str(visit.id), "2026-07-02 13:45", "3", "5", "Changed",
        "16", "2", "New museum", "New city", "New country", "New category",
        "17", "Renamed Alex", "renamed@example.com",
        "12", "3", "Updated July", "", "", "", "1", "0",
    ], monkeypatch)
    restored = journal_database.load()
    saved = restored.visits[0]
    assert saved.trip is restored.trips[2]
    assert saved.trip.place is restored.places[1]
    assert saved.trip.place.name == "New museum"
    assert saved.trip.place.city == "New city"
    assert saved.trip.place.country == "New country"
    assert saved.trip.place.category == "New category"
    assert saved.trip.name == "Updated July"
    assert saved.visited_at == "2026-07-02 13:45"
    assert saved.rating == 5
    assert saved.note == "Changed"
    assert saved.user.name == "Renamed Alex"
    assert saved.user.email == "renamed@example.com"
    output = capsys.readouterr().out
    assert "Отметка обновлена:" in output
    assert "Место обновлено:" in output
    assert "Профиль обновлен:" in output
    assert "Changed" in output.split("Отметка обновлена:", 1)[1]


def test_blank_edit_fields_keep_existing_values(journal, journal_database, monkeypatch):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00", 4, "Original")
    journal_database.save(journal)
    before = {
        table: [item.to_data() for item in getattr(journal, table)]
        for table in ("users", "places", "trips", "visits")
    }
    run_session(journal, journal_database, [
        "7", str(visit.id), "", "", "", "",
        "16", "1", "", "", "", "", "17", "", "",
        "12", "1", "", "", "", "", "0",
    ], monkeypatch)
    restored = journal_database.load()
    assert {
        table: [item.to_data() for item in getattr(restored, table)] for table in before
    } == before


def test_edit_clears_rating_and_note_but_keeps_required_trip(
    journal, journal_database, monkeypatch,
):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00", 4, "Original")
    journal_database.save(journal)
    run_session(journal, journal_database, [
        "7", str(visit.id), "", "", "0", "-", "0",
    ], monkeypatch)
    saved = journal_database.load().visits[0]
    assert saved.trip_id == 1
    assert saved.rating is None
    assert saved.note == ""


@pytest.mark.parametrize("trip_id", ["0", "999"])
def test_failed_visit_edit_keeps_record_and_next_command_works(
    journal, journal_database, monkeypatch, capsys, trip_id,
):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00", 4, "Original")
    journal_database.save(journal)
    before = visit.to_data()
    run_session(journal, journal_database, [
        "7", str(visit.id), "", trip_id, "5", "Changed", "1", "0",
    ], monkeypatch)
    assert journal_database.load().visits[0].to_data() == before
    output = capsys.readouterr().out
    assert "Ошибка:" in output
    assert "Отметка обновлена:" not in output
    assert "История посещений:" in output


def test_duplicate_place_and_profile_edits_do_not_change_saved_data(
    journal, journal_database, monkeypatch, capsys,
):
    original_place = journal.places[0].to_data()
    original_user = journal.users[0].to_data()
    run_session(journal, journal_database, [
        "16", "1", "Hermitage", "Saint Petersburg", "Russia", "Museum",
        "17", "Changed", "maria@example.com", "0",
    ], monkeypatch)
    restored = journal_database.load()
    assert restored.places[0].to_data() == original_place
    assert restored.users[0].to_data() == original_user
    assert capsys.readouterr().out.count("Ошибка:") == 2


@pytest.mark.parametrize("exception", [EOFError, KeyboardInterrupt])
def test_end_of_input_exits_cleanly(journal, journal_database, monkeypatch, exception):
    def interrupted_input(prompt):
        raise exception

    monkeypatch.setattr(builtins, "input", interrupted_input)
    assert ConsoleApplication(journal, journal_database).run() == 0


def test_separate_process_restarts_from_sqlite_instead_of_seed(tmp_path):
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
        command, input="2\n0\n", capture_output=True,
        text=True, encoding="utf-8", timeout=10,
    )
    assert second.returncode == 0, second.stderr
    assert "My museum" in second.stdout
    assert len(JournalDatabase(data_dir / "journal.sqlite3").load().places) == 7


def test_visit_edits_survive_an_independent_process_restart(tmp_path, journal):
    data_dir = tmp_path / "data"
    database = JournalDatabase(data_dir / "journal.sqlite3")
    journal.add_visit(1, 1, "2026-06-10 12:00", 3, "Original")
    database.initialize(journal)
    command = [
        sys.executable, str(Path(main.__file__).resolve()), "--data-dir", str(data_dir),
    ]
    edit = subprocess.run(
        command, input="7\n1\n2026-07-02 13:45\n3\n5\nChanged\n0\n",
        capture_output=True, text=True, encoding="utf-8", timeout=10,
    )
    assert edit.returncode == 0, edit.stderr
    restored = subprocess.run(
        command, input="1\n0\n", capture_output=True,
        text=True, encoding="utf-8", timeout=10,
    )
    assert restored.returncode == 0, restored.stderr
    assert "Hermitage" in restored.stdout
    assert "Changed" in restored.stdout
    assert "2026-07-02 13:45" in restored.stdout
