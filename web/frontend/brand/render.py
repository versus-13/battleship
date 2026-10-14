"""
Renders the brand sources (icon.svg, og.html) into public/: favicons, PWA icons, the social cards (en, ru).

Needs Playwright for Python with Chromium (Node is not required):
    python3 -m venv /tmp/pw && /tmp/pw/bin/pip install playwright pillow
    /tmp/pw/bin/playwright install chromium
    /tmp/pw/bin/python web/frontend/brand/render.py

The outputs are committed; rerun only after changing icon.svg or og.html.
"""
import io
import shutil
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PUBLIC = HERE.parent / "public"

icon_svg = (HERE / "icon.svg").read_text()
# iOS and maskable icons get the corners cut by the OS, so they must be full-bleed squares
square_svg = icon_svg.replace('rx="14"', 'rx="0"')


def svg_png(page, svg: str, size: int) -> bytes:
    page.set_viewport_size({"width": size, "height": size})
    sized = svg.replace("<svg ", f'<svg width="{size}" height="{size}" ', 1)
    page.set_content(f'<html><body style="margin:0;background:transparent">{sized}</body></html>')
    return page.screenshot(omit_background=True, clip={"x": 0, "y": 0, "width": size, "height": size})


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()

    (PUBLIC / "icon-192.png").write_bytes(svg_png(page, icon_svg, 192))
    (PUBLIC / "icon-512.png").write_bytes(svg_png(page, icon_svg, 512))
    (PUBLIC / "icon-maskable-512.png").write_bytes(svg_png(page, square_svg, 512))
    (PUBLIC / "apple-touch-icon.png").write_bytes(svg_png(page, square_svg, 180))
    ico = [Image.open(io.BytesIO(svg_png(page, icon_svg, s))) for s in (48, 32, 16)]
    ico[0].save(PUBLIC / "favicon.ico", format="ICO", sizes=[(48, 48), (32, 32), (16, 16)], append_images=ico[1:])

    page.set_viewport_size({"width": 1200, "height": 630})
    for query, name in (("", "og.png"), ("?lang=ru", "og-ru.png")):
        page.goto((HERE / "og.html").as_uri() + query)
        page.evaluate("document.fonts.ready")
        page.wait_for_load_state("networkidle")
        png = page.screenshot(clip={"x": 0, "y": 0, "width": 1200, "height": 630})
        # palette PNG: the card is flat colors, ~4x smaller than truecolor
        Image.open(io.BytesIO(png)).convert("RGB").quantize(colors=128, dither=Image.Dither.NONE).save(
            PUBLIC / name, optimize=True
        )
    browser.close()

shutil.copyfile(HERE / "icon.svg", PUBLIC / "favicon.svg")
for f in sorted(PUBLIC.glob("*.*")):
    print(f"{f.name:24} {f.stat().st_size / 1024:7.1f} KB")
