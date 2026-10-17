import secrets

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError

from db.database import execute, fetch_one


class Command(BaseCommand):
    help = "Подготовить локальный учебный аккаунт, не меняя существующий пароль."

    def handle(self, *args, **options):
        user = fetch_one("SELECT * FROM users WHERE username = 'gleb'")
        if user is None:
            raise CommandError("Сначала выполните python manage.py init_db.")
        if user["password"]:
            self.stdout.write("Логин: gleb. Существующий пароль не изменён.")
            return
        password = secrets.token_urlsafe(12)
        execute(
            "UPDATE users SET password = ?, is_staff = 1 WHERE id = ?",
            (make_password(password), user["id"]),
        )
        self.stdout.write(f"Логин: gleb\nПароль: {password}")
