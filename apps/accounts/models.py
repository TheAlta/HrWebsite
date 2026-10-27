from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

from apps.core.fields import MobileField
from apps.core.text import normalize_mobile


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, mobile, password, **extra_fields):
        if not mobile:
            raise ValueError("mobile is required")
        user = self.model(mobile=normalize_mobile(mobile), **extra_fields)
        # password=None gives an unusable password: normal customers log in by OTP only
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, mobile, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(mobile, password, **extra_fields)

    def create_superuser(self, mobile, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("superuser must have is_staff=True and is_superuser=True")
        return self._create_user(mobile, password, **extra_fields)


class User(AbstractUser):
    """Site user identified by mobile number (spec section 7, accounts.User).

    Customers sign in with mobile + OTP (sprint 2); staff additionally have a
    password for the admin panel.
    """

    username = None
    mobile = MobileField("موبایل", unique=True, help_text="مثل ۰۹۱۲۱۲۳۴۵۶۷")
    email = models.EmailField("ایمیل", blank=True)

    USERNAME_FIELD = "mobile"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "کاربر"
        verbose_name_plural = "کاربران"

    def __str__(self):
        return self.get_full_name() or self.mobile


class OTPCode(models.Model):
    """One-time login code (USER-1). Only an HMAC of the code is stored."""

    mobile = models.CharField(max_length=11, db_index=True)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)
    ip_hash = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "کد ورود"
        verbose_name_plural = "کدهای ورود"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.mobile} @ {self.created_at:%Y-%m-%d %H:%M}"
