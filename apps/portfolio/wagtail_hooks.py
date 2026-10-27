from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup

from .models import Client, Project, Testimonial


class ClientViewSet(SnippetViewSet):
    model = Client
    icon = "group"
    list_display = ["name", "show_logo", "sort_order"]
    list_filter = ["show_logo"]


class TestimonialViewSet(SnippetViewSet):
    model = Testimonial
    icon = "openquote"
    list_display = ["author_name", "client", "is_featured", "consent_received"]
    list_filter = ["is_featured", "consent_received"]


class ProjectViewSet(SnippetViewSet):
    model = Project
    icon = "folder-open-inverse"
    list_display = ["title", "client", "year", "is_published", "is_featured"]
    list_filter = ["is_published", "is_featured"]


class PortfolioGroup(SnippetViewSetGroup):
    menu_label = "نمونه‌کارها"
    menu_icon = "folder-open-inverse"
    menu_order = 200
    items = (ProjectViewSet, ClientViewSet, TestimonialViewSet)


register_snippet(PortfolioGroup)
