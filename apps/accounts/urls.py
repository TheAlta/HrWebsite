from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("login/verify/", views.verify_view, name="verify"),
    path("logout/", views.logout_view, name="logout"),
    path("", views.account_view, name="account"),
]
