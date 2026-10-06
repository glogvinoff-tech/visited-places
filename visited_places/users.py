import re
from typing import Any

from .utils import require_text, validate_identifier


class User:
    """Owner of trips and visit records."""

    def __init__(self, user_id: int, name: str, email: str) -> None:
        self.id = validate_identifier(user_id)
        self.name = require_text(name, "User name")
        self.email = require_text(email, "Email").casefold()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", self.email):
            raise ValueError("Invalid email address")

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "User":
        return cls(data["id"], data["name"], data["email"])

    def to_data(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "email": self.email}

    def __str__(self) -> str:
        return f"{self.name} ({self.email})"
