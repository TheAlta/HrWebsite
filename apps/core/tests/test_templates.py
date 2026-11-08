from pathlib import Path

from django.conf import settings

TEMPLATES = Path(settings.BASE_DIR) / "templates"


def test_no_comment_tag_spans_lines():
    """Django's {# #} is single-line: a multi-line one is printed on the page as text."""
    broken = [
        f"{path.relative_to(TEMPLATES)}:{number}"
        for path in TEMPLATES.rglob("*.html")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if "{#" in line and "#}" not in line.split("{#", 1)[1]
    ]
    assert broken == []


def test_the_web_font_covers_every_character_in_the_templates():
    """The font is cut to Persian and Latin (static/vendor/README.md); others fall back."""
    from fontTools.ttLib import TTFont

    from apps.core.pdf import FONT

    covered = set(TTFont(Path(settings.BASE_DIR) / "static" / FONT).getBestCmap())
    missing = {
        f"U+{ord(char):04X} {path.name}"
        for path in TEMPLATES.rglob("*.html")
        for char in path.read_text(encoding="utf-8")
        if ord(char) > 0x7F and ord(char) not in covered
    }
    assert missing == set()
