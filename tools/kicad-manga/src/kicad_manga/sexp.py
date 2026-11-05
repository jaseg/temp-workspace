"""KiCad s-expression parsing and small geometry/text helpers shared by the renderer."""

import math
import re
from html import escape

TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


def unescape(s):
    return re.sub(r'\\(.)', lambda m: {'n': '\n', 't': '\t'}.get(m.group(1), m.group(1)), s)


def parse_sexp(text):
    """Parse KiCad's s-expression format into nested lists of strings."""
    stack = [[]]
    for m in TOKEN.finditer(text):
        t = m.group()
        if t == '(':
            stack.append([])
        elif t == ')':
            node = stack.pop()
            stack[-1].append(node)
        elif t[0] == '"':
            stack[-1].append(unescape(t[1:-1]))
        else:
            stack[-1].append(t)
    return stack[0][0]


def kids(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def kid(node, key, default=None):
    for c in node:
        if isinstance(c, list) and c and c[0] == key:
            return c
    return default


def val(node, key, idx=1, default=None, conv=None):
    k = kid(node, key) if node is not None else None
    if k is None or len(k) <= idx:
        return default
    return conv(k[idx]) if conv else k[idx]


def xy(node, key='at'):
    k = kid(node, key)
    return (float(k[1]), float(k[2])) if k else (0.0, 0.0)


def angle(node, key='at'):
    k = kid(node, key)
    return float(k[3]) if k and len(k) > 3 else 0.0


def pts(node):
    return [(float(p[1]), float(p[2])) for p in kids(kid(node, 'pts') or [], 'xy')]


def yes(node, key):
    k = kid(node, key)
    return k is not None and (len(k) == 1 or k[1] == 'yes')


def is_hidden(node):
    if yes(node, 'hide'):
        return True
    eff = kid(node, 'effects')
    return eff is not None and yes(eff, 'hide')


def font(node):
    """(size, bold, italic, colour or None) of a text item's effects."""
    f = kid(kid(node, 'effects') or [], 'font') or []
    s = kid(f, 'size')
    size = float(s[1]) if s else 1.27
    return size, yes(f, 'bold'), yes(f, 'italic'), color(f)


def font_size(node, default=1.27):
    f = kid(kid(node, 'effects') or [], 'font')
    s = kid(f, 'size') if f else None
    return float(s[1]) if s else default


def justify(node):
    eff = kid(node, 'effects')
    j = kid(eff, 'justify') if eff is not None else None
    j = j[1:] if j else []
    h = 'left' if 'left' in j else 'right' if 'right' in j else 'center'
    v = 'top' if 'top' in j else 'bottom' if 'bottom' in j else 'center'
    return h, v


def color(node):
    """A (color r g b a) child as '#rrggbb', or None when absent or fully transparent."""
    c = kid(node or [], 'color')
    if not c or len(c) < 5 or float(c[4]) == 0:
        return None
    return '#%02x%02x%02x' % tuple(int(float(v)) for v in c[1:4])


def stroke(node):
    """(width, dash type, colour or None) of a (stroke ...) child."""
    st = kid(node, 'stroke') or []
    return val(st, 'width', default=0, conv=float), val(st, 'type', default='default'), color(st)


DASHES = {'dash': '1.4 .8', 'dot': '.2 .6', 'dash_dot': '1.4 .6 .2 .6', 'dash_dot_dot': '1.4 .6 .2 .6 .2 .6'}


def f2(v):
    return f'{v:.3f}'.rstrip('0').rstrip('.') or '0'


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


# ----------------------------------------------------------------------------
# Text with KiCad's ~{overbar} _{sub} ^{super} markup

MARKUP = re.compile(r'([~_^])\{((?:[^{}]|\{[^{}]*\})*)\}')


def markup_tspans(s):
    out, pos = [], 0
    for m in MARKUP.finditer(s):
        out.append(escape(s[pos:m.start()]))
        kind, inner = m.group(1), escape(m.group(2))
        if kind == '~':
            out.append(f'<tspan class="ovl">{inner}</tspan>')
        elif kind == '_':
            out.append(f'<tspan baseline-shift="sub" font-size="75%">{inner}</tspan>')
        else:
            out.append(f'<tspan baseline-shift="super" font-size="75%">{inner}</tspan>')
        pos = m.end()
    out.append(escape(s[pos:]))
    return ''.join(out)


def plain(s):
    return MARKUP.sub(lambda m: m.group(2), s)


FS = 1.36     # SVG font-size per KiCad text height
CHAR_W = 0.6  # rough average advance (em), only used for collision estimates


def text_extent(s, size):
    lines = plain(s).split('\n')
    return max(len(line) for line in lines) * CHAR_W * FS * size, len(lines) * 1.5 * size


def text_el(x, y, s, size, ang, h, v, cls, extra='', tid=None, style=''):
    """KiCad-style text anchored at (x, y); ang is 0 or 90 (reads bottom-to-top).

    Wrapped in its own <g> holding the position, so a background can be slotted
    in front of the <text> later (see `bg_marker`)."""
    anchor = {'left': 'start', 'right': 'end', 'center': 'middle'}[h]
    lines = s.split('\n')
    lh = 1.55 * size
    if v == 'center':
        y0, base = -(len(lines) - 1) * lh / 2, 'central'
    elif v == 'bottom':
        y0, base = -(len(lines) - 1) * lh, 'alphabetic'
    else:
        y0, base = 0, 'hanging'
    spans = ''.join(f'<tspan x="0" y="{f2(y0 + i * lh)}">{markup_tspans(line)}</tspan>' for i, line in enumerate(lines))
    rot = ' rotate(-90)' if round(ang) % 180 == 90 else ''
    idattr = f' id="{tid}"' if tid else ''
    marker = bg_marker(tid) if tid else ''
    st = f' style="{style}"' if style else ''
    return (f'<g transform="translate({f2(x)} {f2(y)}){rot}">{marker}<text{idattr} class="{cls}" '
            f'font-size="{f2(size * FS)}" text-anchor="{anchor}" dominant-baseline="{base}"{st}{extra}>'
            f'{spans}</text></g>')


def bg_marker(tid):
    """Placeholder that is replaced by a background shape once the text is measured."""
    return f'<!--bg:{tid}-->'


def natural_key(s):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', s)]


# ----------------------------------------------------------------------------
# Component values

SI = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'µ': 1e-6, 'μ': 1e-6, 'm': 1e-3, '': 1,
      'k': 1e3, 'K': 1e3, 'M': 1e6, 'G': 1e9, 'R': 1, 'r': 1}
VALUE = re.compile(r'^\s*(\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([pnuµμmkKMGRr]?)(\d*)')


def parse_si(s):
    """Parse component values: '100n', '100 nF', '0.1uF', '4u7', '4.7µF', '1e-7', '22u/6V3',
    '3k3', '10k 1%' ... Returns None for anything else ('?', 'DNP', 'C')."""
    m = VALUE.match(s or '')
    if not m:
        return None
    num, unit, frac = m.groups()
    if frac:
        if '.' in num or 'e' in num.lower():
            return None
        num = f'{num}.{frac}'
    return float(num) * SI[unit]
