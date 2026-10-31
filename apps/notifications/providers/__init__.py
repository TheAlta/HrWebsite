from django.conf import settings
from django.utils.module_loading import import_string

from .base import SMSError, SMSProvider, SMSResult

__all__ = ["SMSError", "SMSProvider", "SMSResult", "get_sms_provider"]


def get_sms_provider() -> SMSProvider:
    """The provider class named in settings.SMS_PROVIDER — swapping providers is config only."""
    return import_string(settings.SMS_PROVIDER)()
