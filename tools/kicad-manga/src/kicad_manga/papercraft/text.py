"""Fonts and text for the paper craft style.

Fredoka (rounded, like letters cut from card) for headings and labels, Patrick Hand for handwritten notes, and the
manga style's M PLUS Rounded for the small print (pin names, references, values), which needs to stay legible."""

from .. import text as T
from ..fonts import FONTS as BASE_FONTS
from ..svg import Markup, num, tag

FREDOKA = 'Fredoka'
HAND = 'Patrick Hand'

FONTS = BASE_FONTS + [
    (FREDOKA, 500, 'Medium', 'fredoka/files/fredoka-latin-500-normal.woff2'),
    (FREDOKA, 600, 'SemiBold', 'fredoka/files/fredoka-latin-600-normal.woff2'),
    (HAND, 400, 'Regular', 'patrick-hand/files/patrick-hand-latin-400-normal.woff2'),
]

# text classes of this style, for measuring (see text.CLASSES)
T.CLASSES.update({
    'pc-lbl': (FREDOKA, 600, False), 'pc-title': (FREDOKA, 600, False), 'pc-hand': (HAND, 400, False),
    'pc-caption': (FREDOKA, 500, False), 'pc-card': (FREDOKA, 600, False),
})


def ptext(x, y, s, size, ang, h, v, cls, bg=None, style='', **attrs):
    """Like text.text_el, but `bg` is a function (x, y, w, h) -> markup drawing the paper behind the text, in
    the text's own (translated and rotated) coordinates."""
    lines, anchor, box = T.layout(s, size, h, v, cls, style)
    spans = [tag('tspan', [T.markup_tspans(t)], x=lx, y=ly) for lx, ly, t in lines]
    t = tag('text', spans, cls=cls, font_size=size * T.FS, text_anchor=anchor, style=style or None, **attrs)
    rot = ' rotate(-90)' if round(ang) % 180 == 90 else ''
    return tag('g', [Markup(bg(*box)) if bg else None, t], transform=f'translate({num(x)} {num(y)}){rot}')
