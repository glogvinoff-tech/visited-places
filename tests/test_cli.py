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
        "7", str(visit.id), "", "", "", "5", "Updated", "0",
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
        "14", "mOsCoW", "15", "1", "9", "0",
    ], monkeypatch)
    output = capsys.readouterr().out
    assert "Red Square" in output
    assert "Alex note" in output
    assert "Maria note" not in output
    assert "5.00/5" in output


@pytest.mark.parametrize("command, expected", [
    ("1", "A visible visit"),
    ("2", "Red Square, Moscow, Russia"),
    ("3", "Moscow weekend (2026-06-10 - 2026-06-12)"),
])
def test_lists_are_printed_without_additional_input_or_repeating_menu(
    journal, journal_database, monkeypatch, capsys, command, expected,
):
    journal.add_visit(1, 1, "2026-06-10 12:00", note="A visible visit")
    journal_database.save(journal)
    run_session(journal, journal_database, [command, "0"], monkeypatch)
    output = capsys.readouterr().out
    assert expected in output
    assert output.count("0. Выход") == 1
    assert "Неизвестная команда" not in output
    assert "До свидания!" in output


@pytest.mark.parametrize("command, expected", [
    ("1", "Посещений нет"),
    ("2", "Места не найдены"),
    ("3", "Поездок нет"),
])
def test_empty_lists_show_a_result_without_additional_input(
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


def test_edited_records_are_displayed_and_persisted(
    journal, journal_database, monkeypatch, capsys,
):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00", 3, "Original", 1)
    journal_database.save(journal)
    run_session(journal, journal_database, [
        "7", str(visit.id), "", "", "", "5", "Visible update",
        "12", "1", "Updated weekend", "2026-06-09", "2026-06-13",
        "0",
    ], monkeypatch)
    output = capsys.readouterr().out
    after_edit = output.split("Отметка обновлена:", 1)[1]
    assert "5/5" in after_edit
    assert "Visible update" in after_edit
    assert "Updated weekend (2026-06-09 - 2026-06-13)" in after_edit
    restored = journal_database.load()
    assert restored.visits[0].rating == 5
    assert restored.visits[0].note == "Visible update"
    assert restored.trips[0].name == "Updated weekend"


def test_all_editable_fields_are_persisted_and_linked(
    journal, journal_database, monkeypatch, capsys,
):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00", 3, "Original", 1)
    trip = journal.add_trip(1, "July trip", "2026-07-01", "2026-07-03")
    journal_database.save(journal)
    run_session(journal, journal_database, [
        "7", str(visit.id), "2", "2026-07-02 13:45", str(trip.id), "5", "Changed",
        "16", "2", "New museum", "New city", "New country", "New category",
        "17", "Renamed Alex", "renamed@example.com",
        "0",
    ], monkeypatch)
    restored = journal_database.load()
    saved_visit = restored.visits[0]
    assert saved_visit.place is restored.places[1]
    assert saved_visit.place.name == "New museum"
    assert saved_visit.place.city == "New city"
    assert saved_visit.place.country == "New country"
    assert saved_visit.place.category == "New category"
    assert saved_visit.visited_at == "2026-07-02 13:45"
    assert saved_visit.trip is restored.trips[2]
    assert saved_visit.rating == 5
    assert saved_visit.note == "Changed"
    assert saved_visit.user is restored.users[0]
    assert saved_visit.user.name == "Renamed Alex"
    assert saved_visit.user.email == "renamed@example.com"
    output = capsys.readouterr().out
    assert "Отметка обновлена:" in output
    assert "Место обновлено:" in output
    assert "Профиль обновлен:" in output


def test_blank_edit_fields_keep_existing_values(
    journal, journal_database, monkeypatch,
):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00", 4, "Original", 1)
    journal_database.save(journal)
    before = {
        table: [item.to_data() for item in getattr(journal, table)]
        for table in ("users", "places", "trips", "visits")
    }
    run_session(journal, journal_database, [
        "7", str(visit.id), "", "", "", "", "",
        "16", "1", "", "", "", "",
        "17", "", "",
        "12", "1", "", "", "",
        "0",
    ], monkeypatch)
    restored = journal_database.load()
    assert {
        table: [item.to_data() for item in getattr(restored, table)]
        for table in before
    } == before


def test_edit_can_detach_visit_and_clear_rating_and_note(
    journal, journal_database, monkeypatch,
):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00", 4, "Original", 1)
    journal_database.save(journal)
    run_session(journal, journal_database, [
        "7", str(visit.id), "", "2026-10-06 12:00", "0", "0", "-", "0",
    ], monkeypatch)
    restored = journal_database.load().visits[0]
    assert restored.visited_at == "2026-10-06 12:00"
    assert restored.trip is None
    assert restored.rating is None
    assert restored.note == ""


def test_failed_visit_edit_keeps_saved_record_and_next_command_works(
    journal, journal_database, monkeypatch, capsys,
):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00", 4, "Original", 1)
    journal_database.save(journal)
    before = visit.to_data()
    run_session(journal, journal_database, [
        "7", str(visit.id), "999", "", "", "5", "Changed", "1", "0",
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


def test_new_process_prints_catalog_without_additional_input(tmp_path):
    data_dir = tmp_path / "data"
    database = JournalDatabase(data_dir / "journal.sqlite3")
    journal = TravelJournal()
    journal.add_user("Alex", "alex@example.com")
    journal.add_place("Saved museum", "Moscow", "Russia", "Museum")
    database.initialize(journal)
    command = [
        sys.executable, str(Path(main.__file__).resolve()), "--data-dir", str(data_dir),
    ]
    session = subprocess.run(
        command, input="2\n0\n", capture_output=True,
        text=True, encoding="utf-8", timeout=10,
    )
    assert session.returncode == 0, session.stderr
    assert "Saved museum" in session.stdout
    assert "До свидания!" in session.stdout


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
        command, input="14\nMy museum\n0\n",
        capture_output=True, text=True, encoding="utf-8", timeout=10,
    )
    assert second.returncode == 0, second.stderr
    assert "My museum" in second.stdout
    assert len(JournalDatabase(data_dir / "journal.sqlite3").load().places) == 7
