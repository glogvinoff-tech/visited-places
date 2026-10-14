from datetime import datetime
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class User(AbstractUser):
    name = models.CharField("Имя", max_length=150)
    email = models.EmailField("Email", unique=True)
    REQUIRED_FIELDS = ["email", "name"]

    class Meta(AbstractUser.Meta):
        constraints = [
            models.CheckConstraint(condition=~Q(email=""), name="user_email_not_empty"),
        ]

    def save(self, *args, **kwargs):
        self.email = self.email.strip().casefold()
        self.name = (self.name or self.username).strip()
        return super().save(*args, **kwargs)

    def get_full_name(self):
        return self.name or self.username


class Place(models.Model):
    name = models.CharField("Название", max_length=160)
    city = models.CharField("Город", max_length=100)
    country = models.CharField("Страна", max_length=100)
    category = models.CharField("Категория", max_length=60)
    image_url = models.URLField("Фото", blank=True, max_length=500)
    name_key = models.CharField(max_length=480, editable=False, blank=True)
    city_key = models.CharField(max_length=300, editable=False, blank=True)
    country_key = models.CharField(max_length=300, editable=False, blank=True)
    category_key = models.CharField(max_length=180, editable=False, blank=True)

    class Meta:
        ordering = ["name", "id"]
        verbose_name = "место"
        verbose_name_plural = "места"
        constraints = [
            models.UniqueConstraint(
                fields=["name_key", "city_key", "country_key"],
                name="unique_place_location",
            )
        ]
        indexes = [
            models.Index(fields=["city_key", "country_key"], name="place_city_country")
        ]

    def clean(self):
        for field in ("name", "city", "country", "category"):
            raw = getattr(self, field)
            value = raw.strip() if isinstance(raw, str) else ""
            setattr(self, field, value)
            if not value:
                raise ValidationError({field: "Заполните это поле."})
        for field in ("name", "city", "country", "category"):
            setattr(self, f"{field}_key", getattr(self, field).casefold())
        if self.image_url and urlparse(self.image_url).scheme not in {"http", "https"}:
            raise ValidationError({"image_url": "Укажите адрес HTTP или HTTPS."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name}, {self.city}"


class Trip(models.Model):
    place = models.ForeignKey(Place, on_delete=models.PROTECT, related_name="trips")
    name = models.CharField("Название", max_length=160)
    start_date = models.DateField("Начало")
    end_date = models.DateField("Окончание")

    class Meta:
        ordering = ["-start_date", "-id"]
        verbose_name = "поездка"
        verbose_name_plural = "поездки"
        constraints = [
            models.CheckConstraint(
                condition=Q(start_date__lte=F("end_date")),
                name="trip_dates_in_order",
            )
        ]
        indexes = [
            models.Index(
                fields=["place", "start_date", "end_date"],
                name="trip_place_dates",
            )
        ]

    def clean(self):
        self.name = self.name.strip() if isinstance(self.name, str) else ""
        if not self.name:
            raise ValidationError({"name": "Заполните название."})
        if not self.start_date or not self.end_date:
            return
        if self.start_date > self.end_date:
            raise ValidationError(
                {"end_date": "Окончание не может быть раньше начала."}
            )
        if (
            self.pk
            and self.visits.filter(
                Q(visited_at__date__lt=self.start_date)
                | Q(visited_at__date__gt=self.end_date)
            ).exists()
        ):
            raise ValidationError(
                {"start_date": "Новые даты исключают существующие посещения."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Visit(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="visits",
    )
    trip = models.ForeignKey(Trip, on_delete=models.PROTECT, related_name="visits")
    visited_at = models.DateTimeField("Дата посещения")
    rating = models.PositiveSmallIntegerField("Оценка", null=True, blank=True)
    note = models.TextField("Заметка", blank=True, max_length=2000)

    class Meta:
        ordering = ["-visited_at", "-id"]
        verbose_name = "посещение"
        verbose_name_plural = "посещения"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "trip", "visited_at"],
                name="unique_user_trip_visit",
            ),
            models.CheckConstraint(
                condition=Q(rating__isnull=True) | Q(rating__gte=1, rating__lte=5),
                name="visit_rating_range",
            ),
        ]
        indexes = [models.Index(fields=["user", "-visited_at"], name="visit_user_date")]

    def clean(self):
        self.note = self.note.strip() if isinstance(self.note, str) else ""
        if self.rating is not None and not 1 <= self.rating <= 5:
            raise ValidationError({"rating": "Оценка должна быть от 1 до 5."})
        if not self.trip_id or not isinstance(self.visited_at, datetime):
            return
        try:
            trip = self.trip
        except Trip.DoesNotExist:
            return
        timestamp = self.visited_at
        if timezone.is_aware(timestamp):
            timestamp = timezone.localtime(timestamp)
        if not trip.start_date <= timestamp.date() <= trip.end_date:
            raise ValidationError({"visited_at": "Дата не входит в период поездки."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user}: {self.trip}"
