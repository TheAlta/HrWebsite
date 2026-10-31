from abc import ABC, abstractmethod
from dataclasses import dataclass


class SMSError(Exception):
    """The provider rejected the message or could not be reached."""


@dataclass
class SMSResult:
    message_id: str
    raw: dict


class SMSProvider(ABC):
    """Interface every SMS provider implements (spec section 9: providers behind an adapter).

    Transactional messages use pre-approved templates ("Pattern"); the template
    text lives in the provider panel, the site only sends its name and tokens.
    """

    @abstractmethod
    def send_template(self, to: str, template: str, params: dict) -> SMSResult:
        """Send `template` to `to` (09XXXXXXXXX). Raise SMSError on failure."""
