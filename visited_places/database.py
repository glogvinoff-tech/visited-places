import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from .migration import migrate_legacy_records
from .service import TravelJournal
from .storage import journal_from_records


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "database" / "schema.sql"
SCHEMA_VERSION = 2


class JournalDatabase:
    """Persist a journal in SQLite using transactional writes."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.last_backup_path: Path | None = None

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

    def _check_version(self, connection: sqlite3.Connection) -> None:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version == 1:
            self._upgrade(connection)
            return
        if version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported database schema version: {version}")

    @staticmethod
    def _records(connection: sqlite3.Connection) -> dict[str, list[dict]]:
        return {
            table: [dict(row) for row in connection.execute(
                f"SELECT * FROM {table} ORDER BY id"
            )]
            for table in ("users", "places", "trips", "visits")
        }

    def _upgrade(self, connection: sqlite3.Connection) -> None:
        backup_path = self.path.with_name(
            f"{self.path.stem}.v1-backup-{uuid4().hex}{self.path.suffix}"
        )
        if backup_path.exists():
            raise FileExistsError(f"Backup already exists: {backup_path}")
        backup = sqlite3.connect(backup_path)
        try:
            connection.backup(backup)
        finally:
            backup.close()
        connection.execute("BEGIN IMMEDIATE")
        records = migrate_legacy_records(self._records(connection))
        journal = journal_from_records(records)
        for table in ("visits", "trips", "places", "users"):
            connection.execute(f"DROP TABLE {table}")
        # SQLite parses complete statements, including multi-line trigger bodies.
        statement = ""
        for line in SCHEMA_PATH.read_text(encoding="utf-8").splitlines(keepends=True):
            statement += line
            if sqlite3.complete_statement(statement):
                connection.execute(statement)
                statement = ""
        if statement.strip():
            raise sqlite3.OperationalError("Incomplete schema statement")
        self._write(connection, journal)
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise sqlite3.IntegrityError("Migration left invalid foreign keys")
        self.last_backup_path = backup_path

    def load(self) -> TravelJournal:
        if not self.exists:
            raise FileNotFoundError(f"Database not found: {self.path}")
        with self._connection() as connection:
            self._check_version(connection)
            records = self._records(connection)
        return journal_from_records(records)

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
