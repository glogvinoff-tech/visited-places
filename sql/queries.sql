-- 1. List of places: catalog page.
SELECT id, name, city, country, category
FROM places ORDER BY name, id LIMIT 12 OFFSET 0;

-- 2. List of trips: trips page. JOIN connects the trip to its place.
SELECT t.id, t.name, p.name AS place_name, t.start_date, t.end_date
FROM trips AS t JOIN places AS p ON p.id = t.place_id
ORDER BY t.start_date DESC, t.id DESC LIMIT 12 OFFSET 0;

-- 3. WHERE: search by city on the catalog page.
SELECT id, name, city FROM places
WHERE city LIKE '%Москва%' ORDER BY name;

-- 4. WHERE: visit date filter in the personal journal.
SELECT id, visited_at, rating, note FROM visits
WHERE user_id = 1 AND substr(visited_at, 1, 10) BETWEEN '2026-06-01' AND '2026-07-31'
ORDER BY visited_at DESC;

-- 5. JOIN: personal journal, including the trip, place and user.
SELECT v.id, v.visited_at, p.name AS place_name, t.name AS trip_name,
       u.name AS user_name, v.rating, v.note
FROM visits AS v
JOIN trips AS t ON t.id = v.trip_id
JOIN places AS p ON p.id = t.place_id
JOIN users AS u ON u.id = v.user_id
WHERE v.user_id = 1 ORDER BY v.visited_at DESC;

-- 6. JOIN: separate trip page.
SELECT t.*, p.name AS place_name, p.city, p.country
FROM trips AS t JOIN places AS p ON p.id = t.place_id WHERE t.id = 1;

-- 7. NOT EXISTS: places not yet visited by the current user.
SELECT p.* FROM places AS p
WHERE NOT EXISTS (
    SELECT 1 FROM visits AS v JOIN trips AS t ON t.id = v.trip_id
    WHERE v.user_id = 1 AND t.place_id = p.id
)
ORDER BY p.name;

-- 8. COUNT and AVG: personal statistics.
SELECT COUNT(v.id) AS visit_count, COUNT(DISTINCT t.place_id) AS place_count,
       ROUND(AVG(v.rating), 2) AS average_rating
FROM visits AS v JOIN trips AS t ON t.id = v.trip_id WHERE v.user_id = 1;

-- 9. COUNT: number of catalog records for pagination.
SELECT COUNT(*) AS total FROM places;

-- 10. GROUP BY: visits per place. HAVING is the statistics threshold.
SELECT p.id, p.name, p.city, COUNT(v.id) AS visit_count
FROM visits AS v
JOIN trips AS t ON t.id = v.trip_id
JOIN places AS p ON p.id = t.place_id
WHERE v.user_id = 1
GROUP BY p.id, p.name, p.city HAVING COUNT(v.id) >= 1
ORDER BY visit_count DESC, p.name;

-- 11. GROUP BY: visits per country on the statistics page.
SELECT p.country, COUNT(v.id) AS visit_count
FROM visits AS v
JOIN trips AS t ON t.id = v.trip_id
JOIN places AS p ON p.id = t.place_id
WHERE v.user_id = 1
GROUP BY p.country ORDER BY visit_count DESC, p.country;

-- 12. WHERE: trips containing the chosen date.
SELECT id, name, start_date, end_date FROM trips
WHERE start_date <= '2026-06-11' AND end_date >= '2026-06-11'
ORDER BY start_date, id;
