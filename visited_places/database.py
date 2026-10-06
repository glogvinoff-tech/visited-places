import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .places import Place
from .service import TravelJournal
from .trips import Trip
from .users import User
from .visits import Visit


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "database" / "schema.sql"
SCHEMA_VERSION = 1


class JournalDatabase:
    """Persist a journal in SQLite using transactional writes."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self, journal: TravelJournal) -> None:
        """Create a new database without replacing an existing file."""
        journal.validate()
        if self.path.exists():
            raise FileExistsError(f"Database already exists: {self.path}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._connection() as connection:
                connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
                self._write(connection, journal)
        except (OSError, sqlite3.Error):
            self.path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _check_version(connection: sqlite3.Connection) -> None:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported database schema version: {version}")

    def load(self) -> TravelJournal:
        if not self.exists:
            raise FileNotFoundError(f"Database not found: {self.path}")
        with self._connection() as connection:
            self._check_version(connection)
            records = {
                table: [dict(row) for row in connection.execute(
                    f"SELECT * FROM {table} ORDER BY id"
                )]
                for table in ("users", "places", "trips", "visits")
            }
        users = [User.from_data(item) for item in records["users"]]
        places = [Place.from_data(item) for item in records["places"]]
        trips = [Trip.from_data(item, users) for item in records["trips"]]
        visits = [
            Visit.from_data(item, users, places, trips) for item in records["visits"]
        ]
        return TravelJournal(users, places, trips, visits)

    def save(self, journal: TravelJournal) -> None:
        journal.validate()
        if not self.exists:
            raise FileNotFoundError(f"Database not found: {self.path}")
        with self._connection() as connection:
            self._check_version(connection)
            self._write(connection, journal)

    @staticmethod
    def _write(connection: sqlite3.Connection, journal: TravelJournal) -> None:
        # Replace the small local snapshot in one transaction, children first.
        for table in ("visits", "trips", "places", "users"):
            connection.execute(f"DELETE FROM {table}")
        for table in ("users", "places", "trips", "visits"):
            items = getattr(journal, table)
            if not items:
                continue
            records = [item.to_data() for item in items]
            columns = ", ".join(records[0])
            parameters = ", ".join(f":{key}" for key in records[0])
            connection.executemany(
                f"INSERT INTO {table} ({columns}) VALUES ({parameters})", records
            )
