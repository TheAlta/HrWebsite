from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("callback/<slug:gateway>/", views.callback, name="callback"),
    path("pay/<slug:number>/", views.pay, name="pay"),
    path("fake/<slug:authority>/", views.fake_bank, name="fake"),
]
