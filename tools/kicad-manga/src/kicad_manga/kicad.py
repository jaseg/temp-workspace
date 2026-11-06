"""Reading KiCad schematics, through gerbonara's object model: loading, and small accessors that smooth over
the differences between its item types and file format versions."""

import math
import struct
from pathlib import Path

from gerbonara.cad.kicad.schematic import Schematic

PAPER_SIZES = {
    'A5': (210, 148), 'A4': (297, 210), 'A3': (420, 297), 'A2': (594, 420), 'A1': (841, 594), 'A0': (1189, 841),
    'A': (279.4, 215.9), 'B': (431.8, 279.4), 'C': (558.8, 431.8), 'D': (863.6, 558.8), 'E': (1117.6, 863.6),
    'USLetter': (279.4, 215.9), 'USLegal': (355.6, 215.9), 'USLedger': (431.8, 279.4),
}

DASHES = {'dash': '1.4 .8', 'dot': '.2 .6', 'dash_dot': '1.4 .6 .2 .6', 'dash_dot_dot': '1.4 .6 .2 .6 .2 .6'}


def load(path):
    return Schematic.open(Path(path))


def paper_size(sch):
    p = sch.page_settings
    if p.page_format == 'User' and p.width and p.height:
        w, h = float(p.width), float(p.height)
    else:
        w, h = PAPER_SIZES.get(str(p.page_format), PAPER_SIZES['A4'])
    if p.portrait:
        w, h = min(w, h), max(w, h)
    return w, h


def paper_name(sch):
    p = sch.page_settings
    return f'{p.width:g}×{p.height:g} mm' if p.page_format == 'User' and p.width else str(p.page_format)


def hex_color(c):
    """A gerbonara Color as '#rrggbb', or None when absent or fully transparent."""
    if c is None or c.r is None or not c.a:
        return None
    return '#%02x%02x%02x' % (int(c.r), int(c.g), int(c.b))


def stroke(item):
    """(width, dash type, colour or None) of an item's stroke."""
    st = getattr(item, 'stroke', None)
    if st is None:
        return 0, 'default', None
    return float(st.width or 0), str(st.type), hex_color(st.color)


def fill(item):
    """(type, colour or None) of an item's fill."""
    f = getattr(item, 'fill', None)
    if f is None:
        return 'none', None
    return str(f.type), hex_color(getattr(f, 'color', None))


def font(item):
    """(size, bold, italic, colour or None) of a text item's effects."""
    eff = getattr(item, 'effects', None)
    f = eff.font if eff is not None else None
    if f is None:
        return 1.27, False, False, None
    size = float(f.size.x) if f.size is not None and f.size.x is not None else 1.27
    return size, bool(f.bold), bool(f.italic), hex_color(getattr(f, 'color', None))


def justify(item):
    eff = getattr(item, 'effects', None)
    j = eff.justify if eff is not None else None
    h = str(j.h) if j is not None and j.h is not None else 'center'
    v = str(j.v) if j is not None and j.v is not None else 'center'
    return h, v


def hidden(item):
    if item is None:
        return False
    if getattr(item, 'hide', False):
        return True
    eff = getattr(item, 'effects', None)
    return bool(eff is not None and eff.hide)


def at(item):
    a = item.at
    return float(a.x), float(a.y)


def rotation(item):
    return float(getattr(item.at, 'rotation', 0) or 0)


def xy(p):
    return float(p.x), float(p.y)


def png_info(data):
    """(width, height, dots per inch) of PNG data, or None for anything else. KiCad embeds images as PNG."""
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    w, h = struct.unpack('>II', data[16:24])
    dpi, pos = 300, 8
    while pos + 8 <= len(data):
        n, kind = struct.unpack('>I4s', data[pos:pos + 8])
        if kind == b'pHYs' and n >= 9:
            ppu, _, unit = struct.unpack('>IIB', data[pos + 8:pos + 17])
            if unit == 1 and ppu:
                dpi = ppu * .0254
            break
        if kind == b'IDAT':
            break
        pos += 12 + n
    return w, h, dpi


# ----------------------------------------------------------------------------
# Library symbols

class LibSymbol:
    """A library symbol with `(extends ...)` resolved: its own fields, with the units (graphics and pins), pin
    settings and power flag taken from the symbol it extends."""

    def __init__(self, sym, base=None):
        self.sym, base = sym, base or sym
        self.units = base.units
        self.power = sym.power if sym.power is not None else base.power
        self.pin_names = sym.pin_names if sym.extends is None else base.pin_names
        self.pin_numbers = sym.pin_numbers if sym.extends is None else base.pin_numbers

    @property
    def is_power(self):
        return self.power is not None


def lib_symbols(sch):
    """{lib_id: LibSymbol} for the symbols embedded in the schematic."""
    raw = {s.raw_name: s for s in sch.lib_symbols.symbols}
    out = {}
    for name, sym in raw.items():
        base = None
        if sym.extends:
            base = raw.get(f'{name.split(":")[0]}:{sym.extends}') or next(
                (v for k, v in raw.items() if k.split(':')[-1] == sym.extends), None)
        out[name] = LibSymbol(sym, base)
    return out


# ----------------------------------------------------------------------------
# Transforms: library coordinates are y-up, the sheet is y-down.

class Xf:
    def __init__(self, x, y, rot=0, mirror=None):
        self.x, self.y = x, y
        a = math.radians(rot)
        self.c, self.s = round(math.cos(a)), round(math.sin(a))
        self.mirror = mirror

    def lin(self, px, py):
        x, y = px, -py
        x, y = x * self.c + y * self.s, -x * self.s + y * self.c
        if self.mirror == 'x':
            y = -y
        elif self.mirror == 'y':
            x = -x
        return (x, y)

    def __call__(self, px, py):
        dx, dy = self.lin(px, py)
        return (self.x + dx, self.y + dy)


def mirror(sym):
    m = sym.mirror
    return 'x' if m.x else 'y' if m.y else None
