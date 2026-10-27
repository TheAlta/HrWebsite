from django.db import models
from wagtail.admin.panels import FieldPanel
from wagtail.models import Page


class BasePage(Page):
    """Common parent of every site page: share image and breadcrumbs."""

    og_image = models.ForeignKey(
        "wagtailimages.Image",
        verbose_name="تصویر اشتراک‌گذاری",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="پیش‌نمایش لینکدین و تلگرام. اندازه پیشنهادی ۱۲۰۰×۶۳۰",
    )

    promote_panels = [*Page.promote_panels, FieldPanel("og_image")]

    og_type = "website"  # Open Graph type; articles override it

    class Meta:
        abstract = True

    def get_share_image(self):
        return self.og_image

    def get_breadcrumbs(self):
        """Ancestors below the tree root, home page first."""
        return self.get_ancestors().filter(depth__gt=1).specific()
