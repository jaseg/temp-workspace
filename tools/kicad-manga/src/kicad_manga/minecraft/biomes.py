"""Biomes for the land around the circuit, picked the way the game picks them: from two smooth noise fields,
temperature and humidity. Each biome has its ground, its grass and leaf colours, its trees, plants and animals,
and the blocks its hills are made of."""

import math
import random
import zlib

# grass and foliage colours: soft versions of the game's biome colours
BIOMES = {
    'plains': dict(grass=(132, 196, 92), foliage=(110, 178, 72), ground=[('grass_block', 30), ('coarse_dirt', 1)],
                   trees=[('oak', 3), ('birch', 1)], tree_density=.25, hills=1.0,
                   plants=.16, flowers=1.0, animals=['pig', 'sheep', 'chicken', 'sheep']),
    'meadow': dict(grass=(140, 204, 96), foliage=(110, 178, 72), ground=[('grass_block', 1)],
                   trees=[('oak', 1), ('cherry', 1)], tree_density=.12, hills=1.1,
                   plants=.26, flowers=2.2, animals=['sheep', 'sheep', 'pig', 'chicken']),
    'forest': dict(grass=(112, 182, 84), foliage=(92, 164, 62), ground=[('grass_block', 12), ('podzol', 1),
                                                                         ('moss_block', 1)],
                   trees=[('oak', 3), ('birch', 1)], tree_density=1.0, hills=1.2,
                   plants=.14, flowers=.5, animals=['pig', 'chicken']),
    'birch_forest': dict(grass=(136, 192, 104), foliage=(128, 172, 92), ground=[('grass_block', 1)],
                         trees=[('birch', 1)], tree_density=.9, hills=1.0,
                         plants=.14, flowers=1.2, animals=['pig', 'chicken', 'sheep']),
    'cherry_grove': dict(grass=(160, 208, 104), foliage=(150, 200, 100), ground=[('grass_block', 1)],
                         trees=[('cherry', 1)], tree_density=.7, hills=1.4,
                         plants=.12, flowers=1.0, petals=.3, animals=['pig', 'sheep']),
    'taiga': dict(grass=(110, 168, 98), foliage=(97, 153, 97), ground=[('grass_block', 10), ('podzol', 2),
                                                                       ('coarse_dirt', 1)],
                  trees=[('spruce', 1)], tree_density=.9, hills=1.7, top='podzol',
                  plants=.1, plant_kinds=['fern', 'fern', 'large_fern', 'sweet_berry_bush', 'short_grass'],
                  flowers=.2, animals=['pig_cold', 'sheep', 'chicken_cold']),
    'snowy': dict(grass=(128, 180, 151), foliage=(110, 150, 120), ground=[('snow_block', 1)],
                  trees=[('spruce', 1)], tree_density=.3, hills=1.9, top='snow_block',
                  plants=0, flowers=0, pond='ice', animals=['pig_cold', 'sheep', 'chicken_cold']),
    'savanna': dict(grass=(184, 184, 92), foliage=(170, 168, 66), ground=[('grass_block', 10), ('coarse_dirt', 1)],
                    trees=[('acacia', 1)], tree_density=.18, hills=.7,
                    plants=.28, flowers=.2, animals=['pig_warm', 'chicken_warm', 'sheep']),
    'desert': dict(grass=(190, 183, 85), foliage=(174, 164, 42), ground=[('sand', 1)],
                   trees=[('cactus', 1)], tree_density=.12, hills=.6, top='sand', under='sandstone', deep='sandstone',
                   plants=.025, plant_kinds=['dead_bush'], flowers=0, pond_rim='sand', animals=[]),
    'badlands': dict(grass=(144, 129, 77), foliage=(158, 129, 77), ground=[('red_sand', 6), ('terracotta', 1)],
                     trees=[('cactus', 1)], tree_density=.05, hills=1.5, top='red_sand', terraces=2,
                     plants=.03, plant_kinds=['dead_bush'], flowers=0, pond_rim='red_sand',
                     animals=['pig_warm', 'chicken_warm']),
}

BANDS = ['terracotta', 'orange_terracotta', 'yellow_terracotta', 'terracotta', 'white_terracotta',
         'red_terracotta', 'orange_terracotta', 'brown_terracotta', 'light_gray_terracotta']
STONES = ['stone', 'stone', 'stone', 'andesite', 'stone', 'granite', 'stone', 'diorite', 'tuff']
ORES = [('coal_ore', 6), ('iron_ore', 3), ('copper_ore', 2), ('gold_ore', 1), ('lapis_ore', 1),
        ('redstone_ore', 1), ('diamond_ore', .3), ('emerald_ore', .2)]


class Noise:
    """Smooth value noise: random values on a grid `scale` cells apart, eased in between, two octaves."""

    def __init__(self, seed, scale):
        self.seed, self.scale = seed, scale

    def grid(self, a, b):
        return random.Random(zlib.crc32(f'{self.seed}:{a}:{b}'.encode())).random()

    def octave(self, x, y):
        x0, y0 = math.floor(x), math.floor(y)
        fx, fy = x - x0, y - y0
        sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
        a = self.grid(x0, y0) + (self.grid(x0 + 1, y0) - self.grid(x0, y0)) * sx
        b = self.grid(x0, y0 + 1) + (self.grid(x0 + 1, y0 + 1) - self.grid(x0, y0 + 1)) * sx
        return a + (b - a) * sy

    def __call__(self, i, j):
        x, y = i / self.scale, j / self.scale
        return (self.octave(x, y) * 2 + self.octave(x * 2.3 + 17, y * 2.3 + 5)) / 3


def classify(t, u):
    """A biome for a temperature and a humidity (0..1 each)."""
    if t < .16:
        return 'snowy'
    if t < .28:
        return 'taiga'
    if t > .8:
        return 'desert' if u < .36 else 'badlands' if u < .44 else 'savanna'
    if t > .72:
        return 'savanna' if u < .5 else 'plains'
    if u > .64:
        return 'cherry_grove' if t > .52 else 'forest'
    if u > .54:
        return 'birch_forest' if t > .55 else 'forest'
    if u < .38:
        return 'meadow'
    return 'plains'


class Biomes:
    def __init__(self, seed, scale=70):
        self.temp = Noise(f'{seed}t', scale)
        self.humid = Noise(f'{seed}h', scale * .8)
        self.cache = {}

    def __call__(self, c):
        if c not in self.cache:
            # stretch the noise (which bunches up around the middle) so every biome shows up somewhere
            t = min(1, max(0, .5 + (self.temp(*c) - .5) * 1.9))
            u = min(1, max(0, .5 + (self.humid(*c) - .5) * 1.9))
            self.cache[c] = classify(t, u)
        return self.cache[c]


def pick(rng, weighted):
    total = sum(w for _, w in weighted)
    x = rng.random() * total
    for v, w in weighted:
        x -= w
        if x <= 0:
            return v
    return weighted[-1][0]


def column(biome, h, y, i, j, rnd):
    """The block at height y of a hill h blocks high in a biome: (name, props, tint) or None for the default."""
    B = BIOMES[biome]
    top = h - 1
    if y == top:
        if h >= 9 or (h >= 7 and biome in ('snowy', 'taiga')):
            return 'snow_block', (), None
        if h >= 7 and biome not in ('desert', 'badlands'):
            return ('stone' if rnd < .7 else 'gravel'), (), None
        t = B.get('top', 'grass_block')
        if t == 'grass_block' or (t == 'podzol' and rnd < .5):
            return 'grass_block', (('snowy', 'false'),), B['grass']
        return t, (), None
    if biome == 'badlands':
        return BANDS[y % len(BANDS)], (), None
    depth = top - y
    if depth <= 2 and h < 7:
        if 'under' in B:
            return B['under'], (), None
        return ('dirt' if rnd < .85 else 'coarse_dirt'), (), None
    if 'deep' in B:
        return B['deep'], (), None
    if rnd < .07:
        return pick(random.Random(rnd), ORES), (), None
    return STONES[(y * 7 + (i // 5) * 3 + (j // 7)) % len(STONES)], (), None
