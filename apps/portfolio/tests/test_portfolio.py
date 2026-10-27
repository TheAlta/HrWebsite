import pytest

# Module import: a bare "Testimonial" name would be collected by pytest as a test class
from apps.portfolio import models as portfolio
from apps.portfolio.models import Client

pytestmark = pytest.mark.django_db


def test_testimonials_need_consent_to_be_visible():
    shown = portfolio.Testimonial.objects.create(
        author_name="الف", quote="خوب", consent_received=True
    )
    portfolio.Testimonial.objects.create(author_name="ب", quote="خوب", consent_received=False)
    assert list(portfolio.Testimonial.objects.visible()) == [shown]


def test_portfolio_page_hides_unconsented_content(client):
    from django.core.management import call_command

    call_command("seed_demo", verbosity=0)
    portfolio.Testimonial.objects.create(
        author_name="بدون رضایت", quote="نباید دیده شود", consent_received=False
    )
    Client.objects.filter(name="شرکت آلفا").update(show_logo=False)

    html = client.get("/portfolio/").content.decode()
    assert "نباید دیده شود" not in html
    assert 'alt="شرکت آلفا"' not in html
    assert 'alt="بانک دلتا"' in html
