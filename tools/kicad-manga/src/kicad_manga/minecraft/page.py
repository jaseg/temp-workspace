"""Around the circuit: the wooden deck it is built on, the meadow, the page frame, the title block, a legend, and
cherry trees, bushes, flower beds, ponds, little gardens and animals in the empty space. All of it is made of blocks on
the schematic's grid. The frame is drawn flat on top of everything (`overlay`), like a picture frame."""

import math
import random
import re
from pathlib import Path

from ..kicad import paper_size, title_comment
from .world import Block, Plaque

MARGIN_MM = 10              # KiCad's drawing sheet frame
PASTEL_FLOWERS = ['pink_tulip', 'allium', 'azure_bluet', 'oxeye_daisy', 'cornflower', 'lily_of_the_valley',
                  'white_tulip']
GRASS = (132, 196, 92)      # a soft, sunny meadow green instead of the biome colormap's
FOLIAGE = (110, 178, 72)
DIRS4 = (('north', (0, -1)), ('south', (0, 1)), ('east', (1, 0)), ('west', (-1, 0)))

LEGEND = [
    (('state', 'repeater', (('facing', 'west'), ('delay', 2))), 'diode'),
    (('state', 'repeater', (('facing', 'west'), ('delay', 1), ('powered', 'true'))), 'LED'),
    (('state', 'comparator', (('facing', 'west'),)), 'transistor'),
    (('state', 'furnace', (('facing', 'south'), ('lit', 'false'))), 'resistor'),
    (('plates', (1, 0), ('block/gold_block', 'block/polished_deepslate')), 'capacitor (gold: + plate)'),
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
        self.tints = {'grass_block': GRASS, 'short_grass': GRASS, 'tall_grass': GRASS, 'fern': GRASS,
                      'large_fern': GRASS, 'sugar_cane': GRASS, 'pink_petals': GRASS, 'oak_leaves': FOLIAGE,
                      'jungle_leaves': FOLIAGE, 'acacia_leaves': FOLIAGE, 'dark_oak_leaves': FOLIAGE,
                      'mangrove_leaves': FOLIAGE, 'vine': FOLIAGE, 'birch_leaves': (150, 190, 100),
                      'spruce_leaves': (97, 153, 97), 'lily_pad': (60, 150, 60), 'water': (80, 150, 230)}
        self.platform = set()
        self.taken = set()          # cells the page's own structures use
        self.overlay_cells = set()  # the frame's cells, drawn flat on top of everything
        self.height = {}            # cell -> blocks of hill under it
        self.page_mm = None
        self.rng = random.Random(cfg.get('seed', 42))
        PW, PH = builder.paper
        self.paper = (PW, PH)
        W, H = paper_size(sch)
        a = builder.fcell(MARGIN_MM, MARGIN_MM)
        e = builder.fcell(W - MARGIN_MM, H - MARGIN_MM)
        # i0, j0, i1, j1 (exclusive): the cells inside the drawing sheet's frame
        # (cells whose centre lies inside the frame, so that things on the grid at the frame line stay inside)
        self.inner = (math.ceil(a[0] - 1e-6), math.ceil(a[1] - 1e-6),
                      math.floor(e[0] + 1e-6) + 1, math.floor(e[1] + 1e-6) + 1)

    def report(self):
        st = self.b.stats
        return [f'minecraft: {st["nudged"]} parts nudged to fit, {st["unplaced"]} could not be fitted; '
                f'{st["plaques_moved"]} text plaques moved, {st["plaques_stuck"]} overlap something']

    # -------------------------------------------------------------------------
    def build(self):
        self.platform = dilate(self.w.circuit, 1)
        self.frame()
        self.title_block()
        self.legend()
        self.decorate()

    def floor_of(self, c):
        f = self.w.floor.get(c)
        if f:
            return f
        return 'birch_planks' if c in self.platform else 'grass_block'

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

    def put(self, i, y, j, name, props=(), flat=False, overlay=False, absolute=False):
        """A block at height y above the ground of its cell (or at y itself, `absolute`)."""
        if not absolute and not overlay:
            y += self.height.get((i, j), 0)
        flat = flat and y == 0
        self.w.blocks.append(Block(i, y, j, 'state', (name, tuple(props)), flat=flat, owner='page', overlay=overlay))

    def box(self, i, y, j, block, h=16, owner='page'):
        self.w.blocks.append(Block(i, y, j, 'box', (self.b.tex(block, 'up'), self.b.tex(block, 'south'), h, None),
                                   owner=owner))

    def petals(self, c, overlay=False):
        rng = self.rng
        self.put(c[0], 0, c[1], 'pink_petals', [('flower_amount', str(rng.randint(1, 4))),
                                                 ('facing', rng.choice(['north', 'east', 'south', 'west']))],
                 flat=True, overlay=overlay)

    def fence(self, cells, block):
        """A fence along `cells`, each post joined to its neighbours in it."""
        cells = set(cells)
        for (i, j) in cells:
            props = [(d, 'true' if (i + di, j + dj) in cells else 'false') for d, (di, dj) in DIRS4]
            yield i, j, block, props

    def sign(self, text, i, j, style='sign', scale=1, y=0, center=None, width=None, overlay=False):
        """A plaque placed as is (no nudging): top-left at (i, j), or centred on `center`."""
        wc, hc = self.b.text_cells(text, scale)
        wc = max(wc, width or 0)
        if center is not None:
            i, j = center[0] - wc // 2, center[1] - hc // 2
        pq = Plaque(text, i, j, wc, hc, False, style, scale)
        pq.meta['y'] = y
        pq.meta['overlay'] = overlay
        self.w.plaques.append(pq)
        return pq

    # -- the frame ----------------------------------------------------------------------
    def frame(self):
        """A garden path all around the sheet, a flowering hedge with lanterns along its inside, zone signs, petals
        on the path and bushes in the corners. It is drawn flat, on top of everything."""
        W, H = self.paper
        i0, j0, i1, j1 = self.inner
        rng = self.rng
        w = self.w
        # parts of the circuit that were drawn into the margin stay visible: the frame leaves them out
        keep = set(w.circuit)
        for pq in w.plaques:
            keep.update((pq.i + a, pq.j + b) for a in range(pq.w) for b in range(pq.h))
        band = {(i, j) for i in range(max(0, w.i0), min(W, w.W)) for j in range(max(0, w.j0), min(H, w.H))
                if not (i0 <= i < i1 and j0 <= j < j1)} - keep
        for c in band:
            w.floor[c] = 'dirt_path' if rng.random() < .92 else 'coarse_dirt'
        self.overlay_cells |= band
        self.taken |= band
        # the fence along the inside of the path, with lantern posts at the zone boundaries
        nx, ny = self.zones()
        posts = set()
        for k in range(nx + 1):
            x = i0 - 1 + round((i1 - i0 + 1) * k / nx)
            posts.update({(x, j0 - 1), (x, j1)})
        for k in range(ny + 1):
            y = j0 - 1 + round((j1 - j0 + 1) * k / ny)
            posts.update({(i0 - 1, y), (i1, y)})
        ring = set([(i, j0 - 1) for i in range(i0 - 1, i1 + 1)] + [(i, j1) for i in range(i0 - 1, i1 + 1)] +
                   [(i0 - 1, j) for j in range(j0, j1)] + [(i1, j) for j in range(j0, j1)])
        ring -= keep
        for (i, j) in ring:          # a flowering hedge, with lanterns at the zone boundaries
            leaves = 'flowering_azalea_leaves' if rng.random() < .55 else 'azalea_leaves'
            self.put(i, 0, j, leaves, [('persistent', 'true')], overlay=True)
            if (i, j) in posts:
                self.put(i, 1, j, 'lantern', [('hanging', 'false')], overlay=True)
        # zone numbers and letters
        signs = set()
        for k in range(nx):
            c = (round(i0 + (i1 - i0) * (k + .5) / nx), (j0 - 1) // 2)
            for cc in (c, (c[0], j1 + (H - j1) // 2)):
                pq = self.sign(str(k + 1), 0, 0, 'sign', 2, center=cc, overlay=True, width=2)
                signs.update((pq.i + a, pq.j + b) for a in range(pq.w) for b in range(pq.h))
        for k in range(ny):
            c = ((i0 - 1) // 2, round(j0 + (j1 - j0) * (k + .5) / ny))
            for cc in (c, (i1 + (W - i1) // 2, c[1])):
                pq = self.sign(chr(ord('A') + k), 0, 0, 'sign', 2, center=cc, overlay=True, width=2)
                signs.update((pq.i + a, pq.j + b) for a in range(pq.w) for b in range(pq.h))
        # petals on the path, flowering bushes in the corners
        corners = {(i0 - 2, j0 - 2), (i1 + 1, j0 - 2), (i0 - 2, j1 + 1), (i1 + 1, j1 + 1)}
        for c in band:
            if c not in ring and c not in signs and c not in corners and rng.random() < .06:
                self.petals(c, overlay=True)
        for (i, j) in corners:
            self.put(i, 0, j, 'cherry_leaves', [('persistent', 'true')], overlay=True)

    def zones(self):
        """Columns and rows of the sheet's zone grid, about 100 mm each."""
        W, H = paper_size(self.sch)
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
        """A little cherry wood deck in the bottom right corner, with bookshelves, lanterns, a cake and flowers."""
        title, sub, fields = self.title_lines()
        i0, j0, i1, j1 = self.inner
        tc = self.b.text_cells
        scale = 3
        w = min(max(24, tc(title, scale)[0] + 4, tc(fields)[0] + 4, tc(sub)[0] + 4), (i1 - i0) // 2)
        h = 11 if sub else 10
        if w < 6 or h > j1 - j0 - 2:
            return
        spot = self.find_spot(w, h, [(i1 - w - 1, j1 - h - 1)], margin=1)
        if spot is None:            # no room: no title block rather than one on top of the circuit
            return
        x, y = spot

        def fits(text, scale=1):
            return tc(text, scale)[0] <= w - 2
        cells = [(x + a, y + b) for a in range(w) for b in range(h)]
        self.taken.update(cells)
        for (i, j) in cells:
            edge = i in (x, x + w - 1) or j in (y, y + h - 1)
            self.w.floor[(i, j)] = 'stripped_cherry_wood' if edge else 'cherry_planks'
        # bookshelves along the back with potted flowers between them, lanterns in the corners, a cake
        pots = ['potted_pink_tulip', 'potted_azure_bluet', 'potted_allium', 'potted_red_tulip']
        for i in range(x + 2, x + w - 2):
            if (i - x) % 6 != 4:
                self.box(i, 0, y + 1, 'bookshelf', owner='shelf')
            else:
                self.put(i, 0, y + 1, pots[self.rng.randrange(len(pots))])
        for i, j in ((x, y + h - 1), (x + w - 1, y + h - 1), (x, y), (x + w - 1, y)):
            self.put(i, 0, j, 'lantern', [('hanging', 'false')])
        note = 'built from redstone'
        if tc(note)[0] <= w - 6:
            self.put(x + 1, 0, y + h - 2, 'cake')
            self.put(x + w - 2, 0, y + h - 2, 'potted_flowering_azalea_bush')
        while scale > 1 and tc(title, scale)[0] > w - 4:
            scale -= 1
        row = y + 3
        if fits(title, scale):
            self.sign(title, 0, 0, 'title', scale, center=(x + w // 2, row + 1))
        row += 4
        if sub and fits(sub):
            self.sign(sub, 0, 0, 'value', 1, center=(x + w // 2, row))
            row += 1
        if fits(fields):
            self.sign(fields, 0, 0, 'ref', 1, center=(x + w // 2, row))
        if fits(note):
            self.sign(note, 0, 0, 'note', 1, center=(x + w // 2, y + h - 2))

    def find_spot(self, w, h, prefer, margin=2, step=2):
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
        rows = list(LEGEND)
        w = 3 + max(self.b.text_cells(t)[0] for _, t in rows) + 1
        h = len(rows) + 3
        i0, j0, i1, j1 = self.inner
        spot = self.find_spot(w, h, [(i0 + 1, j1 - h - 1)], margin=1)
        if spot is None:
            return
        x, y = spot
        cells = [(x + a, y + b) for a in range(w) for b in range(h)]
        self.taken.update(cells)
        for (i, j) in cells:
            edge = i in (x, x + w - 1) or j in (y, y + h - 1)
            self.w.floor[(i, j)] = 'stripped_birch_wood' if edge else 'smooth_sandstone'
        self.sign('legend', 0, 0, 'sign', 1, center=(x + w // 2, y + 1))
        for k, (spec, text) in enumerate(rows):
            j = y + 2 + k
            if spec[0] == 'box':
                self.box(x + 1, 0, j, spec[1], h=8, owner=f'legend{k}')
            elif spec[0] == 'plates':
                self.w.blocks.append(Block(x + 1, 0, j, 'plates', (spec[1], spec[2]), owner='page'))
            else:
                flat = spec[1] == 'rail'
                self.put(x + 1, 0, j, spec[1], spec[2], flat=flat)
            self.sign(text, x + 3, j, 'label')

    # -- decorations in the empty space ----------------------------------------------------------
    def decorate(self):
        free = [(i, j) for i in range(self.w.i0, self.w.W) for j in range(self.w.j0, self.w.H)
                if self.in_frame((i, j)) and not self.blocked((i, j))]
        self.ponds(free)
        self.gardens(free)
        self.terrain(free)
        self.trees(free)
        self.bushes(free)
        self.props(free)
        self.flowers(free)
        self.animals(free)

    def blocked(self, c):
        return c in self.platform or c in self.taken or c in self.w.solid or not self.in_frame(c)

    def ponds(self, free):
        rng = self.rng
        n = max(1, len(free) // 8000)
        fs = set(free)
        made = 0
        for _ in range(n * 20):
            if made >= n:
                break
            c = rng.choice(free)
            r = rng.randint(3, 5)
            cells = [(c[0] + a, c[1] + b) for a in range(-r - 1, r + 2) for b in range(-r - 1, r + 2)
                     if (a / (r + 1)) ** 2 + (b / (r * .7 + 1)) ** 2 <= 1]
            if not all(x in fs and not self.blocked(x) for x in cells):
                continue
            made += 1
            for x in cells:
                a, b = x[0] - c[0], x[1] - c[1]
                wet = (a / r) ** 2 + (b / (r * .7)) ** 2 <= 1
                self.w.floor[x] = 'water' if wet else 'moss_block'
                self.taken.add(x)
                if wet and rng.random() < .12:
                    self.put(x[0], 0, x[1], 'lily_pad', flat=True)
                elif not wet and rng.random() < .3:
                    self.put(x[0], 0, x[1], rng.choice(['sugar_cane', 'pink_tulip', 'oxeye_daisy', 'fern']))

    def terrain(self, free):
        """Gentle grassy hills in the open meadow, away from the circuit."""
        rng = self.rng
        fs = {c for c in free if not self.blocked(c)}
        # how far each free cell is from anything else (circuit, frame, ponds, ...), up to 8
        dist = {}
        edge = [c for c in fs if any((c[0] + a, c[1] + b) not in fs for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1)))]
        for c in edge:
            dist[c] = 1
        todo = list(edge)
        while todo:
            nxt = []
            for (i, j) in todo:
                for n in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                    if n in fs and n not in dist and dist[(i, j)] < 8:
                        dist[n] = dist[(i, j)] + 1
                        nxt.append(n)
            todo = nxt
        lift = {}
        cand = [c for c in fs if dist.get(c, 9) >= 5]
        for _ in range(len(fs) // 900):
            if not cand:
                break
            (ci, cj), A, r = rng.choice(cand), rng.uniform(1.6, 3.6), rng.uniform(3, 8)
            R = int(r * 2.2)
            for a in range(-R, R + 1):
                for b in range(-R, R + 1):
                    c = (ci + a, cj + b)
                    if c in fs:
                        lift[c] = lift.get(c, 0) + A * math.exp(-(a * a + b * b) / (r * r))
        for c, v in lift.items():
            h = int(min(v, (dist.get(c, 9) - 2) / 1.5, 4))
            if h > 0:
                self.height[c] = h
        H = self.height
        for (i, j), h in H.items():
            for y in range(h):
                # only the blocks that show: the top one, and those with an open south or east side
                if y == h - 1 or H.get((i, j + 1), 0) <= y or H.get((i + 1, j), 0) <= y:
                    self.w.blocks.append(Block(i, y, j, 'state', ('grass_block', (('snowy', 'false'),)),
                                               owner='hill'))

    def gardens(self, free):
        """Little vegetable plots: rows of crops on farmland with a fence around them."""
        rng = self.rng
        n = max(1, len(free) // 12000)
        made = 0
        for _ in range(n * 30):
            if made >= n:
                break
            i, j = rng.choice(free)
            w, h = rng.randint(5, 8), rng.randint(4, 6)
            cells = [(i + a, j + b) for a in range(w) for b in range(h)]
            if not self.free(cells, 1):
                continue
            made += 1
            self.taken.update(cells)
            crops = [('wheat', 7), ('carrots', 7), ('potatoes', 7), ('beetroots', 3)]
            for b in range(1, h - 1):
                crop, age = rng.choice(crops)
                for a in range(1, w - 1):
                    self.w.floor[(i + a, j + b)] = 'farmland'
                    self.put(i + a, 0, j + b, crop, [('age', str(age))])
            edge = [(ci, cj) for ci, cj in cells if ci in (i, i + w - 1) or cj in (j, j + h - 1)]
            for ci, cj, block, props in self.fence(edge, 'spruce_fence'):
                self.put(ci, 0, cj, block, props)

    def trees(self, free):
        rng = self.rng
        n = len(free) // 600
        placed = []
        for _ in range(n * 6):
            if len(placed) >= n:
                break
            i, j = rng.choice(free)
            if any(abs(i - a) + abs(j - b) < 7 for a, b in placed):
                continue
            if not self.free([(i, j)], 3):
                continue
            placed.append((i, j))
            kind = rng.choice(['cherry', 'cherry', 'oak', 'oak', 'birch'])
            self.tree(i, j, kind, rng.randint(5, 7) if kind == 'cherry' else rng.randint(4, 6))

    def tree(self, i, j, kind, hgt):
        """A tree grown the way the game grows it: a trunk `hgt` tall with the canopy at its top. Oak and birch get
        two wide layers and two narrow ones (the top one a plus), the corners left out at random; cherry trees
        a wide, flat crown with leaves hanging from its rim."""
        rng = self.rng
        log, leaves = f'{kind}_log', f'{kind}_leaves'
        cells = set()
        base = self.height.get((i, j), 0)
        top = base + hgt                    # the trunk's last block is top - 1
        if kind == 'cherry':
            top -= 1
            layers = [(top - 1, 3, 4), (top, 2, 3), (top + 1, 1, 1)]
        else:
            layers = [(top - 3, 2, None), (top - 2, 2, None), (top - 1, 1, None), (top, 1, 1)]
        for y in range(base, top):
            self.put(i, y, j, log, [('axis', 'y')], absolute=True)
        leaf = set()
        for y, r, manhattan in layers:
            for a in range(-r, r + 1):
                for b in range(-r, r + 1):
                    if manhattan is not None and abs(a) + abs(b) > manhattan:
                        continue
                    if manhattan is None and abs(a) == r and abs(b) == r and (y == top or rng.random() < .5):
                        continue
                    if a == 0 and b == 0 and y < top:
                        continue            # the trunk
                    leaf.add((i + a, y, j + b))
        if kind == 'cherry':                # leaves hanging down from the rim of the crown
            y0 = top - 1
            for (x, y, z) in list(leaf):
                if y == y0 and abs(x - i) + abs(z - j) >= 3 and rng.random() < .4:
                    leaf.add((x, y - 1, z))
        for (x, y, z) in sorted(leaf, key=lambda t: (t[2], t[1], t[0])):
            self.put(x, y, z, leaves, [('persistent', 'true')], absolute=True)
            cells.add((x, z))
        self.taken.update(cells | {(i, j)})
        # fallen petals under cherry trees, and now and then a mushroom in the shade
        for a in range(-3, 4):
            for b in range(-3, 4):
                c = (i + a, j + b)
                if not self.free([c]):
                    continue
                if kind == 'cherry' and rng.random() < .35:
                    self.petals(c)
                    self.taken.add(c)
                elif rng.random() < .03:
                    self.put(c[0], 0, c[1], rng.choice(['red_mushroom', 'brown_mushroom']))
                    self.taken.add(c)

    def bushes(self, free):
        rng = self.rng
        n = len(free) // 500
        for _ in range(n * 4):
            if n <= 0:
                break
            i, j = rng.choice(free)
            cells = [(i, j), (i + 1, j)] if rng.random() < .5 else [(i, j)]
            if not self.free(cells, 1):
                continue
            for c in cells:
                self.put(c[0], 0, c[1], rng.choice(['azalea_leaves', 'flowering_azalea_leaves',
                                                    'flowering_azalea_leaves']), [('persistent', 'true')])
            self.taken.update(cells)
            n -= 1

    def animals(self, free):
        """Herds of pigs, sheep and chickens on the meadow, and the odd enderman (one of them carrying off a
        resistor)."""
        rng = self.rng
        herds = ['pig', 'pig_warm', 'pig_cold', 'sheep', 'sheep', 'chicken', 'chicken_warm']
        n = max(1, len(free) // 1100)
        for _ in range(n * 4):
            if n <= 0:
                break
            i, j = rng.choice(free)
            if not self.free([(i, j)], 2):
                continue
            kind = rng.choice(herds)
            k = rng.randint(2, 4)
            for _ in range(k * 4):
                if k <= 0:
                    break
                c = (i + rng.randint(-3, 3), j + rng.randint(-2, 2))
                if self.free([c], 1) and self.w.floor.get(c) is None:
                    self.mob(c, kind)
                    k -= 1
            n -= 1
        endermen = 2 if len(free) > 3000 else 1
        for e in range(endermen * 30):
            if endermen <= 0:
                break
            c = rng.choice(free)
            if self.free([c], 1):
                self.mob(c, 'enderman' if endermen == 1 or rng.random() < .3 else 'enderman_empty')
                endermen -= 1

    def mob(self, c, species):
        self.w.blocks.append(Block(c[0], self.height.get(c, 0), c[1], 'mob',
                                   (species, self.rng.choice((0, 90, 180, 270))), owner='page'))
        self.taken.add(c)

    def props(self, free):
        rng = self.rng
        things = [('pumpkin', ()), ('hay_block', (('axis', 'y'),)), ('melon', ()), ('barrel', (('facing', 'up'),)),
                  ('beehive', (('facing', 'south'),)), ('bee_nest', (('facing', 'south'),)),
                  ('composter', ()), ('lantern', (('hanging', 'false'),)), ('sweet_berry_bush', (('age', '3'),)),
                  ('campfire', (('lit', 'true'), ('facing', 'south'))), ('moss_block', ())]
        n = len(free) // 900
        for _ in range(n * 4):
            if n <= 0:
                break
            i, j = rng.choice(free)
            if not self.free([(i, j)], 1):
                continue
            name, props = rng.choice(things)
            self.put(i, 0, j, name, props)
            self.taken.add((i, j))
            n -= 1

    def flowers(self, free):
        """Grass all over the meadow, some of it tall, and flowers in patches of one kind each, as the game
        scatters them."""
        rng = self.rng
        patches = [(rng.choice(free), rng.choice(PASTEL_FLOWERS + ['dandelion', 'poppy']), rng.uniform(2, 3.5))
                   for _ in range(len(free) // 250)]
        near = {}
        for (pi, pj), fl, r in patches:
            R = int(r) + 1
            for a in range(-R, R + 1):
                for b in range(-R, R + 1):
                    if a * a + b * b <= r * r:
                        near.setdefault((pi + a, pj + b), fl)
        for (i, j) in free:
            if (i, j) in self.taken or (i, j) in self.w.solid:
                continue
            x = rng.random()
            if (i, j) in near and x < .35:
                self.put(i, 0, j, near[(i, j)])
            elif x < .14:
                if rng.random() < .12 and self.free([(i, j)]):
                    self.put(i, 0, j, 'tall_grass', [('half', 'lower')])
                    self.put(i, 1, j, 'tall_grass', [('half', 'upper')])
                else:
                    self.put(i, 0, j, rng.choice(['short_grass'] * 6 + ['fern']))


def dilate(cells, r):
    out = set(cells)
    for _ in range(r):
        nxt = set(out)
        for (i, j) in out:
            nxt.update(((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)))
        out = nxt
    return out
