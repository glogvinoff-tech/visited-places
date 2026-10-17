import os
import sqlite3
from contextlib import closing
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "visited_places.sqlite3"


def get_connection(path=None):
    path = Path(path or os.environ.get("VISITED_PLACES_DB", DB_PATH))
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    # SQLite's built-in lower() does not change the case of Russian letters.
    connection.create_function("casefold", 1, lambda value: (value or "").casefold())
    return connection


def fetch_all(sql, parameters=()):
    with closing(get_connection()) as connection:
        return connection.execute(sql, parameters).fetchall()


def fetch_one(sql, parameters=()):
    with closing(get_connection()) as connection:
        return connection.execute(sql, parameters).fetchone()


def execute(sql, parameters=()):
    with closing(get_connection()) as connection:
        cursor = connection.execute(sql, parameters)
        connection.commit()
        return cursor.lastrowid


def create_database(path=None):
    path = Path(path or os.environ.get("VISITED_PLACES_DB", DB_PATH))
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(get_connection(path)) as connection:
        connection.executescript((BASE_DIR / "sql" / "schema.sql").read_text("utf-8"))
