"""Settings: built-in defaults < kicad-manga.toml < command line.

    # kicad-manga.toml
    style = "manga"          # or "minecraft"
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

    [minecraft]              # the minecraft style
    packs = []               # resource packs (.zip or folders), first wins; e.g. ["my-pack.zip", "default.zip"]
    block_mm = 2.54          # one block per this many mm of the schematic
    dust_width = 2.0         # redstone dust drawn this many times wider than in the game
    camera_deg = 55          # the camera's angle above the horizon (90: straight down)
    yaw_deg = 30             # the camera turned this far from due south towards the east
    px_per_block = 16        # raster resolution: 16 shows a 16x16 pack's textures pixel for pixel
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
    'minecraft': {
        'packs': [],
        'block_mm': 2.54,
        'dust_width': 2.0,
        'camera_deg': 55.0,
        'yaw_deg': 30.0,
        'px_per_block': 16,
    },
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
        base = Path(path).resolve().parent      # pack paths are relative to the settings file
        cfg['minecraft']['packs'] = [str(base / p) for p in cfg['minecraft']['packs']]
    return cfg
