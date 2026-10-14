import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from visited_places.migration import migrate_legacy_records
from visited_places.models import Place, Trip, User, Visit
from visited_places.storage import journal_from_records, load_journal


class Command(BaseCommand):
    help = "Импортировать консольный журнал в веб-базу без изменения источника."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            type=Path,
            default=settings.BASE_DIR / "data" / "journal.sqlite3",
        )

    def handle(self, *args, **options):
        source = options["source"].resolve()
        if Place.objects.exists() or Trip.objects.exists() or Visit.objects.exists():
            self.stdout.write("Веб-журнал уже содержит записи. Импорт пропущен.")
            return
        try:
            if source.is_file():
                connection = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
                connection.row_factory = sqlite3.Row
                try:
                    version = connection.execute("PRAGMA user_version").fetchone()[0]
                    if version not in {1, 2}:
                        raise CommandError(
                            "Источник не является консольным журналом версии 1 или 2."
                        )
                    records = {
                        table: [
                            dict(row)
                            for row in connection.execute(
                                f"SELECT * FROM {table} ORDER BY id"
                            )
                        ]
                        for table in ("users", "places", "trips", "visits")
                    }
                finally:
                    connection.close()
                if version == 1:
                    records = migrate_legacy_records(records)
                journal = journal_from_records(records)
            else:
                journal = load_journal(source if source.is_dir() else source.parent)
            with transaction.atomic():
                users = {}
                for item in journal.users:
                    existing = User.objects.filter(email=item.email).first()
                    if existing is None:
                        username = "gleb" if item.id == 1 else f"journal_{item.id}"
                        if User.objects.filter(username=username).exists():
                            username = f"journal_{item.id}"
                        existing = User(
                            username=username, name=item.name, email=item.email
                        )
                        existing.set_unusable_password()
                        existing.save()
                    users[item.id] = existing
                places = {}
                for item in journal.places:
                    places[item.id] = Place.objects.create(**item.to_data())
                trips = {}
                for item in journal.trips:
                    data = item.to_data()
                    data["place"] = places[data.pop("place_id")]
                    trips[item.id] = Trip.objects.create(**data)
                for item in journal.visits:
                    timestamp = datetime.strptime(item.visited_at, "%Y-%m-%d %H:%M")
                    Visit.objects.create(
                        id=item.id,
                        user=users[item.user_id],
                        trip=trips[item.trip_id],
                        visited_at=timezone.make_aware(timestamp),
                        rating=item.rating,
                        note=item.note,
                    )
        except (OSError, sqlite3.Error, ValueError, KeyError) as exc:
            raise CommandError(f"Импорт не выполнен: {exc}") from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Импортировано: {len(journal.users)} пользователей, "
                f"{len(journal.places)} мест, "
                f"{len(journal.trips)} поездок, {len(journal.visits)} посещений."
            )
        )
