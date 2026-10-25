"""Reusable model/form fields."""

import contextlib

from django import forms
from django.core.exceptions import ValidationError
from django.db import models

from .text import normalize_mobile


def validate_mobile(value):
    try:
        normalize_mobile(value)
    except ValueError as exc:
        raise ValidationError("شماره موبایل معتبر نیست.", code="invalid_mobile") from exc


def _normalize_if_valid(value):
    # Invalid input is returned unchanged so validate_mobile can report it
    if value:
        with contextlib.suppress(ValueError):
            return normalize_mobile(value)
    return value


class MobileFormField(forms.CharField):
    default_validators = [validate_mobile]

    def to_python(self, value):
        return _normalize_if_valid(super().to_python(value))


class MobileField(models.CharField):
    """Iranian mobile number stored as 09XXXXXXXXX.

    Normalises input such as "۰۹۱۲ ۱۲۳ ۴۵۶۷" or "+989121234567" in every form
    (Wagtail admin, Django admin, site forms) before length/format validation.
    """

    default_validators = [validate_mobile]

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_length", 11)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if kwargs.get("max_length") == 11:
            del kwargs["max_length"]
        return name, path, args, kwargs

    def to_python(self, value):
        return _normalize_if_valid(super().to_python(value))

    def formfield(self, **kwargs):
        return super().formfield(**{"form_class": MobileFormField, **kwargs})
