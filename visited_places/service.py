from typing import Any

from .places import Place
from .trips import Trip
from .users import User
from .utils import get_next_id, validate_identifier
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
            Trip.from_data(trip.to_data(), self.places)
            if self._require(self.places, trip.place_id, "Place") is not trip.place:
                raise ValueError("Trip must reference a journal place")
        keys = set()
        for visit in self.visits:
            Visit.from_data(visit.to_data(), self.users, self.trips)
            if self._require(self.users, visit.user_id, "User") is not visit.user:
                raise ValueError("Visit owner must reference a journal user")
            if self._require(self.trips, visit.trip_id, "Trip") is not visit.trip:
                raise ValueError("Visit must reference a journal trip")
            key = (visit.user_id, visit.trip_id, visit.visited_at)
            if key in keys:
                raise ValueError("This visit is already recorded")
            keys.add(key)

    def add_user(self, name: str, email: str) -> User:
        user = User(get_next_id(self.users), name, email)
        if any(existing.email == user.email for existing in self.users):
            raise ValueError("Email address is already registered")
        self.users.append(user)
        return user

    def update_user(self, user_id: int, *, name: str, email: str) -> User:
        user = self._require(self.users, user_id, "User")
        replacement = User(user.id, name, email)
        if any(
            item.id != user.id and item.email == replacement.email
            for item in self.users
        ):
            raise ValueError("Email address is already registered")
        user.name = replacement.name
        user.email = replacement.email
        return user

    def add_place(self, name: str, city: str, country: str, category: str) -> Place:
        place = Place(get_next_id(self.places), name, city, country, category)
        if any(self._place_key(item) == self._place_key(place) for item in self.places):
            raise ValueError("Place already exists in this city and country")
        self.places.append(place)
        return place

    def update_place(
        self, place_id: int, *, name: str, city: str, country: str, category: str,
    ) -> Place:
        place = self._require(self.places, place_id, "Place")
        replacement = Place(place.id, name, city, country, category)
        if any(
            item.id != place.id
            and self._place_key(item) == self._place_key(replacement)
            for item in self.places
        ):
            raise ValueError("Place already exists in this city and country")
        place.name = replacement.name
        place.city = replacement.city
        place.country = replacement.country
        place.category = replacement.category
        return place

    def add_trip(
        self, place_id: int, name: str, start_date: str, end_date: str,
    ) -> Trip:
        place = self._require(self.places, place_id, "Place")
        trip = Trip(get_next_id(self.trips), place, name, start_date, end_date)
        self.trips.append(trip)
        return trip

    def add_visit(
        self,
        user_id: int,
        trip_id: int,
        visited_at: str,
        rating: int | None = None,
        note: str = "",
    ) -> Visit:
        user = self._require(self.users, user_id, "User")
        trip = self._require(self.trips, trip_id, "Trip")
        visit = Visit(
            get_next_id(self.visits), user, trip, visited_at, rating, note
        )
        if any(
            (item.user_id, item.trip_id, item.visited_at)
            == (visit.user_id, visit.trip_id, visit.visited_at)
            for item in self.visits
        ):
            raise ValueError("This visit is already recorded")
        self.visits.append(visit)
        return visit

    def update_trip(
        self, trip_id: int, *,
        name: str, start_date: str, end_date: str,
        place_id: int | None = None,
    ) -> Trip:
        """Change a trip only if all its existing visits still fit."""
        trip = self._require(self.trips, trip_id, "Trip")
        place = trip.place if place_id is None else self._require(
            self.places, place_id, "Place"
        )
        replacement = Trip(trip.id, place, name, start_date, end_date)
        for visit in self.visits:
            if visit.trip_id == trip.id:
                Visit(
                    visit.id, visit.user, replacement, visit.visited_at,
                    visit.rating, visit.note,
                )
        trip.name = replacement.name
        trip.place = replacement.place
        trip.start_date = replacement.start_date
        trip.end_date = replacement.end_date
        return trip

    def remove_trip(self, trip_id: int) -> Trip:
        """Only remove unused trips so their visits never lose their place."""
        trip = self._require(self.trips, trip_id, "Trip")
        if any(visit.trip_id == trip.id for visit in self.visits):
            raise ValueError("Сначала удалите или перенесите посещения этой поездки")
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
        visited_at: str | None = None, trip_id: int | None = None,
    ) -> Visit:
        """Validate all fields; omitted trip keeps the existing link."""
        visit = self._owned_visit(user_id, visit_id)
        trip = visit.trip if trip_id is None else self._require(
            self.trips, trip_id, "Trip"
        )
        replacement = Visit(
            visit.id, visit.user, trip,
            visit.visited_at if visited_at is None else visited_at,
            rating, note,
        )
        if any(
            item.id != visit.id
            and (item.user_id, item.trip_id, item.visited_at)
            == (replacement.user_id, replacement.trip_id, replacement.visited_at)
            for item in self.visits
        ):
            raise ValueError("This visit is already recorded")
        visit.visited_at = replacement.visited_at
        visit.trip = replacement.trip
        visit.rating = replacement.rating
        visit.note = replacement.note
        return visit

    def remove_visit(self, user_id: int, visit_id: int) -> Visit:
        visit = self._owned_visit(user_id, visit_id)
        self.visits.remove(visit)
        return visit

    def list_visits(self, user_id: int, trip_id: int | None = None) -> list[Visit]:
        """Return the owner's history, newest first, optionally for one trip."""
        self._require(self.users, user_id, "User")
        if trip_id is not None:
            self._require(self.trips, trip_id, "Trip")
        return sorted(
            (
                visit for visit in self.visits
                if visit.user_id == user_id
                and (trip_id is None or visit.trip_id == trip_id)
            ),
            key=lambda visit: visit.visited_at,
            reverse=True,
        )
