"""Texture packs.

A texture pack is any directory laid out like Factorio's ``base/graphics/entity``::

    <root>/small-electric-pole/small-electric-pole.png         288 x 220 (4 frames of 72 x 220)
    <root>/small-electric-pole/small-electric-pole-shadow.png  1024 x 52 (4 frames of 256 x 52)
    <root>/medium-electric-pole/...
    <root>/big-electric-pole/...

Sheet sizes, frame layout, sprite shifts and wire connection points all follow the game
(see :mod:`prototypes`), so the pack can be swapped for any other with the same layout:
the art that ships with the plugin, a Factorio installation, or the release art.
Missing or wrongly sized sheets fall back to the next pack on the search path, one
sheet at a time.
"""

from __future__ import annotations

import hashlib
import io
import math
import os
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image

from . import geometry
from .prototypes import POLE_TYPES, PoleType, SpriteSheet

#: The art bundled with the plugin; always last on the search path.
BUNDLED = Path(__file__).resolve().parent / "textures"

#: Resolution written into generated PNGs.  KiCad sizes images by their pHYs chunk.
PNG_PPI = 300

#: Factorio draws ``draw_as_shadow`` layers as about 50 % black.
DEFAULT_SHADOW_OPACITY = 0.5


def factorio_install_candidates() -> list[Path]:
    """Places a Factorio installation usually keeps ``base/graphics/entity``."""
    home = Path.home()
    data_dirs = [
        Path("/usr/share/factorio"),
        Path("/opt/factorio/data"),
        home / "factorio" / "data",
        home / ".factorio" / "data",
        home / ".steam/steam/steamapps/common/Factorio/data",
        home / ".local/share/Steam/steamapps/common/Factorio/data",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/common/Factorio/data",
        home / "Library/Application Support/Steam/steamapps/common/Factorio/factorio.app/Contents/data",
        Path("/Applications/factorio.app/Contents/data"),
    ]
    if sys.platform == "win32":
        for env in ("ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(env)
            if base:
                data_dirs.append(Path(base) / "Steam/steamapps/common/Factorio/data")
                data_dirs.append(Path(base) / "Factorio/data")
    return [d / "base" / "graphics" / "entity" for d in data_dirs]


def search_path(configured: Iterable[str | os.PathLike] = (), use_factorio: bool = True) -> list[Path]:
    """Texture roots in priority order: configured, ``$FACTORIO_POLES_TEXTURES``,
    a local Factorio installation, then the bundled art."""
    roots: list[Path] = [Path(p).expanduser() for p in configured if p]
    env = os.environ.get("FACTORIO_POLES_TEXTURES")
    if env:
        roots.extend(Path(p).expanduser() for p in env.split(os.pathsep) if p)
    if use_factorio:
        roots.extend(factorio_install_candidates())
    roots.append(BUNDLED)
    seen: set[Path] = set()
    out = []
    for r in roots:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


class TextureError(Exception):
    pass


def check_sheet(path: Path, sheet: SpriteSheet) -> str | None:
    """Return a problem description, or None if ``path`` is a usable sheet."""
    if not path.is_file():
        return "missing"
    try:
        with Image.open(path) as im:
            size = im.size
    except OSError as e:
        return f"unreadable ({e})"
    if size != sheet.sheet_size:
        w, h = sheet.sheet_size
        return f"is {size[0]}x{size[1]}, expected {w}x{h} ({sheet.frames} frames of {sheet.width}x{sheet.height})"
    return None


@lru_cache(maxsize=64)
def _load_rgba(path: str, mtime: float) -> Image.Image:
    with Image.open(path) as im:
        return im.convert("RGBA")


@dataclass(frozen=True)
class Sprite:
    """One composed pole frame (shadow under picture), ready to drop into KiCad."""

    png: bytes
    size_px: tuple[int, int]
    #: Centre of the image relative to the pole position, tiles.
    center: tuple[float, float]
    #: Size of one pixel, tiles.
    tiles_per_pixel: float
    digest: str


class TexturePack:
    def __init__(self, roots: Sequence[Path]):
        self.roots = list(roots)
        self.warnings: list[str] = []
        self._resolved: dict[str, Path] = {}
        self._sprites: dict[tuple, Sprite] = {}

    def resolve(self, sheet: SpriteSheet) -> Path:
        if sheet.filename in self._resolved:
            return self._resolved[sheet.filename]
        problems = []
        for root in self.roots:
            path = root / sheet.filename
            problem = check_sheet(path, sheet)
            if problem is None:
                # Say so when a sheet was skipped: a wrong size usually means a bad export.
                self.warnings.extend(f"{p}; using {path} instead" for p in problems)
                self._resolved[sheet.filename] = path
                return path
            if problem != "missing":
                problems.append(f"{path} {problem}")
        self.warnings.extend(problems)
        raise TextureError(f"no usable texture for {sheet.filename}" + (": " + "; ".join(problems) if problems else ""))

    def sources(self) -> dict[str, Path]:
        """Which file each sheet comes from (resolving everything)."""
        out = {}
        for t in POLE_TYPES:
            for sheet in (t.picture, t.shadow):
                out[sheet.filename] = self.resolve(sheet)
        return out

    def _frame(self, sheet: SpriteSheet, frame: int) -> Image.Image:
        path = self.resolve(sheet)
        return _load_rgba(str(path), path.stat().st_mtime).crop(sheet.frame_box(frame))

    def sprite(
        self,
        pole: PoleType,
        frame: int,
        shadow: bool = True,
        shadow_angle: float | None = None,
        shadow_opacity: float = DEFAULT_SHADOW_OPACITY,
    ) -> Sprite:
        """One frame of ``pole`` with its shadow underneath, cast towards ``shadow_angle``
        (see :func:`geometry.shadow_matrix`; None keeps the art's own direction)."""
        key = (pole.name, frame, shadow, shadow_angle, shadow_opacity)
        if key not in self._sprites:
            self._sprites[key] = _compose(self, pole, frame, shadow, shadow_angle, shadow_opacity)
        return self._sprites[key]


def _compose(
    pack: TexturePack, pole: PoleType, frame: int, shadow: bool, angle: float | None, opacity: float
) -> Sprite:
    tpp = pole.picture.tiles_per_pixel
    # (image, (left, top, right, bottom) in tiles relative to the pole position)
    layers: list[tuple[Image.Image, tuple[float, float, float, float]]] = []
    if shadow:
        if abs(pole.shadow.tiles_per_pixel - tpp) > 1e-12:
            raise TextureError("layers with different scales are not supported")
        img = pack._frame(pole.shadow, frame)
        alpha = img.getchannel("A").point(lambda v: round(v * opacity))
        black = Image.new("RGBA", img.size, (0, 0, 0, 0))
        black.putalpha(alpha)
        cp = pole.connection_points[frame]
        m = geometry.shadow_matrix(cp.wire.copper, cp.shadow.copper, angle)
        layers.append(_transform(black, pole.shadow.frame_rect_tiles(), m, tpp))
    layers.append((pack._frame(pole.picture, frame), pole.picture.frame_rect_tiles()))

    # All layers share one pixel density; lay them out on a common canvas.
    left = min(r[0] for _, r in layers)
    top = min(r[1] for _, r in layers)
    right = max(r[2] for _, r in layers)
    bottom = max(r[3] for _, r in layers)
    canvas = Image.new("RGBA", (round((right - left) / tpp), round((bottom - top) / tpp)), (0, 0, 0, 0))
    for img, r in layers:
        canvas.alpha_composite(img, (round((r[0] - left) / tpp), round((r[1] - top) / tpp)))

    # Trim fully transparent margins to keep the schematic file small.
    bbox = canvas.getchannel("A").getbbox()
    if bbox is None:
        bbox = (0, 0, 1, 1)
    canvas = canvas.crop(bbox)
    left += bbox[0] * tpp
    top += bbox[1] * tpp
    cw, ch = canvas.size

    buf = io.BytesIO()
    canvas.save(buf, "PNG", optimize=True, dpi=(PNG_PPI, PNG_PPI))
    png = buf.getvalue()
    return Sprite(
        png=png,
        size_px=(cw, ch),
        center=(left + cw * tpp / 2.0, top + ch * tpp / 2.0),
        tiles_per_pixel=tpp,
        digest=hashlib.sha1(png).hexdigest()[:12],
    )


def _transform(
    img: Image.Image, rect: tuple[float, float, float, float], m: geometry.Matrix, tpp: float
) -> tuple[Image.Image, tuple[float, float, float, float]]:
    """Apply the linear map ``m`` (tiles, about the pole position) to a layer."""
    if m == geometry.IDENTITY:
        return img, rect
    corners = [geometry.apply(m, (x, y)) for x in (rect[0], rect[2]) for y in (rect[1], rect[3])]
    left = min(c[0] for c in corners)
    top = min(c[1] for c in corners)
    w = max(1, math.ceil((max(c[0] for c in corners) - left) / tpp))
    h = max(1, math.ceil((max(c[1] for c in corners) - top) / tpp))
    # PIL wants the inverse: output pixel -> input pixel.
    (a, b), (c, d) = m
    det = a * d - b * c
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    coeffs = (
        ia, ib, (ia * left + ib * top - rect[0]) / tpp,
        ic, id_, (ic * left + id_ * top - rect[1]) / tpp,
    )  # fmt: skip
    out = img.transform((w, h), Image.Transform.AFFINE, coeffs, resample=Image.Resampling.BICUBIC)
    return out, (left, top, left + w * tpp, top + h * tpp)


def kicad_image_scale(tiles_per_pixel: float, tile_mm: float) -> float:
    """``image_scale`` that makes one sprite pixel ``tiles_per_pixel * tile_mm`` wide."""
    native_mm = 25.4 / PNG_PPI
    return tiles_per_pixel * tile_mm / native_mm
