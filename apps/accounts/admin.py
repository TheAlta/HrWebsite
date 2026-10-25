from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-date_joined",)
    list_display = ("mobile", "first_name", "last_name", "email", "is_staff", "date_joined")
    search_fields = ("mobile", "first_name", "last_name", "email")
    fieldsets = (
        (None, {"fields": ("mobile", "password")}),
        ("اطلاعات شخصی", {"fields": ("first_name", "last_name", "email")}),
        (
            "دسترسی‌ها",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("تاریخ‌ها", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("mobile", "password1", "password2")}),
    )
