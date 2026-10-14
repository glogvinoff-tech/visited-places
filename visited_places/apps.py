from django.apps import AppConfig


class VisitedPlacesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "visited_places"
    verbose_name = "Посещённые места"

    def ready(self):
        from . import signals  # noqa: F401
