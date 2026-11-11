#!/usr/bin/env python3
"""Draw the placeholder texture pack and the toolbar icons.

The placeholder sheets have exactly the size, frame layout and anchor points of the
game's sprites (see plugin/factorio_poles/prototypes.py): every insulator sits on the
frame's wire connection point and every shadow ends on the shadow connection point.
They are what ships until the release art is dropped in, and they double as a check
that the texture pipeline does not depend on anything but the documented layout.

Usage: python3 tools/gen_placeholder_art.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin"))

from factorio_poles.prototypes import BIG, MEDIUM, POLE_TYPES, SMALL, SUBSTATION, PoleType

OUT = ROOT / "plugin" / "factorio_poles" / "textures"
ICONS = ROOT / "plugin" / "icons"
SS = 4  # supersampling factor

WOOD = (138, 84, 44, 255)
WOOD_DARK = (92, 54, 28, 255)
RUST = (150, 88, 52, 255)
RUST_DARK = (98, 56, 34, 255)
STEEL = (92, 98, 104, 255)
STEEL_DARK = (58, 62, 68, 255)
CONCRETE = (150, 150, 144, 255)
INSULATOR = (226, 230, 232, 255)
COPPER = (205, 120, 60, 255)
SHADOW = (0, 0, 0, 255)

# 3D model space: (x, y, z) in tiles relative to the entity position; x right, y down
# (towards the viewer), z up.  Screen = (x, y - z).


class Pen:
    """Draws 3D line segments either as the picture or as the cast shadow."""

    def __init__(self, img: Image.Image, origin: tuple[float, float], ppt: float, light: tuple[float, float] | None):
        self.d = ImageDraw.Draw(img)
        self.origin = origin
        self.ppt = ppt  # pixels per tile (supersampled)
        self.light = light  # None: picture; (vx, vy): shadow displacement per unit height

    def p(self, q: tuple[float, float, float]) -> tuple[float, float]:
        x, y, z = q
        if self.light is None:
            sx, sy = x, y - z
        else:
            sx, sy = x + z * self.light[0], y + z * self.light[1]
        return (self.origin[0] + sx * self.ppt, self.origin[1] + sy * self.ppt)

    def line(self, pts, color, width_tiles: float) -> None:
        w = max(1, round(width_tiles * self.ppt))
        xy = [self.p(q) for q in pts]
        self.d.line(xy, fill=color if self.light is None else SHADOW, width=w, joint="curve")
        r = w / 2
        for x, y in (xy[0], xy[-1]):
            self.d.ellipse((x - r, y - r, x + r, y + r), fill=color if self.light is None else SHADOW)

    def poly(self, pts, color) -> None:
        self.d.polygon([self.p(q) for q in pts], fill=color if self.light is None else SHADOW)

    def dot(self, q, color, radius_tiles: float) -> None:
        x, y = self.p(q)
        r = radius_tiles * self.ppt
        self.d.ellipse((x - r, y - r, x + r, y + r), fill=color if self.light is None else SHADOW)


def lift(pt: tuple[float, float]) -> tuple[float, float, float]:
    """A wire connection point (screen offset) as a 3D point straight above y=0."""
    return (pt[0], 0.0, -pt[1])


def draw_small(pen: Pen, pole: PoleType, frame: int) -> None:
    cp = pole.connection_points[frame].wire
    top = lift(cp.copper)
    pen.poly([(-0.18, 0.12, 0), (0.18, 0.12, 0), (0.12, -0.1, 0), (-0.12, -0.1, 0)], CONCRETE)
    pen.line([(0, 0, 0), (top[0] * 0.9, 0, top[2] - 0.25)], WOOD, 0.16)
    pen.line([(0, 0, 0.05), (top[0] * 0.2, 0, top[2] * 0.45)], WOOD_DARK, 0.05)
    red, green = lift(cp.red), lift(cp.green)
    arm_mid = (top[0] * 0.9, 0, top[2] - 0.25)
    pen.line([green, arm_mid, red], WOOD_DARK, 0.07)
    pen.line([arm_mid, top], WOOD_DARK, 0.06)
    for q in (top, red, green):
        pen.dot(q, INSULATOR, 0.07)


def draw_lattice(
    pen: Pen, pole: PoleType, frame: int, base_half: float, top_half: float, color, dark, rungs: int
) -> None:
    cp = pole.connection_points[frame].wire
    top = lift(cp.copper)
    h = top[2] - 0.3
    lean = 0.0  # the copper point's x offset comes from the rotated cross-arm, not a lean
    corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]

    def at(t: float, cx: int, cy: int) -> tuple[float, float, float]:
        half = base_half + (top_half - base_half) * t
        return (lean * t + cx * half, cy * half * 0.6, h * t)

    # back legs first, then bracing, then front legs
    for cx, cy in corners:
        if cy < 0:
            pen.line([at(0, cx, cy), at(1, cx, cy)], dark, 0.06)
    for i in range(rungs):
        t0, t1 = i / rungs, (i + 1) / rungs
        for (ax, ay), (bx, by) in ((corners[3], corners[2]), (corners[0], corners[3]), (corners[1], corners[2])):
            pen.line([at(t0, ax, ay), at(t1, bx, by)], dark, 0.035)
            pen.line([at(t0, bx, by), at(t1, ax, ay)], dark, 0.035)
            pen.line([at(t1, ax, ay), at(t1, bx, by)], color, 0.035)
    for cx, cy in corners:
        if cy > 0:
            pen.line([at(0, cx, cy), at(1, cx, cy)], color, 0.07)
    red, green = lift(cp.red), lift(cp.green)
    head = (lean, 0, h)
    mid = ((red[0] + green[0]) / 2, 0, (red[2] + green[2]) / 2)
    pen.line([green, red], color, 0.08)
    pen.line([head, mid], color, 0.07)
    pen.line([head, top], color, 0.06)
    for q in (top, red, green):
        pen.dot(q, INSULATOR, 0.08)


def draw_substation(pen: Pen, pole: PoleType, frame: int) -> None:
    cp = pole.connection_points[frame].wire
    top = lift(cp.copper)
    # transformer box
    b = 0.85
    hgt = 1.1
    pen.poly([(-b, b * 0.6, 0), (b, b * 0.6, 0), (b, b * 0.6, hgt), (-b, b * 0.6, hgt)], STEEL)
    pen.poly([(-b, b * 0.6, hgt), (b, b * 0.6, hgt), (b, -b * 0.6, hgt), (-b, -b * 0.6, hgt)], CONCRETE)
    for i in range(5):
        x = -b + (i + 0.5) * 2 * b / 5
        pen.line([(x, b * 0.6, 0.15), (x, b * 0.6, hgt - 0.15)], STEEL_DARK, 0.06)
    # mast
    pen.line([(0, 0, hgt), (top[0], 0, top[2] - 0.2)], STEEL_DARK, 0.12)
    red, green = lift(cp.red), lift(cp.green)
    head = (top[0], 0, top[2] - 0.2)
    pen.line([green, head, red], STEEL_DARK, 0.07)
    pen.line([head, top], STEEL_DARK, 0.06)
    for q in (top, red, green):
        pen.dot(q, INSULATOR, 0.08)


def draw(pen: Pen, pole: PoleType, frame: int) -> None:
    if pole is SMALL:
        draw_small(pen, pole, frame)
    elif pole is MEDIUM:
        draw_lattice(pen, pole, frame, 0.32, 0.12, RUST, RUST_DARK, 5)
    elif pole is BIG:
        draw_lattice(pen, pole, frame, 0.85, 0.3, STEEL, STEEL_DARK, 6)
    elif pole is SUBSTATION:
        draw_substation(pen, pole, frame)
    else:
        raise ValueError(pole.name)


def light_vector(pole: PoleType, frame: int) -> tuple[float, float]:
    """Shadow displacement per tile of height, chosen so the copper point's shadow lands
    exactly on the frame's shadow connection point."""
    cp = pole.connection_points[frame]
    h = -cp.wire.copper[1]
    return ((cp.shadow.copper[0] - cp.wire.copper[0]) / h, cp.shadow.copper[1] / h)


def sheet(pole: PoleType, shadow: bool) -> Image.Image:
    s = pole.shadow if shadow else pole.picture
    ppt = 1 / s.tiles_per_pixel
    out = Image.new("RGBA", s.sheet_size, (0, 0, 0, 0))
    for f in range(s.frames):
        big = Image.new("RGBA", (s.width * SS, s.height * SS), (0, 0, 0, 0))
        origin = ((s.width / 2 - s.shift[0] * ppt) * SS, (s.height / 2 - s.shift[1] * ppt) * SS)
        draw(Pen(big, origin, ppt * SS, light_vector(pole, f) if shadow else None), pole, f)
        out.paste(big.resize((s.width, s.height), Image.LANCZOS), (f * s.width, 0))
    return out


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
    for pole in POLE_TYPES:
        d = OUT / pole.name
        d.mkdir(parents=True, exist_ok=True)
        for shadow in (False, True):
            s = pole.shadow if shadow else pole.picture
            img = sheet(pole, shadow)
            assert img.size == s.sheet_size
            path = OUT / s.filename
            img.save(path, optimize=True)
            print(f"wrote {path.relative_to(ROOT)} {img.size[0]}x{img.size[1]}")
    ICONS.mkdir(parents=True, exist_ok=True)
    for size in (24, 48):
        for dark in (False, True):
            path = ICONS / f"pole-{'dark' if dark else 'light'}-{size}.png"
            icon(size, dark).save(path, optimize=True)
            print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
