from django.core.management import call_command
from django.core.management.base import BaseCommand

from db.import_json import import_json


class Command(BaseCommand):
    help = "Создать SQLite-базу, импортировать JSON и подготовить учебный вход."

    def handle(self, *args, **options):
        imported = import_json()
        self.stdout.write(
            "JSON импортирован." if imported else "База уже заполнена; импорт пропущен."
        )
        call_command("setup_demo", stdout=self.stdout)
