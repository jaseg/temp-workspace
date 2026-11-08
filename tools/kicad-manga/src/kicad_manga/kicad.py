"""Reading KiCad schematics, through gerbonara's object model: loading, and small accessors that smooth over
the differences between its item types and file format versions."""

from pathlib import Path

from gerbonara.cad.kicad.schematic import Schematic

DASHES = {'dash': '1.4 .8', 'dot': '.2 .6', 'dash_dot': '1.4 .6 .2 .6', 'dash_dot_dot': '1.4 .6 .2 .6 .2 .6'}


def load(path):
    return Schematic.open(Path(path))


def paper_size(sch):
    return sch.page_settings.size


def paper_name(sch):
    p = sch.page_settings
    return f'{p.width:g}×{p.height:g} mm' if p.page_format == 'User' and p.width else str(p.page_format)


def title_comment(tb, n):
    """Title block comment n (from 1), with older and newer gerbonara alike."""
    if tb is None:
        return ''
    if hasattr(tb, 'comment'):
        return tb.comment(n) or ''
    cs = tb.comments or []
    return (cs[n - 1] or '') if 0 < n <= len(cs) and isinstance(cs[n - 1], str) else ''


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
    """Whether a text item, pin name/number or pin is hidden."""
    if item is None:
        return False
    if hasattr(item, 'is_hidden'):
        return item.is_hidden
    eff = getattr(item, 'effects', None)
    return bool(getattr(item, 'hide', False)) or bool(eff is not None and eff.hide)


def at(item):
    a = item.at
    return float(a.x), float(a.y)


def rotation(item):
    return float(getattr(item.at, 'rotation', 0) or 0)


def xy(p):
    return float(p.x), float(p.y)


# ----------------------------------------------------------------------------
# Library symbols

class LibSymbol:
    """A library symbol with `(extends ...)` resolved: its own fields, with the units (graphics and pins), pin
    settings and power flag taken from the symbol it extends."""

    def __init__(self, sym):
        try:
            base = sym.resolve()
        except KeyError:
            base = sym
        self.sym = sym
        self.units = base.units
        self.power = sym.power if sym.power is not None else base.power
        self.pin_names = base.pin_names
        self.pin_numbers = base.pin_numbers

    @property
    def is_power(self):
        return self.power is not None


def lib_symbols(sch):
    """{lib_id: LibSymbol} for the symbols embedded in the schematic."""
    return {s.raw_name: LibSymbol(s) for s in sch.lib_symbols.symbols}


def quarter_turned(sym):
    """Whether a placed symbol is rotated by 90 or 270 degrees."""
    return round(sym.at.rotation or 0) % 180 == 90
