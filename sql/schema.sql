PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password TEXT NOT NULL DEFAULT '',
    is_staff INTEGER NOT NULL DEFAULT 0 CHECK (is_staff IN (0, 1)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS places (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE,
    city TEXT NOT NULL COLLATE NOCASE,
    country TEXT NOT NULL COLLATE NOCASE,
    category TEXT NOT NULL,
    image_url TEXT NOT NULL DEFAULT '',
    UNIQUE (name, city, country)
);

CREATE TABLE IF NOT EXISTS trips (
    id INTEGER PRIMARY KEY,
    place_id INTEGER NOT NULL REFERENCES places(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    CHECK (start_date <= end_date)
);

CREATE TABLE IF NOT EXISTS visits (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE RESTRICT,
    visited_at TEXT NOT NULL,
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    note TEXT NOT NULL DEFAULT '',
    UNIQUE (user_id, trip_id, visited_at)
);

CREATE INDEX IF NOT EXISTS trip_place ON trips(place_id);
CREATE INDEX IF NOT EXISTS visit_trip ON visits(trip_id);
CREATE INDEX IF NOT EXISTS visit_user_date ON visits(user_id, visited_at);
