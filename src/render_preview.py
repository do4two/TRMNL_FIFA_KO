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

# device pixel sizes per TRMNL layout
SIZES = {
    "full": (800, 480),
    "half_horizontal": (800, 240),
    "half_vertical": (400, 480),
    "quadrant": (400, 240),
}

SHELL = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="https://trmnl.com/css/latest/plugins.css">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
<style>
  /* preview-only: frame each render at the real device size, 1-bit look */
  body {{ background:#888; margin:0; padding:0; font-family:Inter,Arial,sans-serif; }}
  .device {{ width:{w}px; height:{h}px; background:#fff; overflow:hidden; }}
</style>
</head>
<body class="environment trmnl">
  <div class="device">{body}</div>
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
        chrome, "--headless", "--disable-gpu", "--hide-scrollbars",
        "--force-device-scale-factor=1", "--default-background-color=FFFFFFFF",
        "--window-size=%d,%d" % (w, h),
        "--screenshot=" + png_path, "file://" + os.path.abspath(html_path),
    ], check=True, capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "output", "trmnl_data.json"))
    ap.add_argument("--png", action="store_true", help="also render PNGs via Chrome")
    args = ap.parse_args()

    with open(args.data, encoding="utf-8") as f:
        data = json.load(f)

    env = Environment()
    os.makedirs(PREVIEW, exist_ok=True)

    with open(os.path.join(MARKUP, "shared.liquid"), encoding="utf-8") as f:
        shared = f.read()

    chrome = _chrome() if args.png else None
    if args.png and not chrome:
        print("WARNING: --png requested but no Chrome found; writing HTML only",
              file=sys.stderr)

    for name, (w, h) in SIZES.items():
        with open(os.path.join(MARKUP, name + ".liquid"), encoding="utf-8") as f:
            layout = f.read()
        # TRMNL prepends Shared Markup to each view; mirror that here.
        template = env.from_string(shared + "\n" + layout)
        body = template.render(**data)
        html = SHELL.format(name=name, w=w, h=h, body=body)
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
