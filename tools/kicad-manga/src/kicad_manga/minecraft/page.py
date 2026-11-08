"""Around the circuit: the stone platform it is built on, the meadow, the page border, the title block, a legend,
and trees, flowers and ponds in the empty space. All of it is made of blocks on the schematic's grid, and nothing
tall stands where it would hide part of the circuit."""

import random
import re
from pathlib import Path

from PIL import Image

from ..kicad import title_comment
from ..svg import tag
from .iso import PIXELATED, png_uri, proj
from .world import Block, Plaque

MARGIN_MM = 10              # KiCad's drawing sheet frame
FLOWERS = ['poppy', 'dandelion', 'cornflower', 'oxeye_daisy', 'azure_bluet', 'allium', 'red_tulip', 'orange_tulip',
           'pink_tulip', 'white_tulip', 'lily_of_the_valley', 'blue_orchid']

LEGEND = [
    (('state', 'repeater', (('facing', 'west'), ('delay', 2))), 'diode'),
    (('state', 'repeater', (('facing', 'west'), ('delay', 1), ('powered', 'true'))), 'LED'),
    (('state', 'comparator', (('facing', 'west'),)), 'transistor'),
    (('box', 'bricks'), 'resistor'),
    (('state', 'heavy_weighted_pressure_plate', ()), 'capacitor (gold: + plate)'),
    (('box', 'cut_copper'), 'inductor'),
    (('box', 'oxidized_cut_copper'), 'ferrite bead'),
    (('state', 'redstone_torch', (('lit', 'true'),)), 'supply'),
    (('state', 'hopper', (('facing', 'down'),)), 'ground'),
    (('state', 'cobweb', ()), 'not connected'),
    (('state', 'rail', (('shape', 'east_west'),)), 'bus'),
]


class Page:
    def __init__(self, world, builder, sch, path, cfg, pack, font):
        self.w, self.b, self.sch, self.path, self.cfg, self.pack, self.font = world, builder, sch, path, cfg, pack, font
        grass, foliage = pack.colormap('grass'), pack.colormap('foliage')
        self.tints = {'grass_block': grass, 'short_grass': grass, 'tall_grass': grass, 'fern': grass,
                      'large_fern': grass, 'oak_leaves': foliage, 'jungle_leaves': foliage,
                      'acacia_leaves': foliage, 'dark_oak_leaves': foliage, 'mangrove_leaves': foliage,
                      'vine': foliage, 'birch_leaves': (128, 167, 85), 'spruce_leaves': (97, 153, 97),
                      'lily_pad': (32, 128, 48), 'water': (63, 118, 228)}
        self.extra_tall = []
        self.platform = set()
        self.taken = set()          # cells the page's own structures use
        self.page_mm = None
        self.rng = random.Random(cfg.get('seed', 42))
        m = round(MARGIN_MM / builder.b)
        PW, PH = builder.paper
        self.paper = (PW, PH)
        self.inner = (m, m, PW - m, PH - m)      # i0, j0, i1, j1 (exclusive)

    def report(self):
        st = self.b.stats
        return [f'minecraft: {st["nudged"]} parts nudged to fit, {st["unplaced"]} could not be fitted; '
                f'{st["plaques_moved"]} text plaques moved, {st["plaques_stuck"]} overlap something']

    # -------------------------------------------------------------------------
    def build(self):
        self.platform = dilate(self.w.circuit, 2)
        self.frame()
        self.title_block()
        self.legend()
        self.decorate()

    def floor_of(self, c):
        f = self.w.floor.get(c)
        if f:
            return f
        return 'smooth_stone' if c in self.platform else 'grass_block'

    def free(self, cells, margin=0):
        """Whether cells (and `margin` cells around them) are clear of the circuit and of the page's things."""
        for (i, j) in cells:
            for a in range(-margin, margin + 1):
                for b in range(-margin, margin + 1):
                    c = (i + a, j + b)
                    if c in self.platform or c in self.taken or c in self.w.solid or not self.in_frame(c):
                        return False
        return True

    def in_frame(self, c):
        """Inside the border, or in the world beyond the sheet (where parts placed off the sheet are)."""
        i0, j0, i1, j1 = self.inner
        if i0 <= c[0] < i1 and j0 <= c[1] < j1:
            return True
        PW, PH = self.paper
        w = self.w
        on_sheet = 0 <= c[0] < PW and 0 <= c[1] < PH
        return not on_sheet and w.i0 + 2 <= c[0] < w.W - 2 and w.j0 + 2 <= c[1] < w.H - 2

    def put(self, i, y, j, name, props=(), flat=False):
        self.w.blocks.append(Block(i, y, j, 'state', (name, tuple(props)), flat=flat, owner='page'))

    def box(self, i, y, j, block, h=16, owner='page'):
        self.w.blocks.append(Block(i, y, j, 'box', (self.b.tex(block, 'up'), self.b.tex(block, 'south'), h, None),
                                   owner=owner))

    def sign(self, text, i, j, style='sign', scale=1, y=0, center=None, width=None):
        """A plaque placed as is (no nudging): top-left at (i, j), or centred on `center`."""
        wc, hc = self.b.text_cells(text, scale)
        wc = max(wc, width or 0)
        if center is not None:
            i, j = center[0] - wc // 2, center[1] - hc // 2
        pq = Plaque(text, i, j, wc, hc, False, style, scale)
        pq.meta['y'] = y
        self.w.plaques.append(pq)
        return pq

    # -- the border -------------------------------------------------------------------
    def frame(self):
        W, H = self.paper
        i0, j0, i1, j1 = self.inner
        rng = self.rng
        bricks = ['stone_bricks'] * 6 + ['mossy_stone_bricks', 'cracked_stone_bricks']
        for i in range(W):
            for j in range(H):
                if not (i0 <= i < i1 and j0 <= j < j1):
                    self.w.floor[(i, j)] = rng.choice(bricks)
                    self.taken.add((i, j))
        # a low wall along the inside of the border, with lantern posts at the zone boundaries
        nx, ny = self.zones()
        posts = set()
        for k in range(nx + 1):
            x = i0 - 1 + round((i1 - i0 + 1) * k / nx)
            posts.update({(x, j0 - 1), (x, j1)})
        for k in range(ny + 1):
            y = j0 - 1 + round((j1 - j0 + 1) * k / ny)
            posts.update({(i0 - 1, y), (i1, y)})
        ring = [(i, j0 - 1) for i in range(i0 - 1, i1 + 1)] + [(i, j1) for i in range(i0 - 1, i1 + 1)] + \
               [(i0 - 1, j) for j in range(j0, j1)] + [(i1, j) for j in range(j0, j1)]
        ring = set(ring)
        for (i, j) in ring:
            nb = {d: (n in ring) for d, n in (('north', (i, j - 1)), ('south', (i, j + 1)),
                                               ('east', (i + 1, j)), ('west', (i - 1, j)))}
            post = (i, j) in posts
            props = [(d, 'low' if v else 'none') for d, v in nb.items()] + [('up', 'true' if post else 'false')]
            self.put(i, 0, j, 'stone_brick_wall', props)
            if post:
                self.put(i, 1, j, 'lantern', [('hanging', 'false')])
        # zone numbers and letters in the border
        for k in range(nx):
            c = (round(i0 + (i1 - i0) * (k + .5) / nx), (j0 - 1) // 2)
            self.sign(str(k + 1), 0, 0, 'sign', 2, center=c)
            self.sign(str(k + 1), 0, 0, 'sign', 2, center=(c[0], j1 + (H - j1) // 2))
        for k in range(ny):
            c = ((i0 - 1) // 2, round(j0 + (j1 - j0) * (k + .5) / ny))
            self.sign(chr(ord('A') + k), 0, 0, 'sign', 2, center=c)
            self.sign(chr(ord('A') + k), 0, 0, 'sign', 2, center=(i1 + (W - i1) // 2, c[1]))
        # corner towers
        for (i, j) in ((i0 - 4, j0 - 4), (i1 + 3, j0 - 4), (i0 - 4, j1 + 3), (i1 + 3, j1 + 3)):
            for y in range(3):
                self.box(i, y, j, 'chiseled_stone_bricks')
            self.put(i, 3, j, 'lantern', [('hanging', 'false')])

    def zones(self):
        """Columns and rows of the sheet's zone grid, about 50 mm each like KiCad's."""
        W, H = self.paper[0] * self.b.b, self.paper[1] * self.b.b
        return max(1, round((W - 2 * MARGIN_MM) / 100)), max(1, round((H - 2 * MARGIN_MM) / 100))

    # -- the title block ------------------------------------------------------------------
    def title_lines(self):
        tb = self.sch.title_block
        t = self.cfg.get('title', {})
        stem = re.sub(r'^[0-9a-f]{8}-', '', Path(self.path).stem)
        title = t.get('title') or (tb.title if tb is not None else '') or stem
        sub = t.get('subtitle') or title_comment(tb, 1)
        pages = [p.page for p in self.sch.sheet_instances]
        p = self.sch.page_settings
        paper = f'{p.width:g}x{p.height:g} mm' if p.page_format == 'User' and p.width else str(p.page_format)
        fields = [f'sheet {pages[0]}' if pages and pages[0] else '',
                  f'rev {tb.rev}' if tb is not None and tb.rev else '',
                  tb.date if tb is not None else '', tb.company if tb is not None else '', f'paper {paper}']
        return title, sub, ' - '.join(x for x in fields if x)

    def title_block(self):
        title, sub, fields = self.title_lines()
        i0, j0, i1, j1 = self.inner
        tw = self.b.text_cells(title, 3)[0]
        w = min(max(48, tw + 8, self.b.text_cells(fields)[0] + 6, self.b.text_cells(sub, 2)[0] + 6),
                (i1 - i0) // 2)
        h = 18 if sub else 14
        spot = self.find_spot(w, h, [(i1 - w - 1, j1 - h - 1)], margin=2)
        if spot is None:
            spot = (i1 - w - 1, j1 - h - 1)
        x, y = spot
        cells = [(x + a, y + b) for a in range(w) for b in range(h)]
        self.taken.update(cells)
        for (i, j) in cells:
            edge = i in (x, x + w - 1) or j in (y, y + h - 1)
            self.box(i, 0, j, 'stripped_dark_oak_log' if edge else 'dark_oak_planks', owner='title')
        # a row of bookshelves along the back, lanterns on the front corners
        for i in range(x + 1, x + w - 1):
            if (i - x) % 9 in (4, 5):
                continue
            self.box(i, 1, y + 1, 'bookshelf', owner='shelf')
        for i, j in ((x, y + h - 1), (x + w - 1, y + h - 1), (x, y), (x + w - 1, y)):
            self.put(i, 1, j, 'lantern', [('hanging', 'false')])
        self.put(x + 2, 1, y + h - 3, 'lectern', [('facing', 'south')])
        self.put(x + w - 3, 1, y + h - 3, 'crafting_table')
        scale = 3 if tw <= w - 6 else 2
        cy = y + 4 + (3 if scale == 3 else 2) // 2
        self.sign(title, 0, 0, 'title', scale, y=1, center=(x + w // 2, cy))
        row = cy + 3
        if sub:
            self.sign(sub, 0, 0, 'value', 2 if self.b.text_cells(sub, 2)[0] <= w - 6 else 1, y=1,
                      center=(x + w // 2, row + 1))
            row += 3
        self.sign(fields, 0, 0, 'ref', 1, y=1, center=(x + w // 2, row + 1))
        self.sign('built from redstone', 0, 0, 'note', 1, y=1, center=(x + w // 2, y + h - 2))

    def find_spot(self, w, h, prefer, margin=2, step=4):
        """Where a w x h block of cells fits inside the frame, clear of everything: the preferred spots first, then
        the nearest spot to the first of them."""
        i0, j0, i1, j1 = self.inner
        for (x, y) in prefer:
            if self.free([(x + a, y + b) for a in range(w) for b in range(h)], margin):
                return x, y
        px, py = prefer[0]
        cands = [(x, y) for x in range(i0 + 1, i1 - w, step) for y in range(j0 + 1, j1 - h, step)]
        cands.sort(key=lambda c: abs(c[0] - px) + abs(c[1] - py))
        for (x, y) in cands:
            if self.free([(x + a, y + b) for a in range(w) for b in range(h)], margin):
                return x, y
        return None

    # -- the legend ---------------------------------------------------------------------------
    def legend(self):
        rows = [(spec, text) for spec, text in LEGEND]
        w = 4 + max(self.b.text_cells(t)[0] for _, t in rows) + 2
        h = 2 * len(rows) + 5
        i0, j0, i1, j1 = self.inner
        spot = self.find_spot(w, h, [(i0 + 2, j1 - h - 2)], margin=2)
        if spot is None:
            return
        x, y = spot
        cells = [(x + a, y + b) for a in range(w) for b in range(h)]
        self.taken.update(cells)
        for c in cells:
            self.w.floor[c] = 'polished_andesite'
        self.sign('LEGEND', 0, 0, 'sign', 2, center=(x + w // 2, y + 2))
        for k, (spec, text) in enumerate(rows):
            j = y + 5 + 2 * k
            if spec[0] == 'box':
                self.box(x + 2, 0, j, spec[1], h=8, owner=f'legend{k}')
            else:
                flat = spec[1] in ('heavy_weighted_pressure_plate', 'rail')
                self.put(x + 2, 0, j, spec[1], spec[2], flat=flat)
            self.sign(text, x + 4, j, 'label')

    # -- decorations in the empty space ----------------------------------------------------------
    def decorate(self):
        rng = self.rng
        free = [(i, j) for i in range(self.w.i0, self.w.W) for j in range(self.w.j0, self.w.H)
                if self.in_frame((i, j)) and (i, j) not in self.platform and (i, j) not in self.taken and (i, j) not in self.w.solid]
        self.ponds(free)
        self.trees(free)
        self.props(free)
        self.flowers(free)

    def blocked(self, c):
        return c in self.platform or c in self.taken or c in self.w.solid or not self.in_frame(c)

    def clear_behind(self, i, j, height, r=1):
        """Whether something `height` blocks tall and r cells wide at (i, j) leaves the circuit in view: the cells
        it covers on screen (those behind it) must not be part of the circuit."""
        for a in range(-r - 1, r + 2):
            for b in range(-r - 1, r + 2):
                for t in range(0, int(height) + 2):
                    c = (i + a - t, j + b - t)
                    if c in self.platform or c in self.taken or not self.in_frame(c):
                        return False
        return True

    def ponds(self, free):
        rng = self.rng
        area = len(free)
        n = max(1, area // 30000)
        fs = set(free)
        made = 0
        for _ in range(n * 20):
            if made >= n:
                break
            c = rng.choice(free)
            r = rng.randint(4, 8)
            cells = [(c[0] + a, c[1] + b) for a in range(-r - 2, r + 3) for b in range(-r - 2, r + 3)
                     if (a / (r + 2)) ** 2 + (b / (r * .7 + 2)) ** 2 <= 1]
            if not all(x in fs and not self.blocked(x) for x in cells):
                continue
            made += 1
            for x in cells:
                a, b = x[0] - c[0], x[1] - c[1]
                wet = (a / r) ** 2 + (b / (r * .7)) ** 2 <= 1
                self.w.floor[x] = 'water' if wet else 'sand'
                self.taken.add(x)
                if wet and rng.random() < .06:
                    self.put(x[0], 0, x[1], 'lily_pad', flat=True)
                elif not wet and rng.random() < .15:
                    self.put(x[0], 0, x[1], 'sugar_cane')

    def trees(self, free):
        rng = self.rng
        n = len(free) // 900
        placed = []
        for _ in range(n * 6):
            if len(placed) >= n:
                break
            i, j = rng.choice(free)
            if any(abs(i - a) + abs(j - b) < 9 for a, b in placed):
                continue
            kind = rng.choice(['oak', 'oak', 'birch', 'spruce'])
            hgt = rng.randint(4, 6)
            if not self.free([(i, j)], 3) or not self.clear_behind(i, j, hgt + 2, 2):
                continue
            placed.append((i, j))
            self.tree(i, j, kind, hgt)

    def tree(self, i, j, kind, hgt):
        rng = self.rng
        log, leaves = f'{kind}_log', f'{kind}_leaves'
        cells = set()
        for y in range(hgt):
            self.put(i, y, j, log, [('axis', 'y')])
        if kind == 'spruce':
            layers = [(hgt - 3, 2), (hgt - 2, 1), (hgt - 1, 2), (hgt, 1), (hgt + 1, 0)]
        else:
            layers = [(hgt - 3, 2), (hgt - 2, 2), (hgt - 1, 1), (hgt, 1)]
        for y, r in layers:
            for a in range(-r, r + 1):
                for b in range(-r, r + 1):
                    if r and abs(a) == r and abs(b) == r and rng.random() < .6:
                        continue
                    if a == 0 and b == 0 and y < hgt:
                        continue
                    self.put(i + a, y, j + b, leaves, [('persistent', 'true')])
                    cells.add((i + a, j + b))
        self.taken.update(cells | {(i, j)})

    def props(self, free):
        rng = self.rng
        things = [('pumpkin', ()), ('hay_block', (('axis', 'y'),)), ('melon', ()), ('barrel', (('facing', 'up'),)),
                  ('mossy_cobblestone', ()), ('campfire', (('lit', 'true'), ('facing', 'south'))),
                  ('composter', ()), ('beehive', (('facing', 'south'),))]
        n = len(free) // 1500
        for _ in range(n * 4):
            if n <= 0:
                break
            i, j = rng.choice(free)
            if not self.free([(i, j)], 1) or not self.clear_behind(i, j, 1, 0):
                continue
            name, props = rng.choice(things)
            self.put(i, 0, j, name, props)
            self.taken.add((i, j))
            n -= 1

    def flowers(self, free):
        rng = self.rng
        patches = [(rng.choice(free), rng.choice(FLOWERS), rng.uniform(3, 7)) for _ in range(len(free) // 400)]
        for (i, j) in free:
            if (i, j) in self.taken or (i, j) in self.w.solid:
                continue
            p = .03
            plant = 'short_grass'
            for (pi, pj), fl, r in patches:
                d = abs(i - pi) + abs(j - pj)
                if d < r:
                    p, plant = .35 * (1 - d / r) + .03, fl
                    break
            if rng.random() >= p:
                continue
            if plant == 'short_grass' and rng.random() < .25:
                plant = rng.choice(['fern', 'short_grass', 'dandelion', 'poppy'])
            if not self.clear_behind(i, j, 1, 0):
                continue
            self.put(i, 0, j, plant)

    # -- the sky ------------------------------------------------------------------------------------
    def sky(self):
        """A sky gradient and a few clouds from the pack's cloud texture in the corners of the page."""
        defs = [tag('linearGradient', [tag('stop', offset=0, stop_color='#7fb2ff'),
                                       tag('stop', offset=1, stop_color='#cfe4ff')],
                    id='sky', x1=0, y1=0, x2=0, y2=1)]
        clouds = []
        data = self.pack.asset('textures', 'environment/clouds', '.png')
        if data is not None:
            import io
            img = Image.open(io.BytesIO(data)).convert('RGBA')
            i0, j0, W, H = self.w.i0, self.w.j0, self.w.W, self.w.H
            left, top = proj(i0 - .5, 0, H - .5)[0], proj(i0 - .5, 0, j0 - .5)[1]
            right = proj(W - .5, 0, j0 - .5)[0]
            bottom = proj(W - .5, 0, H - .5)[1]
            rng = self.rng
            for k in range(8):
                for _ in range(30):
                    cw, ch = rng.randint(12, 28), rng.randint(6, 12)
                    sx, sy = rng.randint(0, 255 - cw), rng.randint(0, 255 - ch)
                    crop = img.crop((sx, sy, sx + cw, sy + ch))
                    if crop.getbbox() is None:
                        continue
                    scale = rng.uniform(40, 70)
                    gw, gh = cw * scale, ch * scale * .5
                    x = rng.uniform(left - gw / 2, right - gw / 2)
                    y = rng.uniform(top - 6 * 16, bottom)
                    if self.over_island(x, y, gw, gh):
                        continue
                    white = Image.new('RGBA', crop.size, (255, 255, 255, 0))
                    white.putalpha(crop.getchannel('A').point(lambda v: 230 if v else 0))
                    clouds.append(tag('image', x=x, y=y, width=gw, height=gh, preserveAspectRatio='none',
                                      style=PIXELATED, href=png_uri(white)))
                    break
        return {'fill': 'url(#sky)', 'defs': defs, 'background': clouds}

    def over_island(self, x, y, w, h):
        i0, j0, W, H = self.w.i0, self.w.j0, self.w.W, self.w.H
        poly = [proj(i0 - .5, 0, j0 - .5), proj(W - .5, 0, j0 - .5), proj(W - .5, 0, H - .5), proj(i0 - .5, 0, H - .5)]
        for px in (x - 16 * 4, x + w / 2, x + w + 16 * 4):
            for py in (y - 16 * 4, y + h / 2, y + h + 16 * 4):
                if inside(px, py, poly):
                    return True
        # the island's edges crossing the cloud
        cx, cy = x + w / 2, y + h / 2
        return inside(cx, cy, poly)


def inside(x, y, poly):
    res = False
    n = len(poly)
    for k in range(n):
        (x1, y1), (x2, y2) = poly[k], poly[(k + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            res = not res
    return res


def dilate(cells, r):
    out = set(cells)
    for _ in range(r):
        nxt = set(out)
        for (i, j) in out:
            nxt.update(((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)))
        out = nxt
    return out

