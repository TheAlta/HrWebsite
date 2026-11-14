import pytest
from django_q.tasks import async_task, result

pytestmark = pytest.mark.django_db


def test_healthz_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_rejects_post(client):
    assert client.post("/healthz").status_code == 405


def test_home_page_renders_rtl_persian(client):
    # Without sections the home page shows a hint for the editor (sprint 1)
    response = client.get("/")
    assert response.status_code == 200
    html = response.content.decode()
    assert 'dir="rtl"' in html
    assert "بخش‌های صفحه اصلی را از پنل مدیریت اضافه کنید" in html


def test_unknown_url_gives_persian_404(client):
    response = client.get("/no-such-page/")
    assert response.status_code == 404
    assert "پیدا نشد" in response.content.decode()


def test_background_task_runs():
    # Q_CLUSTER runs synchronously in test settings
    task_id = async_task("apps.core.tasks.ping", "hello")
    assert result(task_id) == "hello"


def test_favicon_ico_points_to_the_svg_icon(client):
    response = client.get("/favicon.ico")
    assert response.status_code == 301
    assert response.url.endswith(".svg")


@pytest.mark.parametrize(
    ("cookie", "expected"),
    [("dark", '<html lang="fa" dir="rtl" data-theme="dark">'), ("light", 'data-theme="light"')],
)
def test_the_chosen_theme_is_on_the_page_before_it_paints(client, cookie, expected):
    """The switch keeps the choice in a cookie; the server writes it on <html> (REPORT #055)."""
    client.cookies["theme"] = cookie
    assert expected in client.get("/").content.decode()


def test_without_a_valid_theme_the_device_decides(client):
    client.cookies["theme"] = '"><script>'
    html = client.get("/").content.decode()
    assert "data-theme" not in html.split("<head>", 1)[0]
