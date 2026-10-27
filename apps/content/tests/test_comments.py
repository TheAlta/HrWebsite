import pytest

from apps.content.comments import RATE_LIMIT_COUNT
from apps.content.models import Comment

pytestmark = pytest.mark.django_db

VALID = {"name": "علي", "email": "", "text": "نظر من درباره اين مطلب", "website": ""}


def comment_url(article):
    return f"{article.url}comment/"


def test_comment_is_saved_as_pending_and_normalised(client, article):
    response = client.post(comment_url(article), VALID)
    assert response.status_code == 302
    comment = Comment.objects.filter(page=article).latest("created_at")
    assert comment.status == Comment.Status.PENDING
    assert comment.name == "علی"  # Arabic yeh normalised
    assert comment.ip_hash and "127.0.0.1" not in comment.ip_hash


def test_pending_comment_is_not_shown_until_approved(client, article):
    client.post(comment_url(article), {**VALID, "text": "متن مخصوص این تست"})
    assert "متن مخصوص این تست" not in client.get(article.url).content.decode()
    Comment.objects.filter(text="متن مخصوص این تست").update(status=Comment.Status.APPROVED)
    assert "متن مخصوص این تست" in client.get(article.url).content.decode()


def test_honeypot_silently_drops_bot(client, article):
    before = Comment.objects.count()
    response = client.post(
        comment_url(article), {**VALID, "website": "http://spam.example"}, HTTP_HX_REQUEST="true"
    )
    assert response.status_code == 200
    assert "ثبت شد" in response.content.decode()  # bot sees "success"
    assert Comment.objects.count() == before


def test_rate_limit(client, article):
    for _ in range(RATE_LIMIT_COUNT):
        assert client.post(comment_url(article), VALID, HTTP_HX_REQUEST="true").status_code == 200
    response = client.post(comment_url(article), VALID, HTTP_HX_REQUEST="true")
    assert response.status_code == 429
    assert "چند دقیقه دیگر" in response.content.decode()


def test_invalid_comment_shows_errors(client, article):
    response = client.post(comment_url(article), {**VALID, "text": "x"}, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert 'aria-invalid="true"' in response.content.decode()


def test_get_and_disabled_comments_are_404(client, article):
    assert client.get(comment_url(article)).status_code == 404
    article.allow_comments = False
    article.save_revision().publish()
    assert client.post(comment_url(article), VALID).status_code == 404
