"""Video embeds for Aparat and YouTube, built locally from the URL.

Wagtail's oEmbed would fetch provider APIs from the server, which fails for
YouTube on Iranian hosting, so the iframe URL is derived here instead.
"""

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True)
class VideoEmbed:
    provider: str
    video_id: str
    embed_url: str


_APARAT_RE = re.compile(r"^/(?:v|video/video/embed/videohash)/([A-Za-z0-9]+)")
_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def parse_video_url(url: str) -> VideoEmbed | None:
    """Return the embed for an Aparat or YouTube URL, or None if unsupported."""
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").removeprefix("www.").removeprefix("m.")

    if host == "aparat.com":
        match = _APARAT_RE.match(parsed.path)
        if match:
            vid = match.group(1)
            return VideoEmbed(
                "aparat", vid, f"https://www.aparat.com/video/video/embed/videohash/{vid}/vt/frame"
            )
        return None

    vid = None
    if host == "youtu.be":
        vid = parsed.path.lstrip("/").split("/")[0]
    elif host == "youtube.com":
        if parsed.path == "/watch":
            vid = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith(("/embed/", "/shorts/", "/live/")):
            vid = parsed.path.split("/")[2]
    if vid and _YOUTUBE_ID_RE.match(vid):
        return VideoEmbed("youtube", vid, f"https://www.youtube-nocookie.com/embed/{vid}")
    return None
