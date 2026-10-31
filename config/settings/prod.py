"""Staging and production. Runs behind Caddy, which terminates HTTPS."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False
ALLOW_SEED_DEMO = env.bool("ALLOW_SEED_DEMO", default=False)  # noqa: F405

# Safety net: the fake bank approves anything, so production refuses to start with it
PAYMENT_GATEWAYS.pop("fake")  # noqa: F405
unknown_gateways = set(PAYMENT_GATEWAY_ORDER) - set(PAYMENT_GATEWAYS)  # noqa: F405
if unknown_gateways:
    raise ImproperlyConfigured(f"PAYMENT_GATEWAY_ORDER has invalid gateways: {unknown_gateways}")

STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)  # noqa: F405
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 30)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"

# Error tracking; works with Sentry or a self-hosted GlitchTip
SENTRY_DSN = env("SENTRY_DSN", default="")  # noqa: F405
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(dsn=SENTRY_DSN, send_default_pii=False, traces_sample_rate=0)
