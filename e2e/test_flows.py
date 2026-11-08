"""The four customer journeys of spec section 14, on a phone and a desktop screen."""

from axe_playwright_python.sync_playwright import Axe
from django.urls import reverse
from playwright.sync_api import expect

from apps.booking.models import Booking
from apps.crm.models import Lead
from apps.events.models import Registration
from apps.shop.models import DownloadToken

from .conftest import pay_at_the_test_bank

WCAG = {"runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]}}


def assert_accessible(page):
    """axe-core on the page as the customer sees it, so a redesign cannot quietly break it."""
    results = Axe().run(page, options=WCAG)
    assert results.violations_count == 0, results.generate_report()


def test_consultation_form(page, site):
    page.goto(f"{site}/consultation/")
    assert_accessible(page)
    form = page.locator("#consultation-form")  # the footer has its own mobile field
    form.get_by_text("سازمانم").click()
    form.get_by_text("ارزیابی عملکرد").first.click()
    form.get_by_role("button", name="مرحله بعد").click()
    form.get_by_label("نام سازمان").fill("شرکت نمونه")
    form.get_by_role("button", name="مرحله بعد").click()
    form.get_by_label("نام و نام خانوادگی").fill("مریم احمدی")
    form.get_by_label("موبایل").fill("09121234567")
    form.get_by_role("button", name="ثبت درخواست").click()

    expect(page.get_by_text("درخواست شما ثبت شد", exact=True)).to_be_visible()
    lead = Lead.objects.get()
    assert lead.name == "مریم احمدی"
    page.wait_for_function("window.dataLayer && window.dataLayer.length > 0")
    assert page.evaluate("window.dataLayer.map(e => e.event)") == ["generate_lead"]


def test_booking_a_paid_session(page, site, login):
    login(next_url="/booking/")
    assert_accessible(page)
    page.get_by_role("link", name="انتخاب زمان").first.click()
    second_day = page.get_by_role("tab").nth(1)
    second_day.click()
    expect(second_day).to_have_attribute("aria-selected", "true")  # Alpine has switched days
    page.locator("button[name=start]:visible").first.click()
    assert_accessible(page)
    page.get_by_role("button", name="پرداخت و ثبت رزرو").click()
    pay_at_the_test_bank(page)

    booking = Booking.objects.get()
    assert booking.status == Booking.Status.CONFIRMED
    page.goto(f"{site}/account/sessions/")
    expect(page.get_by_text(booking.session_type.title)).to_be_visible()


def test_buying_a_digital_book(page, site, login):
    page.goto(f"{site}/shop/")
    page.get_by_role("link", name="راهنمای مصاحبه (PDF)").first.click()
    assert_accessible(page)
    page.get_by_role("button", name="افزودن به سبد").click()
    page.get_by_role("link", name="ادامه خرید").click()
    login(next_url="/checkout/")
    page.get_by_role("button", name="پرداخت").click()
    pay_at_the_test_bank(page)
    page.wait_for_function("window.dataLayer && window.dataLayer.length > 0")
    assert page.evaluate("window.dataLayer.map(e => e.event)") == ["purchase"]

    token = DownloadToken.objects.get()
    page.goto(f"{site}/account/downloads/")
    with page.expect_download() as download:
        page.locator(f"a[href='{reverse('shop:download', args=[token.token])}']").click()
    assert download.value.suggested_filename.endswith(".pdf")
    token.refresh_from_db()
    assert token.downloads_left < 5


def test_registering_for_a_paid_course(page, site, login):
    page.goto(f"{site}/events/")
    page.get_by_role("link", name="دوره ارزیابی عملکرد").first.click()
    event_url = page.url
    page.get_by_role("link", name="ورود و ثبت‌نام").click()
    login(next_url=event_url.replace(site, ""))
    page.get_by_role("button", name="ثبت‌نام و پرداخت").click()
    pay_at_the_test_bank(page)

    assert Registration.objects.get().status == Registration.Status.PAID
    page.goto(event_url)
    expect(page.get_by_text("ثبت‌نام شما قطعی است.")).to_be_visible()
    assert_accessible(page)
