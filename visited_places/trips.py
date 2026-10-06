from typing import Any

from .users import User
from .utils import parse_date, require_text, validate_identifier


class Trip:
    """A named date interval belonging to one user."""

    def __init__(
        self,
        trip_id: int,
        user: User,
        name: str,
        start_date: str,
        end_date: str,
    ) -> None:
        self.id = validate_identifier(trip_id)
        self.user = user
        self.name = require_text(name, "Trip name")
        if parse_date(start_date) > parse_date(end_date):
            raise ValueError("Trip start date must not follow its end date")
        self.start_date = start_date
        self.end_date = end_date

    @property
    def user_id(self) -> int:
        return self.user.id

    @classmethod
    def from_data(cls, data: dict[str, Any], users: list[User]) -> "Trip":
        user_id = validate_identifier(data["user_id"])
        user = next((user for user in users if user.id == user_id), None)
        if user is None:
            raise ValueError(f"Trip owner not found: {user_id}")
        return cls(
            data["id"], user, data["name"], data["start_date"], data["end_date"]
        )

    def to_data(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "start_date": self.start_date,
            "end_date": self.end_date,
        }

    def __str__(self) -> str:
        return f"{self.name} ({self.start_date} - {self.end_date})"
