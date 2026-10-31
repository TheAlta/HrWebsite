"""Zarinpal REST API v4. Docs: https://docs.zarinpal.com/paymentGateway/

Settings: ZARINPAL_MERCHANT_ID, ZARINPAL_SANDBOX. Amounts are sent in Rials.
"""

import httpx
from django.conf import settings

from .base import GatewayError, PaymentGateway, PaymentRequest, VerifyResult

TIMEOUT_SECONDS = 15
CODE_OK = 100
CODE_ALREADY_VERIFIED = 101


class ZarinpalGateway(PaymentGateway):
    def __init__(self, merchant_id=None, sandbox=None, client=None):
        self.merchant_id = merchant_id or settings.ZARINPAL_MERCHANT_ID
        self.sandbox = settings.ZARINPAL_SANDBOX if sandbox is None else sandbox
        host = "sandbox.zarinpal.com" if self.sandbox else "payment.zarinpal.com"
        self.api = f"https://{host}/pg/v4/payment"
        self.start_url = f"https://{host}/pg/StartPay"
        self.client = client or httpx.Client(timeout=TIMEOUT_SECONDS)

    def _post(self, path, payload):
        if not self.merchant_id:
            raise GatewayError("ZARINPAL_MERCHANT_ID is not set")
        try:
            response = self.client.post(f"{self.api}/{path}", json=payload)
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GatewayError(f"zarinpal unreachable: {exc}") from exc

    def request(self, amount, callback_url, description, *, mobile="", order_id=""):
        payload = {
            "merchant_id": self.merchant_id,
            "amount": amount,
            "currency": "IRR",
            "callback_url": callback_url,
            "description": description,
            "metadata": {"mobile": mobile, "order_id": order_id},
        }
        body = self._post("request.json", payload)
        data = body.get("data") or {}
        if data.get("code") != CODE_OK:
            raise GatewayError(f"zarinpal refused the request: {body.get('errors')}")
        authority = data["authority"]
        return PaymentRequest(authority=authority, redirect_url=f"{self.start_url}/{authority}")

    def verify(self, authority, amount):
        payload = {"merchant_id": self.merchant_id, "amount": amount, "authority": authority}
        body = self._post("verify.json", payload)
        data = body.get("data") or {}
        if data.get("code") in (CODE_OK, CODE_ALREADY_VERIFIED):
            return VerifyResult(
                ok=True,
                ref_id=str(data.get("ref_id", "")),
                card_mask=data.get("card_pan") or "",
                raw=body,
            )
        return VerifyResult(ok=False, raw=body)

    def authority_from_callback(self, params):
        return params.get("Authority", "")
