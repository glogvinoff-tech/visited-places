PRAGMA foreign_keys = ON;

CREATE TABLE users (
    id INTEGER PRIMARY KEY CHECK (id > 0),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    email TEXT NOT NULL COLLATE NOCASE UNIQUE
        CHECK (length(trim(email)) > 0)
);

CREATE TABLE places (
    id INTEGER PRIMARY KEY CHECK (id > 0),
    name TEXT NOT NULL COLLATE NOCASE CHECK (length(trim(name)) > 0),
    city TEXT NOT NULL COLLATE NOCASE CHECK (length(trim(city)) > 0),
    country TEXT NOT NULL COLLATE NOCASE CHECK (length(trim(country)) > 0),
    category TEXT NOT NULL CHECK (length(trim(category)) > 0),
    UNIQUE (name, city, country)
);

CREATE TABLE trips (
    id INTEGER PRIMARY KEY CHECK (id > 0),
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    start_date TEXT NOT NULL CHECK (
        length(start_date) = 10
        AND date(start_date, '+0 days') IS NOT NULL
        AND date(start_date, '+0 days') = start_date
    ),
    end_date TEXT NOT NULL CHECK (
        length(end_date) = 10
        AND date(end_date, '+0 days') IS NOT NULL
        AND date(end_date, '+0 days') = end_date
    ),
    CHECK (start_date <= end_date)
);

CREATE TABLE visits (
    id INTEGER PRIMARY KEY CHECK (id > 0),
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    place_id INTEGER NOT NULL REFERENCES places(id) ON DELETE RESTRICT,
    trip_id INTEGER REFERENCES trips(id) ON DELETE SET NULL,
    visited_at TEXT NOT NULL CHECK (
        length(visited_at) = 16
        AND datetime(visited_at, '+0 days') IS NOT NULL
        AND strftime('%Y-%m-%d %H:%M', visited_at, '+0 days') = visited_at
    ),
    rating INTEGER CHECK (
        rating IS NULL OR (typeof(rating) = 'integer' AND rating BETWEEN 1 AND 5)
    ),
    note TEXT NOT NULL DEFAULT '',
    UNIQUE (user_id, place_id, visited_at)
);

CREATE INDEX idx_places_city_country ON places(city, country);
CREATE INDEX idx_trips_user_dates ON trips(user_id, start_date, end_date);
CREATE INDEX idx_visits_user_date ON visits(user_id, visited_at DESC);
CREATE INDEX idx_visits_trip ON visits(trip_id);
CREATE INDEX idx_visits_place ON visits(place_id);

-- Keep cross-table ownership and visit dates consistent on both write paths.
CREATE TRIGGER check_visit_trip_insert
BEFORE INSERT ON visits
WHEN NEW.trip_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Visit must belong to the trip owner and date interval')
    WHERE NOT EXISTS (
        SELECT 1 FROM trips
        WHERE id = NEW.trip_id AND user_id = NEW.user_id
            AND substr(NEW.visited_at, 1, 10) BETWEEN start_date AND end_date
    );
END;

CREATE TRIGGER check_visit_trip_update
BEFORE UPDATE OF user_id, trip_id, visited_at ON visits
WHEN NEW.trip_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Visit must belong to the trip owner and date interval')
    WHERE NOT EXISTS (
        SELECT 1 FROM trips
        WHERE id = NEW.trip_id AND user_id = NEW.user_id
            AND substr(NEW.visited_at, 1, 10) BETWEEN start_date AND end_date
    );
END;

CREATE TRIGGER check_trip_visits_update
BEFORE UPDATE OF user_id, start_date, end_date ON trips
BEGIN
    SELECT RAISE(ABORT, 'Trip update would invalidate existing visits')
    WHERE EXISTS (
        SELECT 1 FROM visits
        WHERE trip_id = OLD.id AND (
            user_id != NEW.user_id
            OR substr(visited_at, 1, 10) NOT BETWEEN NEW.start_date AND NEW.end_date
        )
    );
END;

PRAGMA user_version = 1;
