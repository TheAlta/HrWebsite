"""Scenes PNG (from render.py) -> AVIF + WebP at the sizes frontend/main.css uses.

docker compose exec web python docs/design/scenes/convert.py
"""

import pathlib
import tempfile

from PIL import Image, features

SRC = pathlib.Path(tempfile.gettempdir()) / "scenes-png"
DST = pathlib.Path("/app/static/img/scenes")
DST.mkdir(parents=True, exist_ok=True)
WIDTHS = {"hero": (1920, 960), "tall": (520,)}
avif = features.check("avif")
print("avif:", avif)
for png in sorted(SRC.glob("*.png")):
    name = png.stem  # e.g. hero-light
    kind = name.rsplit("-", 1)[0]
    widths = WIDTHS.get(kind, (1520, 760))
    img = Image.open(png).convert("RGB")
    for w in widths:
        h = round(img.height * w / img.width)
        out = img.resize((w, h), Image.LANCZOS)
        out.save(DST / f"{name}-{w}.webp", "WEBP", quality=72, method=6)
        if avif:
            out.save(DST / f"{name}-{w}.avif", "AVIF", quality=55, speed=4)
for f in sorted(DST.iterdir()):
    print(f.name, f.stat().st_size // 1024, "KB")
