"""End-to-end tests in a real browser (spec section 14): the site as a customer uses it.

They run apart from the unit tests: `pytest -m e2e e2e/` (README). Each test starts
a live server on the sample site, drives Chromium through Playwright, and reads
SMS codes from the in-memory outbox, so no outside service is touched.
"""

import os

import pytest
from django.core.management import call_command

from apps.notifications.testing import CapturingSMS

# Playwright's sync API runs an event loop in this thread; Django's ORM calls from
# the test body are still synchronous and safe here
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

PHONE = {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True}
DESKTOP = {"viewport": {"width": 1280, "height": 900}}


def pytest_collection_modifyitems(items):
    for item in items:
        if "/e2e/" in str(item.fspath).replace("\\", "/"):
            item.add_marker(pytest.mark.e2e)
            item.add_marker(pytest.mark.django_db(transaction=True, serialized_rollback=True))


@pytest.fixture(params=["phone", "desktop"])
def browser_context_args(request, browser_context_args):
    """Every flow runs twice: on a phone and on a desktop screen."""
    return {
        **browser_context_args,
        **(PHONE if request.param == "phone" else DESKTOP),
        "locale": "fa-IR",
    }


@pytest.fixture
def site(live_server, settings):
    """The sample site from `seed_demo`, served by a live server."""
    settings.ALLOW_SEED_DEMO = True
    call_command("seed_demo", verbosity=0)
    return live_server.url


@pytest.fixture
def login(page, site):
    """Log in through the real SMS-code form and come back to `next`."""

    def log_in(mobile="09121234567", next_url="/"):
        page.goto(f"{site}/account/login/?next={next_url}")
        page.get_by_label("شماره موبایل").fill(mobile)
        page.get_by_role("button", name="دریافت کد").click()
        page.get_by_label("کد تأیید").wait_for()
        code = [m for m in CapturingSMS.outbox if m["to"] == mobile][-1]["params"]["token"]
        page.get_by_label("کد تأیید").fill(code)
        page.get_by_label("کد تأیید").press("Enter")
        page.wait_for_url(lambda url: "/account/login" not in url)

    return log_in


def pay_at_the_test_bank(page):
    """The local test bank stands in for the gateway; it never runs in production."""
    page.get_by_role("button", name="پرداخت موفق").click()
    page.get_by_text("پرداخت با موفقیت انجام شد").wait_for()
