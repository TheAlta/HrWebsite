from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class GatewayError(Exception):
    """The gateway could not be reached or gave no usable answer. The outcome is unknown."""


@dataclass
class PaymentRequest:
    authority: str
    redirect_url: str


@dataclass
class VerifyResult:
    ok: bool
    ref_id: str = ""
    card_mask: str = ""
    # Amount the gateway confirms, when its API returns one
    amount: int | None = None
    raw: dict = field(default_factory=dict)


class PaymentGateway(ABC):
    """Interface of every gateway (spec section 6). Amounts are always integer Rials."""

    @abstractmethod
    def request(
        self,
        amount: int,
        callback_url: str,
        description: str,
        *,
        mobile: str = "",
        order_id: str = "",
    ) -> PaymentRequest:
        """Ask for a payment token. Raise GatewayError if none was issued."""

    @abstractmethod
    def verify(self, authority: str, amount: int) -> VerifyResult:
        """Ask the gateway whether the money really arrived.

        Return ok=False for a definite no; raise GatewayError when unknown, so
        the payment stays open and is checked again later.
        """

    @abstractmethod
    def authority_from_callback(self, params: dict) -> str:
        """Find the payment id in callback parameters. Nothing else there is trusted."""

    def refund(self, ref_id: str, amount: int) -> bool:
        raise NotImplementedError
