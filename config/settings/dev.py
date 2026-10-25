"""Local development (docker compose)."""

from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]
INSTALLED_APPS.insert(0, "whitenoise.runserver_nostatic")  # noqa: F405
