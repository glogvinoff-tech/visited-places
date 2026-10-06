from typing import Any

from .utils import require_text, validate_identifier


class Place:
    """A location in the shared catalog; a visit records who went there."""

    def __init__(
        self,
        place_id: int,
        name: str,
        city: str,
        country: str,
        category: str,
    ) -> None:
        self.id = validate_identifier(place_id)
        self.name = require_text(name, "Place name")
        self.city = require_text(city, "City")
        self.country = require_text(country, "Country")
        self.category = require_text(category, "Category")

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "Place":
        return cls(
            data["id"], data["name"], data["city"], data["country"], data["category"]
        )

    def to_data(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "city": self.city,
            "country": self.country,
            "category": self.category,
        }

    def __str__(self) -> str:
        return f"{self.name}, {self.city}, {self.country}"


def find_places(places: list[Place], query: str) -> list[Place]:
    """Search names, cities, countries and categories without case sensitivity."""
    query = query.strip().casefold()
    return [
        place
        for place in places
        if any(
            query in value.casefold()
            for value in (place.name, place.city, place.country, place.category)
        )
    ]


def sort_places_by_name(places: list[Place]) -> list[Place]:
    """Return a sorted copy of the catalog."""
    return sorted(places, key=lambda place: place.name.casefold())
