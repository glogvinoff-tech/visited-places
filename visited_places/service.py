from typing import Any

from .places import Place
from .trips import Trip
from .users import User
from .utils import get_next_id, validate_identifier, validate_rating
from .visits import Visit


class TravelJournal:
    """Coordinate the four entities and enforce links and ownership."""

    def __init__(
        self,
        users: list[User] | None = None,
        places: list[Place] | None = None,
        trips: list[Trip] | None = None,
        visits: list[Visit] | None = None,
    ) -> None:
        self.users = list(users or [])
        self.places = list(places or [])
        self.trips = list(trips or [])
        self.visits = list(visits or [])
        self.validate()

    @staticmethod
    def _require(items: list[Any], identifier: int, entity: str) -> Any:
        validate_identifier(identifier)
        item = next((item for item in items if item.id == identifier), None)
        if item is None:
            raise ValueError(f"{entity} not found: {identifier}")
        return item

    @staticmethod
    def _place_key(place: Place) -> tuple[str, str, str]:
        return tuple(value.casefold() for value in (
            place.name, place.city, place.country
        ))

    def validate(self) -> None:
        """Check uniqueness and canonical object links after loading."""
        for items in (self.users, self.places, self.trips, self.visits):
            if len({item.id for item in items}) != len(items):
                raise ValueError("Duplicate entity identifiers")
        for user in self.users:
            User.from_data(user.to_data())
        for place in self.places:
            Place.from_data(place.to_data())
        if len({user.email for user in self.users}) != len(self.users):
            raise ValueError("Email address is already registered")
        if len({self._place_key(place) for place in self.places}) != len(self.places):
            raise ValueError("Place already exists in this city and country")
        for trip in self.trips:
            Trip.from_data(trip.to_data(), self.users)
            if self._require(self.users, trip.user_id, "User") is not trip.user:
                raise ValueError("Trip owner must reference a journal user")
        keys = set()
        for visit in self.visits:
            Visit.from_data(visit.to_data(), self.users, self.places, self.trips)
            if self._require(self.users, visit.user_id, "User") is not visit.user:
                raise ValueError("Visit owner must reference a journal user")
            if self._require(self.places, visit.place_id, "Place") is not visit.place:
                raise ValueError("Visit must reference a journal place")
            if visit.trip is not None:
                if self._require(self.trips, visit.trip_id, "Trip") is not visit.trip:
                    raise ValueError("Visit must reference a journal trip")
            key = (visit.user_id, visit.place_id, visit.visited_at)
            if key in keys:
                raise ValueError("This visit is already recorded")
            keys.add(key)

    def add_user(self, name: str, email: str) -> User:
        user = User(get_next_id(self.users), name, email)
        if any(existing.email == user.email for existing in self.users):
            raise ValueError("Email address is already registered")
        self.users.append(user)
        return user

    def add_place(self, name: str, city: str, country: str, category: str) -> Place:
        place = Place(get_next_id(self.places), name, city, country, category)
        if any(self._place_key(item) == self._place_key(place) for item in self.places):
            raise ValueError("Place already exists in this city and country")
        self.places.append(place)
        return place

    def add_trip(
        self, user_id: int, name: str, start_date: str, end_date: str,
    ) -> Trip:
        user = self._require(self.users, user_id, "User")
        trip = Trip(get_next_id(self.trips), user, name, start_date, end_date)
        self.trips.append(trip)
        return trip

    def add_visit(
        self,
        user_id: int,
        place_id: int,
        visited_at: str,
        rating: int | None = None,
        note: str = "",
        trip_id: int | None = None,
    ) -> Visit:
        user = self._require(self.users, user_id, "User")
        place = self._require(self.places, place_id, "Place")
        trip = None
        if trip_id is not None:
            trip = self._require(self.trips, trip_id, "Trip")
        visit = Visit(
            get_next_id(self.visits), user, place, visited_at, rating, note, trip
        )
        if any(
            (item.user_id, item.place_id, item.visited_at)
            == (visit.user_id, visit.place_id, visit.visited_at)
            for item in self.visits
        ):
            raise ValueError("This visit is already recorded")
        self.visits.append(visit)
        return visit

    def _owned_trip(self, user_id: int, trip_id: int) -> Trip:
        self._require(self.users, user_id, "User")
        trip = self._require(self.trips, trip_id, "Trip")
        if trip.user_id != user_id:
            raise ValueError("A user can only change their own trips")
        return trip

    def update_trip(
        self, user_id: int, trip_id: int, *,
        name: str, start_date: str, end_date: str,
    ) -> Trip:
        """Change a trip only if all its existing visits still fit."""
        trip = self._owned_trip(user_id, trip_id)
        replacement = Trip(trip.id, trip.user, name, start_date, end_date)
        for visit in self.visits:
            if visit.trip_id == trip.id:
                Visit(
                    visit.id, visit.user, visit.place, visit.visited_at,
                    visit.rating, visit.note, replacement,
                )
        trip.name = replacement.name
        trip.start_date = replacement.start_date
        trip.end_date = replacement.end_date
        return trip

    def remove_trip(self, user_id: int, trip_id: int) -> Trip:
        """Remove a trip while keeping its marks as standalone visits."""
        trip = self._owned_trip(user_id, trip_id)
        for visit in self.visits:
            if visit.trip_id == trip.id:
                visit.trip = None
        self.trips.remove(trip)
        return trip

    def _owned_visit(self, user_id: int, visit_id: int) -> Visit:
        self._require(self.users, user_id, "User")
        visit = self._require(self.visits, visit_id, "Visit")
        if visit.user_id != user_id:
            raise ValueError("A user can only change their own visits")
        return visit

    def update_visit(
        self, user_id: int, visit_id: int, *, rating: int | None, note: str,
    ) -> Visit:
        """Replace editable fields, validating both before making changes."""
        visit = self._owned_visit(user_id, visit_id)
        rating = validate_rating(rating)
        if not isinstance(note, str):
            raise ValueError("Note must be a string")
        visit.rating = rating
        visit.note = note.strip()
        return visit

    def remove_visit(self, user_id: int, visit_id: int) -> Visit:
        visit = self._owned_visit(user_id, visit_id)
        self.visits.remove(visit)
        return visit

    def list_visits(self, user_id: int, trip_id: int | None = None) -> list[Visit]:
        """Return the owner's history, newest first, optionally for one trip."""
        self._require(self.users, user_id, "User")
        if trip_id is not None:
            trip = self._require(self.trips, trip_id, "Trip")
            if trip.user_id != user_id:
                raise ValueError("A user can only view their own trips")
        return sorted(
            (
                visit for visit in self.visits
                if visit.user_id == user_id
                and (trip_id is None or visit.trip_id == trip_id)
            ),
            key=lambda visit: visit.visited_at,
            reverse=True,
        )
