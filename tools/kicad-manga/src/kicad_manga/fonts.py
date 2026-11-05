"""The cute fonts (all SIL Open Font License), fetched from fontsource on first use and
cached. Without them the SVG still renders, just in the viewer's default sans-serif."""

import base64
import os
import sys
import urllib.request
from pathlib import Path

BASE = 'https://cdn.jsdelivr.net/npm/@fontsource/'
LATIN = 'unicode-range:U+0000-024F,U+2000-206F,U+2190-21FF,U+2600-27BF;'
JAPANESE = 'unicode-range:U+3000-30FF,U+4E00-9FFF,U+FF00-FFEF,U+2700-27BF;'

# (CSS family, weight, fontsource path, unicode-range)
FONTS = [
    ('MPR', 500, 'm-plus-rounded-1c/files/m-plus-rounded-1c-latin-500-normal.woff2', ''),
    ('MPR', 800, 'm-plus-rounded-1c/files/m-plus-rounded-1c-latin-800-normal.woff2', ''),
    ('Zen', 700, 'zen-maru-gothic/files/zen-maru-gothic-latin-700-normal.woff2', ''),
    ('Pop', 400, 'mochiy-pop-one/files/mochiy-pop-one-latin-400-normal.woff2', LATIN),
    ('Pop', 400, 'mochiy-pop-one/files/mochiy-pop-one-japanese-400-normal.woff2', JAPANESE),
]


def cache_dir():
    base = os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache'
    return Path(base) / 'kicad-manga' / 'fonts'


def load(font_dir=None):
    """[(family, weight, base64 woff2, unicode-range)] for the fonts that are available.
    Missing fonts are downloaded into the cache; an explicit font_dir is used as is."""
    d = Path(font_dir) if font_dir else cache_dir()
    download = not font_dir
    out = []
    for fam, wt, rel, rng in FONTS:
        path = d / Path(rel).name
        if not path.exists() and download:
            try:
                d.mkdir(parents=True, exist_ok=True)
                with urllib.request.urlopen(BASE + rel, timeout=30) as r:
                    path.write_bytes(r.read())
            except OSError as e:
                print(f'kicad-manga: could not download {path.name} ({e}); using a fallback font', file=sys.stderr)
        if path.exists():
            out.append((fam, wt, base64.b64encode(path.read_bytes()).decode(), rng))
    return out
