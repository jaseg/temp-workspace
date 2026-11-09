"""ICs as buildings: small and medium ICs become timber houses with gable roofs, large ones castles with corner
towers, a gate and a keep in the courtyard.

A building stands on a low plinth that covers the whole body. Its walls keep clear of the plinth's edges where
the pin names are painted, and of the strip to the north and west that it leans over when seen from the camera
(`lean`), so it hides nothing outside its own body. Every block is a plain block state of the resource pack."""

import math

from .world import Block

# (pillar log, wall planks, door wood, roof material, plinth)
HOUSES = [
    ('oak_log', 'oak_planks', 'oak', 'brick', 'cobblestone'),
    ('spruce_log', 'spruce_planks', 'spruce', 'dark_oak', 'stone_bricks'),
    ('dark_oak_log', 'birch_planks', 'birch', 'deepslate_tile', 'cobblestone'),
    ('cherry_log', 'cherry_planks', 'cherry', 'dark_oak', 'mossy_cobblestone'),
    ('stripped_spruce_log', 'mud_bricks', 'spruce', 'mangrove', 'packed_mud'),
    ('birch_log', 'oak_planks', 'oak', 'spruce', 'stone_bricks'),
]

ROOFS = {    # material -> (stairs, slab, full block)
    'brick': ('brick_stairs', 'brick_slab', 'bricks'),
    'deepslate_tile': ('deepslate_tile_stairs', 'deepslate_tile_slab', 'deepslate_tiles'),
    'mud_brick': ('mud_brick_stairs', 'mud_brick_slab', 'mud_bricks'),
}

SMALL, LARGE = 40, 200          # body area (cells) up to which an IC is a small house, above which a castle
PLINTH_H = 2                    # 16ths of a block


def roof_blocks(m):
    return ROOFS.get(m) or (f'{m}_stairs', f'{m}_slab', f'{m}_planks')


def size_class(area):
    return 'small' if area <= SMALL else 'medium' if area <= LARGE else 'large'


class Site:
    """Blocks of one building, collected for one owner."""

    def __init__(self, owner, seed):
        self.owner = owner
        self.seed = seed
        self.blocks = {}            # (i, y, j) -> (name, props)
        self.floor = {}             # (i, j) -> block for the plinth there

    def put(self, i, y, j, name, **props):
        self.blocks[(i, y, j)] = (name, tuple(sorted(props.items())))

    def drop(self, i, y, j):
        self.blocks.pop((i, y, j), None)

    def rnd(self, *k):
        """A stable pseudo-random number in [0, 1) for a position."""
        h = hash((self.seed,) + k) & 0xffffffff
        h = (h ^ (h >> 16)) * 0x45d9f3b & 0xffffffff
        return ((h ^ (h >> 16)) & 0xffff) / 0x10000

    def emit(self):
        return [Block(i, y, j, 'state', args, owner=self.owner) for (i, y, j), args in sorted(self.blocks.items())]


def house(site, R, wall_h, max_top, pal, keep=False):
    """A timber house (or, `keep`, a stone keep) filling the rectangle R = (i0, j0, i1, j1), its walls `wall_h`
    blocks high and nothing higher than `max_top`. Returns its top."""
    log, planks, wood, roof, _ = pal
    stairs, slab, full = roof_blocks(roof)
    i0, j0, i1, j1 = R
    w, d = i1 - i0 + 1, j1 - j0 + 1
    for i in range(i0, i1 + 1):
        for j in range(j0, j1 + 1):
            if i not in (i0, i1) and j not in (j0, j1):
                continue
            corner = i in (i0, i1) and j in (j0, j1)
            for y in range(wall_h):
                site.put(i, y, j, log, axis='y') if corner else site.put(i, y, j, planks)
    # windows on the sides the camera sees (south and east), with a bookshelf inside to look at
    if wall_h >= 2:
        for i in range(i0 + 1, i1):
            if (i - i0) % 2 == 1 and i != i0 + w // 2:
                site.put(i, 1, j1, 'glass_pane', east='true', west='true')
                if j1 - 1 > j0:
                    site.put(i, 1, j1 - 1, 'bookshelf')
        for j in range(j0 + 1, j1):
            if (j - j0) % 2 == 1:
                site.put(i1, 1, j, 'glass_pane', north='true', south='true')
                if i1 - 1 > i0:
                    site.put(i1 - 1, 1, j, 'bookshelf')
        # the front door, with a lantern beside it
        ic = i0 + w // 2
        if not keep or w >= 3:
            site.put(ic, 0, j1, f'{wood}_door', facing='north', half='lower', hinge='left', open='false')
            site.put(ic, 1, j1, f'{wood}_door', facing='north', half='upper', hinge='left', open='false')
    # the gable roof, its ridge along the longer side
    along_x = w >= d
    span = d if along_x else w
    layers = math.ceil(span / 2)
    room = max(1, math.floor(max_top) - wall_h)
    flat_at = min(layers, room)                     # higher than this, the roof is cut flat
    top = wall_h
    for k in range(flat_at):
        y = wall_h + k
        top = y + 1
        lo, hi = k, span - 1 - k
        last = k == flat_at - 1 and flat_at < layers
        for a in range(i0, i1 + 1) if along_x else range(j0, j1 + 1):
            def at(b):
                return (a, y, j0 + b) if along_x else (i0 + b, y, a)
            if last:
                for b in range(lo, hi + 1):
                    site.put(*at(b), slab, type='bottom')
                continue
            if lo == hi:
                site.put(*at(lo), slab, type='bottom')
                continue
            if along_x:
                site.put(*at(lo), stairs, facing='south', half='bottom', shape='straight')
                site.put(*at(hi), stairs, facing='north', half='bottom', shape='straight')
            else:
                site.put(*at(lo), stairs, facing='east', half='bottom', shape='straight')
                site.put(*at(hi), stairs, facing='west', half='bottom', shape='straight')
            gable = a in ((i0, i1) if along_x else (j0, j1))
            if gable:
                for b in range(lo + 1, hi):
                    site.put(*at(b), planks)
    # a chimney on bigger houses
    if not keep and w * d >= 12 and w >= 3 and d >= 3 and top + 1 <= max_top + .5:
        ci, cj = i1 - 1, j0 + 1
        for y in range(wall_h, top + 1):
            site.put(ci, y, cj, 'bricks' if roof != 'brick' else 'cobblestone')
        top += 1
    return top


def castle(site, R, max_top, keep_pal):
    """A castle on R: stone walls with battlements, towers on the corners, a gate in the south wall, a mossy
    courtyard and a keep in it when there is room."""
    i0, j0, i1, j1 = R
    w, d = i1 - i0 + 1, j1 - j0 + 1
    wall_h = 3 if max_top >= 6 else 2
    tower = 3 if min(w, d) >= 11 else 2
    tower_h = min(wall_h + 2, math.floor(max_top) - 1)

    def stone(i, y, j):
        r = site.rnd(i, y, j)
        return 'mossy_stone_bricks' if r < .18 else 'cracked_stone_bricks' if r < .28 else 'stone_bricks'

    for i in range(i0, i1 + 1):
        for j in range(j0, j1 + 1):
            if i not in (i0, i1) and j not in (j0, j1):
                site.floor[(i, j)] = 'moss_block' if site.rnd(i, j) < .85 else 'coarse_dirt'
                continue
            for y in range(wall_h):
                site.put(i, y, j, stone(i, y, j))
            if (i + j) % 2 == 0:
                site.put(i, wall_h, j, 'stone_brick_wall', up='true')
    corners = [(i0, j0), (i1 - tower + 1, j0), (i0, j1 - tower + 1), (i1 - tower + 1, j1 - tower + 1)]
    for ci, cj in corners:
        for i in range(ci, ci + tower):
            for j in range(cj, cj + tower):
                for y in range(tower_h):
                    site.put(i, y, j, stone(i, y, j))
                site.drop(i, wall_h, j)
                if (i in (ci, ci + tower - 1) or j in (cj, cj + tower - 1)) and (i + j) % 2 == 0:
                    site.put(i, tower_h, j, 'stone_brick_wall', up='true')
        if tower == 3:
            site.put(ci + 1, tower_h, cj + 1, 'lantern', hanging='false')
    # the gate: a gap in the south wall, a path up to it, torches on both sides
    gi = i0 + w // 2
    gw = 3 if w >= 13 else 1
    for i in range(gi - gw // 2, gi + gw // 2 + 1):
        for y in range(min(2, wall_h - 1)):
            site.drop(i, y, j1)
        site.drop(i, wall_h, j1)
        site.put(i, wall_h, j1, 'stone_brick_slab', type='bottom')
        for j in range(j0 + 1, j1):
            if (i, j) in site.floor:
                site.floor[(i, j)] = 'dirt_path'
    # a keep in the courtyard
    inner = (i0 + tower, j0 + tower, i1 - tower, j1 - tower)
    kw, kd = inner[2] - inner[0] + 1, inner[3] - inner[1] + 1
    top = tower_h + 1
    if kw >= 5 and kd >= 5:
        kh = min(4, kd - 2)
        K = (inner[0] + 1, inner[1], inner[2] - 1, inner[1] + kh - 1)
        if K[2] - K[0] >= 2:
            top = max(top, house(site, K, wall_h + 1, max_top, keep_pal, keep=True))
    return top


def plan(cells, pins, names, owner, seed, lean, box, area_class=None):
    """The blocks of the building for an IC body (a set of cells): ([Block], plinth height in blocks, size class),
    or None when the body is no rectangle. `box(cell, block, h)` makes a low box of block textures (the plinth). `names` maps a side of the body to how far (cells) pin names reach in from it;
    `lean` = (north, west): how far (cells) a block of height leans over to the north and west."""
    I0, I1 = min(c[0] for c in cells), max(c[0] for c in cells)
    J0, J1 = min(c[1] for c in cells), max(c[1] for c in cells)
    if len(cells) < (I1 - I0 + 1) * (J1 - J0 + 1) - len(pins):
        return None
    kind = area_class or size_class((I1 - I0 + 1) * (J1 - J0 + 1))
    site = Site(owner, seed)
    pal = HOUSES[seed % len(HOUSES)]

    # the building's rectangle: clear of the pin names, else of a one block yard, else the whole body
    ins = {k: max(1, math.ceil(names.get(k, 0))) for k in ('north', 'south', 'east', 'west')}
    R = (I0 + ins['west'], J0 + ins['north'], I1 - ins['east'], J1 - ins['south'])
    need = 5 if kind == 'large' else 3
    if R[2] - R[0] + 1 < need or R[3] - R[1] + 1 < need:
        R = (I0 + 1, J0 + 1, I1 - 1, J1 - 1)
        if R[2] - R[0] + 1 < need or R[3] - R[1] + 1 < need:
            R = (I0, J0, I1, J1)
    if kind == 'large' and (R[2] - R[0] + 1 < 5 or R[3] - R[1] + 1 < 5):
        kind = 'medium'

    # how high it may grow without leaning out of its body
    wall_h = {'small': 2, 'medium': 3, 'large': 3}[kind]
    lim = []
    if lean[0] > 0:
        lim.append((R[1] - J0 + .6) / lean[0])
    if lean[1] > 0:
        lim.append((R[0] - I0 + .6) / lean[1])
    # a roof of at least a few steps, even where that leans a little over the neighbours: flat roofs make boxes
    span = min(R[2] - R[0], R[3] - R[1]) + 1
    max_top = max(wall_h + min(3, math.ceil(span / 2)) + (kind != 'small'), min(lim + [9]))
    if kind == 'large':
        castle(site, R, max_top, ('stone_bricks', 'stone_bricks', 'dark_oak', 'deepslate_tile', None))
    else:
        house(site, R, wall_h, max_top, pal)

    # the plinth under all of it, where nothing else stands on the ground
    # the plinth under all of it, where nothing else stands on the ground: a paved yard, a little worn
    plinth = 'stone_bricks' if kind == 'large' else pal[4]
    worn = {'stone_bricks': ('mossy_stone_bricks', 'cracked_stone_bricks'), 'cobblestone': ('mossy_cobblestone',),
            'mossy_cobblestone': ('cobblestone',), 'packed_mud': ('mud_bricks',)}.get(plinth, ())
    out = site.emit()
    ground = {(b.i, b.j) for b in out if b.y == 0}
    for c in sorted(cells):
        if c not in ground:
            r = site.rnd(*c, 'yard')
            block = worn[int(r * 8)] if worn and r * 8 < len(worn) else plinth
            out.append(box(c, site.floor.get(c, block), PLINTH_H))
    return out, PLINTH_H / 16, kind
