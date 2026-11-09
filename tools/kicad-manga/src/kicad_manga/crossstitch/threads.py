"""Embroidery floss: the colours the sampler is stitched in, and the cloth.

Rustic, plant-dyed looking colours on natural linen. Nets keep the manga style's hue families (names sharing a
prefix share a hue), snapped to the nearest floss; supply rails are stitched in madder red and grounds in pewter."""

import colorsys

from ..palette import NetColors

CLOTH = (216, 199, 164)          # natural, unbleached linen
CLOTH_HOLE = (128, 104, 72)
INK = '#3b2826'                  # dark umber: symbol outlines, pins and references
VALUE = '#2c4f4a'                # dark verdigris: values and other fields
PIN_TEXT = '#4f3f3a'             # pin names and numbers
NOTE = '#45352a'                 # free text
NO_CONNECT = '#9c2f25'
SUPPLY = '#a8382c'
GROUND = '#585c5c'


def hex_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[k:k + 2], 16) for k in (0, 2, 4))


def rgb_hex(c):
    return '#%02x%02x%02x' % tuple(max(0, min(255, round(v))) for v in c)


def shade(col, f):
    """Lighter (f > 0) or darker (f < 0), by mixing with white or black."""
    r, g, b = hex_rgb(col)
    if f >= 0:
        return rgb_hex((r + (255 - r) * f, g + (255 - g) * f, b + (255 - b) * f))
    return rgb_hex((r * (1 + f), g * (1 + f), b * (1 + f)))


def floss(col, light=.5, sat=.62):
    """A pastel turned into a thread of the same hue."""
    r, g, b = (v / 255 for v in hex_rgb(col))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb(h, light, min(sat, max(s, .25)))
    return rgb_hex((r * 255, g * 255, b * 255))


# the floss box: (name, colour). Nets are stitched in the mid tones, part bodies in the pastels.
NET_FLOSS = [
    ('madder', '#a3402f'), ('rosehip', '#a85458'), ('rust', '#ad5e28'), ('ochre', '#b3831f'),
    ('olive', '#737529'), ('sage', '#587645'), ('juniper', '#3d6a4c'), ('verdigris', '#3a7569'),
    ('woad', '#456c8c'), ('indigo', '#334d78'), ('heather', '#64527f'), ('elderberry', '#74476f'),
    ('plum', '#844a63'), ('walnut', '#664631'),
]
SUPPLY_FLOSS = ('madder red', SUPPLY)
GROUND_FLOSS = ('pewter', GROUND)
BODY_FLOSS = [
    ('faded rose', '#d9ad9c'), ('straw', '#dcbd8e'), ('wheat', '#d3c487'), ('lichen', '#b3c296'),
    ('sea glass', '#9fbab2'), ('faded blue', '#a9b6cb'), ('thistle', '#bdadc6'), ('blush', '#d3abad'),
]
INK_FLOSS = [('umber', INK), ('dark verdigris', VALUE), ('bark', PIN_TEXT), ('peat', NOTE),
             ('madder', NO_CONNECT)]


def hue_of(col):
    r, g, b = (v / 255 for v in hex_rgb(col))
    return colorsys.rgb_to_hls(r, g, b)[0] * 360


def nearest(col, box):
    h = hue_of(col)
    return min(box, key=lambda f: min(abs(hue_of(f[1]) - h), 360 - abs(hue_of(f[1]) - h)))


class Threads:
    """Thread colours for nets and symbol bodies."""

    def __init__(self, labels, lib_ids):
        from ..palette import LibColors
        self.nets = NetColors(labels)
        self.libs = LibColors(lib_ids)
        self.used = {}           # colour -> [floss name, what it was used for]

    def net(self, name, key=None):
        if not name:
            return self.use(NET_FLOSS[-1], 'unnamed nets')
        up = name.upper()
        if up.startswith(('GND', 'VSS', 'EARTH')) or up in ('0V',):
            return self.use(GROUND_FLOSS, 'ground')
        if NetColors.is_supply(name):
            return self.use(SUPPLY_FLOSS, 'supply rails')
        return self.use(nearest(self.nets(name), NET_FLOSS[:-1]), NetColors.prefix(name))

    def body(self, lib_id):
        return self.use(nearest(self.libs(lib_id), BODY_FLOSS), lib_id.split(':')[0])

    def ink(self, col, what):
        name = next((n for n, c in INK_FLOSS if c == col), None)
        return self.use((name, col), what) if name else col

    def use(self, f, what):
        name, col = f
        self.used.setdefault(col, [name, set()])[1].add(what)
        return col
