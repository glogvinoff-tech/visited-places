from django.urls import path

from . import views

app_name = "visited_places"

urlpatterns = [
    path("", views.visit_list, name="journal"),
    path("places/", views.place_list, name="places"),
    path("places/new/", views.place_edit, name="place-create"),
    path("places/<int:pk>/", views.place_detail, name="place-detail"),
    path("places/<int:pk>/edit/", views.place_edit, name="place-edit"),
    path("places/<int:pk>/delete/", views.place_delete, name="place-delete"),
    path("trips/", views.trip_list, name="trips"),
    path("trips/new/", views.trip_edit, name="trip-create"),
    path("trips/<int:pk>/", views.trip_detail, name="trip-detail"),
    path("trips/<int:pk>/edit/", views.trip_edit, name="trip-edit"),
    path("trips/<int:pk>/delete/", views.trip_delete, name="trip-delete"),
    path("visits/", views.visit_list, name="visits"),
    path("visits/new/", views.visit_edit, name="visit-create"),
    path("visits/<int:pk>/", views.visit_detail, name="visit-detail"),
    path("visits/<int:pk>/edit/", views.visit_edit, name="visit-edit"),
    path("visits/<int:pk>/delete/", views.visit_delete, name="visit-delete"),
    path("statistics/", views.statistics, name="statistics"),
    path("profile/", views.profile, name="profile"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register, name="register"),
]
