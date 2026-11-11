#!/usr/bin/env python3
"""(Re)build demo/demo.kicad_sch by placing poles through the KiCad API.

Needs a running KiCad API server with demo/demo.kicad_pro loaded, e.g.:

    tools/kicad-nightly.sh api-server --socket /tmp/fp.sock demo/demo.kicad_pro &
    python3 tools/make_demo.py --socket ipc:///tmp/fp.sock
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin"))

from factorio_poles import kicad_io
from kipy import KiCad
from kipy.geometry import Vector2
from kipy.proto.common.types import DocumentType

TILE_MM = 2.54

# (symbol, net, x, y) in tiles.  An A4 sheet is about 117 x 83 tiles.
POLES = [
    # +5V: a run of small poles ...
    ("Small_Electric_Pole", "+5V", 10, 14),
    ("Small_Electric_Pole", "+5V", 17, 14),
    ("Small_Electric_Pole", "+5V", 23, 18),
    ("Small_Electric_Pole", "+5V", 29, 14),
    ("Small_Electric_Pole", "+5V", 36, 15),
    # ... branching off to the south ...
    ("Small_Electric_Pole", "+5V", 23, 24),
    # ... and one pole that is out of reach of the rest (gets its reach drawn).
    ("Small_Electric_Pole", "+5V", 50, 22),
    # VBUS: big poles spanning the sheet, ending in a substation.
    ("Big_Electric_Pole", "VBUS", 12, 40),
    ("Big_Electric_Pole", "VBUS", 42, 36),
    ("Big_Electric_Pole", "VBUS", 72, 42),
    ("Big_Electric_Pole", "VBUS", 100, 36),
    ("Substation", "VBUS", 100, 52),
    # GND: medium poles with a small pole at the end.
    ("Medium_Electric_Pole", "GND", 14, 66),
    ("Medium_Electric_Pole", "GND", 22, 66),
    ("Medium_Electric_Pole", "GND", 30, 68),
    ("Medium_Electric_Pole", "GND", 38, 66),
    ("Medium_Electric_Pole", "GND", 30, 76),
    ("Small_Electric_Pole", "GND", 44, 69),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--socket", required=True)
    ap.add_argument("--schematic", default=str(ROOT / "demo" / "demo.kicad_sch"))
    args = ap.parse_args()

    kicad = KiCad(socket_path=args.socket)
    try:
        kicad.open_document(str(Path(args.schematic).resolve()), DocumentType.DOCTYPE_SCHEMATIC)
    except Exception as e:  # noqa: BLE001 - already open
        print(f"open_document: {e}")
    kicad.load_all_libraries()
    sch = kicad.get_schematic()

    # Start from an empty sheet.
    old = [s for s in sch.get_symbols() if kicad_io.pole_type_of(s) is not None]
    old += [i for items in kicad_io.generated_items(sch).values() for i, _ in items]
    if old:
        commit = sch.begin_commit()
        sch.remove_items(old)
        sch.push_commit(commit, "Remove old demo poles")
    placed = []
    for i, (name, net, x, y) in enumerate(POLES, start=1):
        sym = sch.place_symbol_from_library(
            f"factorio_poles:{name}",
            Vector2.from_xy_mm(x * TILE_MM, y * TILE_MM),
            reference=f"#PWR{i:02d}",
        )
        sym.value = net
        placed.append(sym)
    commit = sch.begin_commit()
    kicad_io.update_items(sch, placed)
    sch.push_commit(commit, "Set demo pole nets")
    sch.save()
    print(f"placed {len(placed)} poles in {args.schematic}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
