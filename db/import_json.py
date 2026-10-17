import argparse
import json
from contextlib import closing
from pathlib import Path

from db.database import BASE_DIR, create_database, get_connection


def import_json(directory=None, database=None):
    directory = Path(directory or BASE_DIR / "data")
    create_database(database)
    records = {
        table: json.loads((directory / f"{table}.json").read_text("utf-8"))
        for table in ("users", "places", "trips", "visits")
    }
    with closing(get_connection(database)) as connection:
        if any(
            connection.execute(sql).fetchone()[0]
            for sql in (
                "SELECT COUNT(*) FROM users",
                "SELECT COUNT(*) FROM places",
                "SELECT COUNT(*) FROM trips",
                "SELECT COUNT(*) FROM visits",
            )
        ):
            return False
        # All four imports belong to one transaction: either all succeed or none do.
        with connection:
            connection.executemany(
                "INSERT INTO users(id, username, name, email) VALUES (?, ?, ?, ?)",
                [
                    (
                        u["id"],
                        "gleb" if u["id"] == 1 else f"journal_{u['id']}",
                        u["name"],
                        u["email"].casefold(),
                    )
                    for u in records["users"]
                ],
            )
            connection.executemany(
                "INSERT INTO places(id, name, city, country, category) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (p["id"], p["name"], p["city"], p["country"], p["category"])
                    for p in records["places"]
                ],
            )
            connection.executemany(
                "INSERT INTO trips(id, place_id, name, start_date, end_date) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (t["id"], t["place_id"], t["name"], t["start_date"], t["end_date"])
                    for t in records["trips"]
                ],
            )
            connection.executemany(
                "INSERT INTO visits(id, user_id, trip_id, visited_at, rating, note) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        v["id"],
                        v["user_id"],
                        v["trip_id"],
                        v["visited_at"],
                        v.get("rating"),
                        v.get("note", ""),
                    )
                    for v in records["visits"]
                ],
            )
            connection.commit()
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import the four JSON files into SQLite"
    )
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--database", type=Path)
    arguments = parser.parse_args()
    imported = import_json(arguments.directory, arguments.database)
    print("JSON импортирован." if imported else "База уже заполнена; импорт пропущен.")
