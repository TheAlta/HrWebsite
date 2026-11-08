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
