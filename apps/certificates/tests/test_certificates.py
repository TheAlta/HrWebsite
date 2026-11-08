import re
from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.auth.models import Group
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import SUPPORT, setup_roles
from apps.certificates import services
from apps.certificates.models import Certificate
from apps.events import services as events
from apps.events.models import EventPage, Registration
from apps.notifications.testing import CapturingSMS
from apps.orders import services as orders

pytestmark = pytest.mark.django_db

CODE = re.compile(r"^[2-9A-HJ-NP-Z]{5}-[2-9A-HJ-NP-Z]{5}$")


def issue(event, *registrations):
    return services.issue(event, registrations)


def sms(user, template="certificate-ready"):
    return [m for m in CapturingSMS.outbox if m["to"] == user.mobile and m["template"] == template]


# --- issuing ---------------------------------------------------------------------------------


def test_issue_copies_the_event_and_name_and_texts_the_code(ended_event, seat, attendee):
    registration = seat(attendee)
    [certificate] = issue(ended_event, registration)
    assert CODE.match(certificate.code)
    assert certificate.full_name == "سارا محمدی"
    assert certificate.event_title == "دوره مصاحبه ساختاریافته"
    assert certificate.event_kind == "دوره"
    assert certificate.instructor == "آرزو زحمتبران"
    assert certificate.event_start == ended_event.start_at
    [message] = sms(attendee)
    assert message["params"]["token"] == certificate.code
    assert message["params"]["token20"] == "دوره مصاحبه ساختاریافته"


def test_unticked_attendees_get_nothing_and_stay_eligible(ended_event, seat, attendee, nameless):
    present, absent = seat(attendee), seat(nameless)
    issue(ended_event, present)
    assert list(services.eligible(ended_event)) == [absent]
    assert not sms(nameless)


def test_a_second_issue_skips_those_who_have_one(ended_event, seat, attendee):
    registration = seat(attendee)
    issue(ended_event, registration)
    assert issue(ended_event, registration) == []
    assert Certificate.objects.count() == 1
    assert len(sms(attendee)) == 1


def test_only_confirmed_registrations_are_eligible(ended_event, seat, attendee, nameless):
    seat(attendee, status=Registration.Status.WAITLIST)
    seat(nameless, status=Registration.Status.CANCELLED)
    assert not services.eligible(ended_event).exists()


def test_not_before_the_event_ends(make_event, attendee):
    event = make_event(issues_certificate=True)
    registration = Registration.objects.create(event=event, user=attendee, status="paid")
    with pytest.raises(services.CertificateError, match="بعد از پایان"):
        issue(event, registration)


def test_not_for_an_event_without_certificates(ended_event, seat, attendee):
    EventPage.objects.filter(pk=ended_event.pk).update(issues_certificate=False)
    ended_event.refresh_from_db()
    with pytest.raises(services.CertificateError, match="فعال نیست"):
        issue(ended_event, seat(attendee))


def test_a_registration_of_another_event_is_ignored(ended_event, make_event, attendee):
    other = make_event(issues_certificate=True, start_at=timezone.now() - timedelta(days=2))
    stranger = Registration.objects.create(event=other, user=attendee, status="paid")
    assert issue(ended_event, stranger) == []


def test_a_taken_code_is_drawn_again(ended_event, seat, attendee, nameless):
    [first] = issue(ended_event, seat(attendee))
    with mock.patch.object(services, "new_code", side_effect=[first.code, "ABCDE-FGHJK"]):
        [second] = issue(ended_event, seat(nameless))
    assert second.code == "ABCDE-FGHJK"


def test_a_parallel_issue_of_the_same_seat_returns_none(ended_event, seat, attendee):
    registration = seat(attendee)
    issue(ended_event, registration)
    with transaction.atomic():
        assert services._create(registration, ended_event, None) is None


def test_later_edits_never_change_an_issued_certificate(ended_event, seat, attendee):
    [certificate] = issue(ended_event, seat(attendee))
    EventPage.objects.filter(pk=ended_event.pk).update(title="عنوان تازه")
    attendee.first_name = "نام تازه"
    attendee.save()
    certificate.refresh_from_db()
    assert certificate.event_title == "دوره مصاحبه ساختاریافته"
    assert services.fill_name(certificate) == "سارا محمدی"


# --- codes -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "typed",
    ["abcde-fghjk", " ABCDE FGHJK ", "ABCDEFGHJK", "abcde_fghjk"],
)
def test_typed_codes_are_normalised(typed):
    assert services.normalize_code(typed) == "ABCDE-FGHJK"


def test_persian_digits_are_read():
    assert services.normalize_code("۲۳۴۵۶-۷۸۹AB") == "23456-789AB"


@pytest.mark.parametrize("typed", ["", "ABCDE", "ABCDE-FGHJK-L", "O0OOO-11111"])
def test_impossible_codes_find_nothing(typed):
    assert services.normalize_code(typed) == ""
    assert services.lookup(typed) is None


def test_new_codes_avoid_look_alike_characters():
    for _ in range(200):
        assert CODE.match(services.new_code())


# --- the public check ------------------------------------------------------------------------


def verify(client, code):
    return client.get(reverse("certificates:detail", args=[code]))


def test_a_valid_certificate_is_shown(client, ended_event, seat, attendee):
    [certificate] = issue(ended_event, seat(attendee))
    response = verify(client, certificate.code)
    content = response.content.decode()
    assert response.status_code == 200
    assert "این گواهی معتبر است." in content
    assert "سارا محمدی" in content
    assert "دوره مصاحبه ساختاریافته" in content
    assert response["X-Robots-Tag"] == "noindex"
    assert '<meta name="robots" content="noindex">' in content


def test_the_form_finds_a_code_typed_loosely(client, ended_event, seat, attendee):
    [certificate] = issue(ended_event, seat(attendee))
    typed = certificate.code.lower().replace("-", " ")
    response = client.get(reverse("certificates:verify"), {"code": typed})
    assert "این گواهی معتبر است." in response.content.decode()


def test_a_revoked_certificate_says_so(client, ended_event, seat, attendee):
    [certificate] = issue(ended_event, seat(attendee))
    services.revoke(certificate)
    content = verify(client, certificate.code).content.decode()
    assert "این گواهی باطل شده است." in content
    assert "معتبر است" not in content


def test_an_unknown_code_is_not_found(client):
    content = verify(client, "ABCDE-FGHJK").content.decode()
    assert "گواهی با این کد پیدا نشد" in content


def test_the_empty_page_shows_no_error(client):
    response = client.get(reverse("certificates:verify"), {"utm_source": "x"})
    content = response.content.decode()
    assert "پیدا نشد" not in content
    assert "field-error" not in content


def test_revoking_twice_is_refused(ended_event, seat, attendee):
    [certificate] = issue(ended_event, seat(attendee))
    services.revoke(certificate)
    with pytest.raises(services.CertificateError):
        services.revoke(certificate)


# --- downloads -------------------------------------------------------------------------------


def download_url(certificate):
    return reverse("certificates:download", args=[certificate.code])


def test_the_attendee_downloads_a_real_pdf(client, ended_event, seat, attendee):
    [certificate] = issue(ended_event, seat(attendee))
    client.force_login(attendee)
    response = client.get(download_url(certificate))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Cache-Control"] == "private, no-store"
    assert response.content.startswith(b"%PDF")


def test_the_pdf_carries_the_verify_link_and_qr(client, ended_event, seat, attendee, settings):
    [certificate] = issue(ended_event, seat(attendee))
    client.force_login(attendee)
    with mock.patch("apps.certificates.services.render_pdf", return_value=b"%PDF-1") as render:
        client.get(download_url(certificate))
    context = render.call_args.args[1]
    assert context["verify_url"].endswith(f"/certificates/{certificate.code}/")
    assert context["verify_url"].startswith("http")
    assert context["qr"].startswith("data:image/svg+xml")


def test_another_customer_gets_404(client, ended_event, seat, attendee, nameless):
    [certificate] = issue(ended_event, seat(attendee))
    client.force_login(nameless)
    assert client.get(download_url(certificate)).status_code == 404


def test_download_needs_login(client, ended_event, seat, attendee):
    [certificate] = issue(ended_event, seat(attendee))
    response = client.get(download_url(certificate))
    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


def test_a_revoked_certificate_is_gone_for_the_attendee(client, ended_event, seat, attendee):
    [certificate] = issue(ended_event, seat(attendee))
    services.revoke(certificate)
    client.force_login(attendee)
    assert client.get(download_url(certificate)).status_code == 404


def test_staff_still_open_a_revoked_one(admin_client, ended_event, seat, attendee):
    [certificate] = issue(ended_event, seat(attendee))
    services.revoke(certificate)
    assert admin_client.get(download_url(certificate)).content.startswith(b"%PDF")


def test_without_a_name_the_attendee_is_sent_to_the_profile(client, ended_event, seat, nameless):
    [certificate] = issue(ended_event, seat(nameless))
    assert certificate.full_name == ""
    client.force_login(nameless)
    response = client.get(download_url(certificate))
    assert response.status_code == 302
    assert response.url == reverse("accounts:profile")

    nameless.first_name, nameless.last_name = "رضا", "کریمی"
    nameless.save()
    assert client.get(download_url(certificate)).status_code == 200
    certificate.refresh_from_db()
    assert certificate.full_name == "رضا کریمی"


def test_staff_are_sent_to_the_edit_form_for_a_nameless_one(
    admin_client, ended_event, seat, nameless
):
    [certificate] = issue(ended_event, seat(nameless))
    response = admin_client.get(download_url(certificate))
    assert response.url == reverse("panel_certificates:edit", args=[certificate.pk])


def test_courses_page_links_the_certificate(client, ended_event, seat, attendee):
    [certificate] = issue(ended_event, seat(attendee))
    client.force_login(attendee)
    content = client.get(reverse("accounts:courses")).content.decode()
    assert download_url(certificate) in content
    assert "دریافت گواهی حضور" in content


# --- refunds ---------------------------------------------------------------------------------


def test_a_refund_revokes_the_certificate(make_event, attendee):
    event = make_event(price=10_000_000, issues_certificate=True)
    registration = events.register(attendee, event)
    with transaction.atomic():
        orders.mark_paid(registration.order)
    orders.fulfil(registration.order)
    start = timezone.now() - timedelta(days=1)
    EventPage.objects.filter(pk=event.pk).update(start_at=start, end_at=start + timedelta(hours=2))
    event.refresh_from_db()
    [certificate] = issue(event, registration)

    orders.refund(registration.order)

    certificate.refresh_from_db()
    assert not certificate.is_valid


def test_the_owner_cancelling_a_free_seat_revokes_it(ended_event, seat, attendee):
    registration = seat(attendee)
    [certificate] = issue(ended_event, registration)
    events.cancel(registration, by_owner=True)
    certificate.refresh_from_db()
    assert not certificate.is_valid


def test_an_attendee_cannot_drop_out_after_the_event(client, ended_event, seat, attendee):
    registration = seat(attendee)
    [certificate] = issue(ended_event, registration)
    client.force_login(attendee)
    assert (
        reverse("events:cancel", args=[registration.pk])
        not in client.get(reverse("accounts:courses")).content.decode()
    )
    client.post(reverse("events:cancel", args=[registration.pk]))
    registration.refresh_from_db()
    certificate.refresh_from_db()
    assert registration.status == Registration.Status.PAID
    assert certificate.is_valid


# --- panel -----------------------------------------------------------------------------------


def issue_url(event):
    return reverse("panel_certificates:issue", args=[event.pk])


def test_the_issue_page_lists_attendees_all_ticked(admin_client, ended_event, seat, attendee):
    registration = seat(attendee)
    content = admin_client.get(issue_url(ended_event)).content.decode()
    assert "سارا محمدی" in content
    assert re.search(rf'value="{registration.pk}"[^>]*checked', content)


def test_the_issue_page_issues_the_ticked_ones(admin_client, ended_event, seat, attendee, nameless):
    present = seat(attendee)
    seat(nameless)
    response = admin_client.post(issue_url(ended_event), {"registrations": [present.pk]})
    assert response.url == reverse("panel_certificates:index")
    certificate = Certificate.objects.get()
    assert certificate.registration == present
    assert certificate.issued_by.mobile == "09120000000"


def test_issuing_before_the_end_shows_the_reason(admin_client, make_event, attendee):
    event = make_event(issues_certificate=True)
    registration = Registration.objects.create(event=event, user=attendee, status="paid")
    response = admin_client.post(
        issue_url(event), {"registrations": [registration.pk]}, follow=True
    )
    assert "بعد از پایان رویداد" in response.content.decode()
    assert not Certificate.objects.exists()


def test_the_page_header_offers_issuing_only_when_it_can(admin_client, ended_event, make_event):
    edit = reverse("wagtailadmin_pages:edit", args=[ended_event.pk])
    assert issue_url(ended_event) in admin_client.get(edit).content.decode()

    upcoming = make_event(issues_certificate=True)
    edit = reverse("wagtailadmin_pages:edit", args=[upcoming.pk])
    assert issue_url(upcoming) not in admin_client.get(edit).content.decode()


def test_the_listing_offers_issuing(admin_client, ended_event):
    explore = reverse("wagtailadmin_explore", args=[ended_event.get_parent().pk])
    assert issue_url(ended_event) in admin_client.get(explore).content.decode()


def test_staff_can_revoke_from_the_panel(admin_client, ended_event, seat, attendee):
    [certificate] = issue(ended_event, seat(attendee))
    inspect = reverse("panel_certificates:inspect", args=[certificate.pk])
    revoke = reverse("panel_certificates:revoke", args=[certificate.pk])
    assert revoke in admin_client.get(inspect).content.decode()
    admin_client.post(revoke)
    certificate.refresh_from_db()
    assert not certificate.is_valid
    assert revoke not in admin_client.get(inspect).content.decode()


def test_certificates_cannot_be_added_or_deleted_by_hand(admin_client, ended_event, seat, attendee):
    [certificate] = issue(ended_event, seat(attendee))
    assert admin_client.get(reverse("panel_certificates:add")).status_code == 302
    admin_client.post(reverse("panel_certificates:delete", args=[certificate.pk]))
    assert Certificate.objects.filter(pk=certificate.pk).exists()


def test_support_role_can_issue(client, django_user_model, ended_event, seat, attendee):
    setup_roles()
    staff = django_user_model.objects.create_user("09130000000", password="x")
    staff.groups.add(Group.objects.get(name=SUPPORT))
    client.force_login(staff)
    registration = seat(attendee)
    client.post(issue_url(ended_event), {"registrations": [registration.pk]})
    assert Certificate.objects.filter(registration=registration).exists()


def test_a_customer_cannot_open_the_issue_page(client, ended_event, attendee):
    client.force_login(attendee)
    assert client.get(issue_url(ended_event)).status_code in (302, 403)


def test_event_page_mentions_the_certificate(client, make_event):
    event = make_event(issues_certificate=True)
    assert "گواهی حضور با کد استعلام" in client.get(event.url).content.decode()
