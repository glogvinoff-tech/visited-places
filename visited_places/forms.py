from django import forms
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator

from db.database import fetch_all, fetch_one


class LoginForm(forms.Form):
    username = forms.CharField(label="Логин", max_length=150)
    password = forms.CharField(label="Пароль", widget=forms.PasswordInput, strip=False)


class ProfileForm(forms.Form):
    name = forms.CharField(label="Имя", max_length=150)
    email = forms.EmailField(label="Email")

    def __init__(self, *args, user_id=0, **kwargs):
        self.user_id = user_id
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data["email"].casefold()
        if fetch_one(
            "SELECT id FROM users WHERE email = ? AND id != ?", (email, self.user_id)
        ):
            raise forms.ValidationError("Этот email уже используется.")
        return email


class RegistrationForm(ProfileForm):
    field_order = ["username", "name", "email", "password1", "password2"]
    username = forms.CharField(
        label="Логин",
        max_length=150,
        validators=[UnicodeUsernameValidator()],
    )
    password1 = forms.CharField(label="Пароль", widget=forms.PasswordInput, strip=False)
    password2 = forms.CharField(
        label="Повтор пароля", widget=forms.PasswordInput, strip=False
    )

    def clean_username(self):
        username = self.cleaned_data["username"]
        if fetch_one(
            "SELECT id FROM users WHERE casefold(username) = casefold(?)", (username,)
        ):
            raise forms.ValidationError("Этот логин уже используется.")
        return username

    def clean_password1(self):
        password = self.cleaned_data["password1"]
        validate_password(password)
        return password

    def clean(self):
        data = super().clean()
        if (
            data.get("password1")
            and data.get("password2")
            and data["password1"] != data["password2"]
        ):
            self.add_error("password2", "Пароли не совпадают.")
        return data


class PlaceForm(forms.Form):
    name = forms.CharField(label="Название", max_length=160)
    city = forms.CharField(label="Город", max_length=100)
    country = forms.CharField(label="Страна", max_length=100)
    category = forms.CharField(label="Категория", max_length=60)
    image_url = forms.URLField(label="Фотография (URL)", required=False, max_length=500)

    def __init__(self, *args, record_id=0, **kwargs):
        self.record_id = record_id
        super().__init__(*args, **kwargs)

    def clean_image_url(self):
        url = self.cleaned_data["image_url"]
        if url and not url.startswith(("http://", "https://")):
            raise forms.ValidationError("Нужен адрес HTTP или HTTPS.")
        return url

    def clean(self):
        data = super().clean()
        if all(data.get(field) for field in ("name", "city", "country")):
            duplicate = fetch_one(
                "SELECT id FROM places WHERE casefold(name) = casefold(?) "
                "AND casefold(city) = casefold(?) AND casefold(country) = casefold(?) "
                "AND id != ?",
                (data["name"], data["city"], data["country"], self.record_id),
            )
            if duplicate:
                raise forms.ValidationError("Такое место уже есть в каталоге.")
        return data


class TripForm(forms.Form):
    name = forms.CharField(label="Название поездки", max_length=160)
    place_id = forms.TypedChoiceField(label="Место", coerce=int)
    start_date = forms.DateField(
        label="Начало",
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"type": "date"},
        ),
    )
    end_date = forms.DateField(
        label="Окончание",
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"type": "date"},
        ),
    )

    def __init__(self, *args, record_id=0, **kwargs):
        self.record_id = record_id
        super().__init__(*args, **kwargs)
        self.fields["place_id"].choices = [
            (p["id"], f"{p['name']}, {p['city']}")
            for p in fetch_all("SELECT id, name, city FROM places ORDER BY name")
        ]

    def clean(self):
        data = super().clean()
        start, end = data.get("start_date"), data.get("end_date")
        if start and end:
            if start > end:
                self.add_error("end_date", "Окончание не может быть раньше начала.")
            bounds = fetch_one(
                "SELECT MIN(substr(visited_at, 1, 10)), MAX(substr(visited_at, 1, 10)) "
                "FROM visits WHERE trip_id = ?",
                (self.record_id,),
            )
            if bounds[0] and (
                start.isoformat() > bounds[0] or end.isoformat() < bounds[1]
            ):
                self.add_error(
                    "start_date", "Новые даты исключают уже записанные посещения."
                )
        return data


class VisitForm(forms.Form):
    trip_id = forms.TypedChoiceField(label="Поездка", coerce=int)
    visited_at = forms.DateTimeField(
        label="Дата посещения",
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local"},
        ),
    )
    rating = forms.TypedChoiceField(
        label="Оценка",
        required=False,
        coerce=int,
        empty_value=None,
        choices=[("", "Без оценки")] + [(n, f"{n} / 5") for n in range(1, 6)],
    )
    note = forms.CharField(
        label="Заметка",
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    def __init__(self, *args, user_id=0, record_id=0, **kwargs):
        self.user_id, self.record_id = user_id, record_id
        super().__init__(*args, **kwargs)
        self.fields["trip_id"].choices = [
            (t["id"], f"{t['name']} ({t['start_date']} - {t['end_date']})")
            for t in fetch_all("SELECT * FROM trips ORDER BY start_date DESC, id DESC")
        ]

    def clean(self):
        data = super().clean()
        trip_id, timestamp = data.get("trip_id"), data.get("visited_at")
        if trip_id and timestamp:
            trip = fetch_one("SELECT * FROM trips WHERE id = ?", (trip_id,))
            if (
                trip
                and not trip["start_date"]
                <= timestamp.date().isoformat()
                <= trip["end_date"]
            ):
                self.add_error("visited_at", "Дата должна входить в период поездки.")
            if fetch_one(
                "SELECT id FROM visits WHERE user_id = ? AND trip_id = ? "
                "AND visited_at = ? AND id != ?",
                (
                    self.user_id,
                    trip_id,
                    timestamp.strftime("%Y-%m-%d %H:%M"),
                    self.record_id,
                ),
            ):
                raise forms.ValidationError("Такое посещение уже записано.")
        return data
