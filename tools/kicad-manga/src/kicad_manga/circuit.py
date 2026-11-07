"""Draw the schematic itself: wires, symbols, labels, sheets, text and graphics.

Everything is drawn in sheet coordinates (mm) into named layers. Each schematic item becomes its own <g>
carrying a `data-kind` attribute (and symbols an id named after their reference), so the SVG stays easy to pick
apart in Inkscape. The schematic comes in as gerbonara objects (see kicad.py)."""

import base64
import math
import random
import re

from . import characters as C
from .kicad import DASHES, at, fill, font, hex_color, hidden, justify, lib_symbols, paper_size, quarter_turned, \
    rotation, stroke, xy
from .palette import LINE, LibColors, NetColors
from .svg import Markup, group, num as f2, path, tag
from .text import CHAR_W, FS, plain, text_el, text_extent

LAYERS = [('graphics', 'Graphics'), ('wires', 'Wires & buses'), ('symbols', 'Symbols'), ('sheets', 'Sheets'),
          ('junctions', 'Junctions & no-connects'), ('labels', 'Labels'), ('text', 'Text')]

NET_LABELS = ('local_labels', 'global_labels', 'hierarchical_labels')
LABEL_KIND = {'local_labels': 'label', 'global_labels': 'global_label', 'hierarchical_labels': 'hierarchical_label'}


def dash(kind):
    return DASHES.get(kind)


# ----------------------------------------------------------------------------
# Occupancy grid, used to keep characters' props and decorations out of the circuit

class Grid:
    def __init__(self, w, h, cell=1.0):
        self.w, self.h = w, h
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
        if i0 > i1 or j0 > j1:
            return
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

    def count(self, x0, y0, x1, y1):
        """How many occupied cells (or cells off the grid) a rectangle covers."""
        c = self.cell
        n = 0
        for j in range(int(min(y0, y1) / c), int(max(y0, y1) / c) + 1):
            for i in range(int(min(x0, x1) / c), int(max(x0, x1) / c) + 1):
                n += 1 if not (0 <= i < self.nx and 0 <= j < self.ny) else self.occ[j * self.nx + i]
        return n

    def bbox(self):
        """Bounding box of everything marked, or None."""
        rows = [j for j in range(self.ny) if any(self.occ[j * self.nx:(j + 1) * self.nx])]
        if not rows:
            return None
        cols = [i for i in range(self.nx) if any(self.occ[j * self.nx + i] for j in rows)]
        c = self.cell
        return cols[0] * c, rows[0] * c, (cols[-1] + 1) * c, (rows[-1] + 1) * c

    def runs(self):
        """Occupied cells as (x0, y0, x1, y1) row runs."""
        c = self.cell
        for j in range(self.ny):
            row = self.occ[j * self.nx:(j + 1) * self.nx]
            i = 0
            while i < self.nx:
                if row[i]:
                    k = i
                    while k < self.nx and row[k]:
                        k += 1
                    yield i * c, j * c, k * c, (j + 1) * c
                    i = k
                else:
                    i += 1


# ----------------------------------------------------------------------------
# Nets (only used to colour wires and labels)

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
# Path data

def rounded_poly(points, r):
    """A closed polygon with its corners rounded off by up to r."""
    if math.hypot(points[0][0] - points[-1][0], points[0][1] - points[-1][1]) < 1e-6:
        points = points[:-1]
    out = []
    for i, (x1, y1) in enumerate(points):
        (x0, y0), (x2, y2) = points[i - 1], points[(i + 1) % len(points)]
        d1, d2 = math.hypot(x0 - x1, y0 - y1) or 1, math.hypot(x2 - x1, y2 - y1) or 1
        rr = min(r, d1 * .3, d2 * .3)
        ax, ay = x1 + (x0 - x1) * rr / d1, y1 + (y0 - y1) * rr / d1
        bx, by = x1 + (x2 - x1) * rr / d2, y1 + (y2 - y1) * rr / d2
        out.append(f'{"M" if not i else "L"}{f2(ax)} {f2(ay)}Q{f2(x1)} {f2(y1)} {f2(bx)} {f2(by)}')
    return ''.join(out) + 'Z'


def rounded_rect(x0, y0, x1, y1, r):
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
    return (f'M{f2(x0 + r)} {f2(y0)}H{f2(x1 - r)}Q{f2(x1)} {f2(y0)} {f2(x1)} {f2(y0 + r)}'
            f'V{f2(y1 - r)}Q{f2(x1)} {f2(y1)} {f2(x1 - r)} {f2(y1)}H{f2(x0 + r)}'
            f'Q{f2(x0)} {f2(y1)} {f2(x0)} {f2(y1 - r)}V{f2(y0 + r)}Q{f2(x0)} {f2(y0)} {f2(x0 + r)} {f2(y0)}Z')


def circle_d(cx, cy, r):
    return f'M{f2(cx - r)} {f2(cy)}a{f2(r)} {f2(r)} 0 1 0 {f2(2 * r)} 0a{f2(r)} {f2(r)} 0 1 0 {f2(-2 * r)} 0Z'


def poly_d(points):
    return 'M' + 'L'.join(f'{f2(x)} {f2(y)}' for x, y in points)


def bezier_d(p):
    return f'M{f2(p[0][0])} {f2(p[0][1])}C' + ' '.join(f'{f2(a)} {f2(b)}' for a, b in p[1:4])


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
    a1, a3 = math.atan2(y1 - uy, x1 - ux), math.atan2(y3 - uy, x3 - ux)
    span = (a3 - a1) % (2 * math.pi) if sweep else (a1 - a3) % (2 * math.pi)
    return f'M{f2(x1)} {f2(y1)}A{f2(r)} {f2(r)} 0 {1 if span > math.pi else 0} {sweep} {f2(x3)} {f2(y3)}'


def wrap_text(s, width, size, cls=''):
    """Word wrap to a width in mm, as KiCad does in text boxes."""
    out = []
    for para in s.split('\n'):
        line = ''
        for word in para.split(' '):
            cand = f'{line} {word}' if line else word
            if line and text_extent(cand, size, cls)[0] > width:
                out.append(line)
                line = word
            else:
                line = cand
        out.append(line)
    return '\n'.join(out)


def text_style(bold, italic, col):
    style = []
    if bold:
        style.append('font-weight:800')
    if italic:
        style.append('font-style:italic')
    if col:
        style.append(f'fill:{col}')
    return ';'.join(style)


# ----------------------------------------------------------------------------
# Which symbols become characters (matched on the reference designator prefix, so it works for the KiCad
# standard library and most third-party libraries alike)

def ref_prefix(ref):
    m = re.match(r'#?([A-Za-z]+)', ref or '')
    return m.group(1).upper() if m else ''


def character_kind(ref, lib_id, npins):
    p = ref_prefix(ref)
    name = lib_id.split(':')[-1].lower()
    if p == 'C' and npins == 2:
        return 'cap'
    if p in ('R', 'TH', 'RT') and npins == 2:
        return 'res'
    if p in ('L', 'FB', 'FL') and npins == 2:
        return 'ind'
    if p in ('Y', 'X', 'XTAL') and ('crystal' in name or 'resonator' in name or npins <= 4):
        return 'xtal'
    return None


def unit_graphics(unit):
    """A symbol unit's drawing items, as (kind, item)."""
    for kind in ('rectangles', 'circles', 'arcs', 'polylines', 'beziers', 'texts'):
        for g in getattr(unit, kind, []):
            yield kind[:-1], g


def shape_points(kind, g):
    if kind in ('polyline', 'bezier'):
        return [xy(p) for p in (g.pts if kind == 'polyline' else g.points)]
    if kind == 'rectangle':
        return [xy(g.start), xy(g.end)]
    if kind == 'circle':
        return [xy(g.center)]
    if kind == 'arc':
        return [xy(g.start), xy(g.mid), xy(g.end)]
    return [at(g)]


def prop_value(sym, key):
    return next((p.value for p in sym.properties if p.key == key), None)


# ----------------------------------------------------------------------------

class Circuit:
    def __init__(self, sch, characters=True, seed=7):
        self.sch = sch
        self.W, self.H = paper_size(sch)
        self.characters = characters
        self.layers = {k: [] for k, _ in LAYERS}
        self.grid = Grid(self.W, self.H, 1.0)     # for decorations (generous padding)
        self.fine = Grid(self.W, self.H, 0.5)     # tight, for the characters' props
        self.libs = lib_symbols(sch)
        self.rng = random.Random(seed)
        self.passives = []
        self.symbols = []                         # symbol dicts, assembled into groups at the end
        self.ids = set()
        self.lib_colors = LibColors([s.lib_id for s in sch.symbols
                                     if s.lib_id in self.libs and not self.libs[s.lib_id].is_power])

    def uid(self, base):
        base = re.sub(r'[^A-Za-z0-9_.-]', '_', base) or 'x'
        uid, i = base, 1
        while uid in self.ids:
            i += 1
            uid = f'{base}-{i}'
        self.ids.add(uid)
        return uid

    def lib(self, sym):
        return self.libs.get(sym.lib_name or sym.lib_id) or self.libs.get(sym.lib_id)

    def add(self, layer, svg):
        self.layers[layer].append(svg)

    def mark(self, x0, y0, x1, y1, pad=1.0, fine_pad=0.4):
        self.grid.mark_rect(x0, y0, x1, y1, pad=pad)
        self.fine.mark_rect(x0, y0, x1, y1, pad=fine_pad)

    def mark_text(self, x, y, s, size, ang, h, v, pad=0.6, cls=''):
        w, hh = text_extent(s, size, cls)
        hx = {'left': (0, w), 'right': (-w, 0), 'center': (-w / 2, w / 2)}[h]
        vy = {'top': (0, hh), 'bottom': (-hh, 0), 'center': (-hh / 2, hh / 2)}[v]
        if round(ang) % 180 == 90:
            self.mark(x + vy[0], y - hx[1], x + vy[1], y - hx[0], pad=pad)
        else:
            self.mark(x + hx[0], y + vy[0], x + hx[1], y + vy[1], pad=pad)

    # -- everything ---------------------------------------------------------
    def render(self):
        self.build_nets()
        for sym in self.sch.symbols:
            self.render_symbol(sym)
        self.render_graphics()
        self.render_wires()
        self.render_junctions()
        self.render_sheets()
        self.render_labels()
        self.render_texts()
        if self.characters:
            self.render_characters()
        for s in self.symbols:
            s['parts'] += s['texts'] + ([s['dnp']] if 'dnp' in s else [])
            self.add('symbols', group(s['parts'], id=s['id'], cls='symbol', data_kind='symbol', data_ref=s['ref'],
                                      data_lib=s['lib_id']))
        return self

    def svg(self):
        """The schematic layers, as Inkscape sub-layers."""
        return Markup('\n'.join(group(self.layers[k], id=f'layer-{k}', inkscape__groupmode='layer',
                                      inkscape__label=label) for k, label in LAYERS))

    # -- nets ---------------------------------------------------------------
    def labels(self):
        """All net labels as (kind, label)."""
        for attr in NET_LABELS:
            for lab in getattr(self.sch, attr):
                yield LABEL_KIND[attr], lab

    def build_nets(self):
        wires = [(xy(w.points[0]), xy(w.points[-1])) for w in self.sch.wires if len(w.points) >= 2]
        self.wire_items = [w for w in self.sch.wires if len(w.points) >= 2]
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
        self.wire_at = lambda p: next((i for i, (a, b) in enumerate(wires) if on_segment(p, a, b)), None)
        for _, lab in self.labels():
            i = self.wire_at(at(lab))
            if i is not None:
                names.setdefault(uf.find(i), lab.text)
        for sym in self.sch.symbols:
            lib = self.lib(sym)
            if lib is not None and lib.is_power:
                v = prop_value(sym, 'Value')
                i = self.wire_at(at(sym))
                if v and i is not None:
                    names.setdefault(uf.find(i), v)
        self.net_of = [uf.find(i) for i in range(len(wires))]
        self.net_name = names
        self.colors = NetColors([(lab.text, *at(lab)) for _, lab in self.labels()])

    def net_color(self, root):
        name = self.net_name.get(root)
        return self.colors(name) if name else NetColors.unnamed(root)

    def color_at(self, p, name=None):
        i = self.wire_at(p)
        if i is not None:
            return self.net_color(self.net_of[i])
        return self.colors(name) if name else '#fff3b8'

    # -- wires, buses, junctions ---------------------------------------------
    def render_wires(self):
        by_net = {}
        for w, (a, b), root in zip(self.wire_items, self.wires, self.net_of):
            by_net.setdefault(root, []).append((w, a, b))
            self.mark(a[0], a[1], b[0], b[1], pad=0.8, fine_pad=0.45)
        for root, items in by_net.items():
            col = self.net_color(root)
            outer, inner = [], []
            for w, a, b in items:
                d = f'M{f2(a[0])} {f2(a[1])}L{f2(b[0])} {f2(b[1])}'
                _, kind, scol = stroke(w)
                outer.append(path(d, cls='wire-o', data_kind='wire'))
                inner.append(path(d, cls='wire-i', stroke=scol or col, stroke_dasharray=dash(kind)))
            self.add('wires', group(outer + inner, cls='net', data_net=self.net_name.get(root, '')))
        buses = [[xy(p) for p in b.points] for b in self.sch.buses]
        segs = [(a, b) for p in buses for a, b in zip(p, p[1:]) if key(a) != key(b)]
        entries = []           # (point on the bus, point on the wire, colour)
        for be in self.sch.bus_entries:
            (x, y), (sx, sy) = at(be), xy(be.size)
            p, q = (x, y), (x + sx, y + sy)
            if not any(on_segment(p, a, b) for a, b in segs) and any(on_segment(q, a, b) for a, b in segs):
                p, q = q, p
            entries.append((p, q, self.color_at(q)))
            self.mark(x, y, x + sx, y + sy, pad=1)
        drawn = self.cat_buses(segs, entries) if self.characters else set()
        if not self.characters:
            for p in buses:
                d = poly_d(p)
                self.add('wires', group([path(d, cls='bus-o'), path(d, cls='bus-i')], data_kind='bus'))
        for i, (p, q, col) in enumerate(entries):   # entries not taken care of by a cat: plain wires
            if i not in drawn:
                d = f'M{f2(p[0])} {f2(p[1])}L{f2(q[0])} {f2(q[1])}'
                self.add('wires', group([path(d, cls='wire-o'), path(d, cls='wire-i', stroke=col)],
                                        data_kind='bus_entry'))
        for p in buses:
            for a, c in zip(p, p[1:]):
                self.mark(a[0], a[1], c[0], c[1], pad=2.5 if self.characters else 1.2,
                          fine_pad=2.6 if self.characters else .4)

    def cat_buses(self, segs, all_entries):
        """Each connected bus becomes one long cat: head at one end, tail at the other, legs on the side away
        from the bus entries, which come in through its windows. Returns the indices of the entries it drew."""
        entries = [(p, (q[0] - p[0], q[1] - p[1])) for p, q, _ in all_entries]
        drawn = set()
        uf = UF(len(segs))
        first = {}
        for i, (a, b) in enumerate(segs):
            for q in (a, b):
                first.setdefault(key(q), i)
                uf.union(first[key(q)], i)
        chains = {}
        for i in range(len(segs)):
            chains.setdefault(uf.find(i), []).append(segs[i])
        for chain in chains.values():
            degree, owner = {}, {}
            for a, b in chain:
                for q, other in ((a, b), (b, a)):
                    degree[key(q)] = degree.get(key(q), 0) + 1
                    owner[key(q)] = (q, other)
            ends = [owner[k] for k, n in degree.items() if n == 1] or [chain[0], chain[-1][::-1]]
            e1, e2 = max(((u, v) for i, u in enumerate(ends) for v in ends[i + 1:]),
                         key=lambda uv: math.hypot(uv[0][0][0] - uv[1][0][0], uv[0][0][1] - uv[1][0][1]),
                         default=(ends[0], ends[-1]))

            def outward(e):
                (x, y), (ox, oy) = e
                n = math.hypot(x - ox, y - oy) or 1
                return (x, y, (x - ox) / n, (y - oy) / n)

            def crowd(e):   # how cluttered the spot for the head is
                x, y, ux, uy = outward(e)
                hx, hy = x + ux * 3.1, y + uy * 3.1
                near = sum(1 for (p, _) in entries if math.hypot(p[0] - x, p[1] - y) < 5)
                return self.fine.count(hx - 3, hy - 3.5, hx + 3, hy + 2.5) + 10 * near
            head, tail = (e1, e2) if crowd(e1) <= crowd(e2) else (e2, e1)
            # walk the bus from head to tail, so "left" and "right" mean the same along the whole cat, then
            # put all its legs on whichever side is less cluttered
            route, left, here = [], list(chain), head[0]
            while left:
                nxt = next(((a, b) for a, b in left if key(a) == key(here)), None) or \
                    next(((b, a) for a, b in left if key(b) == key(here)), None) or left[0]
                left.remove(nxt if nxt in left else nxt[::-1])
                route.append(nxt)
                here = nxt[1]

            def clutter(a, b, sx, sy):    # bus entries on that side, and whatever else is in the way
                there = [v for p, v in entries if on_segment(p, a, b)]
                hits = sum(1 for v in there if v[0] * sx + v[1] * sy > 0)
                return 20 * hits + self.fine.count(a[0] + sx * 1.6, a[1] + sy * 1.6, b[0] + sx * 3.4, b[1] + sy * 3.4)

            def side_normals(sign):
                out = []
                for a, b in route:
                    L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1
                    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
                    out.append((a, b, L, ux, uy, -uy * sign, ux * sign))
                return out
            options = [side_normals(1), side_normals(-1)]
            best = min(options, key=lambda segs_: sum(clutter(a, b, nx, ny) for a, b, _, _, _, nx, ny in segs_))
            mine = [i for i, (p, q, _) in enumerate(all_entries) if any(on_segment(p, a, b) for a, b in chain)]
            drawn.update(mine)
            # bus entries on the legs' side become legs themselves; the others come in through windows.
            # Elsewhere legs run the whole length at an even spacing.
            cat_entries = []
            for i in mine:
                p, q, col = all_entries[i]
                seg = next((sg for sg in best if on_segment(p, sg[0], sg[1])), None)
                is_leg = seg is not None and (q[0] - p[0]) * seg[5] + (q[1] - p[1]) * seg[6] > 0
                cat_entries.append((p, q, col, is_leg))
            legs = []
            for a, b, L, ux, uy, nx, ny in best:
                along = sorted(((p[0] - a[0]) * ux + (p[1] - a[1]) * uy, q[0] - p[0], q[1] - p[1])
                               for p, q, _, leg in cat_entries if leg and on_segment(p, a, b))
                if along:   # match the entries: same direction, same spacing, all along this run
                    gaps = [t2 - t1 for (t1, _, _), (t2, _, _) in zip(along, along[1:]) if t2 - t1 > .5]
                    step = max(2.5, min(gaps)) if gaps else 3.8
                    vx, vy = along[0][1], along[0][2]
                    n = math.hypot(vx, vy) or 1
                    # reach as far out from the body as the entry legs do (paw ~2.1 mm out)
                    c = abs(vx / n * nx + vy / n * ny) or 1
                    dx, dy = vx / n / c * .775, vy / n / c * .775
                    t0 = along[0][0]
                    ts = [t0 + k * step for k in range(-int(t0 / step), int((L - t0) / step) + 1)]
                    ts = [t for t in ts if 2 <= t <= L - 1.5 and all(abs(t - e[0]) > .5 for e in along)]
                else:       # nothing to line up with: evenly spaced, straight out
                    dx, dy = nx, ny
                    ts = [2.4 + k * 3.8 for k in range(int(max(0, L - 4.4) / 3.8) + 1)]
                for t in ts:
                    px, py = a[0] + ux * t, a[1] + uy * t
                    if min(math.hypot(px - e[0][0], py - e[0][1]) for e in (head, tail)) > 4.5:
                        legs.append((px, py, dx, dy))
            self.add('wires', group([C.cat_bus(chain, outward(head), outward(tail), legs, cat_entries)],
                                    data_kind='cat_bus'))
        return drawn

    def render_junctions(self):
        for j in self.sch.junctions:
            x, y = at(j)
            r = j.diameter / 2 if j.diameter else .72
            fill_col = hex_color(j.color) or self.color_at((x, y))
            self.add('junctions', tag('circle', data_kind='junction', cx=x, cy=y, r=r, fill=fill_col, stroke=LINE,
                                      stroke_width=.22))
        for n in self.sch.no_connects:
            x, y = at(n)
            d = f'M{f2(x - .7)} {f2(y - .7)}l1.4 1.4M{f2(x + .7)} {f2(y - .7)}l-1.4 1.4'
            self.add('junctions', group([path(d, cls='nc-o'), path(d, cls='nc-i')], data_kind='no_connect'))
            self.mark(x - 1, y - 1, x + 1, y + 1)

    # -- free graphics, images, text boxes, tables ---------------------------
    def shape_attrs(self, item):
        w, kind, scol = stroke(item)
        ftype, fcol = fill(item)
        fcol = {'none': 'none', 'outline': scol or LINE, 'background': '#fff1e0'}.get(ftype) or fcol or 'none'
        return dict(fill=fcol, stroke=scol or LINE, stroke_width=max(w, .25), stroke_dasharray=dash(kind),
                    stroke_linejoin='round', stroke_linecap='round')

    def render_graphics(self):
        sch = self.sch
        for kind, items in (('polyline', sch.polylines), ('rectangle', sch.rectangles), ('circle', sch.circles),
                            ('arc', sch.arcs), ('bezier', sch.beziers)):
            for g in items:
                d, bb = self.graphic_path(g, kind)
                if d:
                    self.add('graphics', path(d, data_kind=kind, **self.shape_attrs(g)))
                    self.mark(*bb, pad=0.5)
        for ra in sch.rule_areas:
            if ra.polyline is not None and ra.polyline.points:
                d, _ = self.graphic_path(ra.polyline, 'polyline')
                self.add('graphics', path(d + 'Z', data_kind='rule_area', fill='#ffd6e7', fill_opacity=.25,
                                          stroke='#e58fb4', stroke_width=.35, stroke_dasharray='1.4 .8'))
        for img in sch.images:
            self.render_image(img)
        for tb in sch.text_boxes:
            self.add('text', self.text_box(tb, 'text_box'))
        for tab in sch.tables:
            ncol = tab.column_count or 1
            header = bool(tab.border.header) if tab.border is not None else False
            parts = [self.text_box(c, 'table_cell', header=i < ncol and header) for i, c in enumerate(tab.cells)]
            self.add('text', group(parts, data_kind='table'))

    def graphic_path(self, g, kind):
        if kind == 'polyline':
            p = [xy(q) for q in g.points]
            d = poly_d(p) if p else None
        elif kind == 'rectangle':
            (x0, y0), (x1, y1) = xy(g.start), xy(g.end)
            p = [(x0, y0), (x1, y1)]
            d = rounded_rect(x0, y0, x1, y1, .6)
        elif kind == 'circle':
            (cx, cy), r = xy(g.center), float(g.radius or 1)
            p = [(cx - r, cy - r), (cx + r, cy + r)]
            d = circle_d(cx, cy, r)
        elif kind == 'arc':
            p = [xy(g.start), xy(g.mid), xy(g.end)]
            d = arc_path(*p)
        else:
            p = [xy(q) for q in g.points]
            if len(p) < 4:
                return None, None
            d = bezier_d(p)
        if not p:
            return None, None
        xs, ys = [q[0] for q in p], [q[1] for q in p]
        return d, (min(xs), min(ys), max(xs), max(ys))

    def render_image(self, img):
        x, y = at(img)
        if img.size is None:
            return
        w, h = img.size
        self.add('graphics', tag('image', data_kind='image', x=x - w / 2, y=y - h / 2, width=w, height=h,
                                 href=f'data:image/png;base64,{base64.b64encode(img.data).decode()}'))
        self.mark(x - w / 2, y - h / 2, x + w / 2, y + h / 2)

    def text_box(self, tb, kind, header=False):
        (x, y), (w, h) = at(tb), xy(tb.size)
        if w < 0:
            x, w = x + w, -w
        if h < 0:
            y, h = y + h, -h
        m = tb.margins
        mg = [float(m.left), float(m.top), float(m.right), float(m.bottom)] if m is not None else [1, 1, 1, 1]
        size, bold, italic, col = font(tb)
        hj, vj = justify(tb)
        if kind == 'text_box' and tb.effects.justify.h is None and tb.effects.justify.v is None:
            hj, vj = 'left', 'top'
        sw, kind_, scol = stroke(tb)
        _, fcol = fill(tb)
        fcol = fcol or ('#e9e0ff' if header else '#fffbe8' if kind == 'text_box' else '#fffdf6')
        border = {} if sw < 0 else dict(stroke=scol or LINE, stroke_width=max(sw, .25), stroke_dasharray=dash(kind_))
        tx = {'left': x + mg[0], 'right': x + w - mg[2], 'center': x + w / 2}[hj]
        ty = {'top': y + mg[1], 'bottom': y + h - mg[3], 'center': y + h / 2}[vj]
        s = wrap_text(tb.text or '', w - mg[0] - mg[2], size, 'boxtext')
        t = text_el(tx, ty, s, size, 0, hj, vj, 'boxtext', style=text_style(bold or header, italic, col))
        self.mark(x, y, x + w, y + h, pad=1)
        box = path(rounded_rect(x, y, x + w, y + h, .8 if kind == 'text_box' else .2), fill=fcol, **border)
        return group([box, t], data_kind=kind)

    # -- hierarchical sheets (the box only; each sheet file is rendered on its own) --
    def render_sheets(self):
        for sh in self.sch.subsheets:
            (x, y), (w, h) = xy(sh.at), xy(sh.size)
            fcol = hex_color(sh.fill.color) if sh.fill is not None else None
            parts = [path(rounded_rect(x + .9, y + .9, x + w + .9, y + h + .9, 1.2), fill='url(#tone-ink)', opacity=.5),
                     path(rounded_rect(x, y, x + w, y + h, 1.2), fill=fcol or '#eef0ff', stroke=LINE, stroke_width=.4),
                     path(rounded_rect(x, y, x + w, y + h, 1.2), fill='url(#tone-w)')]
            for prop in sh._properties:
                if hidden(prop):
                    continue
                px, py = at(prop)
                hj, vj = justify(prop)
                cls = 'sheetname' if prop.key in ('Sheetname', 'Sheet name') else 'sheetfile' if prop.key in (
                    'Sheetfile', 'Sheet file') else 'field'
                txt = prop.value if cls != 'field' else f'{prop.key}: {prop.value}'
                size = font(prop)[0]
                parts.append(text_el(px, py, txt, size, rotation(prop), hj, vj, cls))
                self.mark_text(px, py, txt, size, rotation(prop), hj, vj, cls=cls)
            for pin in sh.pins:
                px, py = at(pin)
                a = round(rotation(pin)) % 360
                size = font(pin)[0]
                ux, uy = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}.get(a, (1, 0))  # into the box
                parts.append(hier_glyph(px, py, -ux, -uy, str(pin.shape), size, '#ffffff'))
                tx, ty = px + ux * size * 1.2, py + uy * size * 1.2
                vert = uy != 0
                hj = ('left' if uy < 0 else 'right') if vert else ('left' if ux > 0 else 'right')
                parts.append(text_el(tx, ty, pin.name, size, 90 if vert else 0, hj, 'center', 'pinname'))
            self.add('sheets', group(parts, data_kind='sheet'))
            self.mark(x, y, x + w, y + h, pad=2)

    # -- labels ---------------------------------------------------------------
    def render_labels(self):
        for kind, lab in self.labels():
            self.net_label(lab, kind)
        for flag in self.sch.netclass_flags:
            self.directive_label(flag)

    def net_label(self, lab, kind):
        x, y = at(lab)
        ang = round(rotation(lab)) % 360
        h, _ = justify(lab)
        size, bold, italic, tcol = font(lab)
        name = lab.text
        col = self.color_at((x, y), name)
        vertical = ang in (90, 270)
        sign = 1 if h != 'right' else -1
        if h == 'center':
            sign = 1 if ang in (0, 90) else -1
            h = 'left' if sign > 0 else 'right'
        style = text_style(bold, italic, tcol)
        ext_w, ext_h = text_extent(name, size, 'lbl')
        if kind == 'label':
            off = .75   # text sits just above the wire
            tx, ty = (x - off, y) if vertical else (x, y - off)
            parts = [text_el(tx, ty, name, size, 90 if vertical else 0, h, 'bottom', 'lbl', bg=('pill', col),
                             style=style)]
            dx, dy = (0, -sign * ext_w) if vertical else (sign * ext_w, 0)
            self.mark(x, y, x + dx - (ext_h + off if vertical else 0), y + dy - (0 if vertical else ext_h + off), pad=0.6)
        else:
            shape = str(lab.shape or 'passive')
            off = size * (1.15 if kind == 'global_label' else 1.9)
            dirx, diry = (0, -sign) if vertical else (sign, 0)
            tx, ty = x + dirx * off, y + diry * off
            parts = [text_el(tx, ty, name, size, 90 if vertical else 0, h, 'center', 'lbl',
                             bg=(kind, col, shape, sign, off, size), style=style)]
            L = off + ext_w + 1.5
            if vertical:
                self.mark(x - ext_h, y, x + ext_h, y - sign * L, pad=0.6)
            else:
                self.mark(x, y - ext_h, x + sign * L, y + ext_h, pad=0.6)
            for prop in lab.properties:     # e.g. visible intersheet references
                if not hidden(prop) and prop.value:
                    px, py = at(prop)
                    hj, vj = justify(prop)
                    parts.append(text_el(px, py, prop.value.replace('${INTERSHEET_REFS}', '[…]'), font(prop)[0],
                                         rotation(prop), hj, vj, 'remark'))
        self.add('labels', group(parts, data_kind=kind, data_net=name))

    def directive_label(self, lab):
        x, y = at(lab)
        length = float(lab.length or 2.54)
        shape = str(lab.shape or 'round')
        props = lab.properties
        prop = props[0] if props else None
        px, py = at(prop) if prop else (x, y - length)
        dx, dy = px - x, py - y
        if abs(dx) > abs(dy):
            ux, uy = (1 if dx > 0 else -1), 0
        else:
            ux, uy = 0, (1 if dy > 0 else -1)
        ex, ey = x + ux * length, y + uy * length
        col = self.colors(prop.value) if prop and prop.value else '#ff9ec7'
        if shape == 'dot':
            head = tag('use', href='#blossom', x=ex, y=ey, fill=col)
        elif shape == 'diamond':
            head = path(f'M{f2(ex)} {f2(ey - .9)}l.9 .9-.9 .9-.9-.9z', fill=col, stroke=LINE, stroke_width=.2)
        elif shape == 'rectangle':
            head = tag('rect', x=ex - .8, y=ey - .8, width=1.6, height=1.6, rx=.3, fill=col, stroke=LINE, stroke_width=.2)
        else:
            head = tag('circle', cx=ex, cy=ey, r=.8, fill=col, stroke=LINE, stroke_width=.2)
        parts = [path(f'M{f2(x)} {f2(y)}L{f2(ex)} {f2(ey)}', cls='flag'), head]
        for p in props:
            if not hidden(p) and p.value:
                qx, qy = at(p)
                hj, vj = justify(p)
                size = font(p)[0]
                parts.append(text_el(qx, qy, p.value, size, rotation(p), hj, vj, 'remark'))
                self.mark_text(qx, qy, p.value, size, rotation(p), hj, vj, cls='remark')
        self.add('labels', group(parts, data_kind='netclass_flag'))
        self.mark(x, y, ex, ey, pad=1.0, fine_pad=1.0)

    # -- free text --------------------------------------------------------------
    def render_texts(self):
        for t in self.sch.texts:
            s = t.text
            x, y = at(t)
            ang = rotation(t)
            size, bold, italic, col = font(t)
            h, v = justify(t)
            bg = None
            if size >= 2.4:
                cls, bg = 'title', ('banner',)
            elif size >= 1.8:
                cls = 'caption'
            elif len(plain(s)) >= 14:
                cls, bg = 'note', ('bubble',)
            else:
                cls = 'remark'
            style = text_style(bold and cls != 'title', italic, col if cls != 'title' else None)
            self.add('text', group([text_el(x, y, s, size, ang, h, v, cls, bg=bg, style=style)], data_kind='text'))
            self.mark_text(x, y, s, size * (1.25 if cls == 'title' else 1), ang, h, v, pad=2.5, cls=cls)

    # -- symbols ------------------------------------------------------------
    def render_symbol(self, sym):
        lib_id = sym.lib_id
        lib = self.lib(sym)
        if lib is None:
            return
        unit = int(sym.unit or 1)
        style = int(sym.body_style or sym.convert or 1)
        dnp = bool(sym.dnp)
        xf = sym.transform_point
        power = lib.is_power
        props = {p.key: p for p in sym.properties}
        ref = props['Reference'].value if 'Reference' in props else '?'
        value = props['Value'].value if 'Value' in props else ''
        fill_col = self.lib_colors(lib_id)
        rail_col = (self.colors(value) or '#ffd0e0') if power else None

        pn = lib.pin_names
        name_off = float(pn.offset) if pn is not None and pn.offset is not None else 0.508
        names_hidden = pn is not None and bool(pn.hide)
        nums_hidden = lib.pin_numbers is not None and bool(lib.pin_numbers.hide)

        units = {u.unit_index for u in lib.units}
        subs = [u for u in lib.units if u.unit_index in (0, unit) and u.demorgan_style in (0, style)]
        all_pins = [p for u in subs for p in u.pins]
        char = character_kind(ref, lib_id, len(all_pins)) if self.characters and not power else None

        shadow, fills, strokes, pins_d, deco, texts = [], [], [], [], [], []
        xs, ys, rects = [], [], []

        def P(px, py):
            X, Y = xf(px, py)
            xs.append(X)
            ys.append(Y)
            return X, Y

        for sub in subs:
            for kind, g in unit_graphics(sub):
                ftype, fcolor = fill(g)
                sw, dkind, scol = stroke(g)
                d, closed = None, False
                if char in ('cap', 'res', 'ind') and kind != 'text':
                    # drawn as a character instead (inductor core lines are added back on top)
                    for q in (shape_points(kind, g) if kind == 'polyline' else []):
                        P(*q)
                    continue
                if kind == 'polyline':
                    p = [P(*q) for q in shape_points(kind, g)]
                    if not p:
                        continue
                    d = poly_d(p)
                    closed = len(p) > 2 and (ftype != 'none' or power)
                    if closed and ftype in ('background', 'color'):
                        d = rounded_poly(p, 1.0)
                elif kind == 'rectangle':
                    (sx, sy), (ex, ey) = xy(g.start), xy(g.end)
                    a, b = P(sx, sy), P(ex, ey)
                    rr = min(0.9, 0.12 * min(abs(a[0] - b[0]), abs(a[1] - b[1])))
                    d = rounded_rect(a[0], a[1], b[0], b[1], rr)
                    closed = True
                    rects.append((sx, sy, ex, ey, ftype))
                    if ftype == 'none':
                        ftype = 'pale'
                elif kind == 'circle':
                    cx, cy = P(*xy(g.center))
                    r = float(g.radius or 1)
                    xs.extend((cx - r, cx + r))
                    ys.extend((cy - r, cy + r))
                    d = circle_d(cx, cy, r)
                    closed = True
                    if ftype == 'none' and r > 1:
                        ftype = 'pale'
                elif kind == 'arc':
                    d = arc_path(P(*xy(g.start)), P(*xy(g.mid)), P(*xy(g.end)))
                elif kind == 'bezier':
                    p = [P(*q) for q in shape_points(kind, g)]
                    if len(p) >= 4:
                        d = bezier_d(p)
                elif kind == 'text':
                    if hidden(g):
                        continue
                    tx, ty = P(*at(g))
                    size, bold, italic, tcol = font(g)
                    h, v = justify(g)
                    ang = rotation(g)
                    ang = ang / 10 if ang > 360 else ang
                    swap = quarter_turned(sym)
                    texts.append(text_el(tx, ty, g.text, size, 90 if (round(ang) % 180 == 90) != swap else 0, h, v,
                                         'symtxt', style=text_style(bold, italic, tcol)))
                    continue
                if d is None:
                    continue
                da = dash(dkind)
                if power and closed:
                    fills.append(path(d, fill=rail_col))
                    strokes.append(path(d, cls='sym-s', stroke=scol, stroke_dasharray=da))
                    continue
                if ftype in ('background', 'color'):
                    body = fcolor if ftype == 'color' and fcolor else fill_col
                    shadow.append(path(d))
                    fills.append(path(d, fill=body))
                    fills.append(path(d, fill='url(#tone-w)'))
                elif ftype == 'pale' and closed:
                    fills.append(path(d, fill=fill_col, fill_opacity=.85))
                elif ftype == 'outline' and closed:
                    fills.append(path(d, fill=scol or LINE))
                strokes.append(path(d, cls='sym-s thick' if sw >= 0.25 else 'sym-s', stroke=scol, stroke_dasharray=da))

        # pins
        pin_info = []
        for pin in all_pins:
            if pin.hide:
                continue
            px, py, pa = float(pin.at.x), float(pin.at.y), float(pin.at.rotation or 0)
            L = float(pin.length if pin.length is not None else 2.54)
            ux, uy = round(math.cos(math.radians(pa))), round(math.sin(math.radians(pa)))
            a = P(px, py)
            b = P(px + ux * L, py + uy * L)
            pin_info.append((a, b, L, pin))
            sdx, sdy = b[0] - a[0], b[1] - a[1]
            nrm = math.hypot(sdx, sdy) or 1
            sdx, sdy = sdx / nrm, sdy / nrm
            ptype, pshape = str(pin.etype), str(pin.style)
            line_end = b
            if pshape in ('inverted', 'inverted_clock') and L > 1.3:
                r = .5
                line_end = (b[0] - sdx * 2 * r, b[1] - sdy * 2 * r)
                deco.append(tag('circle', cx=b[0] - sdx * r, cy=b[1] - sdy * r, r=r, cls='pin-bubble'))
            if L > 0:
                pins_d.append(f'M{f2(a[0])} {f2(a[1])}L{f2(line_end[0])} {f2(line_end[1])}')
            nx, ny = -sdy, sdx
            if pshape in ('clock', 'inverted_clock', 'clock_low', 'edge_clock_high'):
                deco.append(path(f'M{f2(b[0] + nx * .55)} {f2(b[1] + ny * .55)}L{f2(b[0] + sdx * .9)} '
                                 f'{f2(b[1] + sdy * .9)}L{f2(b[0] - nx * .55)} {f2(b[1] - ny * .55)}', cls='pin-deco'))
            if pshape in ('input_low', 'clock_low'):
                deco.append(path(f'M{f2(b[0])} {f2(b[1])}L{f2(b[0] - sdx * 1.27 - nx * .9)} '
                                 f'{f2(b[1] - sdy * 1.27 - ny * .9)}L{f2(b[0] - sdx * 1.27)} {f2(b[1] - sdy * 1.27)}',
                                 cls='pin-deco'))
            if pshape == 'output_low':
                deco.append(path(f'M{f2(b[0] - nx * .9)} {f2(b[1] - ny * .9)}L{f2(b[0] - sdx * 1.27)} '
                                 f'{f2(b[1] - sdy * 1.27)}', cls='pin-deco'))
            if pshape == 'non_logic' or ptype == 'no_connect':
                deco.append(path(f'M{f2(a[0] - .45)} {f2(a[1] - .45)}l.9 .9M{f2(a[0] + .45)} {f2(a[1] - .45)}l-.9 .9',
                                 cls='pin-deco'))
            if char:
                continue
            vertical = abs(sdy) > 0.5
            name = pin.name.value or '' if pin.name is not None else ''
            num = pin.number.value or '' if pin.number is not None else ''
            nsize = font(pin.name)[0] if pin.name is not None else 1.27
            msize = font(pin.number)[0] if pin.number is not None else 1.27
            show_name = not names_hidden and name not in ('', '~') and nsize > 0 and not power and not hidden(pin.name)
            show_num = not nums_hidden and num != '' and msize > 0 and not power and not hidden(pin.number)
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            if show_name:
                if name_off > 0:
                    tx, ty = b[0] + sdx * name_off, b[1] + sdy * name_off
                    h = ('left' if sdy < 0 else 'right') if vertical else ('left' if sdx > 0 else 'right')
                    texts.append(text_el(tx, ty, name, nsize, 90 if vertical else 0, h, 'center', 'pinname'))
                elif vertical:
                    texts.append(text_el(mx - 0.4, my, name, nsize, 90, 'center', 'bottom', 'pinname'))
                else:
                    texts.append(text_el(mx, my - 0.4, name, nsize, 0, 'center', 'bottom', 'pinname'))
            if show_num:
                above = name_off > 0 or not show_name
                if vertical:
                    texts.append(text_el(mx - 0.4 if above else mx + 0.4, my, num, msize, 90, 'center',
                                         'bottom' if above else 'top', 'pinnum'))
                else:
                    texts.append(text_el(mx, my - 0.4 if above else my + 0.4, num, msize, 0, 'center',
                                         'bottom' if above else 'top', 'pinnum'))

        # fields
        nunits = len(units - {0})
        for pname, prop in props.items():
            if hidden(prop) or not prop.value:
                continue
            s = prop.value
            if pname == 'Reference':
                if s.startswith('#'):
                    continue
                if nunits > 1:
                    s += chr(ord('A') + unit - 1)
            if prop.show_name:
                s = f'{pname}: {s}'
            fx, fy = at(prop)
            fang = rotation(prop)
            h, v = justify(prop)
            size, bold, italic, tcol = font(prop)
            swap = quarter_turned(sym)  # rotated by 90/270: KiCad toggles field orientation
            vertical = (round(fang) % 180 == 90) != swap
            dvec = {'left': 1, 'right': -1, 'center': 0}[h]
            if dvec:        # justification, transformed like the symbol, then made readable
                rd = (math.cos(math.radians(fang)), -math.sin(math.radians(fang)))
                tx_, ty_ = sym.transform_vector(rd[0] * dvec, -rd[1] * dvec)
                if vertical and abs(ty_) > 0.5:
                    h = 'left' if ty_ < 0 else 'right'
                elif not vertical and abs(tx_) > 0.5:
                    h = 'left' if tx_ > 0 else 'right'
            cls = {'Reference': 'ref', 'Value': 'pwr' if power else 'value'}.get(pname, 'field')
            texts.append(text_el(fx, fy, s, size, 90 if vertical else 0, h, v, cls, style=text_style(bold, italic, tcol)))
            self.mark_text(fx, fy, s, size, 90 if vertical else 0, h, v, pad=0.8, cls=cls)

        sid = self.uid(ref)
        entry = {'id': sid, 'ref': ref, 'lib_id': lib_id, 'parts': []}
        parts = entry['parts']
        if shadow:
            parts.append(group(shadow, cls='shadow', transform='translate(.9 .9)', fill='url(#tone-ink)', opacity=.55))
        parts += fills + strokes
        if pins_d:
            parts.append(path(''.join(pins_d), cls='pin'))
        parts += deco
        if xs:
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            self.grid.mark_rect(x0, y0, x1, y1, pad=2.0)
            self.fine.mark_rect(x0, y0, x1, y1, pad=0.3)
            if not power and not dnp and not char:
                face = self.face_for(xf, rects, all_pins, name_off, names_hidden, subs)
                if face:
                    parts.append(face)
        # texts and the DNP cross go on top of characters, so they are added at the end
        entry['texts'] = texts
        if char:
            self.passives.append({'entry': entry, 'kind': char, 'xf': xf, 'subs': subs, 'value': value,
                                  'lib_id': lib_id, 'pins': pin_info})
        if dnp and xs:
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            x0, x1 = min(x0, mx - 1.6), max(x1, mx + 1.6)
            y0, y1 = min(y0, my - 1.6), max(y1, my + 1.6)
            entry['dnp'] = path(f'M{f2(x0)} {f2(y0)}L{f2(x1)} {f2(y1)}M{f2(x1)} {f2(y0)}L{f2(x0)} {f2(y1)}', cls='dnp')
        self.symbols.append(entry)

    def face_for(self, xf, rects, pins, name_off, names_hidden, subs):
        big = [r for r in rects if r[4] == 'background' and abs(r[2] - r[0]) >= 9 and abs(r[3] - r[1]) >= 9]
        if not big:
            return None
        sx, sy, ex, ey, _ = max(big, key=lambda r: abs(r[2] - r[0]) * abs(r[3] - r[1]))
        x0, x1 = sorted((sx, ex))
        y0, y1 = sorted((sy, ey))
        # no face if the body already has drawings in it (diodes, logos, ...)
        for sub in subs:
            for kind, g in unit_graphics(sub):
                if kind == 'rectangle' and (*xy(g.start), *xy(g.end)) == (sx, sy, ex, ey):
                    continue
                if any(x0 + .3 < px < x1 - .3 and y0 + .3 < py < y1 - .3 for px, py in shape_points(kind, g)):
                    return None
        fx0, fx1, fy0, fy1 = x0 + 1, x1 - 1, y0 + 1, y1 - 1
        for pin in pins:
            if pin.hide:
                continue
            pa = float(pin.at.rotation or 0)
            name = pin.name.value or '' if pin.name is not None else ''
            intr = .5 if names_hidden or name in ('', '~') else \
                name_off + len(plain(name)) * CHAR_W * FS * font(pin.name)[0] + 1.0
            px, py = xy(pin.at)
            L = float(pin.length if pin.length is not None else 2.54)
            bx, by = px + round(math.cos(math.radians(pa))) * L, py + round(math.sin(math.radians(pa))) * L
            if pa == 0 and fy0 - 1.4 < by < fy1 + 1.4:
                fx0 = max(fx0, x0 + intr)
            elif pa == 180 and fy0 - 1.4 < by < fy1 + 1.4:
                fx1 = min(fx1, x1 - intr)
            elif pa == 90 and fx0 - 1.4 < bx < fx1 + 1.4:
                fy0 = max(fy0, y0 + intr)
            elif pa == 270 and fx0 - 1.4 < bx < fx1 + 1.4:
                fy1 = min(fy1, y1 - intr)
        size = min(fx1 - fx0, fy1 - fy0, 16) * 0.8
        if size < 4:
            return None
        cx, cy = xf((fx0 + fx1) / 2, (fy0 + fy1) / 2)
        mood = self.rng.choice(['happy', 'wink', 'smile', 'cat', 'sparkle'])
        return tag('use', cls='face', href=f'#face-{mood}', transform=f'translate({f2(cx)} {f2(cy)}) scale({f2(size / 10)})')

    # -- passive components as characters -----------------------------------
    def cast(self):
        """Which characters appear on the sheet, for the legend."""
        cast = {p['kind']: True for p in self.passives}
        if self.characters and self.sch.buses:
            cast['bus'] = True
        inds = [p for p in self.passives if p['kind'] == 'ind']
        if inds:
            beads = [p for p in inds if ref_prefix(p['entry']['ref']) == 'FB' or 'bead' in p['lib_id'].lower()]
            cast['ind'] = 'ferrite bead' if len(beads) == len(inds) else 'inductor'
        return cast

    def render_characters(self):
        rng = random.Random(11)
        moods = ['grumpy', 'yell', 'smug', 'pout']
        for p in self.passives:
            entry, kind, xf = p['entry'], p['kind'], p['xf']
            pins = p['pins']
            if len(pins) < 2:
                continue
            # the two pins furthest apart define the body axis
            a_, b_ = max(((u, v) for i, u in enumerate(pins) for v in pins[i + 1:]),
                         key=lambda uv: math.hypot(uv[0][0][0] - uv[1][0][0], uv[0][0][1] - uv[1][0][1]))
            (pa, pa_in, _, _), (pb, pb_in, _, _) = a_, b_
            cx, cy = (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
            vertical = abs(pa[1] - pb[1]) > abs(pa[0] - pb[0])
            half = math.hypot(pa_in[0] - pb_in[0], pa_in[1] - pb_in[1]) / 2
            add = lambda svg, kind=kind: entry['parts'].append(group([svg], cls='character', data_character=kind))
            if kind == 'cap':
                plus = None
                if 'polar' in p['lib_id'].lower() or p['lib_id'].split(':')[-1].upper().startswith('CP'):
                    pos = next((q for q in pins if q[3].number is not None and q[3].number.value == '1'), None)
                    plus = pos[1] if pos else None
                add(C.cat_capacitor(rng, cx, cy, vertical, p['value'], [], plus=plus))
                self.fine.mark_rect(cx - 2.4, cy - 2.4, cx + 2.4, cy + 2.4)
            elif kind == 'res':
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
                add(C.resistor_guy(rng, cx, cy, vertical, max(1.2, half), rng.choice(moods), throw))
            elif kind == 'ind':
                a, b = sorted((pa_in, pb_in), key=lambda q: (q[1], q[0]))
                core = [[xf(*xy(q)) for q in g.pts] for sub in p['subs'] for g in sub.polylines]
                add(C.caterpillar(rng, a, b, [(q[0], q[-1]) for q in core if len(q) >= 2]))
            elif kind == 'xtal':
                box = [(xf(*xy(g.start)), xf(*xy(g.end))) for sub in p['subs'] for g in sub.rectangles]
                if box:
                    (x0, y0), (x1, y1) = box[0]
                else:
                    x0, y0, x1, y1 = cx - .8, cy - 1.5, cx + .8, cy + 1.5
                add(C.dancing_crystal(rng, cx, cy, (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)),
                                      lambda qx, qy: self.fine.free(qx - .9, qy - .9, qx + .9, qy + .9)))


def hier_glyph(x, y, ux, uy, shape, size, fill):
    """The input/output/bidirectional/... flag of a hierarchical label or sheet pin at (x, y), pointing along
    (ux, uy) away from the connection point."""
    s = size * .5
    nx, ny = -uy, ux
    P = lambda u, n: f'{f2(x + ux * u + nx * n)} {f2(y + uy * u + ny * n)}'
    if shape == 'input':          # arrow pointing at the wire
        d = f'M{P(0, 0)}L{P(s, s)}L{P(2 * s, s)}L{P(2 * s, -s)}L{P(s, -s)}Z'
    elif shape == 'output':       # arrow pointing away from it
        d = f'M{P(0, s)}L{P(s, s)}L{P(2 * s, 0)}L{P(s, -s)}L{P(0, -s)}Z'
    elif shape in ('bidirectional', 'tri_state'):
        d = f'M{P(0, 0)}L{P(s, s)}L{P(2 * s, 0)}L{P(s, -s)}Z'
    else:
        d = f'M{P(0, s)}L{P(2 * s, s)}L{P(2 * s, -s)}L{P(0, -s)}Z'
    return path(d, fill=fill, stroke=LINE, stroke_width=.22, stroke_linejoin='round')
