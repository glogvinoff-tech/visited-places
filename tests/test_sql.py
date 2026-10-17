import json
import sqlite3
from pathlib import Path

import pytest

from db.database import create_database, get_connection
from db.import_json import import_json

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sql_connection(tmp_path):
    path = tmp_path / "journal.sqlite3"
    import_json(database=path)
    connection = get_connection(path)
    yield connection
    connection.close()


def test_tables_and_import(sql_connection):
    for sql, count in [
        ("SELECT COUNT(*) FROM users", 3),
        ("SELECT COUNT(*) FROM places", 6),
        ("SELECT COUNT(*) FROM trips", 6),
        ("SELECT COUNT(*) FROM visits", 6),
    ]:
        assert sql_connection.execute(sql).fetchone()[0] == count
    assert sql_connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert sql_connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_named_rows_and_join(sql_connection):
    row = sql_connection.execute(
        "SELECT t.name, p.city FROM trips t JOIN places p ON t.place_id = p.id "
        "WHERE t.id = ?",
        (1,),
    ).fetchone()
    assert isinstance(row, sqlite3.Row)
    assert row["city"] == "Москва"


def test_constraints(sql_connection):
    with pytest.raises(sqlite3.IntegrityError):
        sql_connection.execute("DELETE FROM places WHERE id = 1")
    with pytest.raises(sqlite3.IntegrityError):
        sql_connection.execute("UPDATE visits SET rating = 6 WHERE id = 1")
    with pytest.raises(sqlite3.IntegrityError):
        sql_connection.execute("UPDATE trips SET end_date = '2020-01-01' WHERE id = 1")


def test_import_is_non_destructive(tmp_path):
    path = tmp_path / "test.sqlite3"
    assert import_json(database=path)
    with get_connection(path) as connection:
        connection.execute("UPDATE places SET name = 'Keep me' WHERE id = 1")
    assert not import_json(database=path)
    connection = get_connection(path)
    try:
        assert (
            connection.execute("SELECT name FROM places WHERE id = 1").fetchone()[0]
            == "Keep me"
        )
    finally:
        connection.close()


def test_import_rolls_back(tmp_path):
    source = tmp_path / "json"
    source.mkdir()
    for name in ("users", "places", "trips", "visits"):
        rows = json.loads((ROOT / "data" / f"{name}.json").read_text("utf-8"))
        if name == "visits":
            rows[0]["trip_id"] = 99999
        (source / f"{name}.json").write_text(json.dumps(rows), encoding="utf-8")
    path = tmp_path / "test.sqlite3"
    with pytest.raises(sqlite3.IntegrityError):
        import_json(source, path)
    connection = get_connection(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    finally:
        connection.close()


def test_all_example_queries(sql_connection):
    statements, current = [], ""
    for line in (ROOT / "sql" / "queries.sql").read_text("utf-8").splitlines():
        current += line + "\n"
        if sqlite3.complete_statement(current):
            statements.append(current)
            current = ""
    assert len(statements) >= 10
    assert sum("GROUP BY" in q for q in statements) >= 2
    assert sum("JOIN" in q for q in statements) >= 2
    assert sum("COUNT(" in q for q in statements) >= 2
    assert sum("WHERE" in q for q in statements) >= 2
    for sql in statements:
        sql_connection.execute(sql).fetchall()


def test_create_database_without_import(tmp_path):
    path = tmp_path / "new.sqlite3"
    create_database(path)
    connection = get_connection(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM places").fetchone()[0] == 0
    finally:
        connection.close()
