import pytest

from visited_places.places import Place, find_places, sort_places_by_name
from visited_places.service import TravelJournal
from visited_places.statistics import build_travel_statistics
from visited_places.trips import Trip
from visited_places.users import User
from visited_places.visits import Visit


def test_entities_round_trip_and_preserve_only_the_new_links(journal):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00", 5, "Great view")
    trip = Trip.from_data(journal.trips[0].to_data(), journal.places)
    restored = Visit.from_data(visit.to_data(), journal.users, journal.trips)
    assert trip.place is journal.places[0]
    assert restored.user is journal.users[0]
    assert restored.trip is journal.trips[0]
    assert restored.trip.place is journal.places[0]
    assert restored.to_data() == visit.to_data()
    assert "Red Square" in str(restored)
    assert not hasattr(trip, "user")
    assert not hasattr(trip, "user_id")
    assert not hasattr(visit, "place")
    assert not hasattr(visit, "place_id")
    assert "user_id" not in trip.to_data()
    assert "place_id" not in visit.to_data()


@pytest.mark.parametrize("email", ["alex@example.com", " ALEX@EXAMPLE.COM "])
def test_duplicate_user_email_is_rejected(journal, email):
    with pytest.raises(ValueError, match="already registered"):
        journal.add_user("Someone else", email)
    assert len(journal.users) == 2


def test_duplicate_place_uses_case_insensitive_location(journal):
    with pytest.raises(ValueError, match="already exists"):
        journal.add_place(" red SQUARE ", " MOSCOW ", "Russia", "Square")
    assert journal.add_place("Red Square", "Other city", "Russia", "Square").id == 4


@pytest.mark.parametrize("identifier", [0, -1, True, 1.5, "1"])
def test_invalid_identifiers_are_rejected(identifier):
    with pytest.raises(ValueError, match="positive integer"):
        User(identifier, "Alex", "alex@example.com")


@pytest.mark.parametrize("email", ["", "alex", "a@b", "a b@example.com"])
def test_invalid_email_is_rejected(email):
    with pytest.raises(ValueError):
        User(1, "Alex", email)


@pytest.mark.parametrize("name", ["", "   ", None])
def test_empty_place_name_is_rejected(name):
    with pytest.raises(ValueError):
        Place(1, name, "Moscow", "Russia", "Landmark")


@pytest.mark.parametrize("start,end", [
    ("2026-06-12", "2026-06-10"), ("2026-02-30", "2026-03-02"),
    ("2026-6-10", "2026-06-12"), ("10.06.2026", "2026-06-12"),
])
def test_invalid_trip_dates_are_rejected(journal, start, end):
    with pytest.raises(ValueError):
        journal.add_trip(1, "Invalid trip", start, end)
    assert len(journal.trips) == 3


@pytest.mark.parametrize("place_id", [999, 0, None])
def test_trip_requires_an_existing_place(journal, place_id):
    with pytest.raises(ValueError):
        journal.add_trip(place_id, "Trip", "2026-06-10", "2026-06-12")


@pytest.mark.parametrize("timestamp", ["2026-06-10 00:00", "2026-06-12 23:59"])
def test_visit_date_includes_both_trip_boundaries(journal, timestamp):
    assert journal.add_visit(1, 1, timestamp).trip is journal.trips[0]


@pytest.mark.parametrize("timestamp", ["2026-06-09 23:59", "2026-06-13 00:00"])
def test_visit_outside_trip_dates_is_rejected(journal, timestamp):
    with pytest.raises(ValueError, match="trip interval"):
        journal.add_visit(1, 1, timestamp)
    assert not journal.visits


def test_different_users_can_mark_the_same_shared_trip(journal):
    first = journal.add_visit(1, 1, "2026-06-10 12:00")
    second = journal.add_visit(2, 1, "2026-06-10 12:00")
    assert first.trip is second.trip
    assert second.user is journal.users[1]


@pytest.mark.parametrize("changes", [
    {"user_id": 999}, {"trip_id": 999}, {"trip_id": None},
    {"visited_at": "2026-02-30 12:00"}, {"note": None},
])
def test_invalid_visit_links_and_fields_are_rejected(journal, changes):
    arguments = {"user_id": 1, "trip_id": 1, "visited_at": "2026-06-10 12:00"}
    arguments.update(changes)
    with pytest.raises(ValueError):
        journal.add_visit(**arguments)
    assert not journal.visits


@pytest.mark.parametrize("rating", [0, 6, -1, True, 4.5, "5"])
def test_invalid_visit_ratings_are_rejected(journal, rating):
    with pytest.raises(ValueError, match="Rating"):
        journal.add_visit(1, 1, "2026-06-10 12:00", rating)


def test_repeat_visits_allowed_but_identical_marks_rejected(journal):
    journal.add_visit(1, 1, "2026-06-10 12:00")
    with pytest.raises(ValueError, match="already recorded"):
        journal.add_visit(1, 1, "2026-06-10 12:00", 5)
    journal.add_visit(1, 1, "2026-06-11 12:00", 4)
    journal.add_visit(2, 1, "2026-06-10 12:00", 5)
    assert len(journal.visits) == 3


def test_visit_update_and_remove_enforce_ownership(journal):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00", 4, "Original")
    with pytest.raises(ValueError, match="own visits"):
        journal.update_visit(2, visit.id, rating=1, note="Not mine")
    with pytest.raises(ValueError, match="own visits"):
        journal.remove_visit(2, visit.id)
    assert visit.rating == 4
    assert journal.update_visit(1, visit.id, rating=None, note=" Updated ") is visit
    assert visit.note == "Updated"
    assert visit.rating is None
    assert journal.remove_visit(1, visit.id) is visit


def test_user_update_preserves_visit_links_without_adding_a_trip_owner(journal):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00")
    user = journal.update_user(1, name=" Renamed Alex ", email=" NEW@EXAMPLE.COM ")
    assert user.name == "Renamed Alex"
    assert user.email == "new@example.com"
    assert visit.user is user
    assert "user_id" not in visit.trip.to_data()
    journal.validate()


@pytest.mark.parametrize("name, email", [
    ("Changed", "MARIA@EXAMPLE.COM"), ("Changed", "not-an-email"),
    ("", "new@example.com"),
])
def test_invalid_user_update_preserves_original_fields(journal, name, email):
    before = journal.users[0].to_data()
    with pytest.raises(ValueError):
        journal.update_user(1, name=name, email=email)
    assert journal.users[0].to_data() == before


def test_place_update_is_visible_through_trip_not_stored_on_visit(journal):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00")
    place = journal.update_place(
        1, name="New square", city="New city", country="New country", category="Park"
    )
    assert visit.trip.place is place
    assert not hasattr(visit, "place")
    journal.validate()


@pytest.mark.parametrize("changes", [
    {"name": ""}, {"city": ""}, {"country": ""}, {"category": ""},
    {"name": " hermitage ", "city": "SAINT PETERSBURG", "country": "Russia"},
])
def test_invalid_place_update_preserves_original_fields(journal, changes):
    before = journal.places[0].to_data()
    fields = {key: value for key, value in before.items() if key != "id"}
    fields.update(changes)
    with pytest.raises(ValueError):
        journal.update_place(1, **fields)
    assert journal.places[0].to_data() == before


def test_visit_update_changes_timestamp_and_trip_with_canonical_links(journal):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00")
    updated = journal.update_visit(
        1, visit.id, visited_at="2026-07-02 13:45", trip_id=3,
        rating=5, note=" Changed ",
    )
    assert updated is visit
    assert updated.trip is journal.trips[2]
    assert updated.trip.place is journal.places[1]
    assert updated.note == "Changed"
    journal.validate()


def test_omitted_trip_keeps_link_and_visit_constructor_rejects_no_trip(journal):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00")
    journal.update_visit(1, visit.id, rating=5, note="Keep trip")
    assert visit.trip is journal.trips[0]
    with pytest.raises(ValueError, match="requires a trip"):
        Visit(2, journal.users[0], None, "2026-06-10 12:00")


@pytest.mark.parametrize("changes", [
    {"trip_id": 999}, {"trip_id": 0}, {"trip_id": 2},
    {"visited_at": "not-a-date"}, {"visited_at": "2026-06-13 12:00"},
    {"rating": 6}, {"note": None},
])
def test_invalid_visit_field_update_is_atomic(journal, changes):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00", 4, "Original")
    before = visit.to_data()
    arguments = {"rating": 5, "note": "Changed"}
    arguments.update(changes)
    with pytest.raises(ValueError):
        journal.update_visit(1, visit.id, **arguments)
    assert visit.to_data() == before


def test_visit_edit_cannot_create_duplicate_mark(journal):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00", 4, "Original")
    journal.add_visit(1, 1, "2026-06-11 12:00")
    before = visit.to_data()
    with pytest.raises(ValueError, match="already recorded"):
        journal.update_visit(
            1, visit.id, visited_at="2026-06-11 12:00", rating=5, note="Changed"
        )
    assert visit.to_data() == before


def test_list_visits_filters_user_and_shared_trip_and_sorts(journal):
    first = journal.add_visit(1, 1, "2026-06-10 12:00")
    second = journal.add_visit(1, 3, "2026-07-01 12:00")
    journal.add_visit(2, 1, "2026-06-10 12:00")
    assert journal.list_visits(1) == [second, first]
    assert journal.list_visits(1, 1) == [first]
    assert journal.list_visits(1, 2) == []


def test_search_checks_location_and_category_and_sort_keeps_original(journal):
    places = journal.places
    assert find_places(places, " MOSCOW ") == [places[0]]
    assert find_places(places, "museum") == [places[1]]
    assert find_places(places, "nothing") == []
    assert sort_places_by_name(places) == [places[2], places[1], places[0]]
    assert places[0].name == "Red Square"


def test_statistics_are_personal_and_resolve_places_from_trips(journal):
    journal.add_visit(1, 1, "2026-06-10 12:00", 5)
    journal.add_visit(1, 1, "2026-06-11 12:00", 4)
    journal.add_visit(1, 3, "2026-07-01 12:00")
    journal.add_visit(2, 2, "2026-08-16 12:00", 1)
    assert build_travel_statistics(journal.visits, 1) == {
        "visits": 3, "visited_places": 2, "cities": 2, "countries": 1,
        "trips": 2, "average_rating": 4.5,
    }
    assert build_travel_statistics(journal.visits)["countries"] == 2


def test_statistics_distinguish_same_named_cities_in_different_countries(journal):
    place = journal.add_place("Other square", "Moscow", "Other country", "Square")
    trip = journal.add_trip(place.id, "Another trip", "2026-06-10", "2026-06-12")
    journal.add_visit(1, 1, "2026-06-10 12:00")
    journal.add_visit(1, trip.id, "2026-06-11 12:00")
    statistics = build_travel_statistics(journal.visits, 1)
    assert statistics["cities"] == 2
    assert statistics["average_rating"] == 0.0


def test_empty_journal_statistics():
    assert build_travel_statistics([]) == {
        "visits": 0, "visited_places": 0, "cities": 0, "countries": 0,
        "trips": 0, "average_rating": 0.0,
    }


def test_duplicate_identifiers_rejected_when_constructing_journal(journal):
    with pytest.raises(ValueError, match="Duplicate"):
        TravelJournal(users=[journal.users[0], journal.users[0]])


def test_journal_requires_canonical_trip_place_references(journal):
    other_place = Place.from_data(journal.places[0].to_data())
    trip = Trip(1, other_place, "Trip", "2026-06-10", "2026-06-12")
    with pytest.raises(ValueError, match="journal place"):
        TravelJournal(places=journal.places, trips=[trip])


def test_trip_updates_preserve_links_and_check_all_users_visits(journal):
    visit = journal.add_visit(2, 1, "2026-06-10 12:00")
    trip = journal.update_trip(
        1, name="Extended trip", place_id=2,
        start_date="2026-06-09", end_date="2026-06-13",
    )
    assert visit.trip is trip
    assert visit.trip.place is journal.places[1]
    with pytest.raises(ValueError, match="trip interval"):
        journal.update_trip(
            1, name="Invalid", place_id=3,
            start_date="2026-06-11", end_date="2026-06-13",
        )
    assert trip.name == "Extended trip"
    assert trip.place_id == 2
    assert trip.start_date == "2026-06-09"


def test_used_trip_deletion_is_restricted_without_removing_any_visits(journal):
    visit = journal.add_visit(1, 1, "2026-06-10 12:00", 5)
    with pytest.raises(ValueError, match="посещения"):
        journal.remove_trip(1)
    assert visit.trip is journal.trips[0]
    assert len(journal.trips) == 3
    journal.remove_visit(1, visit.id)
    journal.remove_trip(1)
    assert len(journal.trips) == 2
    journal.validate()
