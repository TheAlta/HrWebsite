import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError

pytestmark = pytest.mark.django_db
User = get_user_model()


def test_create_user_normalises_mobile_and_has_no_password():
    user = User.objects.create_user("+98 912 123 4567")
    assert user.mobile == "09121234567"
    assert not user.has_usable_password()  # customers log in by OTP
    assert not user.is_staff


def test_create_superuser():
    admin = User.objects.create_superuser("09120000000", password="s3cret-pass")
    assert admin.is_staff and admin.is_superuser
    assert admin.check_password("s3cret-pass")


def test_mobile_is_unique():
    User.objects.create_user("09121234567")
    with pytest.raises(IntegrityError):
        User.objects.create_user("۰۹۱۲۱۲۳۴۵۶۷")


def test_invalid_mobile_fails_validation():
    user = User(mobile="12345")
    with pytest.raises(ValidationError):
        user.full_clean()


def test_str_prefers_full_name():
    user = User.objects.create_user("09121234567", first_name="سارا", last_name="احمدی")
    assert str(user) == "سارا احمدی"


def test_wagtail_admin_accepts_persian_digit_mobile(client):
    admin = User.objects.create_superuser("09120000000", password="s3cret-pass")
    client.force_login(admin)
    response = client.post(
        "/panel/users/new/",
        {
            "mobile": "۰۹۳۵ ۱۱۱ ۲۲۳۳",
            "email": "staff@example.com",
            "first_name": "تست",
            "last_name": "کارمند",
            "password1": "Strong-pass-9876",
            "password2": "Strong-pass-9876",
        },
    )
    assert response.status_code == 302
    assert User.objects.filter(mobile="09351112233").exists()
