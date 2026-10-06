from typing import Any

from .places import Place
from .trips import Trip
from .users import User
from .utils import parse_date, parse_datetime, validate_identifier, validate_rating


class Visit:
    """A user's timestamped mark at a place, optionally part of a trip."""

    def __init__(
        self,
        visit_id: int,
        user: User,
        place: Place,
        visited_at: str,
        rating: int | None = None,
        note: str = "",
        trip: Trip | None = None,
    ) -> None:
        self.id = validate_identifier(visit_id)
        visit_date = parse_datetime(visited_at).date()
        if trip is not None:
            if trip.user_id != user.id:
                raise ValueError("Visit and trip must belong to the same user")
            start_date = parse_date(trip.start_date)
            end_date = parse_date(trip.end_date)
            if not start_date <= visit_date <= end_date:
                raise ValueError("Visit date must fall within the trip interval")
        if not isinstance(note, str):
            raise ValueError("Note must be a string")
        self.user = user
        self.place = place
        self.trip = trip
        self.visited_at = visited_at
        self.rating = validate_rating(rating)
        self.note = note.strip()

    @property
    def user_id(self) -> int:
        return self.user.id

    @property
    def place_id(self) -> int:
        return self.place.id

    @property
    def trip_id(self) -> int | None:
        return self.trip.id if self.trip is not None else None

    @classmethod
    def from_data(
        cls,
        data: dict[str, Any],
        users: list[User],
        places: list[Place],
        trips: list[Trip],
    ) -> "Visit":
        user_id = validate_identifier(data["user_id"])
        place_id = validate_identifier(data["place_id"])
        trip_id = data.get("trip_id")
        user = next((user for user in users if user.id == user_id), None)
        place = next((place for place in places if place.id == place_id), None)
        if user is None or place is None:
            raise ValueError("Visit references an unknown user or place")
        trip = None
        if trip_id is not None:
            validate_identifier(trip_id)
            trip = next((trip for trip in trips if trip.id == trip_id), None)
            if trip is None:
                raise ValueError(f"Visit references an unknown trip: {trip_id}")
        return cls(
            data["id"], user, place, data["visited_at"],
            data.get("rating"), data.get("note", ""), trip,
        )

    def to_data(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "place_id": self.place_id,
            "trip_id": self.trip_id,
            "visited_at": self.visited_at,
            "rating": self.rating,
            "note": self.note,
        }

    def __str__(self) -> str:
        return f"{self.place.name}: {self.visited_at} ({self.user.name})"
