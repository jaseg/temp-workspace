"""Animals (and the odd enderman), as block-model elements built from the mobs' boxes and the resource pack's
entity textures.

The game draws mobs with models in its code, not in the pack, so their boxes are written down here in the
game's texture pixels (a mob faces north, y up, its feet at 0) with the usual box unwrapping of entity textures:
for a box w x h x d at texture offset (u, v), the top is at (u + d, v), the right side at (u, v + d), the
front at (u + d, v + d), the left side at (u + d + w, v + d) and the back at (u + 2d + w, v + d). Mobs are
drawn at the game's size (a texture pixel is a 16th of a block), reaching out of their cell, and turned to face one of four ways."""

TEX = 64        # entity textures are 64 pixels wide; model uv runs 0..16 over the width


def uv(a, b, c, d):
    k = 16 / TEX
    return [a * k, b * k, c * k, d * k]


def cube(x0, y0, z0, x1, y1, z1, tex, u, v, w, h, d, inflate=0):
    """A box with the standard entity unwrapping; w, h, d its size in texture pixels."""
    faces = {
        'up': {'uv': uv(u + d, v, u + d + w, v + d)},
        'down': {'uv': uv(u + d + w, v + d, u + d + 2 * w, v)},
        'east': {'uv': uv(u, v + d, u + d, v + d + h)},
        'north': {'uv': uv(u + d, v + d, u + d + w, v + d + h)},
        'west': {'uv': uv(u + d + w, v + d, u + 2 * d + w, v + d + h)},
        'south': {'uv': uv(u + 2 * d + w, v + d, u + 2 * d + 2 * w, v + d + h)},
    }
    for f in faces.values():
        f['texture'] = '#t' if tex is None else tex
    i = inflate
    return {'from': [x0 - i, y0 - i, z0 - i], 'to': [x1 + i, y1 + i, z1 + i], 'faces': faces}


def lying(x0, y0, z0, x1, y1, z1, tex, u, v, w, h, d, inflate=0):
    """A body box w x h x d turned to lie along z (as pigs, sheep and chickens wear theirs): its texture's front
    is the back of the animal, its top the chest end."""
    faces = {
        'up': {'uv': uv(u + d, v + d, u + d + w, v + d + h)},
        'down': {'uv': uv(u + 2 * d + w, v + d, u + 2 * d + 2 * w, v + d + h)},
        'north': {'uv': uv(u + d, v, u + d + w, v + d)},
        'south': {'uv': uv(u + d + w, v, u + d + 2 * w, v + d)},
        'east': {'uv': uv(u, v + d, u + d, v + d + h), 'rotation': 90},
        'west': {'uv': uv(u + d + w, v + d, u + 2 * d + w, v + d + h), 'rotation': 270},
    }
    for f in faces.values():
        f['texture'] = '#t' if tex is None else tex
    i = inflate
    return {'from': [x0 - i, y0 - i, z0 - i], 'to': [x1 + i, y1 + i, z1 + i], 'faces': faces}


def legs(xs, zs, tex, u, v, w, h, d, inflate=0, y0=0):
    return [cube(x, y0, z, x + w, y0 + h, z + d, tex, u, v, w, h, d, inflate) for x in xs for z in zs]


def pig(variant='temperate'):
    t = f'entity/pig/pig_{variant}'
    return t, [
        *legs((-5, 1), (-7, 3), None, 0, 16, 4, 6, 4),
        lying(-5, 6, -8, 5, 14, 8, None, 28, 8, 10, 16, 8),
        cube(-4, 8, -14, 4, 16, -6, None, 0, 0, 8, 8, 8),
        cube(-2, 9, -15, 2, 12, -14, None, 16, 16, 4, 3, 1),
    ], {}


def sheep():
    wool = 'entity/sheep/sheep_wool'
    return 'entity/sheep/sheep', [
        *legs((-5, 1), (-7, 3), None, 0, 16, 4, 12, 4),
        *legs((-5, 1), (-7, 3), wool, 0, 16, 4, 6, 4, inflate=.5, y0=6),
        lying(-4, 12, -8, 4, 18, 8, None, 28, 8, 8, 16, 6),
        lying(-4, 12, -8, 4, 18, 8, wool, 28, 8, 8, 16, 6, inflate=1.75),
        cube(-3, 15, -14, 3, 21, -6, None, 0, 0, 6, 6, 8),
        cube(-3, 15, -12, 3, 21, -6, wool, 0, 0, 6, 6, 6, inflate=.6),
    ], {}


def chicken(variant='temperate'):
    t = f'entity/chicken/chicken_{variant}'
    return t, [
        *legs((-2.5, .5), (-.5,), None, 26, 0, 3, 5, 3),
        lying(-3, 5, -4, 3, 11, 4, None, 0, 9, 6, 8, 6),
        cube(-4, 7, -3, -3, 11, 3, None, 24, 13, 1, 4, 6),
        cube(3, 7, -3, 4, 11, 3, None, 24, 13, 1, 4, 6),
        cube(-2, 9, -6, 2, 15, -3, None, 0, 0, 4, 6, 3),
        cube(-2, 11, -8, 2, 13, -6, None, 14, 0, 4, 2, 2),
        cube(-1, 9, -7, 1, 11, -5, None, 14, 4, 2, 2, 2),
    ], {}


def enderman(holding=True):
    t = 'entity/enderman/enderman'
    els = [
        cube(-3, 0, -1, -1, 30, 1, None, 56, 0, 2, 30, 2),
        cube(1, 0, -1, 3, 30, 1, None, 56, 0, 2, 30, 2),
        cube(-4, 30, -2, 4, 42, 2, None, 32, 16, 8, 12, 4),
        cube(-6, 12, -1, -4, 42, 1, None, 56, 0, 2, 30, 2),
        cube(4, 12, -1, 6, 42, 1, None, 56, 0, 2, 30, 2),
        cube(-4, 42, -4, 4, 50, 4, None, 0, 0, 8, 8, 8),
        cube(-4, 42, -4, 4, 50, 4, 'entity/enderman/enderman_eyes', 0, 0, 8, 8, 8, inflate=.01),
    ]
    if holding:     # a stolen resistor (a furnace) under its arm
        side, front, top = 'block/furnace_side', 'block/furnace_front', 'block/furnace_top'
        f = {k: {'texture': side, 'uv': [0, 0, 16, 16]} for k in ('east', 'west', 'south', 'down')}
        f['north'] = {'texture': front, 'uv': [0, 0, 16, 16]}
        f['up'] = {'texture': top, 'uv': [0, 0, 16, 16]}
        els.append({'from': [-5, 26, -11], 'to': [5, 36, -1], 'faces': f})
    return t, els, {}


def chest(variant='normal'):
    """A chest (the game draws them like mobs): a base and a lid with the lock on the front. Chest textures are
    stored upside down, so tops come from the bottom's place and the sides are flipped."""
    t = f'entity/chest/{variant}'

    def box(x0, y0, z0, x1, y1, z1, u, v, w, h, d):
        el = cube(x0, y0, z0, x1, y1, z1, None, u, v, w, h, d)
        f = el['faces']
        f['up']['uv'], f['down']['uv'] = uv(u + d + w, v, u + d + 2 * w, v + d), uv(u + d, v, u + d + w, v + d)
        for k in ('north', 'south', 'east', 'west'):
            a, b, c, e = f[k]['uv']
            f[k]['uv'] = [a, e, c, b]
        return el
    return t, [
        box(-7, 0, -7, 7, 10, 7, 0, 19, 14, 10, 14),
        box(-7, 9, -7, 7, 14, 7, 0, 0, 14, 5, 14),
        box(-1, 7, -8, 1, 11, -7, 0, 0, 2, 4, 1),
    ], {}


SPECIES = {
    'pig': (pig, 1), 'pig_warm': (lambda: pig('warm'), 1), 'pig_cold': (lambda: pig('cold'), 1),
    'sheep': (sheep, 1),
    'chicken': (chicken, 1), 'chicken_warm': (lambda: chicken('warm'), 1),
    'chicken_cold': (lambda: chicken('cold'), 1),
    'enderman': (enderman, 1),
    'chest': (chest, 1), 'chest_copper': (lambda: chest('copper'), 1), 'chest_ender': (lambda: chest('ender'), 1),
    'chest_trapped': (lambda: chest('trapped'), 1), 'enderman_empty': (lambda: enderman(False), 1),
}


def model(species):
    """A block model of a mob, facing north, centred on its cell."""
    make, k = SPECIES[species]
    tex, els, _ = make()
    out = []
    for el in els:
        e = dict(el)
        e['from'] = [8 + el['from'][0] * k, el['from'][1] * k, 8 + el['from'][2] * k + 2 * k]
        e['to'] = [8 + el['to'][0] * k, el['to'][1] * k, 8 + el['to'][2] * k + 2 * k]
        out.append(e)
    return {'textures': {'t': tex}, 'elements': out}
