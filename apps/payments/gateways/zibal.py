"""Zibal API (backup gateway). Docs: https://help.zibal.ir/IPG/API/

Setting: ZIBAL_MERCHANT (the value "zibal" is Zibal's test merchant). Amounts are in Rials.
"""

import httpx
from django.conf import settings

from .base import GatewayError, PaymentGateway, PaymentRequest, VerifyResult

API = "https://gateway.zibal.ir/v1"
START_URL = "https://gateway.zibal.ir/start"
TIMEOUT_SECONDS = 15
RESULT_OK = 100
RESULT_ALREADY_VERIFIED = 201


class ZibalGateway(PaymentGateway):
    def __init__(self, merchant=None, client=None):
        self.merchant = merchant or settings.ZIBAL_MERCHANT
        self.client = client or httpx.Client(timeout=TIMEOUT_SECONDS)

    def _post(self, path, payload):
        if not self.merchant:
            raise GatewayError("ZIBAL_MERCHANT is not set")
        try:
            return self.client.post(f"{API}/{path}", json=payload).json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GatewayError(f"zibal unreachable: {exc}") from exc

    def request(self, amount, callback_url, description, *, mobile="", order_id=""):
        payload = {
            "merchant": self.merchant,
            "amount": amount,
            "callbackUrl": callback_url,
            "description": description,
            "orderId": order_id,
            "mobile": mobile,
        }
        body = self._post("request", payload)
        if body.get("result") != RESULT_OK:
            raise GatewayError(f"zibal refused the request: {body}")
        track_id = str(body["trackId"])
        return PaymentRequest(authority=track_id, redirect_url=f"{START_URL}/{track_id}")

    def verify(self, authority, amount):
        body = self._post("verify", {"merchant": self.merchant, "trackId": authority})
        if body.get("result") in (RESULT_OK, RESULT_ALREADY_VERIFIED):
            return VerifyResult(
                ok=True,
                ref_id=str(body.get("refNumber") or authority),
                card_mask=body.get("cardNumber") or "",
                amount=body.get("amount"),
                raw=body,
            )
        return VerifyResult(ok=False, raw=body)

    def authority_from_callback(self, params):
        return params.get("trackId", "")
