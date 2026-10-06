from pathlib import Path

import pytest

from visited_places.storage import (
    load_journal,
    load_json,
    load_places,
    load_trips,
    load_users,
    load_visits,
    save_journal,
    save_json,
)


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_save_and_load_json_preserves_text(tmp_path):
    path = tmp_path / "nested" / "records.json"
    records = [{"id": 1, "name": "Museum", "note": "A travel memory"}]
    save_json(path, records)
    assert load_json(path) == records


def test_invalid_json_raises_useful_error(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{invalid", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid UTF-8 JSON"):
        load_json(path)


def test_missing_file_raises_useful_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="Data file not found"):
        load_json(tmp_path / "missing.json")


@pytest.mark.parametrize("data", [{}, [1], ["invalid"], None])
def test_invalid_record_collections_are_rejected(tmp_path, data):
    path = tmp_path / "users.json"
    save_json(path, data)
    with pytest.raises(ValueError, match="array of objects"):
        load_users(path)


@pytest.mark.parametrize("loader", [load_users, load_places])
def test_missing_entity_fields_are_reported(tmp_path, loader):
    path = tmp_path / "records.json"
    save_json(path, [{"id": 1}])
    with pytest.raises(ValueError, match="Missing"):
        loader(path)


def test_save_and_load_journal_preserves_all_links_and_values(tmp_path, journal):
    journal.add_visit(1, 1, "2026-06-10 12:00", 5, "Great view", 1)
    journal.add_visit(2, 3, "2026-08-16 12:00")
    save_journal(tmp_path, journal)
    restored = load_journal(tmp_path)

    for attribute in ("users", "places", "trips", "visits"):
        assert [item.to_data() for item in getattr(restored, attribute)] == [
            item.to_data() for item in getattr(journal, attribute)
        ]
    assert restored.trips[0].user is restored.users[0]
    assert restored.visits[0].user is restored.users[0]
    assert restored.visits[0].place is restored.places[0]
    assert restored.visits[0].trip is restored.trips[0]
    assert restored.visits[1].trip is None
    assert restored.visits[1].rating is None


def test_demo_data_loads_as_a_consistent_journal():
    journal = load_journal(DATA_DIR)
    assert (len(journal.users), len(journal.places)) == (3, 6)
    assert (len(journal.trips), len(journal.visits)) == (3, 6)
    assert len(journal.list_visits(1)) == 4


def test_orphan_trip_is_rejected(tmp_path):
    path = tmp_path / "trips.json"
    save_json(path, [{
        "id": 1, "user_id": 999, "name": "Trip",
        "start_date": "2026-06-10", "end_date": "2026-06-12",
    }])
    with pytest.raises(ValueError, match="owner not found"):
        load_trips(path, [])


@pytest.mark.parametrize("changes", [
    {"user_id": 999}, {"place_id": 999}, {"trip_id": 999},
    {"trip_id": 2}, {"visited_at": "2026-06-13 12:00"},
])
def test_invalid_visit_references_rejected_on_load(tmp_path, journal, changes):
    path = tmp_path / "visits.json"
    visit = journal.add_visit(1, 1, "2026-06-10 12:00", trip_id=1)
    data = visit.to_data()
    data.update(changes)
    save_json(path, [data])
    with pytest.raises(ValueError):
        load_visits(path, journal.users, journal.places, journal.trips)


def test_duplicate_ids_in_files_are_rejected(tmp_path, journal):
    save_journal(tmp_path, journal)
    users = load_json(tmp_path / "users.json")
    users.append(users[0])
    save_json(tmp_path / "users.json", users)
    with pytest.raises(ValueError, match="Duplicate"):
        load_journal(tmp_path)


def test_duplicate_visit_records_in_files_are_rejected(tmp_path, journal):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00")
    save_journal(tmp_path, journal)
    duplicate = visit.to_data()
    duplicate["id"] = 99
    save_json(tmp_path / "visits.json", [visit.to_data(), duplicate])
    with pytest.raises(ValueError, match="already recorded"):
        load_journal(tmp_path)


@pytest.mark.parametrize("changes", [
    {"rating": 10}, {"visited_at": "2026-06-13 12:00"}, {"user_id": 2},
])
def test_invalid_object_state_is_rejected_before_saving(tmp_path, journal, changes):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00", trip_id=1)
    if "user_id" in changes:
        visit.user = journal.users[1]
    else:
        for name, value in changes.items():
            setattr(visit, name, value)
    with pytest.raises(ValueError):
        save_journal(tmp_path, journal)
    assert not list(tmp_path.iterdir())
