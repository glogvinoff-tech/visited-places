import argparse
import sqlite3
import sys
from pathlib import Path

from visited_places.cli import ConsoleApplication
from visited_places.database import JournalDatabase
from visited_places.service import TravelJournal
from visited_places.storage import load_journal


DATA_DIR = Path(__file__).resolve().parent / "data"


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Система учета посещенных мест")
    parser.add_argument(
        "--data-dir", type=Path, default=DATA_DIR,
        help="Каталог базы данных и начальных JSON-файлов",
    )
    arguments = parser.parse_args(argv)
    data_dir = arguments.data_dir.resolve()
    database = JournalDatabase(data_dir / "journal.sqlite3")

    try:
        if database.exists:
            journal = database.load()
        else:
            seed_files = [
                data_dir / f"{table}.json"
                for table in ("users", "places", "trips", "visits")
            ]
            journal = load_journal(data_dir) if any(
                path.exists() for path in seed_files
            ) else TravelJournal()
            database.initialize(journal)
        return ConsoleApplication(journal, database).run()
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Ошибка данных: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
