from django.urls import path

from . import views

app_name = "crm"

urlpatterns = [
    path("<slug:kind>/", views.submit, name="submit"),
]
