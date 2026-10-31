from django.urls import path

from . import views

app_name = "events"

urlpatterns = [
    path("<int:pk>/cancel/", views.cancel, name="cancel"),
]
