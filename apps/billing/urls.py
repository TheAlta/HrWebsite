from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("invoices/<int:number>/", views.invoice, name="invoice"),
    path("proformas/<int:pk>/", views.proforma, name="proforma"),
]
