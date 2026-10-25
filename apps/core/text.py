"""Persian text normalisation.

Applied when saving and searching, so "علي" (Arabic yeh) and "علی" (Persian yeh)
are treated as the same word.
"""

import re

ZWNJ = "‌"

_CHAR_MAP = str.maketrans(
    {
        "ي": "ی",  # Arabic yeh
        "ى": "ی",  # Arabic alef maksura
        "ك": "ک",  # Arabic kaf
        "ة": "ه",  # teh marbuta
        "ـ": "",  # tatweel (kashida)
    }
)
_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_TO_EN_DIGITS = str.maketrans(_FA_DIGITS + _AR_DIGITS, "0123456789" * 2)
_TO_FA_DIGITS = str.maketrans("0123456789" + _AR_DIGITS, _FA_DIGITS * 2)

_MULTI_ZWNJ = re.compile(f"{ZWNJ}{{2,}}")
_ZWNJ_NEAR_SPACE = re.compile(rf"\s*{ZWNJ}\s+|\s+{ZWNJ}\s*")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")


def to_en_digits(text: str) -> str:
    return text.translate(_TO_EN_DIGITS)


def to_fa_digits(value) -> str:
    return str(value).translate(_TO_FA_DIGITS)


def normalize_fa(text: str) -> str:
    """Unify Arabic/Persian characters and tidy zero-width non-joiners and spaces."""
    text = text.translate(_CHAR_MAP)
    text = _MULTI_ZWNJ.sub(ZWNJ, text)
    text = _ZWNJ_NEAR_SPACE.sub(" ", text)
    text = _MULTI_SPACE.sub(" ", text)
    return text.strip()


def normalize_for_search(text: str) -> str:
    """Normalised form used for both indexed text and search queries."""
    return to_en_digits(normalize_fa(text)).replace(ZWNJ, " ")


_MOBILE_RE = re.compile(r"^09\d{9}$")


def normalize_mobile(value: str) -> str:
    """Return an Iranian mobile number as 09XXXXXXXXX, or raise ValueError.

    Accepts Persian/Arabic digits, spaces, dashes and the +98 / 0098 / 98 prefixes.
    """
    digits = re.sub(r"[\s\-()]", "", to_en_digits(str(value)))
    if digits.startswith("+98"):
        digits = "0" + digits[3:]
    elif digits.startswith("0098"):
        digits = "0" + digits[4:]
    elif digits.startswith("98") and len(digits) == 12:
        digits = "0" + digits[2:]
    elif digits.startswith("9") and len(digits) == 10:
        digits = "0" + digits
    if not _MOBILE_RE.match(digits):
        raise ValueError(f"invalid Iranian mobile number: {value!r}")
    return digits
