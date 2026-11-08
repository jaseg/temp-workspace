"""Settings: built-in defaults < kicad-manga.toml < command line.

    # kicad-manga.toml
    style = "manga"          # or "papercraft"
    formats = ["svg", "png", "pdf"]
    png_px_per_mm = 10
    seed = 42
    characters = true        # passives as cats, grumpy resistors, ...
    decorations = true       # plants, garlands, cables, shelves, sparkles
    sound_effects = true     # the faint katakana
    font_dir = ""            # default: download into ~/.cache/kicad-manga/fonts

    [title]                  # empty: taken from the schematic's title block
    title = ""               # default: title block title, else the file name
    subtitle = ""            # default: title block comment 1
    kicker = "回路図"         # the line above the title
    bubble = ""              # what the mascot says; default: title block comment 2
"""

import copy
import sys
import tomllib
from pathlib import Path

DEFAULTS = {
    'style': 'manga',
    'formats': ['svg', 'png', 'pdf'],
    'png_px_per_mm': 10.0,
    'seed': 42,
    'characters': True,
    'decorations': True,
    'sound_effects': True,
    'font_dir': '',
    'title': {'title': '', 'subtitle': '', 'kicker': '回路図', 'bubble': ''},
}

FILENAME = 'kicad-manga.toml'


def merge(base, extra, where=''):
    for k, v in extra.items():
        if k not in base:
            print(f'kicad-manga: ignoring unknown setting {where}{k}', file=sys.stderr)
        elif isinstance(base[k], dict):
            merge(base[k], v, f'{where}{k}.')
        else:
            base[k] = v
    return base


def find(schematic, explicit=None):
    if explicit:
        return Path(explicit)
    for d in (Path(schematic).resolve().parent, Path.cwd()):
        if (d / FILENAME).exists():
            return d / FILENAME
    return None


def load(path=None):
    cfg = copy.deepcopy(DEFAULTS)
    if path:
        with open(path, 'rb') as f:
            merge(cfg, tomllib.load(f))
    return cfg
