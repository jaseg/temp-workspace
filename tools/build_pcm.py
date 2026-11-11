#!/usr/bin/env python3
"""Build a KiCad Plugin and Content Manager (PCM) package.

    python3 tools/build_pcm.py            # -> dist/factorio-poles-<version>.zip

Install it with "Install from File..." in KiCad's Plugin and Content Manager.  The
archive contains the IPC plugin (plugins/), the pole symbol library (symbols/) and an
icon (resources/).  To ship different pole art, replace the sheets in
plugin/factorio_poles/textures/ (same file names and sizes) before building.
"""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin"))

from factorio_poles import __version__
from factorio_poles.prototypes import POLE_TYPES
from factorio_poles.textures import BUNDLED, check_sheet
from PIL import Image

IDENTIFIER = "org.jaseg.factorio-poles"


def metadata(version: str) -> dict:
    return {
        "$schema": "https://go.kicad.org/pcm/schemas/v2",
        "name": "Factorio Power Poles",
        "description": "Power symbols that wire themselves to nearby poles on the same net.",
        "description_full": (
            "Adds Factorio-style electric poles to the schematic editor.  Each pole is a power "
            "symbol: its Value names the net, like VCC or GND.  Poles on the same net that are "
            "within reach of each other (small 7.5, medium 9, big 32 tiles, substation 18) are "
            "joined by drooping power lines, drawn as a real catenary with shadows.  Run "
            "'Update power lines' after editing, or toggle 'Live power lines' to keep them "
            "up to date while you work.  Requires KiCad 11 (nightly) with the IPC API enabled."
        ),
        "identifier": IDENTIFIER,
        "type": "plugin",
        "author": {"name": "jaseg", "contact": {}},
        "license": "TBD",
        "resources": {},
        "tags": ["schematic", "power", "fun"],
        "versions": [
            {
                "version": version,
                "status": "development",
                "kicad_version": "10.99",
                "runtime": "ipc",
            }
        ],
    }


def plugin_files() -> list[tuple[Path, str]]:
    src = ROOT / "plugin"
    out = []
    for path in sorted(src.rglob("*")):
        if path.is_dir() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        out.append((path, "plugins/" + path.relative_to(src).as_posix()))
    return out


def main() -> int:
    # Refuse to package a broken texture pack.
    for pole in POLE_TYPES:
        for sheet in (pole.picture, pole.shadow):
            problem = check_sheet(BUNDLED / sheet.filename, sheet)
            if problem:
                print(f"error: {sheet.filename} {problem}")
                return 1

    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    out = dist / f"factorio-poles-{__version__}.zip"
    meta = metadata(__version__)
    install_size = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path, arc in plugin_files():
            z.write(path, arc)
            install_size += path.stat().st_size
        lib = ROOT / "symbols" / "factorio_poles.kicad_sym"
        z.write(lib, "symbols/factorio_poles.kicad_sym")
        install_size += lib.stat().st_size
        icon = Image.open(ROOT / "plugin" / "icons" / "pole-light-48.png").resize((64, 64), Image.LANCZOS)
        icon_path = dist / "icon.png"
        icon.save(icon_path)
        z.write(icon_path, "resources/icon.png")
        meta["versions"][0]["install_size"] = install_size
        z.writestr("metadata.json", json.dumps(meta, indent=2))
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size} bytes, sha256 {digest})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
