import django.contrib.auth.models
import django.contrib.auth.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="User",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                (
                    "last_login",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="last login"
                    ),
                ),
                (
                    "is_superuser",
                    models.BooleanField(
                        default=False,
                        help_text="Designates that this user has all permissions without explicitly assigning them.",
                        verbose_name="superuser status",
                    ),
                ),
                (
                    "username",
                    models.CharField(
                        error_messages={
                            "unique": "A user with that username already exists."
                        },
                        help_text="Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.",
                        max_length=150,
                        unique=True,
                        validators=[
                            django.contrib.auth.validators.UnicodeUsernameValidator()
                        ],
                        verbose_name="username",
                    ),
                ),
                (
                    "first_name",
                    models.CharField(
                        blank=True, max_length=150, verbose_name="first name"
                    ),
                ),
                (
                    "last_name",
                    models.CharField(
                        blank=True, max_length=150, verbose_name="last name"
                    ),
                ),
                (
                    "is_staff",
                    models.BooleanField(
                        default=False,
                        help_text="Designates whether the user can log into this admin site.",
                        verbose_name="staff status",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Designates whether this user should be treated as active. Unselect this instead of deleting accounts.",
                        verbose_name="active",
                    ),
                ),
                (
                    "date_joined",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="date joined"
                    ),
                ),
                ("name", models.CharField(max_length=150, verbose_name="Имя")),
                (
                    "email",
                    models.EmailField(
                        max_length=254, unique=True, verbose_name="Email"
                    ),
                ),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions for this user.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
            ],
            options={
                "verbose_name": "user",
                "verbose_name_plural": "users",
                "abstract": False,
            },
            managers=[
                ("objects", django.contrib.auth.models.UserManager()),
            ],
        ),
        migrations.CreateModel(
            name="Place",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=160, verbose_name="Название")),
                ("city", models.CharField(max_length=100, verbose_name="Город")),
                ("country", models.CharField(max_length=100, verbose_name="Страна")),
                ("category", models.CharField(max_length=60, verbose_name="Категория")),
                (
                    "image_url",
                    models.URLField(blank=True, max_length=500, verbose_name="Фото"),
                ),
                (
                    "name_key",
                    models.CharField(blank=True, editable=False, max_length=480),
                ),
                (
                    "city_key",
                    models.CharField(blank=True, editable=False, max_length=300),
                ),
                (
                    "country_key",
                    models.CharField(blank=True, editable=False, max_length=300),
                ),
                (
                    "category_key",
                    models.CharField(blank=True, editable=False, max_length=180),
                ),
            ],
            options={
                "verbose_name": "место",
                "verbose_name_plural": "места",
                "ordering": ["name", "id"],
                "indexes": [
                    models.Index(
                        fields=["city_key", "country_key"], name="place_city_country"
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("name_key", "city_key", "country_key"),
                        name="unique_place_location",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="Trip",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=160, verbose_name="Название")),
                ("start_date", models.DateField(verbose_name="Начало")),
                ("end_date", models.DateField(verbose_name="Окончание")),
                (
                    "place",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="trips",
                        to="visited_places.place",
                    ),
                ),
            ],
            options={
                "verbose_name": "поездка",
                "verbose_name_plural": "поездки",
                "ordering": ["-start_date", "-id"],
            },
        ),
        migrations.CreateModel(
            name="Visit",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("visited_at", models.DateTimeField(verbose_name="Дата посещения")),
                (
                    "rating",
                    models.PositiveSmallIntegerField(
                        blank=True, null=True, verbose_name="Оценка"
                    ),
                ),
                (
                    "note",
                    models.TextField(
                        blank=True, max_length=2000, verbose_name="Заметка"
                    ),
                ),
                (
                    "trip",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="visits",
                        to="visited_places.trip",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="visits",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "посещение",
                "verbose_name_plural": "посещения",
                "ordering": ["-visited_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.CheckConstraint(
                condition=models.Q(("email", ""), _negated=True),
                name="user_email_not_empty",
            ),
        ),
        migrations.AddIndex(
            model_name="trip",
            index=models.Index(
                fields=["place", "start_date", "end_date"], name="trip_place_dates"
            ),
        ),
        migrations.AddConstraint(
            model_name="trip",
            constraint=models.CheckConstraint(
                condition=models.Q(("start_date__lte", models.F("end_date"))),
                name="trip_dates_in_order",
            ),
        ),
        migrations.AddIndex(
            model_name="visit",
            index=models.Index(fields=["user", "-visited_at"], name="visit_user_date"),
        ),
        migrations.AddConstraint(
            model_name="visit",
            constraint=models.UniqueConstraint(
                fields=("user", "trip", "visited_at"), name="unique_user_trip_visit"
            ),
        ),
        migrations.AddConstraint(
            model_name="visit",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("rating__isnull", True),
                    models.Q(("rating__gte", 1), ("rating__lte", 5)),
                    _connector="OR",
                ),
                name="visit_rating_range",
            ),
        ),
    ]
