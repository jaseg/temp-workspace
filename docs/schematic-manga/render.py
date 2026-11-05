#!/usr/bin/env python3
"""Render a KiCad 10 schematic (.kicad_sch) as a pastel, manga-styled SVG.

    python render.py INPUT.kicad_sch FONT_DIR OUT.svg

The SVG this writes still needs `finish.js` (run in Chromium via Playwright):
that step measures the real text extents with the embedded fonts, draws the
label pills / speech bubbles / title banners behind them, and exports the final
SVG and PNG.
"""

import base64
import colorsys
import hashlib
import math
import random
import re
import sys

import characters as C
from html import escape

# ----------------------------------------------------------------------------
# S-expression parsing

TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


def unescape(s):
    return re.sub(r'\\(.)', lambda m: {'n': '\n', 't': '\t'}.get(m.group(1), m.group(1)), s)


def parse_sexp(text):
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
    k = kid(node, key)
    if k is None or len(k) <= idx:
        return default
    return conv(k[idx]) if conv else k[idx]


def xy(node, key='at'):
    k = kid(node, key)
    return (float(k[1]), float(k[2])) if k else (0.0, 0.0)


def is_hidden(node):
    h = kid(node, 'hide')
    if h is not None:
        return len(h) == 1 or h[1] == 'yes'
    eff = kid(node, 'effects')
    if eff is not None:
        h = kid(eff, 'hide')
        if h is not None:
            return len(h) == 1 or h[1] == 'yes'
        return 'hide' in eff
    return False


def font_size(node, default=1.27):
    eff = kid(node, 'effects')
    if eff is None:
        return default
    f = kid(eff, 'font')
    if f is None:
        return default
    s = kid(f, 'size')
    return float(s[1]) if s else default


def justify(node):
    eff = kid(node, 'effects')
    j = kid(eff, 'justify') if eff is not None else None
    j = j[1:] if j else []
    h = 'left' if 'left' in j else 'right' if 'right' in j else 'center'
    v = 'top' if 'top' in j else 'bottom' if 'bottom' in j else 'center'
    return h, v, ('mirror' in j)


# ----------------------------------------------------------------------------
# Palette

INK = '#4b3a5a'          # soft plum "ink" instead of black
INK_SOFT = '#8a7499'
PAPER = '#fffaf2'
PASTELS = ['#ffb8d0', '#a9e6cf', '#a9d4ff', '#ffe58f', '#d4c1ff', '#ffc9a3',
           '#9fe3e0', '#f7b9f0', '#c5e89c', '#ffd0dc', '#b9c7ff', '#ffdf9e']


def hls_hex(h, l, s):
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, l, s)
    return '#%02x%02x%02x' % (round(r * 255), round(g * 255), round(b * 255))


def _jitter(name, n):
    return int(hashlib.md5(name.encode()).hexdigest()[:8], 16) % n


class NetColors:
    """Pastel net colours in families: every net whose name starts with the same word
    (FPGA_*, SEND_*, LED1..3, ...) gets a shade of one hue; positive supply rails share
    warm coral/amber shades and grounds share neutral lilac-greys."""

    SIGNAL_HUES = (55, 330)   # the warm 330..55 range is kept for the supply rails

    def __init__(self, names):
        prefixes = sorted({self.prefix(n) for n in names if not self.is_supply(n)})
        lo, hi = self.SIGNAL_HUES
        golden = 0.6180339887
        self.hue = {p: lo + ((i * golden) % 1) * (hi - lo) for i, p in enumerate(prefixes)}

    @staticmethod
    def is_supply(name):
        return name.startswith('+') or name.startswith('GND') or name.startswith('VCC')

    @staticmethod
    def prefix(name):
        m = re.match(r'[A-Za-z]+', name.lstrip('+~{'))
        return m.group(0).upper() if m else name

    def __call__(self, name):
        if name is None:
            return None
        j = _jitter(name, 1000) / 1000
        if name.startswith('GND'):
            return hls_hex(262 + 18 * j, .80 + .05 * j, .22)
        if self.is_supply(name):
            return hls_hex(-8 + 48 * j, .78, .9)
        base = re.sub(r'(_?[PN])$', '', name)          # a diff pair's two halves match
        j = _jitter(base, 1000) / 1000
        lo, hi = self.SIGNAL_HUES
        hue = self.hue.get(self.prefix(name), lo + _jitter(self.prefix(name), hi - lo))
        return hls_hex(hue + 14 * (j - .5), .76 + .08 * j, .72)

BODY_COLORS = [
    (('MCU', 'FPGA', 'Gowin'), '#e6d9ff'),
    (('Connector',), '#d3ebff'),
    (('Regulator', 'Power_Management', 'Power_Protection'), '#ffe2cc'),
    (('Amplifier',), '#fff1b5'),
    (('HighSpeed', 'Interface'), '#cff3e2'),
    (('Memory',), '#ffd9ea'),
]


def hashcol(s, pal=PASTELS):
    h = int(hashlib.md5(s.encode()).hexdigest(), 16)
    return pal[h % len(pal)]


def body_color(lib_id):
    for keys, c in BODY_COLORS:
        if any(k in lib_id for k in keys):
            return c
    return hashcol(lib_id, ['#ffd9e6', '#d9f5e9', '#dcecff', '#fff3c4', '#ece0ff', '#ffe4d1'])


def f2(v):
    return f'{v:.3f}'.rstrip('0').rstrip('.')


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


FS = 1.36   # SVG font-size per KiCad text height
CHAR_W = 0.6  # rough average advance (em) used for collision estimates only


def text_extent(s, size):
    lines = plain(s).split('\n')
    return max(len(l) for l in lines) * CHAR_W * FS * size, len(lines) * 1.5 * size


class Svg:
    def __init__(self):
        self.layers = {}

    def add(self, layer, s):
        self.layers.setdefault(layer, []).append(s)


def text_el(x, y, s, size, angle, h, v, cls, extra=''):
    """KiCad-style text anchored at (x, y); angle is 0 or 90 (reads bottom-to-top)."""
    anchor = {'left': 'start', 'right': 'end', 'center': 'middle'}[h]
    lines = s.split('\n')
    lh = 1.55 * size
    if v == 'center':
        y0 = -(len(lines) - 1) * lh / 2
        base = 'central'
    elif v == 'bottom':
        y0 = -(len(lines) - 1) * lh
        base = 'alphabetic'
    else:
        y0 = 0
        base = 'hanging'
    spans = ''.join(
        f'<tspan x="0" y="{f2(y0 + i * lh)}">{markup_tspans(l)}</tspan>' for i, l in enumerate(lines))
    rot = ' rotate(-90)' if angle % 180 == 90 else ''
    return (f'<g transform="translate({f2(x)} {f2(y)}){rot}"><text class="{cls}" '
            f'font-size="{f2(size * FS)}" text-anchor="{anchor}" dominant-baseline="{base}"{extra}>'
            f'{spans}</text></g>')


# ----------------------------------------------------------------------------
# Occupancy grid, used to keep decorations out of the circuit

class Grid:
    def __init__(self, w, h, cell=1.0):
        self.cell, self.nx, self.ny = cell, int(w / cell) + 1, int(h / cell) + 1
        self.occ = bytearray(self.nx * self.ny)

    def mark_rect(self, x0, y0, x1, y1, pad=0.0):
        if x0 > x1:
            x0, x1 = x1, x0
        if y0 > y1:
            y0, y1 = y1, y0
        c = self.cell
        i0, i1 = max(0, int((x0 - pad) / c)), min(self.nx - 1, int((x1 + pad) / c))
        j0, j1 = max(0, int((y0 - pad) / c)), min(self.ny - 1, int((y1 + pad) / c))
        for j in range(j0, j1 + 1):
            row = j * self.nx
            self.occ[row + i0:row + i1 + 1] = b'\x01' * (i1 - i0 + 1)

    def free(self, x0, y0, x1, y1):
        c = self.cell
        i0, i1 = int(x0 / c), int(x1 / c)
        j0, j1 = int(y0 / c), int(y1 / c)
        if i0 < 0 or j0 < 0 or i1 >= self.nx or j1 >= self.ny:
            return False
        for j in range(j0, j1 + 1):
            row = j * self.nx
            if any(self.occ[row + i0:row + i1 + 1]):
                return False
        return True


# ----------------------------------------------------------------------------
# Nets (only used to colour wires and label pills)

class UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.p[b] = a


def on_segment(p, a, b, eps=0.01):
    (px, py), (ax, ay), (bx, by) = p, a, b
    if abs((bx - ax) * (py - ay) - (by - ay) * (px - ax)) > eps * max(1, math.hypot(bx - ax, by - ay)):
        return False
    return (min(ax, bx) - eps <= px <= max(ax, bx) + eps) and (min(ay, by) - eps <= py <= max(ay, by) + eps)


def key(p):
    return (round(p[0] * 100), round(p[1] * 100))


# ----------------------------------------------------------------------------

PAPER_SIZES = {'A4': (297, 210), 'A3': (420, 297), 'A2': (594, 420), 'A1': (841, 594), 'A0': (1189, 841)}


CHARACTER_PARTS = {'Device:C_Small', 'Device:C', 'Device:R', 'Device:R_Small', 'Device:L_Ferrite',
                   'Device:Crystal_GND24_Small'}


class Renderer:
    def __init__(self, sch):
        self.sch = sch
        paper = val(sch, 'paper', default='A4')
        self.W, self.H = PAPER_SIZES.get(paper, (297, 210))
        self.svg = Svg()
        self.grid = Grid(self.W, self.H, 1.0)
        self.libs = {s[1]: s for s in kids(kid(sch, 'lib_symbols'), 'symbol')}
        self.rng = random.Random(7)
        self.faces = []
        self.fine = Grid(self.W, self.H, 0.5)   # tight occupancy, for the characters' props
        self.passives = []

    # -- nets ---------------------------------------------------------------
    def build_nets(self):
        wires = []
        for w in kids(self.sch, 'wire'):
            pts = [(float(p[1]), float(p[2])) for p in kids(kid(w, 'pts'), 'xy')]
            wires.append((pts[0], pts[1]))
        self.wires = wires
        uf = UF(len(wires))
        ends = {}
        for i, (a, b) in enumerate(wires):
            for p in (a, b):
                k = key(p)
                if k in ends:
                    uf.union(ends[k], i)
                else:
                    ends[k] = i
        for i, (a, b) in enumerate(wires):
            for j, (c, d) in enumerate(wires):
                if i != j and (on_segment(c, a, b) or on_segment(d, a, b)):
                    uf.union(i, j)
        names = {}

        def name_at(p, name):
            for i, (a, b) in enumerate(wires):
                if on_segment(p, a, b):
                    names.setdefault(uf.find(i), name)
                    return

        for lab in kids(self.sch, 'label'):
            name_at(xy(lab), lab[1])
        for sym in kids(self.sch, 'symbol'):
            lib = self.libs.get(val(sym, 'lib_id'))
            if lib is not None and kid(lib, 'power') is not None:
                v = next((p[2] for p in kids(sym, 'property') if p[1] == 'Value'), None)
                if v:
                    name_at(xy(sym), v)
        self.net_of = [uf.find(i) for i in range(len(wires))]
        self.net_name = names
        self.colors = NetColors(set(names.values()))

    def net_color(self, root):
        name = self.net_name.get(root)
        if name:
            return self.colors(name)
        # unnamed nets: a muted grey-teal family
        return hls_hex(175 + 30 * _jitter(str(root), 1000) / 1000, .8, .28)

    # -- primitives ---------------------------------------------------------
    def render_wires(self):
        outer, inner = [], []
        for (a, b), root in zip(self.wires, self.net_of):
            d = f'M{f2(a[0])} {f2(a[1])}L{f2(b[0])} {f2(b[1])}'
            outer.append(d)
            inner.append((self.net_color(root), d))
            self.grid.mark_rect(a[0], a[1], b[0], b[1], pad=0.8)
            self.fine.mark_rect(a[0], a[1], b[0], b[1], pad=0.45)
        self.svg.add('wire_o', f'<path class="wire-o" d="{"".join(outer)}"/>')
        by_col = {}
        for c, d in inner:
            by_col.setdefault(c, []).append(d)
        for c, ds in by_col.items():
            self.svg.add('wire_i', f'<path class="wire-i" stroke="{c}" d="{"".join(ds)}"/>')
        bus = []
        for b in kids(self.sch, 'bus'):
            pts = [(float(p[1]), float(p[2])) for p in kids(kid(b, 'pts'), 'xy')]
            bus.append('M' + 'L'.join(f'{f2(x)} {f2(y)}' for x, y in pts))
            self.grid.mark_rect(pts[0][0], pts[0][1], pts[-1][0], pts[-1][1], pad=1.2)
        for be in kids(self.sch, 'bus_entry'):
            x, y = xy(be)
            sx, sy = xy(be, 'size')
            bus.append(f'M{f2(x)} {f2(y)}l{f2(sx)} {f2(sy)}')
        if bus:
            d = ''.join(bus)
            self.svg.add('wire_o', f'<path class="bus-o" d="{d}"/>')
            self.svg.add('wire_i', f'<path class="bus-i" d="{d}"/>')

    def render_junctions(self):
        for j in kids(self.sch, 'junction'):
            x, y = xy(j)
            self.svg.add('junction', f'<circle cx="{f2(x)}" cy="{f2(y)}" r=".62" fill="{INK}"/>')
        for n in kids(self.sch, 'no_connect'):
            x, y = xy(n)
            d = f'M{f2(x - .7)} {f2(y - .7)}l1.4 1.4M{f2(x + .7)} {f2(y - .7)}l-1.4 1.4'
            self.svg.add('junction', f'<path class="nc-o" d="{d}"/><path class="nc-i" d="{d}"/>')

    def render_flags(self):
        for fl in kids(self.sch, 'netclass_flag'):
            x, y = xy(fl)
            length = val(fl, 'length', default=2.54, conv=float)
            prop = kid(fl, 'property')
            px, py = xy(prop) if prop else (x, y - length)
            dx, dy = px - x, py - y
            if abs(dx) > abs(dy):
                ux, uy = (1 if dx > 0 else -1), 0
            else:
                ux, uy = 0, (1 if dy > 0 else -1)
            ex, ey = x + ux * length, y + uy * length
            name = prop[2] if prop else ''
            col = hashcol('flag' + name, ['#ff9ec7', '#9fdcff', '#b7eb9c'])
            self.svg.add('flag', f'<path class="flag" d="M{f2(x)} {f2(y)}L{f2(ex)} {f2(ey)}"/>'
                                 f'<use href="#blossom" x="{f2(ex)}" y="{f2(ey)}" fill="{col}"/>')
            self.grid.mark_rect(x, y, ex, ey, pad=1.0)
            self.fine.mark_rect(x, y, ex, ey, pad=1.0)

    def render_labels(self):
        for lab in kids(self.sch, 'label'):
            x, y = xy(lab)
            ang = float(kid(lab, 'at')[3]) if len(kid(lab, 'at')) > 3 else 0
            h, v, _ = justify(lab)
            size = font_size(lab)
            name = lab[1]
            col = '#fff6b8'
            for i, (a, b) in enumerate(self.wires):
                if on_segment((x, y), a, b):
                    col = self.net_color(self.net_of[i])
                    break
            vertical = ang % 180 == 90
            off = 0.75
            if vertical:
                tx, ty = x - off, y
            else:
                tx, ty = x, y - off
            self.svg.add('label', text_el(tx, ty, name, size, 90 if vertical else 0, h, 'bottom', 'lbl',
                                          f' data-pill="{col}"'))
            w, hh = text_extent(name, size)
            sign = 1 if h == 'left' else -1
            if vertical:
                self.grid.mark_rect(x - off - hh, y, x, y - sign * w, pad=0.6)
                self.fine.mark_rect(x - off - hh, y, x, y - sign * w, pad=0.4)
            else:
                self.grid.mark_rect(x, y - off - hh, x + sign * w, y, pad=0.6)
                self.fine.mark_rect(x, y - off - hh, x + sign * w, y, pad=0.4)

    def render_texts(self):
        for t in kids(self.sch, 'text'):
            s = t[1]
            x, y = xy(t)
            at = kid(t, 'at')
            ang = float(at[3]) if len(at) > 3 else 0
            size = font_size(t)
            h, v, _ = justify(t)
            w, hh = text_extent(s, size)
            if size >= 2.4:
                cls, extra = 'title', ' data-banner="1"'
                w, hh = w * 1.25, hh * 1.4
            elif size >= 1.8:
                cls, extra = 'caption', ''
            elif len(plain(s)) >= 14:
                cls, extra = 'note', ' data-bubble="1"'
            else:
                cls, extra = 'remark', ''
            self.svg.add('title' if cls == 'title' else 'text', text_el(x, y, s, size, ang, h, v, cls, extra))
            hx = {'left': (0, w), 'right': (-w, 0), 'center': (-w / 2, w / 2)}[h]
            vy = {'top': (0, hh), 'bottom': (-hh, 0), 'center': (-hh / 2, hh / 2)}[v]
            if ang % 180 == 90:
                self.grid.mark_rect(x + vy[0], y - hx[1], x + vy[1], y - hx[0], pad=2.5)
                self.fine.mark_rect(x + vy[0], y - hx[1], x + vy[1], y - hx[0], pad=0.8)
            else:
                self.grid.mark_rect(x + hx[0], y + vy[0], x + hx[1], y + vy[1], pad=2.5)
                self.fine.mark_rect(x + hx[0], y + vy[0], x + hx[1], y + vy[1], pad=0.8)

    # -- symbols ------------------------------------------------------------
    def render_symbols(self):
        for sym in kids(self.sch, 'symbol'):
            self.render_symbol(sym)

    def render_symbol(self, sym):
        lib_id = val(sym, 'lib_id')
        lib = self.libs[lib_id]
        at = kid(sym, 'at')
        x, y = float(at[1]), float(at[2])
        rot = float(at[3]) if len(at) > 3 else 0
        mirror = val(sym, 'mirror')
        unit = val(sym, 'unit', default=1, conv=int)
        style = val(sym, 'body_style', default=1, conv=int)
        dnp = val(sym, 'dnp') == 'yes'
        xf = Xf(x, y, rot, mirror)
        power = kid(lib, 'power') is not None
        fill_col = body_color(lib_id)
        rail_col = None
        props = {p[1]: p for p in kids(sym, 'property')}
        if power:
            rail_col = self.colors(props.get('Value', [0, 0, ''])[2]) or '#ffd0e0'

        pn = kid(lib, 'pin_names')
        name_off = val(pn, 'offset', default=0.508, conv=float) if pn is not None else 0.508
        names_hidden = pn is not None and is_hidden(pn)
        pnum = kid(lib, 'pin_numbers')
        nums_hidden = pnum is not None and is_hidden(pnum)

        units = set()
        subs = []
        for sub in kids(lib, 'symbol'):
            m = re.match(r'.*_(\d+)_(\d+)$', sub[1])
            u, st = int(m.group(1)), int(m.group(2))
            units.add(u)
            if u in (0, unit) and st in (0, style):
                subs.append(sub)

        shadow, fills, strokes, pins_svg, texts = [], [], [], [], []
        xs, ys = [], []
        rects = []
        pins = []

        def P(px, py):
            X, Y = xf(px, py)
            xs.append(X)
            ys.append(Y)
            return X, Y

        for sub in subs:
            for g in sub[2:]:
                if not isinstance(g, list):
                    continue
                kind = g[0]
                ftype = val(kid(g, 'fill') or [], 'type', default='none')
                sw = val(kid(g, 'stroke') or [], 'width', default=0, conv=float)
                d = None
                closed = False
                if kind == 'polyline':
                    pts = [P(float(p[1]), float(p[2])) for p in kids(kid(g, 'pts'), 'xy')]
                    d = 'M' + 'L'.join(f'{f2(a)} {f2(b)}' for a, b in pts)
                    closed = len(pts) > 2 and (ftype != 'none' or power)
                    if closed and ftype == 'background':
                        d = rounded_poly(pts, 1.0)
                elif kind == 'rectangle':
                    (sx, sy), (ex, ey) = xy(g, 'start'), xy(g, 'end')
                    a, b = P(sx, sy), P(ex, ey)
                    rx0, rx1 = sorted((a[0], b[0]))
                    ry0, ry1 = sorted((a[1], b[1]))
                    rr = min(0.9, 0.12 * min(rx1 - rx0, ry1 - ry0))
                    d = (f'M{f2(rx0 + rr)} {f2(ry0)}H{f2(rx1 - rr)}Q{f2(rx1)} {f2(ry0)} {f2(rx1)} {f2(ry0 + rr)}'
                         f'V{f2(ry1 - rr)}Q{f2(rx1)} {f2(ry1)} {f2(rx1 - rr)} {f2(ry1)}H{f2(rx0 + rr)}'
                         f'Q{f2(rx0)} {f2(ry1)} {f2(rx0)} {f2(ry1 - rr)}V{f2(ry0 + rr)}Q{f2(rx0)} {f2(ry0)} {f2(rx0 + rr)} {f2(ry0)}Z')
                    closed = True
                    rects.append((sx, sy, ex, ey, ftype))
                    if ftype == 'none':
                        ftype = 'pale'
                elif kind == 'circle':
                    cx, cy = P(*xy(g, 'center'))
                    r = val(g, 'radius', conv=float)
                    xs.extend((cx - r, cx + r))
                    ys.extend((cy - r, cy + r))
                    d = f'M{f2(cx - r)} {f2(cy)}a{f2(r)} {f2(r)} 0 1 0 {f2(2 * r)} 0a{f2(r)} {f2(r)} 0 1 0 {f2(-2 * r)} 0Z'
                    closed = True
                    if ftype == 'none' and r > 1:
                        ftype = 'pale'
                elif kind == 'arc':
                    s, m_, e = P(*xy(g, 'start')), P(*xy(g, 'mid')), P(*xy(g, 'end'))
                    d = arc_path(s, m_, e)
                elif kind == 'bezier':
                    pts = [P(float(p[1]), float(p[2])) for p in kids(kid(g, 'pts'), 'xy')]
                    d = f'M{f2(pts[0][0])} {f2(pts[0][1])}C' + ' '.join(f'{f2(a)} {f2(b)}' for a, b in pts[1:])
                elif kind == 'text':
                    if is_hidden(g):
                        continue
                    tx, ty = P(*xy(g))
                    ang = float(kid(g, 'at')[3]) if len(kid(g, 'at')) > 3 else 0
                    h, v, _ = justify(g)
                    texts.append(text_el(tx, ty, g[1], font_size(g), ang / 10 if ang > 360 else ang, h, v, 'symtxt'))
                    continue
                elif kind == 'pin':
                    pins.append(g)
                    continue
                if d is None:
                    continue
                if power and closed:
                    fills.append(f'<path d="{d}" fill="{rail_col}"/>')
                    strokes.append(f'<path d="{d}" class="sym-s"/>')
                    continue
                if ftype == 'background':
                    shadow.append(f'<path d="{d}"/>')
                    fills.append(f'<path d="{d}" fill="{fill_col}"/>')
                    fills.append(f'<path d="{d}" fill="url(#tone-w)"/>')
                elif ftype == 'pale' and closed:
                    fills.append(f'<path d="{d}" fill="{fill_col}" fill-opacity=".85"/>')
                elif ftype == 'outline' and closed:
                    fills.append(f'<path d="{d}" fill="{INK}"/>')
                strokes.append(f'<path d="{d}" class="sym-s{" thick" if sw >= 0.25 else ""}"/>')

        # pins
        for pin in pins:
            if is_hidden(pin):
                continue
            at = kid(pin, 'at')
            px, py, pa = float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0
            L = val(pin, 'length', default=2.54, conv=float)
            ux, uy = round(math.cos(math.radians(pa))), round(math.sin(math.radians(pa)))
            a = P(px, py)
            b = P(px + ux * L, py + uy * L)
            if L > 0:
                pins_svg.append(f'M{f2(a[0])} {f2(a[1])}L{f2(b[0])} {f2(b[1])}')
            sdx, sdy = b[0] - a[0], b[1] - a[1]
            nrm = math.hypot(sdx, sdy) or 1
            sdx, sdy = sdx / nrm, sdy / nrm
            vertical = abs(sdy) > 0.5
            name_node = kid(pin, 'name')
            num_node = kid(pin, 'number')
            name = name_node[1] if name_node else ''
            num = num_node[1] if num_node else ''
            nsize = font_size(name_node) if name_node else 1.27
            msize = font_size(num_node) if num_node else 1.27
            show_name = not names_hidden and name not in ('', '~') and nsize > 0 and not power
            show_num = not nums_hidden and num != '' and msize > 0 and not power
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            if show_name:
                if name_off > 0:
                    tx, ty = b[0] + sdx * name_off, b[1] + sdy * name_off
                    if vertical:
                        h = 'left' if sdy < 0 else 'right'
                    else:
                        h = 'left' if sdx > 0 else 'right'
                    texts.append(text_el(tx, ty, name, nsize, 90 if vertical else 0, h, 'center', 'pinname'))
                else:
                    if vertical:
                        texts.append(text_el(mx - 0.4, my, name, nsize, 90, 'center', 'bottom', 'pinname'))
                    else:
                        texts.append(text_el(mx, my - 0.4, name, nsize, 0, 'center', 'bottom', 'pinname'))
            if show_num:
                if vertical:
                    if name_off > 0 or not show_name:
                        texts.append(text_el(mx - 0.4, my, num, msize, 90, 'center', 'bottom', 'pinnum'))
                    else:
                        texts.append(text_el(mx + 0.4, my, num, msize, 90, 'center', 'top', 'pinnum'))
                else:
                    if name_off > 0 or not show_name:
                        texts.append(text_el(mx, my - 0.4, num, msize, 0, 'center', 'bottom', 'pinnum'))
                    else:
                        texts.append(text_el(mx, my + 0.4, num, msize, 0, 'center', 'top', 'pinnum'))

        # fields
        nunits = len(units - {0})
        for pname, prop in props.items():
            if is_hidden(prop) or pname not in ('Reference', 'Value') and kid(prop, 'show_name') is None:
                continue
            if is_hidden(prop):
                continue
            s = prop[2]
            if pname == 'Reference':
                if s.startswith('#'):
                    continue
                if nunits > 1:
                    s += chr(ord('A') + unit - 1)
            elif pname != 'Value':
                continue
            fx, fy = xy(prop)
            fat = kid(prop, 'at')
            fang = float(fat[3]) if len(fat) > 3 else 0
            h, v, _ = justify(prop)
            swap = xf.c == 0  # rotated by 90/270: KiCad toggles field orientation
            vertical = (fang % 180 == 90) != swap
            # justification direction, transformed like the symbol, then made readable
            dvec = {'left': 1, 'right': -1, 'center': 0}[h]
            if dvec:
                rd = (math.cos(math.radians(fang)), -math.sin(math.radians(fang)))
                tx_, ty_ = xf.lin(rd[0] * dvec, -rd[1] * dvec)
                if vertical and abs(ty_) > 0.5:
                    h = 'left' if ty_ < 0 else 'right'
                elif not vertical and abs(tx_) > 0.5:
                    h = 'left' if tx_ > 0 else 'right'
            cls = 'ref' if pname == 'Reference' else ('pwr' if power else 'value')
            texts.append(text_el(fx, fy, s, font_size(prop), 90 if vertical else 0, h, v, cls))
            w, hh = text_extent(s, font_size(prop))
            self.grid.mark_rect(fx - w, fy - w if vertical else fy - hh, fx + w, fy + (w if vertical else hh), pad=0.8)
            fsz = font_size(prop) * 1.1
            ext = {'left': (0, w), 'right': (-w, 0), 'center': (-w / 2, w / 2)}[h]
            if vertical:
                self.fine.mark_rect(fx - fsz, fy - ext[1], fx + fsz, fy - ext[0], pad=0.4)
            else:
                self.fine.mark_rect(fx + ext[0], fy - fsz, fx + ext[1], fy + fsz, pad=0.4)

        if xs:
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            self.grid.mark_rect(x0, y0, x1, y1, pad=2.0)
            self.fine.mark_rect(x0, y0, x1, y1, pad=0.3)

        if shadow:
            self.svg.add('shadow', f'<g transform="translate(.9 .9)">{"".join(shadow)}</g>')
        if fills:
            self.svg.add('fill', ''.join(fills))
        if strokes:
            self.svg.add('stroke', ''.join(strokes))
        if pins_svg:
            self.svg.add('stroke', f'<path class="pin" d="{"".join(pins_svg)}"/>')
        if texts:
            self.svg.add('symtext', ''.join(texts))
        if lib_id in CHARACTER_PARTS and xs:
            self.passives.append({'lib_id': lib_id, 'xf': xf, 'lib': lib, 'subs': subs,
                                  'value': props.get('Value', [0, 0, ''])[2], 'dnp': dnp})
        if dnp and xs:
            self.svg.add('dnp', f'<path class="dnp" d="M{f2(x0)} {f2(y0)}L{f2(x1)} {f2(y1)}M{f2(x1)} {f2(y0)}L{f2(x0)} {f2(y1)}"/>')

        # a little face on the larger ICs
        if not power and not dnp:
            self.face_for(lib, xf, rects, pins, name_off, names_hidden, subs)

    def face_for(self, lib, xf, rects, pins, name_off, names_hidden, subs):
        big = [r for r in rects if r[4] == 'background' and abs(r[2] - r[0]) >= 9 and abs(r[3] - r[1]) >= 9]
        if not big:
            return
        body = max(big, key=lambda r: abs(r[2] - r[0]) * abs(r[3] - r[1]))
        sx, sy, ex, ey, _ = body
        x0, x1 = sorted((sx, ex))
        y0, y1 = sorted((sy, ey))
        # no face if the body already has drawings in it (diodes, logos, ...)
        for sub in subs:
            for g in sub[2:]:
                if not isinstance(g, list) or g[0] not in ('polyline', 'rectangle', 'circle', 'arc', 'bezier', 'text'):
                    continue
                if g[0] == 'rectangle':
                    (a, b), (c, d) = xy(g, 'start'), xy(g, 'end')
                    if (a, b, c, d) == (sx, sy, ex, ey):
                        continue
                    gp = [(a, b), (c, d)]
                elif g[0] in ('polyline', 'bezier'):
                    gp = [(float(q[1]), float(q[2])) for q in kids(kid(g, 'pts'), 'xy')]
                elif g[0] == 'circle':
                    gp = [xy(g, 'center')]
                elif g[0] == 'arc':
                    gp = [xy(g, 'start'), xy(g, 'mid'), xy(g, 'end')]
                else:
                    gp = [xy(g)]
                if any(x0 + .3 < px < x1 - .3 and y0 + .3 < py < y1 - .3 for px, py in gp):
                    return
        fx0, fx1, fy0, fy1 = x0 + 1, x1 - 1, y0 + 1, y1 - 1
        for pin in pins:
            if is_hidden(pin):
                continue
            at = kid(pin, 'at')
            pa = float(at[3]) if len(at) > 3 else 0
            name_node = kid(pin, 'name')
            name = name_node[1] if name_node else ''
            if names_hidden or name in ('', '~'):
                intr = 0.5
            else:
                intr = name_off + len(plain(name)) * CHAR_W * FS * font_size(name_node) + 1.0
            hgt = 1.4
            px, py = float(at[1]), float(at[2])
            L = val(pin, 'length', default=2.54, conv=float)
            bx = px + round(math.cos(math.radians(pa))) * L
            by = py + round(math.sin(math.radians(pa))) * L
            if pa == 0:      # pin on the left edge pointing right
                if fy0 - hgt < by < fy1 + hgt:
                    fx0 = max(fx0, x0 + intr)
            elif pa == 180:
                if fy0 - hgt < by < fy1 + hgt:
                    fx1 = min(fx1, x1 - intr)
            elif pa == 90:   # bottom edge pointing up (lib y-up)
                if fx0 - hgt < bx < fx1 + hgt:
                    fy0 = max(fy0, y0 + intr)
            elif pa == 270:
                if fx0 - hgt < bx < fx1 + hgt:
                    fy1 = min(fy1, y1 - intr)
        # inner symbol text
        for sub in kids(lib, 'symbol'):
            for t in kids(sub, 'text'):
                tx, ty = xy(t)
                if fx0 < tx < fx1 and fy0 < ty < fy1:
                    w, _ = text_extent(t[1], font_size(t))
                    if ty > (fy0 + fy1) / 2:
                        fy1 = min(fy1, ty - 2)
                    else:
                        fy0 = max(fy0, ty + 2)
        fw, fh = fx1 - fx0, fy1 - fy0
        size = min(fw, fh, 16) * 0.8
        if size < 4:
            return
        cx, cy = xf((fx0 + fx1) / 2, (fy0 + fy1) / 2)
        mood = self.rng.choice(['happy', 'wink', 'smile', 'cat', 'sparkle'])
        self.svg.add('face', f'<use href="#face-{mood}" transform="translate({f2(cx)} {f2(cy)}) scale({f2(size / 10)})"/>')

    # -- passive components as characters -----------------------------------
    def render_characters(self):
        rng = random.Random(11)
        moods = ['grumpy', 'yell', 'smug', 'pout']
        add = lambda svg: self.svg.add('char', svg)
        for p in self.passives:
            xf, lib_id = p['xf'], p['lib_id']
            cx, cy = xf(0, 0)
            ax, ay = xf.lin(0, 1)
            vertical = abs(ay) > .5
            polys = [[xf(float(q[1]), float(q[2])) for q in kids(kid(g, 'pts'), 'xy')]
                     for sub in p['subs'] for g in kids(sub, 'polyline')]
            if lib_id in ('Device:C_Small', 'Device:C'):
                add(C.cat_capacitor(rng, cx, cy, vertical, p['value'], []))
                self.fine.mark_rect(cx - 2.4, cy - 2.4, cx + 2.4, cy + 2.4)
            elif lib_id in ('Device:R', 'Device:R_Small'):
                half = 2.54 if lib_id == 'Device:R' else 1.778
                throw = None
                if rng.random() < .8:
                    nx, ny = (1, 0) if vertical else (0, 1)
                    tx, ty = (0, 1) if vertical else (1, 0)
                    cands = []
                    for dist in (3.8, 5.2, 6.6, 8.2):
                        ring = [(s1 * nx * dist + s2 * tx * 1.6, s1 * ny * dist + s2 * ty * 1.6 - (0 if vertical else .4 * s1))
                                for s1 in (-1, 1) for s2 in (-1.5, -.5, .5, 1.5)]
                        rng.shuffle(ring)
                        cands += ring
                    for dx, dy in cands:
                        px, py = cx + dx, cy + dy
                        mx, my = cx + dx * .6, cy + dy * .6 - 1
                        if self.fine.free(px - 1.8, py - 3.2, px + 1.8, py + 1.9) and \
                                self.fine.free(mx - .5, my - .5, mx + .5, my + .5):
                            throw = (dx, dy, rng.choice(('brick', 'molotov')))
                            self.fine.mark_rect(px - 1.8, py - 3.2, px + 1.8, py + 1.9)
                            self.fine.mark_rect(mx - .6, my - .6, mx + .6, my + .6)
                            break
                add(C.resistor_guy(rng, cx, cy, vertical, half, rng.choice(moods), throw))
            elif lib_id == 'Device:L_Ferrite':
                a, b = xf(0, 2.54), xf(0, -2.54)
                if (a[1], a[0]) > (b[1], b[0]):
                    a, b = b, a
                add(C.caterpillar(rng, a, b, [(q[0], q[-1]) for q in polys]))
            elif lib_id == 'Device:Crystal_GND24_Small':
                (x0, y0), (x1, y1) = xf(-.762, -1.524), xf(.762, 1.524)
                add(C.dancing_crystal(rng, cx, cy, (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)),
                                      lambda qx, qy: self.fine.free(qx - .9, qy - .9, qx + .9, qy + .9)))

    def render_legend(self):
        svg, w, h = C.legend(random.Random(5))
        W, H, m = self.W, self.H, 16
        for x, y in ((m, 30), (W - m - w, 30), (m, H - 70 - h), (m, (H - h) / 2), (W - m - w, (H - h) / 2)):
            if self.grid.free(x - 3, y - 3, x + w + 3, y + h + 3):
                self.svg.add('titlepanel', f'<g transform="translate({f2(x)} {f2(y)})">{svg}</g>')
                self.grid.mark_rect(x, y, x + w, y + h, pad=4)
                return
        print('warning: no free corner for the legend', file=sys.stderr)

    # -- decorations --------------------------------------------------------
    def decorate(self):
        import drawings as D
        rng = random.Random(42)
        W, H = self.W, self.H
        G = self.grid
        fm = 8          # outer frame line
        m = 14          # keep floating things this far inside the page edge
        add = self.svg.add
        top, base = fm + 0.8, H - fm - 0.8   # inner edges of the frame line

        def try_place(wd, ht, tries, pad=1.0):
            for _ in range(tries):
                x = rng.uniform(m + wd / 2, W - m - wd / 2)
                y = rng.uniform(m + ht / 2, H - m - ht / 2)
                if G.free(x - wd / 2 - pad, y - ht / 2 - pad, x + wd / 2 + pad, y + ht / 2 + pad):
                    G.mark_rect(x - wd / 2, y - ht / 2, x + wd / 2, y + ht / 2, pad=pad)
                    return x, y
            return None

        # 1. leafy garlands hanging from the top of the frame, with charms
        x = fm + 5
        joints = []
        while x < W - fm - 25:
            span, sag = rng.uniform(40, 75), rng.uniform(6, 12)
            x1 = min(x + span, W - fm - 5)
            if G.free(x, top + 1.5, x1, top + sag + 4):
                add('edgefront', D.vine(rng, D.garland_pts(x, x1, top + .4, sag), leaf_gap=2.4))
                G.mark_rect(x, top, x1, top + sag + 4, pad=1)
                joints += [x, x1]
                mid = (x + x1) / 2 + rng.uniform(-6, 6)
                L = rng.uniform(5, 13)
                ymid = top + .4 + sag * (1 - ((mid - (x + x1) / 2) / ((x1 - x) / 2)) ** 2) - .3
                if rng.random() < .55 and G.free(mid - 4, ymid + 1, mid + 4, ymid + L + 12):
                    add('edgefront', D.charm(rng, mid, ymid, L))
                    G.mark_rect(mid - 4, ymid, mid + 4, ymid + L + 10, pad=1)
                x = x1
            else:
                x += 5
        for jx in sorted(set(round(v, 1) for v in joints)):
            add('edgefront', D.bow(jx, top + .6, rng.choice(D.FLOWERS)))

        # 2. vines wound around the side frame lines: hanging from the garlands at the
        #    top corners, and growing up out of a pot in the bottom corners
        def strip_free(ex, side, y0, y1, reach=5.5):
            x0, x1 = (ex - 2, ex + reach) if side < 0 else (ex - reach, ex + 2)
            return G.free(x0, min(y0, y1), x1, max(y0, y1))

        for side in (-1, 1):
            ex = fm if side < 0 else W - fm
            # from the top corner downwards
            y, y_stop = top + 1, top + rng.uniform(90, 200)
            while y < y_stop and strip_free(ex, side, y, y + 1, 3 if y < top + 20 else 5.5):
                y += 1
            if y - top > 25:
                back, front = D.twining_vine(rng, ex, top + .6, y - 2)
                add('edgeback', back)
                add('edgefront', front)
                G.mark_rect(ex - 4, top, ex + 4, y, pad=1)
            # from a pot in the bottom corner upwards
            pcx = ex - side * 7
            if G.free(pcx - 5, base - 9, pcx + 5, base - 1.2):
                pot_svg, ptop = D.pot(rng, 8, 6.5, rng.choice(D.POTS), True)
                start = base - 6.5 - 1
                y, y_stop = start - 6, start - rng.uniform(80, 190)
                while y > y_stop and strip_free(ex, side, y - 1, y):
                    y -= 1
                if start - y > 25:
                    lead = [(pcx, base - 6.5), (pcx + side * 1.5, base - 9), (ex - side * 1.2, base - 12.5)]
                    back, front = D.twining_vine(rng, ex, base - 13, y + 2, lead_in=lead)
                    add('edgeback', back)
                    add('edgefront', front + f'<g transform="translate({f2(pcx)} {f2(base)})">{D.wrap(pot_svg)}</g>')
                    G.mark_rect(pcx - 5, base - 9, pcx + 5, base, pad=1)
                    G.mark_rect(ex - 4, y, ex + 4, base, pad=1)

        # 3. things standing on the bottom of the frame: plants, a mug, books, a cat
        limits = {'cat': 1, 'mug': 2, 'books': 2, 'floor_cable': 3}
        ground = D.GROUND_ITEMS * 3 + D.PART_ITEMS + [(None, 3, 3, 0)] * 2
        x = fm + 6
        while x < W - fm - 8:
            draw, lo, hi, ar = rng.choice(ground)
            name = draw.__name__ if draw else 'floor_cable'
            if name == 'floor_cable' and limits['floor_cable'] > 0:
                cw = rng.uniform(40, 52)
                if x + cw < W - fm - 6 and G.free(x, base - 6, x + cw, base - 1.2):
                    add('edgefront', D.floor_cable(rng, x, base, cw, rng.choice(D.CABLES)))
                    G.mark_rect(x, base - 5, x + cw, base, pad=1)
                    limits['floor_cable'] -= 1
                    x += cw + rng.uniform(2, 5)
                continue
            if limits.get(name, 99) <= 0:
                continue
            placed = False
            for h in (rng.uniform(lo, hi), lo, lo * .75):
                w = h * ar
                need = h * (1.6 if name == 'cat' else 1.08)
                if x + w < W - fm - 6 and G.free(x, base - need - 1, x + w, base - 1.2):
                    add('edgefront', f'<g transform="translate({f2(x + w / 2)} {f2(base)})">{draw(rng, h)}</g>')
                    G.mark_rect(x, base - need, x + w, base, pad=1.5)
                    limits[name] = limits.get(name, 99) - 1
                    x += w + rng.uniform(1, 4)
                    placed = True
                    break
            if not placed:
                x += 2.5
                continue
            gw = rng.uniform(5, 16)
            if rng.random() < .7 and G.free(x, base - 7, x + gw, base - 1.2):
                add('edgefront', D.grass(rng, x, base, gw))
                G.mark_rect(x, base - 6, x + gw, base, pad=.5)
                x += gw + rng.uniform(0, 3)

        # 4. cables clipped to the side frame lines, hanging straight down
        cables, tries = 0, 0
        while cables < 8 and tries < 200:
            tries += 1
            side = rng.choice((-1, 1))
            ex = fm if side < 0 else W - fm
            ay = rng.uniform(top + 15, base - 60)
            drop = rng.uniform(22, 55)
            x0, x1 = sorted((ex - side * 5, ex - side * 14))
            if not G.free(x0, ay - 2, x1, ay + drop + 12):
                continue
            add('edgefront', D.hanging_cable(rng, ex, ay, -side, drop, rng.choice(D.CABLES)))
            G.mark_rect(x0, ay - 3, x1, ay + drop + 12, pad=4)
            cables += 1

        # 5. wall shelves with plants and clutter in the big empty areas
        shelf_items = [it for it in D.GROUND_ITEMS if it[0].__name__ != 'cat'] * 3 + D.PART_ITEMS
        for _ in range(5):
            sw, sh = rng.uniform(42, 72), rng.uniform(26, 40)
            pos = try_place(sw, sh + 7, 500, pad=5)
            if not pos:
                continue
            x0 = pos[0] - sw / 2
            plank = pos[1] + (sh + 7) / 2 - 7
            add('deco', D.shelf(x0, plank, sw))
            x, fails, once = x0 + 3, 0, set()
            while x < x0 + sw - 4 and fails < 12:
                draw, lo, hi, ar = rng.choice(shelf_items)
                if draw.__name__ in once:
                    fails += 1
                    continue
                if draw.__name__ in ('mug', 'books'):
                    once.add(draw.__name__)
                h = rng.uniform(lo, min(hi, sh - 2)) if lo < sh - 2 else 0
                if not h or x + h * ar > x0 + sw - 2:
                    fails += 1
                    continue
                add('deco', f'<g transform="translate({f2(x + h * ar / 2)} {f2(plank)})">{draw(rng, h)}</g>')
                x += h * ar + rng.uniform(1.5, 4)
            if rng.random() < .75:
                side = rng.choice((-1, 1))
                edge = x0 + sw if side > 0 else x0
                drop = rng.uniform(14, 30)
                gx0, gx1 = sorted((edge - side * 2, edge + side * 6))
                if G.free(gx0, plank + 13, gx1, plank + drop + 12):
                    add('deco', D.draped_cable(rng, edge, plank, side, drop, rng.choice(D.CABLES)))
                    G.mark_rect(gx0, plank, gx1, plank + drop + 12, pad=2)

        # 6. a few clouds
        for _ in range(6):
            w = rng.uniform(16, 28)
            pos = try_place(w * 1.2, w * .55, 300, pad=3)
            if pos:
                add('deco', f'<g transform="translate({f2(pos[0])} {f2(pos[1] + w * .25)})">{D.cloud(w)}</g>')

        # 7. just a few faint sound effects
        sfx = [('キラキラ', 'kira kira'), ('ふわふわ', 'fuwa fuwa'), ('ドキドキ', 'doki doki')]
        cols = ['#ffb3d1', '#a6e3d3', '#b3d4ff', '#ffd98f', '#cdb8ff', '#ffbfa3']
        for i, (jp, ro) in enumerate(sfx):
            size = rng.uniform(7, 9)
            pos = try_place(len(jp) * size * 1.05, size * 1.6, 600, pad=6)
            if pos:
                add('deco', f'<g transform="translate({f2(pos[0])} {f2(pos[1])}) rotate({f2(rng.uniform(-12, 12))})">'
                            f'<text class="sfx" font-size="{f2(size)}" fill="{cols[i]}" text-anchor="middle" dominant-baseline="central">{jp}</text>'
                            f'<text class="sfx-ro" font-size="{f2(size * 0.24)}" y="{f2(size * 0.85)}" text-anchor="middle">{ro} ♡</text></g>')

        # 8. a light sprinkle of sparkles and confetti
        kinds = [('sparkle', 4, 7), ('heart-d', 3, 5), ('star', 3.5, 6), ('blossom-d', 3.5, 6), ('sparkle', 2.5, 3.5)]
        for _ in range(170):
            k, lo, hi = rng.choice(kinds)
            sz = rng.uniform(lo, hi)
            pos = try_place(sz, sz, 3, pad=6)
            if pos:
                add('deco', f'<use href="#{k}" transform="translate({f2(pos[0])} {f2(pos[1])}) rotate({f2(rng.uniform(-25, 25))}) scale({f2(sz / 10)})" fill="{rng.choice(cols)}" opacity=".38"/>')
        for _ in range(260):
            sz = rng.uniform(.8, 1.6)
            pos = try_place(sz, sz, 2, pad=4)
            if pos:
                add('deco', f'<circle cx="{f2(pos[0])}" cy="{f2(pos[1])}" r="{f2(sz / 2)}" fill="{rng.choice(cols)}" opacity=".28"/>')

    # -- page ---------------------------------------------------------------
    def frame_and_title(self, title):
        W, H = self.W, self.H
        m = 8
        self.svg.add('bg', f'<rect width="{W}" height="{H}" fill="{PAPER}"/>'
                           f'<rect width="{W}" height="{H}" fill="url(#tone-bg)" mask="url(#vignette)" opacity=".7"/>')
        # speed lines radiating from the title corner
        rng = random.Random(3)
        lines = []
        ox, oy = W - 120, H - 60
        for i in range(80):
            a = rng.uniform(0, 2 * math.pi)
            r0 = rng.uniform(95, 140)
            r1 = r0 + rng.uniform(40, 160)
            w = rng.uniform(0.15, 0.9)
            x0, y0 = ox + math.cos(a) * r0, oy + math.sin(a) * r0 * 0.55
            x1, y1 = ox + math.cos(a) * r1, oy + math.sin(a) * r1 * 0.55
            nx, ny = -math.sin(a) * w, math.cos(a) * w
            lines.append(f'M{f2(x0)} {f2(y0)}L{f2(x1 + nx)} {f2(y1 + ny)}L{f2(x1 - nx)} {f2(y1 - ny)}Z')
        self.svg.add('bg', f'<path d="{"".join(lines)}" fill="#f6e2ee" opacity=".4"/>')
        # manga panel frame
        self.svg.add('frame', f'<rect x="{m}" y="{m}" width="{W - 2 * m}" height="{H - 2 * m}" rx="6" class="frame"/>'
                              f'<rect x="{m + 2.6}" y="{m + 2.6}" width="{W - 2 * m - 5.2}" height="{H - 2 * m - 5.2}" rx="4.5" class="frame2"/>')
        for (cx, cy) in ((m + 2, m + 2), (W - m - 2, m + 2), (m + 2, H - m - 2), (W - m - 2, H - m - 2)):
            self.svg.add('frame', f'<use href="#blossom-d" transform="translate({cx} {cy}) scale(1.1)" fill="#ffb8d0"/>')
        # rulers like KiCad's frame, but cute
        for i in range(1, 9):
            x = m + (W - 2 * m) * (i - 0.5) / 8
            self.svg.add('frame', f'<text class="coord" x="{f2(x)}" y="{m - 2.4}" text-anchor="middle">{i}</text>'
                                  f'<text class="coord" x="{f2(x)}" y="{H - m + 5.2}" text-anchor="middle">{i}</text>')
        for i in range(6):
            y = m + (H - 2 * m) * (i + 0.5) / 6
            self.svg.add('frame', f'<text class="coord" x="{m - 4}" y="{f2(y)}" text-anchor="middle" dominant-baseline="central">{"ABCDEF"[i]}</text>'
                                  f'<text class="coord" x="{W - m + 4}" y="{f2(y)}" text-anchor="middle" dominant-baseline="central">{"ABCDEF"[i]}</text>')
        # title panel bottom-right, like a manga cover
        tw, th = 176, 58
        tx, ty = W - m - 8 - tw, H - m - 8 - th
        self.grid.mark_rect(tx - 50, ty - 38, tx + tw + 4, ty + th + 4)
        self.svg.add('titlepanel', f'''
<g transform="translate({f2(tx)} {f2(ty)})">
  <rect x="2.2" y="2.2" width="{tw}" height="{th}" rx="7" fill="url(#tone-ink)"/>
  <rect width="{tw}" height="{th}" rx="7" fill="#fff" stroke="{INK}" stroke-width="1.1"/>
  <rect x="2" y="2" width="{tw - 4}" height="{th - 4}" rx="5.5" fill="url(#title-grad)"/>
  <rect x="2" y="2" width="{tw - 4}" height="{th - 4}" rx="5.5" fill="url(#tone-w)" opacity=".8"/>
  <text class="t-jp" x="{tw / 2}" y="14" text-anchor="middle">✦ センサー回路図 ✦</text>
  <text class="t-main" x="{tw / 2}" y="30" text-anchor="middle">{escape(title)}</text>
  <text class="t-sub" x="{tw / 2}" y="40" text-anchor="middle">~ the pillowbox sensor board ~</text>
  <g transform="translate(12 50)">
    <text class="t-small" x="0" y="0">sheet ♡ 1 / 1</text>
    <text class="t-small" x="{tw - 24}" y="0" text-anchor="end">KiCad 10 · paper A1 · drawn with love ♪</text>
  </g>
</g>
<g transform="translate({f2(tx - 22)} {f2(ty + 28)})"><use href="#mascot" transform="scale(1.9)"/></g>
<g transform="translate({f2(tx - 6)} {f2(ty - 34)})">
  <path d="M6 0H52A6 6 0 0 1 58 6V16A6 6 0 0 1 52 22H16L-10 30 8 22H6A6 6 0 0 1 0 16V6A6 6 0 0 1 6 0Z" fill="#fff" stroke="{INK}" stroke-width=".7" stroke-linejoin="round"/>
  <text class="bubble-t" x="29" y="8.6" text-anchor="middle">let's sense some</text>
  <text class="bubble-t" x="29" y="15.6" text-anchor="middle">pillows~! ♡</text>
</g>''')

    def defs(self, fonts):
        faces = ''.join(
            f"@font-face{{font-family:'{fam}';font-weight:{wt};src:url(data:font/woff2;base64,{b64}) format('woff2');{rng}}}"
            for fam, wt, b64, rng in fonts)
        return f'''<defs>
<style>
{faces}
text{{font-family:'MPR',sans-serif}}
:where(text:not([fill])){{fill:{INK}}}
.wire-o{{fill:none;stroke:{INK};stroke-width:.62;stroke-linecap:round;stroke-linejoin:round}}
.wire-i{{fill:none;stroke-width:.3;stroke-linecap:round;stroke-linejoin:round}}
.bus-o{{fill:none;stroke:{INK};stroke-width:1.35;stroke-linecap:round}}
.bus-i{{fill:none;stroke:#c7a9ff;stroke-width:.85;stroke-linecap:round}}
.sym-s{{fill:none;stroke:{INK};stroke-width:.3;stroke-linecap:round;stroke-linejoin:round}}
.sym-s.thick{{stroke-width:.4}}
.pin{{fill:none;stroke:{INK};stroke-width:.24;stroke-linecap:round}}
.nc-o{{fill:none;stroke:{INK};stroke-width:.7;stroke-linecap:round}}
.nc-i{{fill:none;stroke:#ff8fa8;stroke-width:.35;stroke-linecap:round}}
.flag{{fill:none;stroke:{INK};stroke-width:.25}}
.dnp{{fill:none;stroke:#ff6f91;stroke-width:.8;stroke-linecap:round;opacity:.75}}
.pinname{{font-weight:500}}
.pinnum{{fill:#b0709d;font-weight:500}}
.ref{{font-family:'MPR';font-weight:800;fill:#d6457f}}
.value{{font-family:'MPR';font-weight:800;fill:#2f8f86}}
.ref,.value{{paint-order:stroke;stroke:{PAPER};stroke-width:.32;stroke-linejoin:round}}
.pwr{{font-family:'Pop';fill:{INK};paint-order:stroke;stroke:#fff;stroke-width:.35}}
.symtxt{{font-weight:500}}
.lbl{{font-weight:800}}
.title{{font-family:'Pop';fill:#fff;paint-order:stroke;stroke:{INK};stroke-width:.55;stroke-linejoin:round}}
.caption{{font-family:'Zen';font-weight:700;fill:#7b5b94}}
.note{{font-family:'Zen';font-weight:700;fill:{INK}}}
.remark{{font-family:'Zen';font-weight:700;fill:#7b5b94}}
.ovl{{text-decoration:overline}}
.sfx{{font-family:'Pop';paint-order:stroke;stroke:#fff;stroke-width:.9;stroke-linejoin:round;opacity:.55}}
.sfx-ro{{font-family:'Zen';font-weight:700;fill:{INK_SOFT};opacity:.5}}
.frame{{fill:none;stroke:{INK};stroke-width:1.6}}
.frame2{{fill:none;stroke:#ffb8d0;stroke-width:.6;stroke-dasharray:2.2 1.4}}
.coord{{font-family:'Pop';font-size:3.6px;fill:#d68ab5}}
.t-jp{{font-family:'Pop';font-size:7.5px;fill:#ff7fb2;paint-order:stroke;stroke:#fff;stroke-width:1.2}}
.t-main{{font-family:'Pop';font-size:8.6px;fill:#fff;paint-order:stroke;stroke:{INK};stroke-width:1.1;stroke-linejoin:round}}
.t-sub{{font-family:'Zen';font-weight:700;font-size:5px;fill:#7b5b94}}
.t-small{{font-family:'MPR';font-weight:800;font-size:3.2px;fill:{INK_SOFT}}}
.bubble-t{{font-family:'Pop';font-size:4.6px;fill:{INK}}}
</style>
<pattern id="tone-w" width="1.1" height="1.1" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><circle cx=".55" cy=".55" r=".2" fill="#fff" opacity=".7"/></pattern>
<pattern id="tone-ink" width=".9" height=".9" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><circle cx=".45" cy=".45" r=".3" fill="{INK}"/></pattern>
<pattern id="tone-pink" width="3" height="3" patternUnits="userSpaceOnUse" patternTransform="rotate(30)"><circle cx="1.5" cy="1.5" r=".7" fill="#ffc2da"/></pattern>
<pattern id="tone-bg" width="3.2" height="3.2" patternUnits="userSpaceOnUse" patternTransform="rotate(30)"><circle cx="1.6" cy="1.6" r=".42" fill="#ffd3e4"/></pattern>
<radialGradient id="vig-g" cx=".5" cy=".5" r=".72"><stop offset=".75" stop-color="#000"/><stop offset="1" stop-color="#fff"/></radialGradient>
<mask id="vignette"><rect width="{self.W}" height="{self.H}" fill="url(#vig-g)"/></mask>
<linearGradient id="title-grad" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffd6e8"/><stop offset=".5" stop-color="#e7dcff"/><stop offset="1" stop-color="#cdf3ea"/></linearGradient>
<linearGradient id="banner-grad" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffc1dc"/><stop offset=".5" stop-color="#d9c8ff"/><stop offset="1" stop-color="#bdeee2"/></linearGradient>
<path id="heart" d="M0 .55C-.95-.1-1-.75-.62-.95-.32-1.1-.08-.9 0-.65.08-.9.32-1.1.62-.95 1-.75.95-.1 0 .55Z" fill="#ff7fb2" stroke="{INK}" stroke-width=".16" stroke-linejoin="round"/>
<g id="blossom"><circle r=".75" stroke="{INK}" stroke-width=".18"/><circle r=".28" fill="#fff6a8"/></g>
<path id="sparkle" d="M0-5C.6-1.2 1.2-.6 5 0 1.2.6.6 1.2 0 5-.6 1.2-1.2.6-5 0-1.2-.6-.6-1.2 0-5Z" stroke="{INK}" stroke-width=".35" stroke-linejoin="round"/>
<path id="heart-d" d="M0 4C-6.5-.5-6.8-4.6-4.2-5.8-2.2-6.7-.6-5.3 0-3.8.6-5.3 2.2-6.7 4.2-5.8 6.8-4.6 6.5-.5 0 4Z" transform="translate(0 1)" stroke="{INK}" stroke-width=".4" stroke-linejoin="round"/>
<path id="star" d="M0-5 1.4-1.6 5-1.5 2.2.8 3.1 4.4 0 2.4-3.1 4.4-2.2.8-5-1.5-1.4-1.6Z" stroke="{INK}" stroke-width=".4" stroke-linejoin="round"/>
<g id="blossom-d" stroke="{INK}" stroke-width=".35">
  <g id="petals">{''.join(f'<ellipse cx="0" cy="-2.6" rx="1.9" ry="2.6" transform="rotate({a})"/>' for a in range(0, 360, 72))}</g>
  <circle r="1.3" fill="#fff3a0"/>
</g>
{face_defs()}
{C.resistor_face_defs()}
{mascot_def()}
</defs>'''

    def render(self, fonts, title):
        self.build_nets()
        self.render_symbols()
        self.render_wires()
        self.render_junctions()
        self.render_flags()
        self.render_labels()
        self.render_texts()
        self.render_characters()
        self.render_legend()
        self.frame_and_title(title)
        self.decorate()
        order = ['bg', 'deco', 'edgeback', 'shadow', 'fill', 'face', 'wire_o', 'wire_i', 'stroke', 'char', 'dnp', 'junction',
                 'flag', 'symtext', 'text', 'label', 'title', 'frame', 'edgefront', 'titlepanel']
        body = []
        for layer in order:
            items = self.svg.layers.get(layer, [])
            extra = ' fill="url(#tone-ink)" opacity=".7"' if layer == 'shadow' else ''
            body.append(f'<g id="layer-{layer}"{extra}>' + '\n'.join(items) + '</g>')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.W}mm" height="{self.H}mm" '
                f'viewBox="0 0 {self.W} {self.H}">\n{self.defs(fonts)}\n' + '\n'.join(body) + '\n</svg>\n')


def rounded_poly(pts, r):
    """A closed polygon with its corners rounded off by up to r."""
    if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 1e-6:
        pts = pts[:-1]
    out = []
    for i, (x1, y1) in enumerate(pts):
        (x0, y0), (x2, y2) = pts[i - 1], pts[(i + 1) % len(pts)]
        d1, d2 = math.hypot(x0 - x1, y0 - y1), math.hypot(x2 - x1, y2 - y1)
        rr = min(r, d1 * .3, d2 * .3)
        ax, ay = x1 + (x0 - x1) * rr / d1, y1 + (y0 - y1) * rr / d1
        bx, by = x1 + (x2 - x1) * rr / d2, y1 + (y2 - y1) * rr / d2
        out.append(f'{"M" if not i else "L"}{f2(ax)} {f2(ay)}Q{f2(x1)} {f2(y1)} {f2(bx)} {f2(by)}')
    return ''.join(out) + 'Z'


def arc_path(s, m, e):
    (x1, y1), (x2, y2), (x3, y3) = s, m, e
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-9:
        return f'M{f2(x1)} {f2(y1)}L{f2(x3)} {f2(y3)}'
    ux = ((x1 ** 2 + y1 ** 2) * (y2 - y3) + (x2 ** 2 + y2 ** 2) * (y3 - y1) + (x3 ** 2 + y3 ** 2) * (y1 - y2)) / d
    uy = ((x1 ** 2 + y1 ** 2) * (x3 - x2) + (x2 ** 2 + y2 ** 2) * (x1 - x3) + (x3 ** 2 + y3 ** 2) * (x2 - x1)) / d
    r = math.hypot(x1 - ux, y1 - uy)
    cross = (x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1)
    sweep = 1 if cross > 0 else 0
    a1 = math.atan2(y1 - uy, x1 - ux)
    a3 = math.atan2(y3 - uy, x3 - ux)
    span = (a3 - a1) % (2 * math.pi) if sweep else (a1 - a3) % (2 * math.pi)
    large = 1 if span > math.pi else 0
    return f'M{f2(x1)} {f2(y1)}A{f2(r)} {f2(r)} 0 {large} {sweep} {f2(x3)} {f2(y3)}'


def face_defs():
    eye = '<ellipse cx="{x}" cy="-.6" rx=".75" ry="1.05" fill="#4b3a5a"/><circle cx="{hx}" cy="-1" r=".3" fill="#fff"/>'
    blush = '<ellipse cx="-3" cy=".9" rx="1.1" ry=".6" fill="#ff9cc2" opacity=".75"/><ellipse cx="3" cy=".9" rx="1.1" ry=".6" fill="#ff9cc2" opacity=".75"/>'
    eyes = eye.format(x=-1.9, hx=-1.65) + eye.format(x=1.9, hx=2.15)
    st = 'fill="none" stroke="#4b3a5a" stroke-width=".38" stroke-linecap="round" stroke-linejoin="round"'
    return f'''
<g id="face-happy">{eyes}{blush}<path d="M-.7 .7Q0 1.5.7 .7" {st}/></g>
<g id="face-smile"><path d="M-2.7 -.4Q-1.9 -1.5 -1.1 -.4M1.1 -.4Q1.9 -1.5 2.7 -.4" {st}/>{blush}<path d="M-.9 .6Q0 1.7.9 .6Z" fill="#ff7f9e" stroke="#4b3a5a" stroke-width=".3"/></g>
<g id="face-wink">{eye.format(x=-1.9, hx=-1.65)}<path d="M1.2 -.5Q1.9 -1.3 2.6 -.5" {st}/>{blush}<path d="M-.7 .7Q0 1.4.7 .7" {st}/></g>
<g id="face-cat">{eyes}{blush}<path d="M-1 .6Q-.5 1.2 0 .6Q.5 1.2 1 .6" {st}/></g>
<g id="face-sparkle"><path d="M-1.9 -1.6l.35 .8.8 .35-.8 .35-.35 .8-.35-.8-.8-.35.8-.35zM1.9 -1.6l.35 .8.8 .35-.8 .35-.35 .8-.35-.8-.8-.35.8-.35z" fill="#4b3a5a"/>{blush}<path d="M-.7 .7Q0 1.5.7 .7" {st}/></g>'''


def mascot_def():
    """A small bunny-ish blob holding a probe, drawn around (0, 0)."""
    ink = INK
    return f'''<g id="mascot" stroke="{ink}" stroke-width=".45" stroke-linejoin="round" stroke-linecap="round">
  <ellipse cx="0" cy="9.2" rx="8" ry="1.4" fill="url(#tone-ink)" stroke="none" opacity=".5"/>
  <path d="M-3.4 -5.5C-5.4 -11 -5.6 -15.6 -3.7 -16 -1.8 -16.3 -1.2 -11.5 -1.6 -6Z" fill="#fff"/>
  <path d="M-3.1 -7C-4.3 -10.8 -4.3 -13.8 -3.5 -14.1 -2.7 -14.3 -2.3 -11 -2.4 -7Z" fill="#ffc2da" stroke="none"/>
  <path d="M1.6 -6C1.9 -11.5 3.2 -15.8 5.1 -15.4 7 -15 6.1 -10.6 3.4 -5.4Z" fill="#fff"/>
  <path d="M2.4 -7C2.9 -10.6 3.9 -13.6 4.7 -13.4 5.5 -13.2 4.7 -10.2 3.2 -6.8Z" fill="#ffc2da" stroke="none"/>
  <path d="M-8 3C-8 -4 -4.5 -7.5 0 -7.5 4.5 -7.5 8 -4 8 3 8 7.5 4.5 9 0 9 -4.5 9 -8 7.5 -8 3Z" fill="#fff"/>
  <path d="M-8 3C-8 -4 -4.5 -7.5 0 -7.5 4.5 -7.5 8 -4 8 3 8 7.5 4.5 9 0 9 -4.5 9 -8 7.5 -8 3Z" fill="url(#tone-pink)" stroke="none" opacity=".35"/>
  <g transform="translate(0 0.4) scale(.95)" stroke="none"><use href="#face-happy"/></g>
  <path d="M6.5 2.5L12 -3" stroke-width=".9"/>
  <path d="M12 -3L13.6 -4.6" stroke="#ff7fb2" stroke-width=".9"/>
  <circle cx="7" cy="2.4" r="1.4" fill="#fff"/>
  <circle cx="-7" cy="3" r="1.4" fill="#fff"/>
  <path d="M-3 9.2v-1.2M3 9.2v-1.2" />
  <use href="#sparkle" transform="translate(15.5 -7) scale(.35)" fill="#ffe58f"/>
  <use href="#heart-d" transform="translate(-10 -10) scale(.3)" fill="#ff9cc2"/>
</g>'''


def load_fonts(font_dir):
    import os

    def b64(name):
        with open(os.path.join(font_dir, name), 'rb') as f:
            return base64.b64encode(f.read()).decode()
    latin = 'unicode-range:U+0000-024F,U+2000-206F,U+2190-21FF,U+2600-27BF;'
    return [
        ('MPR', 500, b64('m-plus-rounded-1c-latin-500-normal.woff2'), ''),
        ('MPR', 800, b64('m-plus-rounded-1c-latin-800-normal.woff2'), ''),
        ('Zen', 700, b64('zen-maru-gothic-latin-700-normal.woff2'), ''),
        ('Pop', 400, b64('mochiy-pop-one-latin-400-normal.woff2'), latin),
        ('Pop', 400, b64('mochiy-pop-one-japanese-400-normal.woff2'), 'unicode-range:U+3000-30FF,U+4E00-9FFF,U+FF00-FFEF,U+2700-27BF;'),
    ]


def main():
    src, font_dir, out = sys.argv[1:4]
    with open(src, encoding='utf-8') as f:
        sch = parse_sexp(f.read())
    import os
    title = re.sub(r'^[0-9a-f]{8}-', '', os.path.basename(src)).replace('.kicad_sch', '')
    r = Renderer(sch)
    svg = r.render(load_fonts(font_dir), title)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(svg)
    print(f'wrote {out} ({len(svg) / 1e6:.1f} MB)')


if __name__ == '__main__':
    main()
