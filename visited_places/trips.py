from typing import Any

from .places import Place
from .utils import parse_date, require_text, validate_identifier


class Trip:
    """A shared trip to one place during a named date interval."""

    def __init__(
        self,
        trip_id: int,
        place: Place,
        name: str,
        start_date: str,
        end_date: str,
    ) -> None:
        self.id = validate_identifier(trip_id)
        if not isinstance(place, Place):
            raise ValueError("Trip requires a place")
        self.place = place
        self.name = require_text(name, "Trip name")
        if parse_date(start_date) > parse_date(end_date):
            raise ValueError("Trip start date must not follow its end date")
        self.start_date = start_date
        self.end_date = end_date

    @property
    def place_id(self) -> int:
        return self.place.id

    @classmethod
    def from_data(cls, data: dict[str, Any], places: list[Place]) -> "Trip":
        place_id = validate_identifier(data["place_id"])
        place = next((place for place in places if place.id == place_id), None)
        if place is None:
            raise ValueError(f"Trip place not found: {place_id}")
        return cls(
            data["id"], place, data["name"], data["start_date"], data["end_date"]
        )

    def to_data(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "place_id": self.place_id,
            "name": self.name,
            "start_date": self.start_date,
            "end_date": self.end_date,
        }

    def __str__(self) -> str:
        return f"{self.name}: {self.place} ({self.start_date} - {self.end_date})"
