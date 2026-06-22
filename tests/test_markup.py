#!/usr/bin/env python3
"""Structural checks for TRMNL-hosted plugin markup."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MARKUP = ROOT / "markup"
LAYOUTS = (
    "full.liquid",
    "half_horizontal.liquid",
    "half_vertical.liquid",
    "quadrant.liquid",
)


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    print("ok  ", label)


for filename in LAYOUTS:
    text = (MARKUP / filename).read_text(encoding="utf-8")
    active = re.sub(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", "", text, flags=re.S)
    check(
        'class="layout layout--col"' in active,
        f"{filename}: plugin root is column Layout",
    )
    check(
        'class="wm-ko ko-canvas ' in active,
        f"{filename}: content is isolated in KO canvas",
    )
    check('class="screen' not in active, f"{filename}: no plugin-owned Screen")
    check('class="view' not in active, f"{filename}: no plugin-owned View")
    check("position: fixed" not in active, f"{filename}: no fixed viewport root")

shared = (MARKUP / "shard.liquid").read_text(encoding="utf-8")
css = re.sub(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", "", shared, flags=re.S)
check(".ko-canvas {" in css, "shared CSS: defines KO canvas sizing")
check("--ko-revision: 20260622-1415;" in css, "shared CSS: expected revision")
check("flex: 1 1 100%;" in css, "shared CSS: KO canvas fills layout main axis")
check("align-self: stretch;" in css, "shared CSS: KO canvas fills cross axis")
for forbidden in (
    ".trmnl .screen",
    ".trmnl .view",
    "100vw",
    "100vh",
    "transform: none",
    "position: fixed",
):
    check(forbidden not in css, f"shared CSS: excludes {forbidden!r}")

print("\nall markup structure checks passed")
