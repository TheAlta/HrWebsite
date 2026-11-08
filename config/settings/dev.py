"""Local development (docker compose)."""

from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]  # noqa: S104 — local only
INSTALLED_APPS.insert(0, "whitenoise.runserver_nostatic")  # noqa: F405
# Off on your own computer so local testing needs no phone; on everywhere else
PANEL_2FA_REQUIRED = env.bool("PANEL_2FA_REQUIRED", default=False)  # noqa: F405
