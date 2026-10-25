from wagtail.models import Page


class HomePage(Page):
    """Site root page. Real sections (hero, services, testimonials...) arrive in sprint 1."""

    max_count = 1
    parent_page_types = ["wagtailcore.Page"]

    class Meta:
        verbose_name = "صفحه اصلی"
