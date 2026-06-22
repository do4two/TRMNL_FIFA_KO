#!/usr/bin/env python3
"""
Render the TRMNL Liquid layouts locally so you can eyeball them before pasting
into TRMNL. For each layout it prepends shared.liquid (mirroring how TRMNL
prepends "Shared Markup"), renders with the computed data, and wraps the result
in the TRMNL HTML shell at the exact device size for that layout.

  python src/render_preview.py             # uses output/trmnl_data.json
  python src/render_preview.py --data output/trmnl_data.json
  python src/render_preview.py --png       # also write preview/<layout>.png
                                           # (needs Google Chrome installed)

Output: preview/<layout>.html (+ optional .png), each sized to the device.
"""
import argparse
import glob
import os
import json
import shutil
import subprocess
import sys

from liquid import Environment

HERE = os.path.dirname(__file__)
ROOT = os.path.dirname(HERE)
MARKUP = os.path.join(ROOT, "markup")
PREVIEW = os.path.join(ROOT, "preview")

# Preview targets:
# name -> (layout file, view class, mashup class or None, screen classes,
#          physical width/height).
#
# TRMNL X uses the Framework's 1040x780 logical `screen--v2` canvas and the
# Framework itself scales it by 1.8 to the 1872x1404 panel.
SIZES = {
    "full": (
        "full", "view--full", None, "screen--v2 screen--4bit", 1872, 1404
    ),
    "full_og": (
        "full", "view--full", None, "screen--og screen--1bit", 800, 480
    ),
    "half_horizontal": (
        "half_horizontal", "view--half_horizontal", "mashup--1Tx1B",
        "screen--v2 screen--4bit", 1872, 702
    ),
    "half_vertical": (
        "half_vertical", "view--half_vertical", "mashup--1Lx1R",
        "screen--v2 screen--4bit", 936, 1404
    ),
    "quadrant": (
        "quadrant", "view--quadrant", "mashup--2x2",
        "screen--v2 screen--4bit", 936, 702
    ),
}

SHELL = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="https://trmnl.com/css/3.1.1/plugins.css">
<script src="https://trmnl.com/js/3.1.1/plugins.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
<style>
  html, body {{ width:{w}px; height:{h}px; margin:0; overflow:hidden; }}
  body {{ background:#888; font-family:Inter,Arial,sans-serif; }}
  .preview-device {{ width:{w}px; height:{h}px; overflow:hidden; background:#fff; }}
</style>
</head>
<body class="trmnl environment">
  <div class="preview-device">
    <div class="screen {screen_classes}">
{view_markup}
    </div>
  </div>
</body>
</html>
"""

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]


def _chrome():
    for c in CHROME_CANDIDATES:
        if c and os.path.exists(c):
            return c
    return None


def _screenshot(chrome, html_path, png_path, w, h):
    subprocess.run([
        chrome, "--headless", "--no-sandbox", "--disable-gpu",
        "--disable-crash-reporter", "--hide-scrollbars",
        "--user-data-dir=/tmp/trmnl-preview-chrome",
        "--force-device-scale-factor=1", "--default-background-color=FFFFFFFF",
        "--window-size=%d,%d" % (w, h),
        "--screenshot=" + png_path, "file://" + os.path.abspath(html_path),
    ], check=True, capture_output=True)


def _view_markup(body, view_class, mashup_class):
    content_view = '      <div class="view %s">\n%s\n      </div>' % (
        view_class, body
    )
    if not mashup_class:
        return content_view

    view_count = 4 if mashup_class == "mashup--2x2" else 2
    empty_view = '      <div class="view %s"></div>' % view_class
    views = [content_view] + [empty_view] * (view_count - 1)
    return '      <div class="mashup %s">\n%s\n      </div>' % (
        mashup_class, "\n".join(views)
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "output", "trmnl_data.json"))
    ap.add_argument("--png", action="store_true", help="also render PNGs via Chrome")
    args = ap.parse_args()

    with open(args.data, encoding="utf-8") as f:
        data = json.load(f)

    env = Environment()
    os.makedirs(PREVIEW, exist_ok=True)

    with open(os.path.join(MARKUP, "shard.liquid"), encoding="utf-8") as f:
        shared = f.read()

    chrome = _chrome() if args.png else None
    if args.png and not chrome:
        print("WARNING: --png requested but no Chrome found; writing HTML only",
              file=sys.stderr)

    for name, (
        layout_name, view_class, mashup_class, screen_classes, w, h
    ) in SIZES.items():
        with open(os.path.join(MARKUP, layout_name + ".liquid"), encoding="utf-8") as f:
            layout = f.read()
        # TRMNL prepends Shared Markup to each view; mirror that here.
        template = env.from_string(shared + "\n" + layout)
        body = template.render(**data)
        html = SHELL.format(
            view_markup=_view_markup(body, view_class, mashup_class),
            screen_classes=screen_classes,
            w=w,
            h=h,
        )
        html_out = os.path.join(PREVIEW, name + ".html")
        with open(html_out, "w", encoding="utf-8") as f:
            f.write(html)
        msg = os.path.relpath(html_out, ROOT)
        if chrome:
            png_out = os.path.join(PREVIEW, name + ".png")
            _screenshot(chrome, html_out, png_out, w, h)
            msg += "  +  " + os.path.relpath(png_out, ROOT)
        print("rendered", msg)


if __name__ == "__main__":
    main()
