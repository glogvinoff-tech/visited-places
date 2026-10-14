from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("visited_places.urls")),
]

handler404 = "visited_places.views.page_not_found"
