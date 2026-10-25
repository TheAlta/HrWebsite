from decimal import Decimal

import pytest

from apps.core.money import format_toman, rial_to_toman, toman_to_rial


def test_rial_toman_conversion():
    assert rial_to_toman(12_000_000) == 1_200_000
    assert toman_to_rial(1_200_000) == 12_000_000


def test_format_toman_uses_persian_digits_and_separator():
    assert format_toman(12_000_000) == "۱٬۲۰۰٬۰۰۰ تومان"
    assert format_toman(5_000, suffix=False) == "۵۰۰"


@pytest.mark.parametrize("bad", [1200.0, Decimal("1200"), True, "1200"])
def test_non_integer_amounts_rejected(bad):
    # Money must never be float (spec section 7)
    with pytest.raises(TypeError):
        rial_to_toman(bad)
