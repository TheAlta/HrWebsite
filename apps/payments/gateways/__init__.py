from django.conf import settings
from django.utils.module_loading import import_string

from .base import GatewayError, PaymentGateway, PaymentRequest, VerifyResult

__all__ = ["GatewayError", "PaymentGateway", "PaymentRequest", "VerifyResult", "get_gateway"]


def get_gateway(name: str) -> PaymentGateway:
    """Gateway classes are named in settings, so swapping one is configuration only."""
    return import_string(settings.PAYMENT_GATEWAYS[name])()
