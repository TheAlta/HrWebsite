from django.urls import path

from . import views

app_name = "booking"

urlpatterns = [
    path("<int:pk>/cancel/", views.cancel, name="cancel"),
    path("<int:pk>/reschedule/", views.reschedule, name="reschedule"),
]
