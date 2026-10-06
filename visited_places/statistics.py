from .visits import Visit


def build_travel_statistics(
    visits: list[Visit], user_id: int | None = None,
) -> dict[str, float | int]:
    """Count visited locations, rather than unvisited catalog entries."""
    selected = [
        visit for visit in visits if user_id is None or visit.user_id == user_id
    ]
    ratings = [visit.rating for visit in selected if visit.rating is not None]
    return {
        "visits": len(selected),
        "visited_places": len({visit.place_id for visit in selected}),
        "cities": len({
            (visit.place.city.casefold(), visit.place.country.casefold())
            for visit in selected
        }),
        "countries": len({visit.place.country.casefold() for visit in selected}),
        "trips": len({
            visit.trip_id for visit in selected if visit.trip_id is not None
        }),
        "average_rating": sum(ratings) / len(ratings) if ratings else 0.0,
    }
