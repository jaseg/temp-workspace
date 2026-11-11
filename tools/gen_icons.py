#!/usr/bin/env python3
"""Draw the toolbar icons (plugin/icons/pole-{light,dark}-{24,48}.png).

Usage: python3 tools/gen_icons.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "plugin" / "icons"
SS = 4  # supersampling factor
COPPER = (205, 120, 60, 255)


def icon(size: int, dark: bool) -> Image.Image:
    big = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    u = size * SS / 24
    pole = (220, 220, 220, 255) if dark else (70, 60, 52, 255)
    wire = COPPER
    # two poles with a drooping wire between them
    for x in (5, 19):
        d.line([(x * u, 22 * u), (x * u, 6 * u)], fill=pole, width=int(2.2 * u))
        d.line([((x - 3) * u, 7 * u), ((x + 3) * u, 7 * u)], fill=pole, width=int(1.6 * u))
    pts = []
    for i in range(33):
        t = i / 32
        x = 5 + 14 * t
        y = 6 + 5.5 * (1 - (2 * t - 1) ** 2)
        pts.append((x * u, y * u))
    d.line(pts, fill=wire, width=int(1.6 * u), joint="curve")
    return big.resize((size, size), Image.LANCZOS)


def main() -> int:
    ICONS.mkdir(parents=True, exist_ok=True)
    for size in (24, 48):
        for dark in (False, True):
            path = ICONS / f"pole-{'dark' if dark else 'light'}-{size}.png"
            icon(size, dark).save(path, optimize=True)
            print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
