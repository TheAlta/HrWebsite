from wagtail.admin.panels import FieldPanel
from wagtail.fields import StreamField

from ..blocks import HomeBlock
from .base import BasePage


class HomePage(BasePage):
    """Site root. Sections are StreamField blocks so they can be reordered in the panel."""

    body = StreamField(HomeBlock(), blank=True, verbose_name="بخش‌ها")

    content_panels = [*BasePage.content_panels, FieldPanel("body")]

    max_count = 1
    parent_page_types = ["wagtailcore.Page"]

    class Meta:
        verbose_name = "صفحه اصلی"
