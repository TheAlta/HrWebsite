import pytest

from apps.core.text import (
    ZWNJ,
    normalize_fa,
    normalize_for_search,
    normalize_mobile,
    to_en_digits,
    to_fa_digits,
)


def test_arabic_yeh_and_kaf_become_persian():
    assert normalize_fa("علي كريمي") == "علی کریمی"


def test_tatweel_removed_and_spaces_collapsed():
    assert normalize_fa("  مـــدیریت   منابع  ") == "مدیریت منابع"


def test_zwnj_cleanup():
    assert normalize_fa(f"می{ZWNJ}{ZWNJ}خواهم") == f"می{ZWNJ}خواهم"
    assert normalize_fa(f"کتاب {ZWNJ} ها") == "کتاب ها"


def test_digit_conversion_both_ways():
    assert to_en_digits("۱۴۰۵/٠٨/۰۳") == "1405/08/03"
    assert to_fa_digits(1405) == "۱۴۰۵"


def test_search_normalisation_matches_variants():
    assert normalize_for_search("كتاب‌هاي ۲") == normalize_for_search("کتاب های 2")


@pytest.mark.parametrize(
    "raw",
    [
        "09121234567",
        "۰۹۱۲۱۲۳۴۵۶۷",
        "+989121234567",
        "00989121234567",
        "989121234567",
        "9121234567",
        "0912 123 4567",
        "0912-123-4567",
    ],
)
def test_mobile_variants_normalise(raw):
    assert normalize_mobile(raw) == "09121234567"


@pytest.mark.parametrize("raw", ["", "0912123456", "08121234567", "abc", "091212345678"])
def test_invalid_mobile_rejected(raw):
    with pytest.raises(ValueError):
        normalize_mobile(raw)
