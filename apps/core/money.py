"""Money helpers. Amounts are always stored as integer Rials (never float);
Tomans exist only for display. See spec section 7.
"""

from .text import to_fa_digits

FA_THOUSANDS_SEP = "٬"


def _ensure_rial(amount) -> int:
    # bool is a subclass of int; float/Decimal are rejected on purpose
    if not isinstance(amount, int) or isinstance(amount, bool):
        raise TypeError(f"amount must be an int number of Rials, got {type(amount).__name__}")
    return amount


def rial_to_toman(amount: int) -> int:
    return _ensure_rial(amount) // 10


def toman_to_rial(amount: int) -> int:
    return _ensure_rial(amount) * 10


def format_toman(amount: int, *, suffix: bool = True) -> str:
    """12000000 Rials -> '۱٬۲۰۰٬۰۰۰ تومان'."""
    toman = rial_to_toman(amount)
    text = to_fa_digits(f"{toman:,}".replace(",", FA_THOUSANDS_SEP))
    return f"{text} تومان" if suffix else text
