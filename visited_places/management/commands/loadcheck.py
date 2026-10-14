import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.test import Client

from visited_places.models import User


class Command(BaseCommand):
    help = "Небольшая нагрузочная проверка читающего API без изменения журнала."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="gleb")
        parser.add_argument("--requests", type=int, default=60)
        parser.add_argument("--workers", type=int, default=4)
        parser.add_argument("--base-url", default="")

    def handle(self, *args, **options):
        total, workers = options["requests"], options["workers"]
        if not 1 <= total <= 5000 or not 1 <= workers <= 8:
            raise CommandError("Допустимо 1-5000 запросов и 1-8 потоков.")
        base = options["base_url"].rstrip("/")
        if base:
            target = urlparse(base)
            if target.scheme not in {"http", "https"} or target.hostname not in {
                "localhost",
                "127.0.0.1",
                "::1",
            }:
                raise CommandError("HTTP-проверка разрешена только для localhost.")
        user = User.objects.filter(username=options["username"], is_active=True).first()
        if user is None:
            raise CommandError("Пользователь не найден.")
        client = Client()
        client.force_login(user)
        session_key = client.cookies[settings.SESSION_COOKIE_NAME].value
        paths = ["/api/places/", "/api/trips/", "/api/visits/", "/api/statistics/"]

        def request(index):
            start = time.perf_counter()
            try:
                path = paths[index % len(paths)]
                if base:
                    headers = {
                        "Cookie": f"{settings.SESSION_COOKIE_NAME}={session_key}"
                    }
                    with urlopen(
                        Request(base + path, headers=headers), timeout=15
                    ) as response:
                        json.loads(response.read())
                        status = response.status
                else:
                    worker = Client()
                    worker.cookies[settings.SESSION_COOKIE_NAME] = session_key
                    response = worker.get(path, HTTP_HOST="localhost")
                    status = response.status_code
                    response.json()
                return status, (time.perf_counter() - start) * 1000
            except Exception:
                return 500, (time.perf_counter() - start) * 1000
            finally:
                close_old_connections()

        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(request, range(total)))
        finally:
            Session.objects.filter(session_key=session_key).delete()
        durations = sorted(duration for _, duration in results)
        failures = sum(status != 200 for status, _ in results)
        self.stdout.write(
            json.dumps(
                {
                    "requests": total,
                    "workers": workers,
                    "failures": failures,
                    "mean_ms": round(statistics.mean(durations), 2),
                    "p95_ms": round(durations[min(total - 1, int(total * 0.95))], 2),
                }
            )
        )
        if failures:
            raise CommandError("Часть запросов завершилась ошибкой.")
