from django.urls import path

from . import views

app_name = "shop"

urlpatterns = [
    path("cart/", views.cart_view, name="cart"),
    path("cart/add/<int:pk>/", views.cart_add, name="cart_add"),
    path("cart/update/<int:pk>/", views.cart_update, name="cart_update"),
    path("cart/coupon/", views.cart_coupon, name="cart_coupon"),
    path("checkout/", views.checkout, name="checkout"),
    path("downloads/<str:token>/", views.download, name="download"),
]
