"""Mobile + one-time-code login (USER-1, spec section 11).

- 5-digit code, valid 2 minutes, at most 5 guesses
- at most 3 codes per mobile and 10 per IP in 10 minutes (no captcha, REPORT #023);
  the IP limit is looser because Iranian mobile carriers share IPs between many users
- the account is created on first successful login
"""

import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.core.text import normalize_mobile, to_en_digits
from apps.notifications.services import send_sms

from .models import OTPCode

CODE_LENGTH = 5
CODE_TTL = timedelta(minutes=2)
MAX_ATTEMPTS = 5
RATE_WINDOW = timedelta(minutes=10)
MAX_PER_MOBILE = 3
MAX_PER_IP = 10


class OTPError(Exception):
    """A user-facing reason the request was refused (message is Persian)."""


def _hash(mobile: str, code: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(), f"{mobile}:{code}".encode(), hashlib.sha256
    ).hexdigest()


def request_code(mobile: str, ip_hash: str) -> OTPCode:
    mobile = normalize_mobile(mobile)
    since = timezone.now() - RATE_WINDOW
    recent = OTPCode.objects.filter(created_at__gte=since)
    if recent.filter(mobile=mobile).count() >= MAX_PER_MOBILE:
        raise OTPError("برای این شماره کد زیادی درخواست شده است. چند دقیقه دیگر تلاش کنید.")
    if recent.filter(ip_hash=ip_hash).count() >= MAX_PER_IP:
        raise OTPError("درخواست‌های زیادی از شبکه شما ارسال شده است. چند دقیقه دیگر تلاش کنید.")

    code = "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))
    with transaction.atomic():
        # Only the newest code is valid
        OTPCode.objects.filter(mobile=mobile, used_at__isnull=True).update(used_at=timezone.now())
        otp = OTPCode.objects.create(
            mobile=mobile,
            code_hash=_hash(mobile, code),
            expires_at=timezone.now() + CODE_TTL,
            ip_hash=ip_hash,
        )
    send_sms(mobile, "otp", {"token": code})
    return otp


def verify_code(mobile: str, code: str):
    """Return the (possibly new) user for a correct code, or raise OTPError."""
    mobile = normalize_mobile(mobile)
    code = to_en_digits(code.strip())
    # The error is raised only after the transaction commits: raising inside
    # `atomic()` would roll back the attempt counter and allow unlimited guesses.
    error = None
    with transaction.atomic():
        otp = (
            OTPCode.objects.select_for_update()
            .filter(mobile=mobile, used_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if otp is None or otp.expires_at < timezone.now():
            error = "کد منقضی شده است. دوباره درخواست کد بدهید."
        elif otp.attempts >= MAX_ATTEMPTS:
            error = "تعداد تلاش‌ها زیاد بود. دوباره درخواست کد بدهید."
        else:
            otp.attempts += 1
            if hmac.compare_digest(otp.code_hash, _hash(mobile, code)):
                otp.used_at = timezone.now()
            else:
                error = "کد وارد شده درست نیست."
            otp.save(update_fields=["attempts", "used_at"])
    if error:
        raise OTPError(error)

    User = get_user_model()
    user = User.objects.filter(mobile=mobile).first()
    if user is None:
        # create_user gives an explicitly unusable password: customers log in by OTP only
        user = User.objects.create_user(mobile)
    if not user.is_active:
        raise OTPError("این حساب غیرفعال است.")
    return user
