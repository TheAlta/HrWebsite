"""Second step for the panel: a code from an authenticator app (spec section 11).

Everyone who can open the panel sets up an app (Google or Microsoft
Authenticator) once, gets ten backup codes, and then types the app's code once
per login session. Customers never see this. Off on a developer's computer with
PANEL_2FA_REQUIRED (REPORT #051).
"""

from base64 import b32encode
from urllib.parse import quote

import segno
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django_otp import user_has_device
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.core.http import is_panel_path

BACKUP_CODES = 10
APP_DEVICE_NAME = "اپ Authenticator"
BACKUP_DEVICE_NAME = "کدهای پشتیبان"


def can_open_panel(user) -> bool:
    return user.is_authenticated and (user.is_staff or user.has_perm("wagtailadmin.access_admin"))


def needs_second_step(request) -> bool:
    return (
        settings.PANEL_2FA_REQUIRED
        and can_open_panel(request.user)
        and not request.user.is_verified()
    )


def is_set_up(user) -> bool:
    return user_has_device(user, confirmed=True)


def pending_app_device(user) -> TOTPDevice:
    """The app being set up: the same secret until a code from it is confirmed."""
    device = TOTPDevice.objects.filter(user=user, confirmed=False).first()
    return device or TOTPDevice.objects.create(user=user, name=APP_DEVICE_NAME, confirmed=False)


def secret_for_typing(device: TOTPDevice) -> str:
    key = b32encode(device.bin_key).decode()
    return " ".join(key[i : i + 4] for i in range(0, len(key), 4))


def qr_code(device: TOTPDevice) -> str:
    return segno.make(device.config_url, error="m").svg_data_uri(scale=5, border=2)


def confirm_app(device: TOTPDevice, code: str) -> list[str] | None:
    """Turn the app on if the code is right, and return the new backup codes."""
    if not device.verify_token(code):
        return None
    device.confirmed = True
    device.save(update_fields=["confirmed"])
    return new_backup_codes(device.user)


def new_backup_codes(user) -> list[str]:
    StaticDevice.objects.filter(user=user).delete()
    backup = StaticDevice.objects.create(user=user, name=BACKUP_DEVICE_NAME)
    codes = [StaticToken.random_token() for _ in range(BACKUP_CODES)]
    StaticToken.objects.bulk_create(StaticToken(device=backup, token=code) for code in codes)
    return codes


def reset(user) -> int:
    """For a lost phone: the user sets up an app again at the next panel visit."""
    deleted = 0
    for model in (TOTPDevice, StaticDevice):
        deleted += model.objects.filter(user=user).delete()[0]
    return deleted


class PanelTwoFactorMiddleware:
    """Panel pages wait until the session has passed the second step."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if is_panel_path(request.path_info) and needs_second_step(request):
            exempt = (reverse("wagtailadmin_login"), reverse("wagtailadmin_logout"))
            if request.path_info not in exempt:
                target = reverse("accounts:two_factor")
                return redirect(f"{target}?next={quote(request.get_full_path())}")
        return self.get_response(request)
