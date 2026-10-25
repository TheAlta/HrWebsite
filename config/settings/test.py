"""Test run (pytest locally and in CI)."""

from .base import *  # noqa: F403

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
Q_CLUSTER = {**Q_CLUSTER, "sync": True}  # noqa: F405 — run tasks inline in tests
