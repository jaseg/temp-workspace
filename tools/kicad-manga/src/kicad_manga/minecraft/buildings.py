"""ICs as buildings: small and medium ICs become timber houses with gable roofs, large ones castles with corner
towers, a gate and a keep in the courtyard.

A building fills its whole body, and the pin names are painted over its walls and roof. Connectors become
picnics (`picnic`). Every block is a plain block state of the resource pack."""

import math
import zlib

from .world import DIRS, Block

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

TURN = ['north', 'east', 'south', 'west']


def turn(d, r):
    return TURN[(TURN.index(d) + r) % 4]


SMALL, LARGE = 40, 200          # body area (cells) up to which an IC is a small house, above which a castle
PLINTH_H = 2                    # 16ths of a block: floors inside buildings


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
        h = zlib.crc32(repr((self.seed,) + k).encode())
        h = (h ^ (h >> 16)) * 0x45d9f3b & 0xffffffff
        return ((h ^ (h >> 16)) & 0xffff) / 0x10000

    def turned(self, r, I0, J0, W, D):
        """The site built in a W x D frame at (0, 0), turned r quarter turns clockwise (seen from above) and
        moved to (I0, J0)."""
        def at(x, z):
            return [(x, z), (D - 1 - z, x), (W - 1 - x, D - 1 - z), (z, W - 1 - x)][r]

        def props(ps):
            out = []
            for k, v in ps:
                if k in TURN:
                    k = turn(k, r)
                elif k == 'facing' and v in TURN:
                    v = turn(v, r)
                elif k == 'axis' and r % 2 and v in ('x', 'z'):
                    v = 'z' if v == 'x' else 'x'
                out.append((k, v))
            return tuple(sorted(out))
        blocks = {}
        for (x, y, z), (name, ps) in self.blocks.items():
            i, j = at(x, z)
            blocks[(I0 + i, y, J0 + j)] = (name, props(ps))
        self.blocks = blocks
        self.floor = {(I0 + at(x, z)[0], J0 + at(x, z)[1]): b for (x, z), b in self.floor.items()}

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
                site.floor[(i, j)] = 'moss_block' if site.rnd(i, j) < .95 else 'coarse_dirt'
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
    K = None
    if kw >= 5 and kd >= 5:
        kh = min(4, kd - 2)
        K = (inner[0] + 1, inner[1], inner[2] - 1, inner[1] + kh - 1)
        if K[2] - K[0] >= 2:
            top = max(top, house(site, K, wall_h + 1, max_top, keep_pal, keep=True))
        else:
            K = None
    furnish(site, R, tower, K, (gi - gw // 2, gi + gw // 2))
    return top


FLOWERS = ['poppy', 'dandelion', 'cornflower', 'allium', 'oxeye_daisy', 'azure_bluet', 'lily_of_the_valley',
           'red_tulip', 'orange_tulip', 'pink_tulip', 'white_tulip']
CROPS = [('wheat', 'age', '7'), ('carrots', 'age', '7'), ('potatoes', 'age', '7'), ('beetroots', 'age', '3')]


def furnish(site, R, tower, K, path):
    """Life in a castle's courtyard: cottages and vegetable gardens along the walls, a well on the square in the
    middle, lanterns on posts along the path, beehives, hay, barrels and flowers everywhere else."""
    i0, j0, i1, j1 = R
    F = PLINTH_H / 16                                   # the courtyard's floor
    used = set()
    if K:
        used |= {(i, j) for i in range(K[0] - 1, K[2] + 2) for j in range(K[1], K[3] + 2)}
    used |= {(i, j) for i in range(path[0], path[1] + 1) for j in range(j0, j1 + 1)}

    def free(cells):
        return all(i0 < i < i1 and j0 < j < j1 and (i, j) not in used and (i, j) in site.floor for i, j in cells)

    def take(cells):
        used.update(cells)

    def rect(a, b, c, d):
        return [(i, j) for i in range(a, c + 1) for j in range(b, d + 1)]

    # the square with the well, halfway down the path
    jt = (K[3] + 2) if K else j0 + tower
    jm = (jt + j1 - tower) // 2
    pc = (path[0] + path[1]) // 2
    sq = rect(pc - 2, jm - 2, pc + 2, jm + 2)
    if all(i0 < i < i1 and j0 + tower <= j < j1 - tower for i, j in sq):
        for c in sq:
            site.floor[c] = 'dirt_path' if c[0] in range(path[0], path[1] + 1) else 'gravel'
            used.add(c)
        for c in rect(pc - 1, jm - 1, pc + 1, jm + 1):
            site.floor[c] = 'cobblestone'
        site.put(pc, F, jm, 'water_cauldron', level='3')
        for a, b in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            site.put(pc + a, F, jm + b, 'oak_fence')
            site.put(pc + a, F + 1, jm + b, 'oak_fence')
        for c in rect(pc - 1, jm - 1, pc + 1, jm + 1):
            site.put(c[0], F + 2, c[1], 'spruce_slab', type='bottom')
        for a in (-1, 1):
            site.put(pc + a, F, jm, 'cobblestone_slab', type='bottom')
        site.put(pc, F, jm - 1, 'cobblestone_slab', type='bottom')
        site.put(pc + 2, F, jm + 2, 'campfire', lit='true', facing='south')

    # lanterns on posts along the path
    for j in range(jt + 1, j1 - 1, 4):
        for i in (path[0] - 1, path[1] + 1):
            if free([(i, j)]):
                site.put(i, F, j, 'oak_fence')
                site.put(i, F + 1, j, 'lantern', hanging='false')
                take([(i, j)])

    # along both walls, from the north down: cottages, gardens and little stores
    houses = [h for h in HOUSES if h[3] != 'deepslate_tile']
    for side in ('west', 'east'):
        room = (path[0] - 2 - i0) if side == 'west' else (i1 - 2 - path[1])
        cw = min(3, room)
        if cw < 2:
            continue
        a = i0 + 1 if side == 'west' else i1 - cw
        j = j0 + tower if not K else j0 + 1
        k = 0
        while j < j1 - 1:
            r = site.rnd(side, j, 'what')
            if r < .4 and free(rect(a, j, a + cw - 1, j + 2)):
                # a cottage
                take(rect(a, j, a + cw - 1, j + 3))
                house(site, (a, j, a + cw - 1, j + 2), 2, 4, houses[int(site.rnd(side, j) * len(houses))])
                j += 4
            elif r < .7 and free(rect(a, j, a + cw - 1, j + 1)):
                # a vegetable garden
                crop = CROPS[int(site.rnd(j, side, 'crop') * len(CROPS))]
                for c in rect(a, j, a + cw - 1, j + 1):
                    site.floor[c] = 'farmland'
                    site.put(c[0], F, c[1], crop[0], **{crop[1]: crop[2]})
                take(rect(a, j, a + cw - 1, j + 2))
                j += 3
            elif free([(a, j)]):
                # a little store: barrels, hay, a beehive, a crafting table
                stuff = [('barrel', {'facing': 'up', 'open': 'false'}), ('hay_block', {'axis': 'y'}),
                         ('beehive', {'facing': 'south', 'honey_level': '5'}), ('crafting_table', {}),
                         ('flowering_azalea', {}), ('composter', {'level': '6'}), ('smoker', {'facing': 'south'})]
                for n, c in enumerate(rect(a, j, a + cw - 1, j)):
                    if free([c]) and site.rnd(*c, 'stuff') < .8:
                        name, props = stuff[int(site.rnd(c[1], c[0], 'stuff') * len(stuff))]
                        site.put(c[0], F, c[1], name, **props)
                take(rect(a, j, a + cw - 1, j + 1))
                j += 2
            else:
                j += 1
            k += 1

    # flowers on the grass that is left
    for c in sorted(site.floor):
        i, j = c
        if site.floor[c] == 'moss_block' and c not in used and (i, F, j) not in site.blocks:
            r = site.rnd(i, j, 'flower')
            if r < .22:
                site.put(i, F, j, FLOWERS[int(site.rnd(j, i, 'f') * len(FLOWERS))])
            elif r < .25:
                site.put(i, F, j, 'flowering_azalea' if r < .24 else 'azalea')


def plan(cells, pins, owner, seed, box, area_class=None):
    """The building for an IC body (a set of cells): ([Block], height in blocks to paint the pin names at, size
    class), or None when the body is no rectangle. The building fills the whole body: its pin names lie on its
    walls and roof. `box(cell, block, h)` makes a low box of block textures (the floors inside)."""
    I0, I1 = min(c[0] for c in cells), max(c[0] for c in cells)
    J0, J1 = min(c[1] for c in cells), max(c[1] for c in cells)
    if len(cells) < (I1 - I0 + 1) * (J1 - J0 + 1) - len(pins):
        return None
    R = (I0, J0, I1, J1)
    w, d = I1 - I0 + 1, J1 - J0 + 1
    kind = area_class or size_class(w * d)
    if kind == 'large' and min(w, d) < 5:
        kind = 'medium'
    if min(w, d) < 2:
        return None
    site = Site(owner, seed)
    pal = HOUSES[seed % len(HOUSES)]
    wall_h = {'small': 2, 'medium': 3, 'large': 3}[kind]
    max_top = wall_h + {'small': 3, 'medium': 4, 'large': 4}[kind]
    # built facing south in its own frame, then turned to face a random way
    r = int(site.rnd('turn') * 4)
    W, D = (w, d) if r % 2 == 0 else (d, w)
    local = (0, 0, W - 1, D - 1)
    if kind == 'large':
        castle(site, local, max_top + 2, ('stone_bricks', 'stone_bricks', 'dark_oak', 'deepslate_tile', None))
    else:
        house(site, local, wall_h, max_top, pal)
    site.turned(r, I0, J0, W, D)

    # floors inside (under the roof, the courtyard), where nothing else stands on the ground
    plinth = 'stone_bricks' if kind == 'large' else pal[4]
    out = site.emit()
    ground = {(b.i, b.j) for b in out if b.y == 0}
    for c in sorted(cells):
        if c not in ground:
            out.append(box(c, site.floor.get(c, plinth), PLINTH_H))
    return out, wall_h, kind


CANDLES = ['white', 'orange', 'magenta', 'light_blue', 'yellow', 'lime', 'pink', 'cyan', 'purple', 'blue', 'red']
TREATS = [('cake', {}), ('melon', {}), ('pumpkin', {}), ('hay_block', {'axis': 'y'}), ('jukebox', {}),
          ('barrel', {'facing': 'up', 'open': 'false'}), ('beehive', {'facing': 'south', 'honey_level': '5'}),
          ('lantern', {'hanging': 'false'}), ('flower_pot', {}), ('composter', {'level': '0'})]


def picnic(cells, pins, owner, seed, box):
    """A connector as a picnic: a red and white checkered blanket over its body, a birthday cake with a candle
    wherever a pin plugs in (the candle's colour by net, so pins of one net match), and treats spread around
    the middle. Returns [Block] and the height to paint the pin names at."""
    site = Site(owner, seed)
    inner = {}
    for p in pins:
        path = list(p['line'])
        if p['dir']:
            d = DIRS[p['dir']]
            path += [(p['inner'][0] + d[0] * k, p['inner'][1] + d[1] * k) for k in range(1, 8)]
        for c in path:
            if c in cells:
                inner[c] = p['net']
                break
    for (i, j) in sorted(cells):
        if (i, j) in inner:
            net = inner[(i, j)]
            colour = CANDLES[zlib.crc32(repr(net).encode()) % len(CANDLES)]
            site.put(i, 0, j, f'{colour}_candle_cake', lit='true')
            continue
        edge = any((i + a, j + b) not in cells for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        r = site.rnd(i, j)
        if not edge and r < .12:
            name, props = TREATS[int(site.rnd(j, i) * len(TREATS))]
            site.put(i, 0, j, name, **props)
    out = site.emit()
    ground = {(b.i, b.j) for b in out}
    for (i, j) in sorted(cells):
        if (i, j) not in ground:
            out.append(box((i, j), 'red_wool' if (i + j) % 2 else 'white_wool', 1))
    return out, 1 / 16
