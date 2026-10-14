import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from .places import Place
from .migration import migrate_legacy_records
from .service import TravelJournal
from .trips import Trip
from .users import User
from .visits import Visit


def load_json(path: str | Path) -> Any:
    """Load UTF-8 JSON with useful file error messages."""
    data_path = Path(path)
    try:
        with data_path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError as error:
        raise FileNotFoundError(f"Data file not found: {data_path}") from error
    except (JSONDecodeError, UnicodeError) as error:
        raise ValueError(f"Invalid UTF-8 JSON file: {data_path}") from error


def save_json(path: str | Path, data: Any) -> None:
    """Save JSON without escaping names and notes."""
    data_path = Path(path)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    with data_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _load_records(path: str | Path) -> list[dict[str, Any]]:
    data = load_json(path)
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise ValueError(f"Expected a JSON array of objects: {path}")
    return data


def load_users(path: str | Path) -> list[User]:
    try:
        return [User.from_data(item) for item in _load_records(path)]
    except KeyError as error:
        raise ValueError(f"Missing user field in {path}: {error}") from error


def save_users(path: str | Path, users: list[User]) -> None:
    save_json(path, [user.to_data() for user in users])


def load_places(path: str | Path) -> list[Place]:
    try:
        return [Place.from_data(item) for item in _load_records(path)]
    except KeyError as error:
        raise ValueError(f"Missing place field in {path}: {error}") from error


def save_places(path: str | Path, places: list[Place]) -> None:
    save_json(path, [place.to_data() for place in places])


def load_trips(path: str | Path, places: list[Place]) -> list[Trip]:
    try:
        return [Trip.from_data(item, places) for item in _load_records(path)]
    except KeyError as error:
        raise ValueError(f"Missing trip field in {path}: {error}") from error


def save_trips(path: str | Path, trips: list[Trip]) -> None:
    save_json(path, [trip.to_data() for trip in trips])


def load_visits(
    path: str | Path, users: list[User], trips: list[Trip],
) -> list[Visit]:
    try:
        return [
            Visit.from_data(item, users, trips) for item in _load_records(path)
        ]
    except KeyError as error:
        raise ValueError(f"Missing visit field in {path}: {error}") from error


def save_visits(path: str | Path, visits: list[Visit]) -> None:
    save_json(path, [visit.to_data() for visit in visits])


def load_journal(directory: str | Path) -> TravelJournal:
    """Load parents first, then resolve trip and visit references."""
    directory = Path(directory)
    records = {
        table: _load_records(directory / f"{table}.json")
        for table in ("users", "places", "trips", "visits")
    }
    if any("user_id" in item for item in records["trips"]) or any(
        "place_id" in item for item in records["visits"]
    ):
        try:
            records = migrate_legacy_records(records)
        except KeyError as error:
            raise ValueError(f"Missing legacy journal field: {error}") from error
    return journal_from_records(records)


def journal_from_records(records: dict[str, list[dict[str, Any]]]) -> TravelJournal:
    try:
        users = [User.from_data(item) for item in records["users"]]
        places = [Place.from_data(item) for item in records["places"]]
        trips = [Trip.from_data(item, places) for item in records["trips"]]
        visits = [Visit.from_data(item, users, trips) for item in records["visits"]]
    except KeyError as error:
        raise ValueError(f"Missing journal field: {error}") from error
    return TravelJournal(users, places, trips, visits)


def save_journal(directory: str | Path, journal: TravelJournal) -> None:
    """Validate and save the four linked entity collections."""
    journal.validate()
    directory = Path(directory)
    save_users(directory / "users.json", journal.users)
    save_places(directory / "places.json", journal.places)
    save_trips(directory / "trips.json", journal.trips)
    save_visits(directory / "visits.json", journal.visits)
