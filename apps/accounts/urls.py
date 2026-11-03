from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("login/verify/", views.verify_view, name="verify"),
    path("logout/", views.logout_view, name="logout"),
    path("", views.account_view, name="account"),
    path("orders/", views.orders_view, name="orders"),
    path("invoices/", views.invoices_view, name="invoices"),
    path("sessions/", views.sessions_view, name="sessions"),
    path("courses/", views.courses_view, name="courses"),
    path("downloads/", views.downloads_view, name="downloads"),
    path("profile/", views.profile_view, name="profile"),
]
