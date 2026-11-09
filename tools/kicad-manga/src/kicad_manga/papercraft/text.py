"""Fonts and text for the paper craft style.

Mali (a rounded, childlike hand that stays legible down to pin names) for all the text on the sheet, and Sniglet
(bubbly, like letters cut from card) for headings and the title."""

import contextlib

from .. import text as T
from ..fonts import FONTS as BASE_FONTS, POP
from ..svg import Markup, num, tag

MALI = 'Mali'
BUBBLE = 'Sniglet'

FONTS = [f for f in BASE_FONTS if f[0] == POP] + [     # Mochiy Pop One stays, for the Japanese kicker
    (MALI, 500, 'Medium', 'mali/files/mali-latin-500-normal.woff2'),
    (MALI, 700, 'Bold', 'mali/files/mali-latin-700-normal.woff2'),
    (BUBBLE, 800, 'ExtraBold', 'sniglet/files/sniglet-latin-800-normal.woff2'),
]

# The font of each text class in this style, for measuring (see text.CLASSES)
CLASSES = {cls: (MALI, 500, False) for cls in T.CLASSES}
CLASSES.update({
    'ref': (MALI, 700, False), 'value': (MALI, 700, False), 'pwr': (MALI, 700, False), 'lbl': (MALI, 700, False),
    'sheetname': (BUBBLE, 800, False), 'pc-lbl': (MALI, 700, False), 'pc-title': (BUBBLE, 800, False),
    'pc-hand': (MALI, 500, False), 'pc-caption': (MALI, 700, False), 'pc-card': (BUBBLE, 800, False),
})


@contextlib.contextmanager
def measuring():
    """Measure text in this style's fonts while the page is built."""
    saved = dict(T.CLASSES)
    T.CLASSES.clear()
    T.CLASSES.update(saved, **CLASSES)
    try:
        yield
    finally:
        T.CLASSES.clear()
        T.CLASSES.update(saved)


def ptext(x, y, s, size, ang, h, v, cls, bg=None, style='', **attrs):
    """Like text.text_el, but `bg` is a function (x, y, w, h) -> markup drawing the paper behind the text, in
    the text's own (translated and rotated) coordinates."""
    lines, anchor, box = T.layout(s, size, h, v, cls, style)
    spans = [tag('tspan', [T.markup_tspans(t)], x=lx, y=ly) for lx, ly, t in lines]
    t = tag('text', spans, cls=cls, font_size=size * T.FS, text_anchor=anchor, style=style or None, **attrs)
    rot = ' rotate(-90)' if round(ang) % 180 == 90 else ''
    return tag('g', [Markup(bg(*box)) if bg else None, t], transform=f'translate({num(x)} {num(y)}){rot}')
