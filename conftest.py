import pytest
from django.core.cache import cache
from django.core.management import call_command

from apps.content.models import ArticlePage, BlogIndexPage, HomePage


@pytest.fixture(autouse=True)
def _isolated_media_and_cache(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    cache.clear()


@pytest.fixture(autouse=True)
def sms_outbox(settings):
    """Every test sends SMS to an in-memory outbox (like Django's mail.outbox)."""
    from apps.notifications.testing import CapturingSMS

    settings.SMS_PROVIDER = "apps.notifications.testing.CapturingSMS"
    CapturingSMS.outbox.clear()
    return CapturingSMS.outbox


@pytest.fixture
def demo_site(db):
    """The full sample site from `seed_demo` (19 pages, settings, snippets)."""
    call_command("seed_demo", verbosity=0)
    return HomePage.objects.get()


@pytest.fixture
def blog(demo_site):
    return BlogIndexPage.objects.get()


@pytest.fixture
def article(blog):
    return ArticlePage.objects.get(slug="post-1")
