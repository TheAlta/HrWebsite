"""Render the demo's drawn scenes to PNG (REPORT #055). Not part of the app.

Run inside the web container (it has Playwright):
    docker compose exec web python docs/design/scenes/render.py
then convert.py writes the AVIF/WebP files the site uses.
"""

import json
import pathlib
import tempfile

from playwright.sync_api import sync_playwright

OUT = pathlib.Path(tempfile.gettempdir()) / "scenes-png"  # outside the repository
OUT.mkdir(parents=True, exist_ok=True)
DEMO = "file:///app/docs/design/demo.html"
KEY_THEME, KEY_STATE = "arezoo-hr:theme", "arezoo-hr:state:v3"


def grab(page, selector):
    return page.eval_on_selector(selector, "e => e.outerHTML")


with sync_playwright() as p:
    browser = p.chromium.launch()
    for theme in ("light", "dark"):
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.add_init_script(f"localStorage.setItem('{KEY_THEME}', '{theme}')")
        page.goto(DEMO + "#/")
        page.wait_for_timeout(1500)
        svgs = {
            "hero": (grab(page, "svg.hero-scene"), 1440, 860),
            "window-0": (grab(page, ".about-visual svg"), 760, 330),
            "window-2-plain": (grab(page, ".event-feature .ev-visual svg"), 760, 330),
        }
        thumbs = page.eval_on_selector_all(
            ".insight-card .thumb svg", "es => es.map(e => e.outerHTML)"
        )
        svgs["window-2"] = (thumbs[0], 760, 330)
        svgs["window-1"] = (thumbs[1], 760, 330)
        # Sign in as the demo customer to reach the panel's tall scene.
        state = json.loads(page.evaluate(f"localStorage.getItem('{KEY_STATE}')"))
        state["sessionUserId"] = "u_maryam"
        page.evaluate(f"s => localStorage.setItem('{KEY_STATE}', s)", json.dumps(state))
        page.goto(DEMO + "#/account")
        page.reload()
        page.wait_for_timeout(1500)
        svgs["tall"] = (grab(page, ".side-promo svg"), 260, 380)
        for name, (markup, w, h) in svgs.items():
            scale = 2 if name != "hero" else 1920 / 1440
            pw, ph = round(w * scale), round(h * scale)
            shot = ctx.new_page()
            shot.set_viewport_size({"width": pw, "height": ph})
            shot.set_content(
                "<html><body style='margin:0'>"
                f"<div style='width:{pw}px;height:{ph}px;transform:scaleX(-1)'>"
                + markup.replace("<svg ", f"<svg width='{pw}' height='{ph}' ", 1)
                + "</div></body></html>"
            )
            shot.wait_for_timeout(300)
            shot.screenshot(path=str(OUT / f"{name}-{theme}.png"))
            shot.close()
            print(theme, name, pw, ph)
        ctx.close()
    browser.close()
