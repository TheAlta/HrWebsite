from django.urls import path

from . import views

app_name = "certificates"

urlpatterns = [
    path("certificates/", views.verify, name="verify"),
    path("certificates/<str:code>/", views.verify, name="detail"),
    path("account/certificates/<str:code>/", views.download, name="download"),
]
