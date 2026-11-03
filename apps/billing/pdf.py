from pathlib import Path

from django.contrib.staticfiles import finders
from django.template.loader import render_to_string

FONT = "fonts/vazirmatn/Vazirmatn-Variable.woff2"


def render_pdf(template: str, context: dict) -> bytes:
    # Imported here: it loads system libraries, and a problem with them must only
    # stop PDF downloads, not the whole site
    from weasyprint import HTML

    font_url = Path(finders.find(FONT)).as_uri()
    return HTML(string=render_to_string(template, {**context, "font_url": font_url})).write_pdf()
