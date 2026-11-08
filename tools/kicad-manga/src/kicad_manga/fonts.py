"""The cute fonts (all SIL Open Font License), fetched from fontsource on first use and cached.

Each font is kept twice: the WOFF2 file, which is embedded in the SVG so browsers show it, and a TTF converted
from it, which HarfBuzz measures text with and resvg/rsvg-convert render with. The TTF gets clean family and
style names, so renderers find it by the same family name and weight as the CSS asks for.

Without the fonts the SVG still renders, just in a fallback sans-serif, and text sizes are estimated."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import requests

BASE = 'https://cdn.jsdelivr.net/npm/@fontsource/'

POP = 'Mochiy Pop One'
ZEN = 'Zen Maru Gothic'
MPR = 'M PLUS Rounded 1c'

# (family, weight, style name, fontsource path). Mochiy Pop One's Japanese subset has the Latin letters too.
FONTS = [
    (MPR, 500, 'Medium', 'm-plus-rounded-1c/files/m-plus-rounded-1c-latin-500-normal.woff2'),
    (MPR, 800, 'ExtraBold', 'm-plus-rounded-1c/files/m-plus-rounded-1c-latin-800-normal.woff2'),
    (ZEN, 700, 'Bold', 'zen-maru-gothic/files/zen-maru-gothic-latin-700-normal.woff2'),
    (POP, 400, 'Regular', 'mochiy-pop-one/files/mochiy-pop-one-japanese-400-normal.woff2'),
]


@dataclass(frozen=True)
class Font:
    family: str
    weight: int
    woff2: Path
    ttf: Path


def cache_dir():
    base = os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache'
    return Path(base) / 'kicad-manga' / 'fonts'


def to_ttf(woff2, ttf, family, style):
    """Decompress a WOFF2 file into a TTF named `family` / `style`."""
    from fontTools.ttLib import TTFont
    font = TTFont(woff2)
    font.flavor = None
    names = font['name']
    for nid in (1, 2, 4, 6, 16, 17):
        names.removeNames(nameID=nid)
    full = f'{family} {style}'
    for nid, text in ((1, family), (2, style), (4, full), (6, full.replace(' ', '-')), (16, family), (17, style)):
        names.setName(text, nid, 3, 1, 0x409)
        names.setName(text, nid, 1, 0, 0)
    ttf.parent.mkdir(parents=True, exist_ok=True)
    font.save(ttf)


def download(url, path):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)


def load(font_dir=None, fonts=None):
    """The fonts that are available, as `Font`s: `fonts` (default: the manga style's FONTS). Missing fonts are downloaded into the cache unless an explicit
    `font_dir` is given, which is then used as is (the converted TTFs still go into the cache)."""
    src = Path(font_dir) if font_dir else cache_dir()
    out = []
    for family, weight, style, rel in fonts or FONTS:
        woff2 = src / Path(rel).name
        if not woff2.exists() and not font_dir:
            try:
                download(BASE + rel, woff2)
            except requests.RequestException as e:
                print(f'kicad-manga: could not download {woff2.name} ({e}); using a fallback font', file=sys.stderr)
        if not woff2.exists():
            continue
        ttf = cache_dir() / 'ttf' / (woff2.stem + '.ttf')
        if not ttf.exists() or ttf.stat().st_mtime < woff2.stat().st_mtime:
            to_ttf(woff2, ttf, family, style)
        out.append(Font(family, weight, woff2, ttf))
    return out
