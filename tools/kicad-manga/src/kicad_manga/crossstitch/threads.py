"""Embroidery floss: the colours the sampler is stitched in, and the cloth.

Thread colours are deeper than the manga style's pastels, so that they read on cream aida. Nets keep the manga
style's hue families (names sharing a prefix share a hue), supply rails are stitched in coral and grounds in
slate."""

import colorsys

from ..palette import NetColors

CLOTH = (241, 233, 214)          # ecru aida
CLOTH_HOLE = (196, 182, 156)
INK = '#4a3150'                  # dark plum: symbol outlines, pins and references
VALUE = '#2f6a6a'                # deep teal: values and other fields
PIN_TEXT = '#6d5a73'             # pin names and numbers, one strand
NOTE = '#5b4a3a'                 # free text
NO_CONNECT = '#c8323c'
SUPPLY = '#d9534f'
GROUND = '#5f6b7a'


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
    ('cherry', '#c23b4e'), ('rose', '#d6608a'), ('tangerine', '#e07f35'), ('marigold', '#d9a020'),
    ('olive', '#8a962c'), ('moss', '#5a9642'), ('fern', '#2c8c68'), ('teal', '#268a93'), ('sky', '#3a8ccc'),
    ('cornflower', '#5568cc'), ('iris', '#7656c2'), ('lavender', '#a068c0'), ('orchid', '#c25aac'),
    ('cocoa', '#8a5a3c'),
]
SUPPLY_FLOSS = ('coral', SUPPLY)
GROUND_FLOSS = ('slate', GROUND)
BODY_FLOSS = [
    ('blush', '#f2c2cd'), ('peach', '#f5cfab'), ('butter', '#f1df98'), ('mint', '#c4e3b9'), ('aqua', '#b8e0e0'),
    ('powder', '#c2d3ef'), ('lilac', '#d8c8ee'), ('petal', '#efc8e3'),
]
INK_FLOSS = [('plum', INK), ('deep teal', VALUE), ('heather', PIN_TEXT), ('walnut', NOTE),
             ('poppy', NO_CONNECT)]


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
