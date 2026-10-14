from copy import deepcopy
from typing import Any

from .utils import parse_datetime, validate_identifier


def migrate_legacy_records(
    records: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Move visit places to trips without dropping any user, place or visit."""
    result = deepcopy(records)
    for table, items in records.items():
        identifiers = [validate_identifier(item["id"]) for item in items]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError(f"Duplicate entity identifiers in {table}")
    users = {item["id"] for item in records["users"]}
    places = {item["id"]: item for item in records["places"]}
    old_trips = {item["id"]: item for item in records["trips"]}
    trip_places: dict[int, set[int]] = {identifier: set() for identifier in old_trips}
    for visit in records["visits"]:
        user_id = validate_identifier(visit["user_id"])
        place_id = validate_identifier(visit["place_id"])
        if user_id not in users or place_id not in places:
            raise ValueError("Legacy visit references an unknown user or place")
        if visit["trip_id"] is not None:
            trip_id = validate_identifier(visit["trip_id"])
            if trip_id not in old_trips:
                raise ValueError("Legacy visit references an unknown trip")
            if old_trips[trip_id]["user_id"] != user_id:
                raise ValueError("Legacy visit and trip have different owners")
            trip_places[trip_id].add(place_id)
    next_id = max(old_trips, default=0) + 1
    mapping: dict[tuple[int, int], int] = {}
    trips = []
    for trip_id, old in sorted(old_trips.items()):
        if validate_identifier(old["user_id"]) not in users:
            raise ValueError("Legacy trip references an unknown user")
        locations = sorted(trip_places[trip_id])
        if not locations:
            raise ValueError(
                f"Cannot infer the place for legacy trip #{trip_id} without visits"
            )
        for index, place_id in enumerate(locations):
            identifier = trip_id if index == 0 else next_id
            if index:
                next_id += 1
            mapping[trip_id, place_id] = identifier
            name = old["name"]
            if index:
                name += f" - {places[place_id]['name']}"
            trips.append({
                "id": identifier, "place_id": place_id, "name": name,
                "start_date": old["start_date"], "end_date": old["end_date"],
            })
    visits = []
    for old in records["visits"]:
        visit = dict(old)
        place_id = visit.pop("place_id")
        if old["trip_id"] is None:
            date = parse_datetime(old["visited_at"]).strftime("%Y-%m-%d")
            visit["trip_id"] = next_id
            trips.append({
                "id": next_id, "place_id": place_id,
                "name": f"Посещение: {places[place_id]['name']}",
                "start_date": date, "end_date": date,
            })
            next_id += 1
        else:
            visit["trip_id"] = mapping[old["trip_id"], place_id]
        visits.append(visit)
    result["trips"] = sorted(trips, key=lambda item: item["id"])
    result["visits"] = visits
    return result
