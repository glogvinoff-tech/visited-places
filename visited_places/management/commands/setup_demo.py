import os

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.utils.crypto import get_random_string

from visited_places.models import User


class Command(BaseCommand):
    help = (
        "Подготовить локальный демонстрационный вход; существующий пароль не меняется."
    )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Демонстрационный вход разрешён только при DEBUG=1.")
        user, created = User.objects.get_or_create(
            username="gleb",
            defaults={
                "name": "Логвинов Глеб Дмитриевич",
                "email": "gleb@example.com",
            },
        )
        password = None
        if created or not user.has_usable_password():
            password = os.environ.get(
                "VISITED_PLACES_DEMO_PASSWORD"
            ) or get_random_string(18)
            validate_password(password, user)
            user.set_password(password)
        user.is_staff = True
        user.is_superuser = True
        user.save()
        self.stdout.write("Локальный администратор: gleb")
        if password:
            self.stdout.write(f"Пароль: {password}")
        else:
            self.stdout.write("Существующий пароль сохранён.")
