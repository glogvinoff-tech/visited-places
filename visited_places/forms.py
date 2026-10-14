from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Place, Trip, User, Visit


class RegistrationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ["username", "name", "email"]

    def clean_email(self):
        return self.cleaned_data["email"].strip().casefold()


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["name", "email"]

    def clean_email(self):
        return self.cleaned_data["email"].strip().casefold()


class PlaceForm(forms.ModelForm):
    class Meta:
        model = Place
        fields = ["name", "city", "country", "category", "image_url"]


class TripForm(forms.ModelForm):
    class Meta:
        model = Trip
        fields = ["place", "name", "start_date", "end_date"]


class VisitForm(forms.ModelForm):
    class Meta:
        model = Visit
        fields = ["trip", "visited_at", "rating", "note"]
