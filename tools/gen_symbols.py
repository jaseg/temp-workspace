#!/usr/bin/env python3
"""Generate symbols/factorio_poles.kicad_sym from the pole prototypes.

Each pole is a global power symbol: its Value names the net, exactly like VCC or GND.
The symbol itself is deliberately tiny - a pin at the pole's base and Factorio-style
selection corners around its footprint.  The pole artwork and the wires are drawn by the
plugin as locked schematic items, so they can be regenerated at any time.

Usage: python3 tools/gen_symbols.py [output.kicad_sym]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin"))

from factorio_poles.prototypes import POLE_FIELD, POLE_TYPES, PoleType

#: Symbols are drawn for the default tile size (one tile = 100 mil).
TILE_MM = 2.54
DEFAULT_NET = "VCC"


def q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def fmt(v: float) -> str:
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def field(
    name: str, value: str, at: tuple[float, float], hide: bool, justify: str | None = None, autoplace: bool = True
) -> str:
    eff = "\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n"
    if justify:
        eff += f"\t\t\t\t(justify {justify})\n"
    eff += "\t\t\t)\n"
    return (
        f"\t\t(property {q(name)} {q(value)}\n"
        f"\t\t\t(at {fmt(at[0])} {fmt(at[1])} 0)\n"
        "\t\t\t(show_name no)\n"
        f"\t\t\t(do_not_autoplace {'no' if autoplace else 'yes'})\n"
        + ("\t\t\t(hide yes)\n" if hide else "")
        + eff
        + "\t\t)\n"
    )


def polyline(points: list[tuple[float, float]], width: float = 0.1524) -> str:
    pts = " ".join(f"(xy {fmt(x)} {fmt(y)})" for x, y in points)
    return (
        "\t\t\t(polyline\n"
        f"\t\t\t\t(pts\n\t\t\t\t\t{pts}\n\t\t\t\t)\n"
        f"\t\t\t\t(stroke\n\t\t\t\t\t(width {fmt(width)})\n\t\t\t\t\t(type default)\n\t\t\t\t)\n"
        "\t\t\t\t(fill\n\t\t\t\t\t(type none)\n\t\t\t\t)\n"
        "\t\t\t)\n"
    )


def selection_corners(pole: PoleType) -> str:
    """The four L-shaped corner marks Factorio draws around a selected entity."""
    (x0, y0), (x1, y1) = pole.selection_box
    # Library coordinates have +y up; the box is symmetric so only the sign matters.
    x0, x1 = x0 * TILE_MM, x1 * TILE_MM
    y0, y1 = -y1 * TILE_MM, -y0 * TILE_MM
    arm = min(x1 - x0, y1 - y0) * 0.3
    out = ""
    for cx, sx in ((x0, 1), (x1, -1)):
        for cy, sy in ((y0, 1), (y1, -1)):
            out += polyline([(cx + sx * arm, cy), (cx, cy), (cx, cy + sy * arm)])
    return out


def symbol(pole: PoleType) -> str:
    name = pole.symbol_name
    half = -pole.selection_box[0][1] * TILE_MM
    desc = (
        f"Factorio {pole.title.lower()}: a power symbol whose Value names the net. "
        f"Wired automatically to nearby poles on the same net "
        f"(reach {fmt(pole.maximum_wire_distance)} tiles) by the Factorio Power Poles plugin."
    )
    s = f"\t(symbol {q(name)}\n"
    s += "\t\t(power global)\n"
    s += "\t\t(pin_numbers\n\t\t\t(hide yes)\n\t\t)\n"
    s += "\t\t(pin_names\n\t\t\t(offset 0)\n\t\t\t(hide yes)\n\t\t)\n"
    s += "\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(in_pos_files yes)\n"
    s += "\t\t(duplicate_pin_numbers_are_jumpers no)\n"
    # Keep the net name below the pole: eeschema's field autoplacement would move it above
    # the base, like VCC's, right into the pole sprite.
    s += field("Reference", "#PWR", (0, -half - 3.81), hide=True, autoplace=False)
    s += field("Value", DEFAULT_NET, (0, -half - 1.524), hide=False, autoplace=False)
    s += field("Footprint", "", (0, 0), hide=True)
    s += field("Datasheet", "", (0, 0), hide=True)
    s += field("Description", desc, (0, 0), hide=True)
    s += field("ki_keywords", "global power factorio electric pole wire", (0, 0), hide=True)
    s += field(POLE_FIELD, pole.name, (0, 0), hide=True)
    s += f"\t\t(symbol {q(name + '_0_1')}\n"
    s += selection_corners(pole)
    s += "\t\t)\n"
    s += f"\t\t(symbol {q(name + '_1_1')}\n"
    s += (
        "\t\t\t(pin power_in line\n"
        "\t\t\t\t(at 0 0 90)\n"
        "\t\t\t\t(length 0)\n"
        '\t\t\t\t(name ""\n\t\t\t\t\t(effects\n\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size 1.27 1.27)\n'
        "\t\t\t\t\t\t)\n\t\t\t\t\t)\n\t\t\t\t)\n"
        '\t\t\t\t(number "1"\n\t\t\t\t\t(effects\n\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size 1.27 1.27)\n'
        "\t\t\t\t\t\t)\n\t\t\t\t\t)\n\t\t\t\t)\n"
        "\t\t\t)\n"
    )
    s += "\t\t)\n"
    s += "\t\t(embedded_fonts no)\n"
    s += "\t)\n"
    return s


def library() -> str:
    out = '(kicad_symbol_lib\n\t(version 20251024)\n\t(generator "factorio_poles_gen_symbols")\n\t(generator_version "1.0")\n'
    for pole in POLE_TYPES:
        out += symbol(pole)
    out += ")\n"
    return out


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else ROOT / "symbols" / "factorio_poles.kicad_sym"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(library())
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
