import pytest

from apps.core.embeds import parse_video_url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.aparat.com/v/AbC12",
        "https://aparat.com/v/AbC12/",
        "https://m.aparat.com/v/AbC12",
    ],
)
def test_aparat(url):
    embed = parse_video_url(url)
    assert embed.provider == "aparat"
    assert embed.embed_url == "https://www.aparat.com/video/video/embed/videohash/AbC12/vt/frame"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "https://youtube.com/shorts/dQw4w9WgXcQ",
    ],
)
def test_youtube(url):
    embed = parse_video_url(url)
    assert embed.provider == "youtube"
    assert embed.embed_url == "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    [
        "https://vimeo.com/123",
        "https://www.youtube.com/watch?v=short",
        "not a url",
        "",
        "https://aparat.com/",
    ],
)
def test_unsupported(url):
    assert parse_video_url(url) is None
