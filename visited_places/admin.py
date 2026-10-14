from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Place, Trip, User, Visit


@admin.register(User)
class JournalUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Журнал", {"fields": ("name",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + ((None, {"fields": ("name", "email")}),)
    list_display = ("username", "name", "email", "is_staff")


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "country", "category")
    search_fields = ("name", "city", "country")
    list_filter = ("country", "category")
    exclude = ("name_key", "city_key", "country_key", "category_key")


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ("name", "place", "start_date", "end_date")
    list_select_related = ("place",)
    search_fields = ("name", "place__name")


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ("user", "trip", "visited_at", "rating")
    list_select_related = ("user", "trip", "trip__place")
    list_filter = ("rating",)
    search_fields = ("user__name", "trip__name", "note")
