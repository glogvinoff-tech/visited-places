from django.urls import path

from . import api, views

app_name = "visited_places"

urlpatterns = [
    path("", views.application, name="journal"),
    path("places/", views.application, {"view": "places"}, name="places"),
    path("places/<int:pk>/", views.detail, {"view": "places"}, name="place-detail"),
    path("trips/", views.application, {"view": "trips"}, name="trips"),
    path("trips/<int:pk>/", views.detail, {"view": "trips"}, name="trip-detail"),
    path("visits/", views.application, name="visits"),
    path("visits/<int:pk>/", views.detail, {"view": "visits"}, name="visit-detail"),
    path("statistics/", views.application, {"view": "statistics"}, name="statistics"),
    path("login/", views.JournalLoginView.as_view(), name="login"),
    path("logout/", views.JournalLogoutView.as_view(), name="logout"),
    path("register/", views.register, name="register"),
    path("api/me/", api.me),
    path("api/places/", api.places),
    path("api/places/<int:pk>/", api.place_detail),
    path("api/trips/", api.trips),
    path("api/trips/<int:pk>/", api.trip_detail),
    path("api/visits/", api.visits),
    path("api/visits/<int:pk>/", api.visit_detail),
    path("api/statistics/", api.statistics),
]
