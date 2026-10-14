from typing import Any

from .trips import Trip
from .users import User
from .utils import parse_date, parse_datetime, validate_identifier, validate_rating


class Visit:
    """A user's timestamped mark for a trip; its place belongs to the trip."""

    def __init__(
        self,
        visit_id: int,
        user: User,
        trip: Trip,
        visited_at: str,
        rating: int | None = None,
        note: str = "",
    ) -> None:
        self.id = validate_identifier(visit_id)
        visit_date = parse_datetime(visited_at).date()
        if not isinstance(user, User):
            raise ValueError("Visit requires a user")
        if not isinstance(trip, Trip):
            raise ValueError("Visit requires a trip")
        start_date = parse_date(trip.start_date)
        end_date = parse_date(trip.end_date)
        if not start_date <= visit_date <= end_date:
            raise ValueError("Visit date must fall within the trip interval")
        if not isinstance(note, str):
            raise ValueError("Note must be a string")
        self.user = user
        self.trip = trip
        self.visited_at = visited_at
        self.rating = validate_rating(rating)
        self.note = note.strip()

    @property
    def user_id(self) -> int:
        return self.user.id

    @property
    def trip_id(self) -> int:
        return self.trip.id

    @classmethod
    def from_data(
        cls,
        data: dict[str, Any],
        users: list[User],
        trips: list[Trip],
    ) -> "Visit":
        user_id = validate_identifier(data["user_id"])
        trip_id = validate_identifier(data["trip_id"])
        user = next((user for user in users if user.id == user_id), None)
        trip = next((trip for trip in trips if trip.id == trip_id), None)
        if user is None or trip is None:
            raise ValueError("Visit references an unknown user or trip")
        return cls(
            data["id"], user, trip, data["visited_at"],
            data.get("rating"), data.get("note", ""),
        )

    def to_data(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "trip_id": self.trip_id,
            "visited_at": self.visited_at,
            "rating": self.rating,
            "note": self.note,
        }

    def __str__(self) -> str:
        return f"{self.trip.place.name}: {self.visited_at} ({self.user.name})"
