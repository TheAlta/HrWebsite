"""Development gateway: a local page plays the bank, so no merchant account is needed.

It can never run in production: config.settings.prod refuses to start with it.
"""

import uuid

from django.core.cache import cache
from django.urls import reverse

from .base import PaymentGateway, PaymentRequest, VerifyResult

CACHE_SECONDS = 60 * 60


def _key(authority):
    return f"fake-gateway:{authority}"


class FakeGateway(PaymentGateway):
    def request(self, amount, callback_url, description, *, mobile="", order_id=""):
        authority = uuid.uuid4().hex
        cache.set(_key(authority), {"amount": amount, "callback_url": callback_url}, CACHE_SECONDS)
        return PaymentRequest(
            authority=authority, redirect_url=reverse("payments:fake", args=[authority])
        )

    def verify(self, authority, amount):
        data = cache.get(_key(authority)) or {}
        if data.get("paid") and data.get("amount") == amount:
            return VerifyResult(
                ok=True,
                ref_id=f"FAKE{authority[:8]}",
                card_mask="6037****0000",
                amount=amount,
                raw={"fake": True},
            )
        return VerifyResult(ok=False, raw={"fake": True})

    def authority_from_callback(self, params):
        return params.get("authority", "")


def simulate_payment(authority, *, paid: bool) -> str | None:
    """What the customer does on the bank page. Returns the callback URL."""
    data = cache.get(_key(authority))
    if data is None:
        return None
    data["paid"] = paid
    cache.set(_key(authority), data, CACHE_SECONDS)
    return f"{data['callback_url']}?authority={authority}&Status={'OK' if paid else 'NOK'}"
