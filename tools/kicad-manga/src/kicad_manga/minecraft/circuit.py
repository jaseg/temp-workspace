"""The schematic, built from blocks.

- **Grid:** one block per 2.54 mm (the usual pin pitch) by default. Wire ends, pins and labels are snapped to it.
- **Wires** are redstone dust, coloured by net (grounds unpowered, supplies at full power), buses are rails.
- **Diodes** are repeaters pointing from anode to cathode (LEDs are lit), **transistors** comparators (P-type in
  subtract mode) with collector/drain at the back, emitter/source in front and the base/gate at a side.
- **Passives** are short rows of blocks between their pins: resistors a furnace each, capacitors a chest each
  (copper for electrolytics, its latch towards the + pin; wooden for the rest), inductors and ferrite beads copper. They often don't fit the grid or each other; they
  are pushed sideways a block or two, and their pins rerouted, until they fit (`Builder.place_line`).
- **ICs** are buildings filling their body: small and medium ones timber houses, large ones castles
  (`buildings`), with the pin names painted over walls and roofs. **Connectors** are portals: nether portals for
  row connectors, end portals for those with pins on several sides.
- **Everything else** gets a low body of block textures with its pin names painted on,
  and pins of dust. Power symbols are redstone torches, grounds hoppers, no-connects cobwebs.
- **Text** (labels, fields, notes) goes onto plaques: thin slabs of block textures with the pack's font painted on
  top. Plaques move out of the way of dust, parts and each other."""

import math
import re
import zlib

from ..circuit import UF, prop_value, ref_prefix, shape_points, unit_graphics
from ..kicad import at, font, hidden, justify, lib_symbols, paper_size, quarter_turned, rotation, xy
from . import buildings
from .world import DIRS, OPP, Block, Plaque, World, cells_on_segment, dir_of

FONT_PX_PER_MM = 10 / 1.27              # font pixels per mm on paper: 8 pixel glyphs about 1 mm high

# plaque styles: base block, text colour, text shadow
STYLES = {
    'label': ('white_wool', (74, 52, 40), False),
    'global': ('pink_wool', (96, 32, 56), False),
    'hier': ('light_blue_wool', (28, 52, 96), False),
    'ref': ('lime_terracotta', (34, 44, 20), False),
    'value': ('cherry_planks', (84, 36, 40), False),
    'power': ('red_wool', (255, 245, 235), True),
    'note': ('calcite', (70, 60, 55), False),
    'heading': ('yellow_wool', (90, 60, 20), False),
    'pin': (None, (255, 250, 240), True),
    'pin_backed': (None, (255, 250, 240), True),
    'title': ('white_wool', (150, 50, 80), False),
    'sign': ('stripped_cherry_wood', (80, 30, 40), False),
}

BODY_BLOCKS = ['spruce_planks', 'dark_oak_planks', 'mangrove_planks', 'brown_terracotta', 'green_terracotta',
               'cyan_terracotta', 'purple_terracotta']
CONNECTOR_BLOCKS = ['stripped_dark_oak_wood', 'stripped_spruce_wood', 'stripped_mangrove_wood']

YROT = {'north': 0, 'east': 90, 'south': 180, 'west': 270}     # model y rotation that turns a front from north
GROUND = re.compile(r'GND|EARTH|VSS|^0V$|CHASSIS', re.I)
SUPPLY = re.compile(r'^\+|VCC|VDD|VBUS|VBAT|^V[0-9]|[0-9]V[0-9]*$', re.I)


def stable_hash(s):
    return zlib.crc32(s.encode())


class Builder:
    def __init__(self, sch, pack, font, block_mm=2.54):
        self.sch, self.pack, self.font, self.b = sch, pack, font, block_mm
        self.fpx = max(8, round(block_mm * FONT_PX_PER_MM))      # font pixels per block
        W, H = paper_size(sch)
        self.origin = self.grid_origin()
        ox, oy = self.origin
        # cells of the sheet: cell (i, j) covers origin + ((i - .5) b, (j - .5) b) to origin + ((i + .5) b, ...)
        self.paper = (math.ceil((W - ox) / block_mm + .5), math.ceil((H - oy) / block_mm + .5))
        # the world is the sheet: whatever was put beside it is left out
        self.world = World(0, 0, *self.paper)
        self.libs = lib_symbols(sch)
        self.net_names = {}
        self.net_power = {}
        self.stuck = []
        self.stats = {'nudged': 0, 'unplaced': 0, 'plaques_moved': 0, 'plaques_stuck': 0}

    def grid_origin(self):
        """Where the block grid starts (mm): on whichever half of the grid most wire ends, pins and labels sit, so
        that they land in the middle of their blocks."""
        b = self.b
        xs, ys = [], []
        for wire in self.sch.wires:
            for p in wire.points:
                xs.append(float(p.x))
                ys.append(float(p.y))
        for item in (*self.sch.symbols, *self.sch.local_labels, *self.sch.global_labels,
                     *self.sch.hierarchical_labels):
            x, y = at(item)
            xs.append(x)
            ys.append(y)

        def best(vs):
            def on(o):
                return sum(1 for v in vs if abs((v - o) / b - round((v - o) / b)) < .05)
            return max((0.0, b / 2), key=on)
        return best(xs), best(ys)

    def fcell(self, x, y):
        """Fractional cell coordinates of a point on the sheet (mm)."""
        return (x - self.origin[0]) / self.b, (y - self.origin[1]) / self.b

    def mm(self, i, j):
        """The centre of a cell on the sheet (mm)."""
        return self.origin[0] + i * self.b, self.origin[1] + j * self.b

    def cell(self, x, y):
        fx, fy = self.fcell(x, y)
        return math.floor(fx + .5 + 1e-9), math.floor(fy + .5 + 1e-9)       # halves always round the same way

    def lib(self, sym):
        return self.libs.get(sym.lib_name or sym.lib_id) or self.libs.get(sym.lib_id)

    # -------------------------------------------------------------------------
    def build(self):
        self.build_nets()
        self.symbols = [self.symbol_info(s) for s in self.sch.symbols]
        self.symbols = [s for s in self.symbols if s is not None]
        for s in self.symbols:             # keep every pin's line clear for its own symbol
            for p in s['pins']:
                for c in p['line']:
                    if c not in self.world.dust or c == p['outer']:
                        self.world.soft.setdefault(c, s['owner'])
        for s in sorted(self.symbols, key=lambda s: (s['order'], self.opamp_pins(s) is None)):
            getattr(self, 'place_' + s['kind'])(s)
        self.world.soft.clear()
        self.no_connects()
        for s in self.symbols:             # supply names first: they must sit right next to their torch
            if s['kind'] == 'power':
                self.fields(s)
        self.labels()
        for s in self.symbols:
            if s['kind'] != 'power':
                self.fields(s)
        self.free_texts()
        self.graphics()
        return self.world

    # -- nets and wires -----------------------------------------------------------
    def build_nets(self):
        w = self.world
        segs = []
        for wire in self.sch.wires:
            pts = [self.cell(*xy(p)) for p in wire.points]
            for a, b in zip(pts, pts[1:]):
                segs.append(cells_on_segment(a, b))
        uf = UF(len(segs))
        where = {}
        for k, cells in enumerate(segs):
            for c in cells:
                where.setdefault(c, []).append(k)
        for k, cells in enumerate(segs):
            for end in (cells[0], cells[-1]):
                for o in where.get(end, ()):
                    uf.union(k, o)
        self.seg_net = [uf.find(k) for k in range(len(segs))]
        self.cell_nets = {c: {self.seg_net[k] for k in ks} for c, ks in where.items()}

        names = {}
        for lab, _ in self.all_labels():
            for n in self.cell_nets.get(self.cell(*at(lab)), ()):
                names.setdefault(n, lab.text)
        for sym in self.sch.symbols:
            lib = self.lib(sym)
            if lib is not None and lib.is_power:
                v = prop_value(sym, 'Value')
                for n in self.cell_nets.get(self.cell(*at(sym)), ()):
                    if v:
                        names.setdefault(n, v)
        self.net_names = names
        for k, cells in enumerate(segs):
            w.path(cells, self.seg_net[k])
        self.buses()

    def power(self, net):
        if net not in self.net_power:
            name = self.net_names.get(net, '')
            if GROUND.search(name):
                p = 4
            elif SUPPLY.search(name):
                p = 15
            else:
                p = 7 + stable_hash(name or str(net)) % 8
            self.net_power[net] = p
        return self.net_power[net]

    def net_at(self, c):
        nets = self.world.dust.get(c)
        return next(iter(nets)) if nets else None

    def new_net(self):
        self._nn = getattr(self, '_nn', 0) - 1
        return self._nn

    def buses(self):
        w = self.world
        rails = {}
        for bus in self.sch.buses:
            pts = [self.cell(*xy(p)) for p in bus.points]
            for a, b in zip(pts, pts[1:]):
                cells = cells_on_segment(a, b)
                for p, q in zip(cells, cells[1:]):
                    d = dir_of(q[0] - p[0], q[1] - p[1])
                    rails.setdefault(p, set()).add(d)
                    rails.setdefault(q, set()).add(OPP[d])
        # bus entries: the wire runs straight up to the bus, onto the rail next to it (laid there if the bus
        # stops short of it), which becomes an activator rail where the signal enters or leaves the bus
        activators = set()
        entries = []
        for be in self.sch.bus_entries:
            (x, y), (sx, sy) = at(be), xy(be.size)
            a, b = self.cell(x, y), self.cell(x + sx, y + sy)
            if b not in rails and a in rails:
                a, b = b, a
            entries.append((a, b, cells_on_segment(a, b)))
        for a, b, cells in entries:
            if b not in rails or a in rails:
                continue
            ds = rails[b]
            along_z = 'north' in ds or 'south' in ds or not ds
            n = (b[0], a[1]) if along_z else (a[0], b[1])
            if n != b and n not in rails:
                d = dir_of(b[0] - n[0], b[1] - n[1])
                if abs(b[0] - n[0]) + abs(b[1] - n[1]) == 1:
                    rails.setdefault(n, set()).add(d)
                    rails[b].add(OPP[d])
            if n in rails:
                activators.add(n)
        for c, ds in rails.items():
            if 'north' in ds or 'south' in ds:
                if 'east' in ds and len(ds) == 2:
                    shape = 'south_east' if 'south' in ds else 'north_east'
                elif 'west' in ds and len(ds) == 2:
                    shape = 'south_west' if 'south' in ds else 'north_west'
                else:
                    shape = 'north_south'
            else:
                shape = 'east_west'
            if c in activators and '_' in shape and shape not in ('north_south', 'east_west'):
                activators.discard(c)
            if c in activators:
                state = ('activator_rail', (('powered', 'true'), ('shape', shape)))
            else:
                state = ('rail', (('shape', shape),))
            w.blocks.append(Block(c[0], 0, c[1], 'state', state, flat=True))
            w.solid[c] = 'bus'
            w.circuit.add(c)
        for a, b, _ in entries:
            net = next(iter(self.cell_nets.get(a, ()) or self.cell_nets.get(b, ()) or [self.new_net()]))
            cells = [c for c in cells_on_segment(a, b) if c not in rails]
            if not cells:
                continue
            w.path(cells, net)
            last = cells[-1]
            for d, (di, dj) in DIRS.items():
                if (last[0] + di, last[1] + dj) in rails and (last[0] + di, last[1] + dj) in activators:
                    w.dust[last][net].add(d)
                    break

    # -- symbols -----------------------------------------------------------------
    def symbol_info(self, sym):
        lib = self.lib(sym)
        if lib is None:
            return None
        unit = int(sym.unit or 1)
        style = int(sym.body_style or sym.convert or 1)
        subs = [u for u in lib.units if u.unit_index in (0, unit) and u.demorgan_style in (0, style)]
        props = {p.key: p for p in sym.properties}
        ref = props['Reference'].value if 'Reference' in props else '?'
        value = props['Value'].value if 'Value' in props else ''
        xf = sym.transform_point
        pins = []
        for sub in subs:
            for pin in sub.pins:
                if pin.hide:
                    continue
                px, py, pa = float(pin.at.x), float(pin.at.y), float(pin.at.rotation or 0)
                L = float(pin.length if pin.length is not None else 2.54)
                ux, uy = round(math.cos(math.radians(pa))), round(math.sin(math.radians(pa)))
                a, b = xf(px, py), xf(px + ux * L, py + uy * L)
                ca, cb = self.cell(*a), self.cell(*b)
                name = (pin.name.value or '') if pin.name is not None else ''
                num = (pin.number.value or '') if pin.number is not None else ''
                net = self.net_at(ca)
                pins.append({'pin': pin, 'name': name, 'num': num, 'a': a, 'b': b, 'outer': ca, 'inner': cb,
                             'line': cells_on_segment(ca, cb), 'net': net if net is not None else self.new_net(),
                             'dir': dir_of(b[0] - a[0], b[1] - a[1]) if (a != b) else None})
        lib_id = sym.lib_id
        p = ref_prefix(ref)
        name = lib_id.split(':')[-1].lower()
        info = {'sym': sym, 'lib': lib, 'lib_id': lib_id, 'ref': ref, 'value': value, 'props': props, 'xf': xf,
                'subs': subs, 'pins': pins, 'owner': f'sym:{ref}:{id(sym)}', 'center': self.cell(*xy(sym.at))}
        n = len(pins)
        if lib.is_power:
            kind, order = 'power', 1
        elif p == 'D' and self.diode_pairs(pins):
            kind, order = 'diode', 3
        elif p == 'Q' and self.transistor_roles(pins):
            kind, order = 'transistor', 3
        elif n == 2 and p in ('R', 'RN', 'TH', 'RT', 'C', 'L', 'FB', 'FL', 'F'):
            kind, order = 'line', 4
        else:
            kind, order = 'body', 0
        info['kind'], info['order'] = kind, order
        info['family'] = {'R': 'res', 'RN': 'res', 'TH': 'res', 'RT': 'res', 'C': 'cap', 'L': 'ind', 'FB': 'fb',
                          'FL': 'fb', 'F': 'fuse'}.get(p, 'other')
        info['led'] = 'led' in name
        info['polar'] = 'polarized' in name or 'pol' in name.split('_')
        info['p_type'] = any(k in name for k in ('pnp', 'pmos', 'p-ch', 'pchannel', 'q_p'))
        return info

    def diode_pairs(self, pins):
        """(anode pin, cathode pin) of each diode in a diode symbol, or None when it is not that simple."""
        an = [p for p in pins if re.fullmatch(r'A\d*', p['name'].upper())]
        ca = [p for p in pins if re.fullmatch(r'K\d*', p['name'].upper())]
        rest = [p for p in pins if p not in an and p not in ca]
        if len(pins) == 2 and len(an) == 1 and len(ca) == 1:
            return [(an[0], ca[0])]
        if len(pins) == 3 and len(an) == 1 and len(ca) == 1 and len(rest) == 1:
            return [(an[0], rest[0]), (rest[0], ca[0])]
        if len(pins) == 3 and len(an) == 2 and len(ca) == 1:
            return [(an[0], ca[0]), (an[1], ca[0])]
        if len(pins) == 3 and len(an) == 1 and len(ca) == 2:
            return [(an[0], ca[0]), (an[0], ca[1])]
        return None

    def transistor_roles(self, pins):
        role = {}
        for p in pins:
            n = p['name'].upper()
            if n in ('B', 'G'):
                role['ctl'] = p
            elif n in ('C', 'D'):
                role['in'] = p
            elif n in ('E', 'S'):
                role['out'] = p
        return role if len(role) == 3 and len(pins) == 3 else None

    def tex(self, block, face='up'):
        """The texture a block shows on one face, from its model."""
        m = self.pack.model(f'block/{block}')
        for el in m['elements']:
            f = el.get('faces', {}).get(face)
            if f:
                t = f.get('texture', '')
                return m['textures'].get(t[1:], t) if t.startswith('#') else t
        return f'block/{block}'

    def box(self, c, block, h, owner, y=0, side=None, tint=None):
        top = self.tex(block, 'up')
        sd = self.tex(side or block, 'south')
        self.world.blocks.append(Block(c[0], y, c[1], 'box', (top, sd, h, tint), owner=owner))

    # -- power symbols --------------------------------------------------------------
    def place_power(self, s):
        if not s['pins']:
            return
        c = s['pins'][0]['outer']
        w = self.world
        if GROUND.search(s['value']):
            w.blocks.append(Block(c[0], 0, c[1], 'state', ('hopper', (('facing', 'down'),)), owner=s['owner']))
        else:
            w.blocks.append(Block(c[0], 0, c[1], 'state', ('redstone_torch', (('lit', 'true'),)),
                                  owner=s['owner']))
        w.solid[c] = s['owner']
        w.dust.pop(c, None)
        w.circuit.add(c)
        s['skip_fields'] = GROUND.search(s['value']) and s['value'].upper() == 'GND'
        s['field_style'] = 'power'

    # -- generic bodies -------------------------------------------------------------
    def body_cells(self, s):
        xf = s['xf']
        cells = set()
        for sub in s['subs']:
            for kind, g in unit_graphics(sub):
                if kind == 'text':
                    continue
                ftype = str(getattr(getattr(g, 'fill', None), 'type', 'none'))
                pts = [xf(*p) for p in shape_points(kind, g)]
                if kind == 'rectangle':
                    (x0, y0), (x1, y1) = pts
                    cells |= self.rect_cells(x0, y0, x1, y1)
                elif kind == 'polyline' and len(pts) > 2 and ftype != 'none':
                    cells |= self.poly_cells(pts)
                elif kind == 'circle' and ftype != 'none':
                    r = float(g.radius or 1)
                    (cx, cy), = pts
                    cells |= {c for c in self.rect_cells(cx - r, cy - r, cx + r, cy + r)
                              if math.hypot(self.mm(*c)[0] - cx, self.mm(*c)[1] - cy) <= r + .2}
        if not cells:      # no filled shapes: the bounding box of the drawing
            xs, ys = [], []
            for sub in s['subs']:
                for kind, g in unit_graphics(sub):
                    if kind != 'text':
                        for p in shape_points(kind, g):
                            X, Y = xf(*p)
                            xs.append(X)
                            ys.append(Y)
            if xs:
                cells = self.rect_cells(min(xs), min(ys), max(xs), max(ys))
            else:
                cells = {s['center']}
        return cells

    def rect_cells(self, x0, y0, x1, y1):
        (x0, y0), (x1, y1) = self.fcell(x0, y0), self.fcell(x1, y1)
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        i0, i1 = math.ceil(x0 - .01), math.floor(x1 + .01)
        j0, j1 = math.ceil(y0 - .01), math.floor(y1 + .01)
        if i1 < i0:
            i0 = i1 = math.floor((x0 + x1) / 2 + .5 + 1e-9)
        if j1 < j0:
            j0 = j1 = math.floor((y0 + y1) / 2 + .5 + 1e-9)
        return {(i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)}

    def poly_cells(self, pts):
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        out = set()
        for c in self.rect_cells(min(xs), min(ys), max(xs), max(ys)):
            if point_in_poly(self.mm(*c), pts):
                out.add(c)
        return out or self.rect_cells(min(xs), min(ys), max(xs), max(ys))

    def body_block(self, s):
        lib = s['lib_id'].split(':')[0]
        if lib.lower().startswith('connector'):
            return CONNECTOR_BLOCKS[stable_hash(s['lib_id']) % len(CONNECTOR_BLOCKS)]
        if lib == 'Mechanical':
            return 'cauldron'
        return BODY_BLOCKS[stable_hash(lib) % len(BODY_BLOCKS)]

    def place_body(self, s):
        w = self.world
        if self.place_opamp(s):
            return
        cells = self.body_cells(s)
        amp = [o for o in self.symbols if o is not s and o['ref'] == s['ref'] and o.get('building') == 'opamp'
               and o['body'] & cells]
        if amp:                     # the supply pins of an op amp drawn over one of its units: wires only
            body = amp[0]['body']
            for p in s['pins']:
                line = []
                for c in p['line']:
                    if c in body:
                        break
                    line.append(c)
                if line:
                    w.path(line, p['net'])
                    nxt = (line[-1][0] + DIRS[p['dir']][0], line[-1][1] + DIRS[p['dir']][1]) if p['dir'] else None
                    if nxt in body:
                        w.dust[line[-1]][p['net']].add(p['dir'])
            return
        pin_ends = {p['outer'] for p in s['pins']}
        cells -= pin_ends
        if not cells:
            cells = {s['center']}
        if self.place_building(s, cells):
            return self.body_pins(s, cells)
        block = self.body_block(s)
        h = 10
        if self.is_card(s):         # a card socket: a thin dark slab, gold contacts along the pin side
            h = 3
            sides = {p['dir'] for p in s['pins'] if p['dir']}
            I0, I1 = min(c[0] for c in cells), max(c[0] for c in cells)
            J0, J1 = min(c[1] for c in cells), max(c[1] for c in cells)
            edge = {'east': lambda c: c[0] == I0, 'west': lambda c: c[0] == I1,
                    'south': lambda c: c[1] == J0, 'north': lambda c: c[1] == J1}
            for c in cells:
                gold = any(edge[d](c) for d in sides)
                tex = 'block/gold_block' if gold else 'block/polished_deepslate'
                w.blocks.append(Block(c[0], 0, c[1], 'box', (tex, 'block/polished_deepslate', h, None),
                                      owner=s['owner']))
            cells = set(cells)
            w.occupy(cells, s['owner'])
            s['body'], s['body_h'] = cells, h / 16
            return self.body_pins(s, cells)
        for c in cells:
            if block == 'cauldron':
                w.blocks.append(Block(c[0], 0, c[1], 'state', ('cauldron', ()), owner=s['owner']))
            else:
                self.box(c, block, h, s['owner'])
        w.occupy(cells, s['owner'])
        s['body'] = cells
        s['body_h'] = h / 16
        self.body_pins(s, cells)

    @staticmethod
    def opamp_pins(s):
        """(+, -, out) pins of an op amp (or comparator) unit, or None."""
        if len(s['pins']) != 3:
            return None
        by = {p['name']: p for p in s['pins']}
        if '+' not in by or '-' not in by:
            return None
        (out,) = [p for p in s['pins'] if p['name'] not in ('+', '-')]
        return by['+'], by['-'], out

    def place_opamp(self, s):
        """Op amps are a stepped triangle of amethyst (it rings, it amplifies) pointing from the inputs to the
        output, with a cluster growing on top and budding amethyst at the tip. Its shape comes from the pins only,
        so every unit looks the same however its outline happens to fall on the grid."""
        pins = self.opamp_pins(s)
        if pins is None:
            return False
        pp, pm, out = pins
        if not (pp['dir'] and pp['dir'] == pm['dir'] and out['dir'] == OPP[pp['dir']]):
            return False
        u = DIRS[pp['dir']]                     # from the inputs towards the output
        q = (-u[1], u[0])
        O = out['inner']
        dot = lambda c, v: (c[0] - O[0]) * v[0] + (c[1] - O[1]) * v[1]
        W = -dot(pp['inner'], u) + 1            # columns, from the inputs' edge to the tip
        if W < 2:
            return False
        H = max(abs(dot(pp['inner'], q)), abs(dot(pm['inner'], q))) + 1
        cells, tip, core = {}, O, None
        for k in range(W):
            hk = round(H * (1 - k / (W - 1)))
            for r in range(-hk, hk + 1):
                back = W - 1 - k
                c = (O[0] - back * u[0] + r * q[0], O[1] - back * u[1] + r * q[1])
                cells[c] = k
        if any(c in self.world.solid and self.world.solid[c] != s['owner'] for c in cells):
            return False        # (another part in the way)
        core = (O[0] - (W - 2) * u[0], O[1] - (W - 2) * u[1]) if W > 2 else O
        for c in cells:
            self.box(c, 'budding_amethyst' if c == tip else 'amethyst_block', 16, s['owner'])
        self.world.blocks.append(Block(core[0], 1, core[1], 'state', ('amethyst_cluster', (('facing', 'up'),)),
                                       owner=s['owner']))
        cells = set(cells)
        self.world.occupy(cells, s['owner'])
        s['body'] = cells
        s['body_h'] = 1.0
        s['building'] = 'opamp'
        self.body_pins(s, cells)
        return True

    def body_pins(self, s, cells):
        w = self.world
        for p in s['pins']:
            line = [c for c in p['line'] if c not in cells]
            if not line:
                continue
            # the line from the pin end to the body: cut where it meets the body
            out = []
            for c in p['line']:
                if c in cells:
                    break
                out.append(c)
            line = out or line[:1]
            if p['dir'] and len(out) == len(p['line']):
                # the pin stops short of the body (its outline drawn inside the pin ends): carry the wire on
                d = DIRS[p['dir']]
                extra, c = [], line[-1]
                for _ in range(6):
                    c = (c[0] + d[0], c[1] + d[1])
                    if c in cells:
                        line = line + extra
                        break
                    if not w.free_for(c, s['owner'], p['net']):
                        break
                    extra.append(c)
            w.path(line, p['net'])
            if p['dir'] and len(line) >= 1:
                nxt = (line[-1][0] + DIRS[p['dir']][0], line[-1][1] + DIRS[p['dir']][1])
                if nxt in cells:
                    w.dust[line[-1]][p['net']].add(p['dir'])
        self.pin_names(s, cells)

    def is_ic(self, s):
        return ref_prefix(s['ref']) in ('U', 'IC', 'MODULE', 'TR')

    @staticmethod
    def is_card(s):
        """Memory card and SIM sockets: flat, so not portals."""
        return bool(re.search(r'micro_?sd|sd_?card|\bsim|card', s['lib_id'], re.I))

    def is_connector(self, s):
        if self.is_card(s):
            return False
        return ref_prefix(s['ref']) in ('J', 'P', 'CN', 'X') or s['lib_id'].lower().startswith('connector')

    def place_building(self, s, cells):
        """ICs: a house (small and medium ones) or a castle (large ones); connectors: a portal. See `buildings`."""
        def box(c, block, h):
            tex = (block, block) if '/' in block else (self.tex(block, 'up'), self.tex(block, 'south'))
            return Block(c[0], 0, c[1], 'box', tex + (h, None), owner=s['owner'])
        seed = stable_hash(s['ref'] or s['lib_id'])
        if self.is_ic(s) and len(cells) >= 4:
            res = buildings.plan(cells, s['pins'], s['owner'], seed, box)
            if res is None:
                return False
            blocks, h, kind = res
        elif self.is_connector(s):
            blocks, h = buildings.portal(cells, s['pins'], s['owner'], seed, box)
            kind = 'portal'
        else:
            return False
        self.world.blocks.extend(blocks)
        self.world.occupy(cells, s['owner'])
        s['body'] = cells
        s['body_h'] = h
        s['building'] = kind
        return True

    def pin_names(self, s, cells):
        lib = s['lib']
        pn = lib.pin_names
        if (pn is not None and pn.hide) or len(cells) < 4:
            return
        off = float(pn.offset) if pn is not None and pn.offset is not None else 0.508
        if off <= 0:
            return
        for p in s['pins']:
            name = p['name']
            if name in ('', '~') or not p['dir'] or hidden(p['pin'].name):
                continue
            name = re.sub(r'~\{([^}]*)\}', r'\1', name)
            d = DIRS[p['dir']]
            start = (p['inner'][0] + d[0], p['inner'][1] + d[1])
            if start not in cells:
                continue
            n = self.font.width(name) / self.fpx
            vertical = d[0] == 0
            # each name starts a fixed inset from the body's edge on its side (not from where its pin happens to
            # end, which rounding moves by a block either way)
            h = s['body_h'] + .001
            I0, I1 = min(c[0] for c in cells), max(c[0] for c in cells)
            J0, J1 = min(c[1] for c in cells), max(c[1] for c in cells)
            inset = .2
            if not vertical:
                y0 = start[1] - .5
                x0 = I0 - .5 + inset if d[0] > 0 else I1 + .5 - inset - n
                origin, u, v = (x0, h, y0), (n, 0, 0), (0, 0, 1)
            else:
                x0 = start[0] - .5
                z0 = J0 - .5 + inset + n if d[1] > 0 else J1 + .5 - inset
                origin, u, v = (x0, h, z0), (0, 0, -n), (1, 0, 0)
            side = {(1, 0): 'west', (-1, 0): 'east', (0, 1): 'north', (0, -1): 'south'}[d]
            self.world.texts.append(('pin_backed' if s.get('building') == 'portal' else 'pin', name, origin, u, v, side))

    # -- passives: rows of blocks between two pins, nudged until they fit ----------
    def place_line(self, s):
        p1, p2 = s['pins']
        A, B = p1['outer'], p2['outer']
        di, dj = B[0] - A[0], B[1] - A[1]
        if (di and dj) or (not di and not dj):
            return self.place_body(s)
        n = abs(di) + abs(dj)
        d = (di // n, dj // n)
        q = (-d[1], d[0])
        fam = s['family']
        designs = self.line_designs(fam, n, s, p1, d)
        best = None
        for shift_cost, shift in ((0, 0), (2, 1), (2, -1), (4, 2), (4, -2)):
            for dcost, design in designs:
                cand = (shift_cost + dcost, shift, design)
                if self.try_line(s, A, B, d, q, *cand[1:], commit=False):
                    best = cand
                    break
            if best:
                break
        if best is None:
            self.stats['unplaced'] += 1
            self.try_line(s, A, B, d, q, 0, designs[0][1], commit=True, force=True)
            return
        if best[0]:
            self.stats['nudged'] += 1
        self.try_line(s, A, B, d, q, best[1], best[2], commit=True)

    def line_designs(self, fam, n, s, p1, d=(1, 0)):
        """Ways to build a passive between pins n cells apart, best first: (cost, {(k, side): block}), where k
        counts cells from pin 1 and side across. None marks a cell kept empty."""
        out = []
        mid = n // 2
        if fam == 'cap':            # a chest: copper for electrolytics (latch to the + pin), wooden for the rest
            if s['polar']:
                face = dir_of(-d[0], -d[1])         # pin 1, the + pin
                chest = ('chest_copper', YROT[face])
            else:
                chest = ('chest', YROT['south' if d[0] else 'east'])
            return [(0, {(mid if n > 1 else 0, 0): ('mob', chest)})]
        if fam == 'res':            # one furnace, its front to the camera
            facing = 'south' if d[0] else 'east'
            return [(0, {(mid if n > 1 else 0, 0): ('state', ('furnace', (('facing', facing), ('lit', 'false'))))})]
        block = {'res': 'bricks', 'ind': 'cut_copper', 'fb': 'oxidized_cut_copper', 'fuse': 'iron_block'}.get(
            fam, 'polished_andesite')
        for cost, L in ((0, 3), (1, 2), (2, 1)):
            L = min(L, n - 1) if n > 1 else 1
            start = max(1, (n - L + 1) // 2) if n > 1 else 0
            cells = {(k, 0): ('body', block) for k in range(start, start + L)}
            out.append((cost, cells))
        return out

    def try_line(self, s, A, B, d, q, shift, design, commit, force=False):
        w = self.world
        owner = s['owner']

        def at_(k, side):
            return (A[0] + d[0] * k + q[0] * (side + shift), A[1] + d[1] * k + q[1] * (side + shift))
        cells = {at_(k, side): v for (k, side), v in design.items()}
        ks = [k for (k, side) in design]
        k0, k1 = min(ks), max(ks)
        p1, p2 = s['pins']
        ends = [(p1, at_(k0 - 1, 0), at_(k0, 0)), (p2, at_(k1 + 1, 0), at_(k1, 0))]
        if not force:
            for c in cells:
                if not w.free_for(c, owner) or c in (A, B):
                    return False
        routes = []
        if not force:
            for p, att, into in ends:
                if att == p['outer']:
                    routes.append(([att], p, into))
                    continue
                if not w.free_for(att, owner, p['net']):
                    return False
                r = w.route(p['outer'], att, p['net'], owner, limit=12, avoid=cells)
                if r is None:
                    return False
                routes.append((r, p, into))
        else:
            routes = [(cells_on_segment(p['outer'], att), p, into) for p, att, into in ends]
        if not commit:
            return True
        for c, v in cells.items():
            if v is None:
                w.solid[c] = owner
                continue
            kind, block = v
            if kind == 'mob':
                w.blocks.append(Block(c[0], 0, c[1], 'mob', block, owner=owner))
            elif kind == 'state':
                w.blocks.append(Block(c[0], 0, c[1], 'state', block, owner=owner))
            else:
                self.box(c, block, 8, owner, side=block)
        w.occupy(cells, owner)
        for r, p, into in routes:
            w.path(r, p['net'])
            dd = dir_of(into[0] - r[-1][0], into[1] - r[-1][1])
            w.dust[r[-1]][p['net']].add(dd)
        s['body'] = set(cells)
        return True

    # -- diodes and transistors: repeaters and comparators ----------------------
    def place_diode(self, s):
        for an, ca in self.diode_pairs(s['pins']):
            a, k = an['outer'], ca['outer']
            mid = (round((a[0] + k[0]) / 2), round((a[1] + k[1]) / 2))
            out = dir_of(k[0] - a[0], k[1] - a[1])
            props = (('delay', 2 if not s['led'] else 1), ('facing', OPP[out]),
                     ('powered', 'true' if s['led'] else 'false'), ('locked', 'false'))
            self.place_device(s, mid, 'repeater', props, out,
                              [(an, OPP[out]), (ca, out)])

    def place_transistor(self, s):
        r = self.transistor_roles(s['pins'])
        a, b = r['in']['outer'], r['out']['outer']
        out = dir_of(b[0] - a[0], b[1] - a[1])
        q = DIRS[out]
        side_vec = (-q[1], q[0])
        c = s['center']
        g = r['ctl']['outer']
        sd = (g[0] - c[0]) * side_vec[0] + (g[1] - c[1]) * side_vec[1]
        side = dir_of(*side_vec) if sd >= 0 else OPP[dir_of(*side_vec)]
        props = (('facing', OPP[out]), ('mode', 'subtract' if s['p_type'] else 'compare'),
                 ('powered', 'false'))
        self.place_device(s, c, 'comparator', props, out, [(r['in'], OPP[out]), (r['out'], out), (r['ctl'], side)])

    def place_device(self, s, mid, block, props, out, terminals):
        """A one-block device near `mid`, each (pin, side) terminal connected with dust to that side."""
        w = self.world
        owner = s['owner']
        best = None
        for off in spiral(2):
            c = (mid[0] + off[0], mid[1] + off[1])
            if not w.free_for(c, owner):
                continue
            routes = []
            ok = True
            for p, side in terminals:
                att = (c[0] + DIRS[side][0], c[1] + DIRS[side][1])
                if not w.free_for(att, owner, p['net']):
                    ok = False
                    break
                rt = w.route(p['outer'], att, p['net'], owner, limit=20, avoid={c})
                if rt is None:
                    ok = False
                    break
                routes.append((rt, p, side))
            if ok:
                best = (c, routes)
                break
        if best is None:
            self.stats['unplaced'] += 1
            best = (mid, [(cells_on_segment(p['outer'], (mid[0] + DIRS[sd][0], mid[1] + DIRS[sd][1])), p, sd)
                          for p, sd in terminals])
        elif best[0] != mid:
            self.stats['nudged'] += 1
        c, routes = best
        w.blocks.append(Block(c[0], 0, c[1], 'state', (block, props), owner=owner))
        w.occupy([c], owner)
        for rt, p, side in routes:
            w.path(rt, p['net'])
            w.dust[rt[-1]][p['net']].add(OPP[side])
        s.setdefault('body', set()).add(c)

    # -- labels, fields, text ---------------------------------------------------------
    def all_labels(self):
        for lab in self.sch.local_labels:
            yield lab, 'label'
        for lab in self.sch.global_labels:
            yield lab, 'global'
        for lab in self.sch.hierarchical_labels:
            yield lab, 'hier'

    def text_cells(self, s, scale=1):
        lines = s.split('\n')
        wpx = max(self.font.width(x) for x in lines) + 2
        hpx = len(lines) * 10
        return max(1, math.ceil(wpx * scale / self.fpx)), max(1, math.ceil(hpx * scale / self.fpx))

    def plaque(self, text, anchor, h, vertical, style, scale=1, reach=3, owner=None, net=None):
        """A plaque for text at anchor (cell), justified h ('left', 'right', 'center') along its reading
        direction, then nudged into a free spot."""
        wc, hc = self.text_cells(text, scale)
        L, T = (hc, wc) if vertical else (wc, hc)
        i, j = anchor
        if not vertical:
            i = {'left': i, 'right': i - wc + 1, 'center': i - (wc - 1) // 2}[h]
            j = j - (hc - 1) // 2
        else:
            j = {'left': j - wc + 1, 'right': j, 'center': j - (wc - 1) // 2}[h]
            i = i - (hc - 1) // 2
        pq = Plaque(text, i, j, L, T, vertical, style, scale)
        home = (pq.i, pq.j)
        ok = self.world.place_plaque(pq, reach=reach, along='z' if vertical else 'x', owner=owner, net=net)
        if not ok:
            self.stats['plaques_stuck'] += 1
            self.stuck.append((style, text))
        elif (pq.i, pq.j) != home:
            self.stats['plaques_moved'] += 1
        return pq

    def labels(self):
        for lab, kind in self.all_labels():
            a = self.cell(*at(lab))
            ang = round(rotation(lab)) % 360
            name = lab.text
            vertical = ang in (90, 270)
            net = self.net_at(a)
            if kind == 'label':         # a name tag lying on its own wire
                anchor = a
                h = 'left' if ang in (0, 90) else 'right'
            else:
                step_ = {0: (1, 0), 180: (-1, 0), 90: (0, -1), 270: (0, 1)}[ang]
                anchor = (a[0] + step_[0], a[1] + step_[1])
                h = 'left' if ang in (0, 90) else 'right'
                if ang == 0 or ang == 180:
                    h = 'left' if step_[0] > 0 else 'right'
                else:
                    h = 'left' if step_[1] < 0 else 'right'
            self.plaque(name, anchor, h, vertical, kind, net=net)

    def fields(self, s):
        if s.get('skip_fields'):
            return
        sym = s['sym']
        nunits = len({u.unit_index for u in s['lib'].units} - {0})
        for pname, prop in s['props'].items():
            if hidden(prop) or not prop.value:
                continue
            txt = prop.value
            if pname == 'Reference':
                if txt.startswith('#'):
                    continue
                if nunits > 1:
                    txt += chr(ord('A') + int(sym.unit or 1) - 1)
            elif pname != 'Value':
                if s['kind'] == 'power':
                    continue
            if prop.show_name:
                txt = f'{pname}: {txt}'
            fx, fy = at(prop)
            fang = rotation(prop)
            h, v = justify(prop)
            vertical = (round(fang) % 180 == 90) != quarter_turned(sym)
            dvec = {'left': 1, 'right': -1, 'center': 0}[h]
            if dvec:
                rd = (math.cos(math.radians(fang)), -math.sin(math.radians(fang)))
                tx_, ty_ = sym.transform_vector(rd[0] * dvec, -rd[1] * dvec)
                if vertical and abs(ty_) > 0.5:
                    h = 'left' if ty_ < 0 else 'right'
                elif not vertical and abs(tx_) > 0.5:
                    h = 'left' if tx_ > 0 else 'right'
            style = s.get('field_style') or ('ref' if pname == 'Reference' else 'value')
            if s['kind'] == 'power' and s['pins']:
                self.power_label(s, txt, self.cell(fx, fy), style)
                continue
            self.plaque(txt, self.cell(fx, fy), h, vertical, style, owner=s['owner'])

    def power_label(self, s, text, want, style):
        """A supply's or ground's name on a plaque right next to its torch or hopper: on whichever side has room
        (nearest to where the schematic put the text first), or on the nearest side when none has."""
        w = self.world
        c = s['pins'][0]['outer']
        net = s['pins'][0]['net']
        wc, hc = self.text_cells(text)
        spots = []
        for k in range(wc):                     # above and below, the torch under any of its cells
            spots += [(c[0] - k, c[1] - hc), (c[0] - k, c[1] + 1)]
        for k in range(hc):                     # left and right
            spots += [(c[0] + 1, c[1] - k), (c[0] - wc, c[1] - k)]

        def cost(sp):
            cx, cy = sp[0] + (wc - 1) / 2, sp[1] + (hc - 1) / 2
            return abs(cx - want[0]) + abs(cy - want[1])

        def clashes(sp):
            n = 0
            for cc in w.plaque_cells(sp[0], sp[1], wc, hc):
                if (not w.inside(cc) or cc in w.solid or w.soft.get(cc) not in (None, s['owner'])
                        or (cc in w.dust and set(w.dust[cc]) != {net})):
                    n += 1
            return n
        spots.sort(key=lambda sp: (clashes(sp) > 0, cost(sp), clashes(sp)))
        i, j = spots[0]
        pq = Plaque(text, i, j, wc, hc, False, style)
        if clashes((i, j)):
            self.stats['plaques_stuck'] += 1
            self.stuck.append((style, text))
        w.plaques.append(pq)
        for cc in w.plaque_cells(i, j, wc, hc):
            w.solid.setdefault(cc, pq)
        w.circuit.update(w.plaque_cells(i, j, wc, hc))

    def free_texts(self):
        for t in self.sch.texts:
            s = t.text.strip()
            if not s:
                continue
            size = font(t)[0]
            scale = max(1, round(size / 1.6))
            h, _ = justify(t)
            vertical = round(rotation(t)) % 180 == 90
            style = 'heading' if scale > 1 else 'note'
            self.plaque(s, self.cell(*at(t)), h, vertical, style, scale=scale, reach=4)

    def no_connects(self):
        w = self.world
        for nc in self.sch.no_connects:
            c = self.cell(*at(nc))
            w.blocks.append(Block(c[0], 0, c[1], 'state', ('cobweb', ()), owner='nc'))
            w.solid[c] = 'nc'
            w.dust.pop(c, None)
            w.circuit.add(c)

    def graphics(self):
        """Lines and boxes drawn on the sheet: paths of polished andesite in the floor."""
        w = self.world
        for g in self.sch.polylines:
            pts = [self.cell(*xy(p)) for p in g.points]
            for a, b in zip(pts, pts[1:]):
                for c in cells_on_segment(a, b):
                    w.floor.setdefault(c, 'polished_andesite')
        for g in self.sch.rectangles:
            (x0, y0), (x1, y1) = self.cell(*xy(g.start)), self.cell(*xy(g.end))
            for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
                for c in cells_on_segment(a, b):
                    w.floor.setdefault(c, 'polished_andesite')


def spiral(r):
    out = [(dx, dz) for dx in range(-r, r + 1) for dz in range(-r, r + 1)]
    out.sort(key=lambda o: (abs(o[0]) + abs(o[1]), abs(o[1]), o))
    return out


def point_in_poly(p, poly):
    x, y = p
    inside = False
    n = len(poly)
    for k in range(n):
        (x1, y1), (x2, y2) = poly[k], poly[(k + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 or 1e-12) + x1:
            inside = not inside
    return inside
