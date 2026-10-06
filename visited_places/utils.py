from datetime import date, datetime
from typing import Any


DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M"


def require_text(value: str, field: str) -> str:
    """Validate and trim a required text field."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value.strip()


def validate_identifier(value: int) -> int:
    """Require positive integer identifiers, excluding booleans."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("Identifier must be a positive integer")
    return value


def parse_date(value: str) -> date:
    """Parse a date using the journal's canonical format."""
    if not isinstance(value, str):
        raise ValueError("Date must be a string in YYYY-MM-DD format")
    try:
        parsed = datetime.strptime(value, DATE_FORMAT).date()
    except ValueError as error:
        raise ValueError(f"Invalid date: {value}; expected YYYY-MM-DD") from error
    if parsed.strftime(DATE_FORMAT) != value:
        raise ValueError(f"Invalid date format: {value}; expected YYYY-MM-DD")
    return parsed


def parse_datetime(value: str) -> datetime:
    """Parse a visit timestamp using the journal's canonical format."""
    if not isinstance(value, str):
        raise ValueError("Timestamp must be a string in YYYY-MM-DD HH:MM format")
    try:
        parsed = datetime.strptime(value, DATETIME_FORMAT)
    except ValueError as error:
        raise ValueError(f"Invalid timestamp: {value}") from error
    if parsed.strftime(DATETIME_FORMAT) != value:
        raise ValueError(f"Invalid timestamp format: {value}")
    return parsed


def format_datetime(value: datetime) -> str:
    """Format a timestamp for the console."""
    return value.strftime("%d.%m.%Y %H:%M")


def validate_rating(value: int | None) -> int | None:
    """Allow an optional integer rating from one through five."""
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5
    ):
        raise ValueError("Rating must be an integer from 1 to 5 or None")
    return value


def get_next_id(items: list[Any]) -> int:
    """Return the next identifier in an object collection."""
    return max((item.id for item in items), default=0) + 1
