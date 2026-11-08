"""The schematic as an embroidery chart.

The holes of the aida cloth sit on the schematic grid (`hole_mm`, 1.27 mm), so:

- **Wires** run from hole to hole and are backstitched, one stitch per grid step, in their net's thread. Buses are
  couched: a thick laid thread tied down with small stitches.
- **Junctions** are French knots, **no-connects** one big red cross stitch.
- **Symbol bodies** that KiCad fills with the background colour are filled with cross stitches, one per cell of
  the cloth they mostly cover, in a pastel thread per library. Small filled shapes (diode triangles and the like)
  are satin stitched.
- **Outlines, pins and text** are backstitched with short stitches along KiCad's own drawing, text in KiCad's
  stroke font. Power symbols are stitched in their rail's thread.

Everything is taken from gerbonara's SVG export, which draws like KiCad. A colour scheme whose colours are role
names tells the parts of that drawing apart."""

import math
from dataclasses import dataclass, field

from ..circuit import UF
from ..kicad import at, lib_symbols, paper_size, xy
from . import threads as th
from .geometry import flatten, point_in_poly


class Roles:
    """A gerbonara colour scheme whose 'colours' name what was drawn with them."""
    wire = 'role:wire'
    bus = 'role:bus'
    lines = 'role:lines'
    no_connect = 'role:nc'
    text = 'role:text'
    values = 'role:values'
    labels = 'role:labels'
    pin_names = 'role:pin_names'
    pin_numbers = 'role:pin_numbers'
    fill = 'role:fill'
    background = 'role:background'


@dataclass
class Stitch:
    """A run of backstitch along a polyline."""
    pts: list
    color: str
    weight: str = 'line'        # 'wire', 'line', 'text', 'fine', 'bus'
    length: float = 0.8         # stitch length; 0: straight from point to point
    width: float = 0.0          # for text: the line width KiCad draws it with


@dataclass
class Chart:
    hole: float
    crosses: dict = field(default_factory=dict)     # (i, j) -> colour; the cell spans holes i..i+1, j..j+1
    stitches: list = field(default_factory=list)
    knots: list = field(default_factory=list)       # (x, y, r, colour)
    satin: list = field(default_factory=list)       # (points, colour)
    big_crosses: list = field(default_factory=list)  # (x, y, half size, colour)
    petite: list = field(default_factory=list)       # (x, y, size, colour): petite point, a quarter of a cell

    def motif(self, chart, i, j, key, overwrite=False):
        """Stitch a charted motif with its top left at cell (i, j)."""
        for r, row in enumerate(chart):
            for c, v in enumerate(row):
                if v != '.' and v in key and (overwrite or (i + c, j + r) not in self.crosses):
                    self.crosses[(i + c, j + r)] = key[v]

    def cell_of(self, x, y):
        return math.floor(x / self.hole), math.floor(y / self.hole)

    def occupied(self, pad=1):
        """Cells anything is stitched in or across, grown by `pad` cells."""
        b = self.hole
        cells = set(self.crosses)
        for s in self.stitches:
            for (x0, y0), (x1, y1) in zip(s.pts, s.pts[1:]):
                n = max(1, int(math.hypot(x1 - x0, y1 - y0) / (b / 2)))
                for k in range(n + 1):
                    cells.add(self.cell_of(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n))
        for x, y, *_ in self.knots + self.big_crosses + self.petite:
            cells.add(self.cell_of(x, y))
        for pts, _ in self.satin:
            for x, y in pts:
                cells.add(self.cell_of(x, y))
        if pad:
            cells = {(i + di, j + dj) for i, j in cells for di in range(-pad, pad + 1) for dj in range(-pad, pad + 1)}
        return cells


def on_seg(p, a, b, eps=1e-3):
    (px, py), (ax, ay), (bx, by) = p, a, b
    if min(ax, bx) - eps <= px <= max(ax, bx) + eps and min(ay, by) - eps <= py <= max(ay, by) + eps:
        return abs((bx - ax) * (py - ay) - (by - ay) * (px - ax)) < eps * max(1, math.hypot(bx - ax, by - ay))
    return False


def key(p):
    return round(p[0], 2), round(p[1], 2)


class Embroiderer:
    """Turns a schematic into a Chart."""

    def __init__(self, sch, hole=1.27):
        self.sch = sch
        self.hole = hole
        self.W, self.H = paper_size(sch)
        self.libs = lib_symbols(sch)
        self.chart = Chart(hole)
        labels = [(lab.text, *at(lab)) for lab in self.all_labels()]
        lib_ids = [s.lib_id for s in sch.symbols if not self.is_power(s)]
        self.threads = th.Threads(labels, lib_ids)

    def lib(self, sym):
        return self.libs.get(sym.lib_name or sym.lib_id) or self.libs.get(sym.lib_id)

    def is_power(self, sym):
        lib = self.lib(sym)
        return lib is not None and lib.is_power

    def all_labels(self):
        return [*self.sch.local_labels, *self.sch.global_labels, *self.sch.hierarchical_labels]

    # -- nets -----------------------------------------------------------------------
    def build_nets(self):
        wires = list(self.sch.wires)
        segs = []
        for k, w in enumerate(wires):
            pts = [xy(p) for p in w.points]
            for a, b in zip(pts, pts[1:]):
                segs.append((k, a, b))
        uf = UF(len(wires))
        ends = {}
        for k, w in enumerate(wires):
            for p in (w.points[0], w.points[-1]):
                ends.setdefault(key(xy(p)), []).append(k)
        for ks in ends.values():
            for k in ks[1:]:
                uf.union(ks[0], k)
        # T joints: a wire's end on another wire's middle (grid-bucketed to keep it quick)
        buckets = {}
        for k, a, b in segs:
            for c in self.cells_along(a, b, 5.0):
                buckets.setdefault(c, []).append((k, a, b))
        for p, ks in ends.items():
            c = (math.floor(p[0] / 5.0), math.floor(p[1] / 5.0))
            for k, a, b in buckets.get(c, ()):
                if on_seg(p, a, b):
                    uf.union(ks[0], k)
        self.wire_net = [uf.find(k) for k in range(len(wires))]
        self.wires = wires
        self.segs = segs
        self.seg_buckets = buckets

        names = {}
        for lab in self.all_labels():
            for k in self.wires_at(at(lab)):
                names.setdefault(self.wire_net[k], lab.text)
        for sym in self.sch.symbols:
            if self.is_power(sym):
                v = next((p.value for p in sym.properties if p.key == 'Value'), '')
                for k in self.wires_at(at(sym)):
                    if v:
                        names.setdefault(self.wire_net[k], v)
        self.net_name = names
        self.net_color = {}
        for k, n in enumerate(self.wire_net):
            if n not in self.net_color:
                self.net_color[n] = self.threads.net(names.get(n), n)

    def cells_along(self, a, b, size):
        (x0, y0), (x1, y1) = a, b
        n = max(1, int(math.hypot(x1 - x0, y1 - y0) / (size / 2)))
        return {(math.floor((x0 + (x1 - x0) * t / n) / size), math.floor((y0 + (y1 - y0) * t / n) / size))
                for t in range(n + 1)}

    def wires_at(self, p):
        c = (math.floor(p[0] / 5.0), math.floor(p[1] / 5.0))
        return [k for k, a, b in self.seg_buckets.get(c, ()) if on_seg(p, a, b)]

    def color_at(self, p, default=th.INK):
        ks = self.wires_at(p)
        return self.net_color[self.wire_net[ks[0]]] if ks else default

    # -- everything -------------------------------------------------------------------
    def build(self):
        self.build_nets()
        c = self.chart
        for k, w in enumerate(self.wires):
            col = self.net_color[self.wire_net[k]]
            c.stitches.append(Stitch([xy(p) for p in w.points], col, 'wire', self.hole))
        for bus in self.sch.buses:
            c.stitches.append(Stitch([xy(p) for p in bus.points], th.INK, 'bus', self.hole))
        for be in self.sch.bus_entries:
            (x, y), (sx, sy) = at(be), xy(be.size)
            col = self.color_at((x, y), None) or self.color_at((x + sx, y + sy))
            c.stitches.append(Stitch([(x, y), (x + sx, y + sy)], col, 'wire', 0))
        for j in self.sch.junctions:
            p = at(j)
            c.knots.append((*p, .5, self.color_at(p)))
        for nc in self.sch.no_connects:
            c.big_crosses.append((*at(nc), .62, th.NO_CONNECT))
        for sym in self.sch.symbols:
            self.symbol(sym)
        for lab in self.all_labels():
            self.label(lab)
        for t in self.sch.texts:
            self.prims(flatten(t.to_svg(Roles)), th.NOTE)
        for item in (*self.sch.netclass_flags, *getattr(self.sch, 'directive_labels', [])):
            col = self.color_at(at(item), th.INK)
            self.prims(flatten(item.to_svg(Roles)), th.shade(col, -.15))
        for kind in ('polylines', 'rectangles', 'circles', 'arcs', 'beziers', 'text_boxes', 'tables', 'sheets',
                     'rule_areas'):
            for item in getattr(self.sch, kind, None) or []:
                try:
                    self.prims(flatten(item.to_svg(Roles)), th.NOTE)
                except Exception:      # an item gerbonara can't draw doesn't stop the sampler
                    continue
        return c

    def symbol(self, sym):
        lib = self.lib(sym)
        if lib is None:
            return
        power = lib.is_power
        if power:
            pins_at = at(sym)
            ink = self.color_at(pins_at, th.SUPPLY)
            body = ink
        else:
            ink = th.INK
            body = self.threads.body(sym.lib_id)
        out = list(sym.to_svg(Roles))
        prop_tags = []
        for prop in sym.properties:
            tags = list(prop.to_svg(Roles))
            prop_tags.append((prop, tags))
        n_props = sum(len(t) for _, t in prop_tags)
        graphics, pins = out[0], out[1]
        texts = out[2:len(out) - n_props]
        self.prims(flatten(graphics), ink, body=body, power=power)
        self.prims(flatten(pins), ink)
        self.prims(flatten(texts), ink)
        for prop, tags in prop_tags:
            if power:
                col = th.shade(ink, -.2)
            elif prop.key == 'Reference':
                col = th.INK
            else:
                col = th.VALUE
            self.prims(flatten(tags), col)

    def label(self, lab):
        col = th.shade(self.color_at(at(lab), th.INK), -.18)
        self.prims(flatten(lab.to_svg(Roles)), col)

    def prims(self, prims, ink, body=None, power=False):
        c = self.chart
        for p in prims:
            text = p.stroke in (Roles.text, Roles.values, Roles.labels, Roles.pin_names, Roles.pin_numbers)
            if p.kind == 'circle':
                if p.fill and p.fill.startswith('role:') and p.fill != Roles.fill:
                    c.knots.append((*p.center, max(p.r, .3), ink))
                    continue
                pts = [(p.center[0] + p.r * math.cos(t * math.pi / 12), p.center[1] + p.r * math.sin(t * math.pi / 12))
                       for t in range(25)]
                if p.fill == Roles.fill and body:
                    self.fill_cells(pts, body, p)
                c.stitches.append(Stitch(pts, ink, 'line', .6))
                continue
            pts = p.pts
            if len(pts) < 2:
                continue
            if p.fill and len(pts) > 2:
                if p.fill == Roles.fill:
                    if body:
                        self.fill_cells(pts, body, p)
                elif p.fill.startswith('role:'):
                    c.satin.append((pts, ink))
                else:
                    self.fill_cells(pts, self.threads.use(th.nearest(p.fill, th.BODY_FLOSS), "part bodies"), p, satin_ink=ink)
            if p.closed:
                pts = pts + [pts[0]]
            if text:
                col = th.PIN_TEXT if p.stroke in (Roles.pin_names, Roles.pin_numbers) else ink
                c.stitches.append(Stitch(pts, col, 'text', 0, p.width))
            elif p.stroke:
                c.stitches.append(Stitch(pts, ink, 'line', .8))

    def fill_cells(self, pts, col, prim, satin_ink=None):
        """Cross stitches in the cells a filled shape mostly covers; satin stitch when it covers too few."""
        b = self.hole
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        i0, i1 = math.floor(min(xs) / b), math.ceil(max(xs) / b)
        j0, j1 = math.floor(min(ys) / b), math.ceil(max(ys) / b)
        cells = []
        for i in range(i0, i1):
            for j in range(j0, j1):
                hit = sum(point_in_poly((i + (u + .5) / 4) * b, (j + (v + .5) / 4) * b, pts)
                          for u in range(4) for v in range(4))
                if hit >= 9:
                    cells.append((i, j))
        if len(cells) < 3:
            self.chart.satin.append((pts, satin_ink or th.shade(col, -.15)))
            return
        for cell in cells:
            self.chart.crosses.setdefault(cell, col)
