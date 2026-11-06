"""Backgrounds behind text (label pills and flags, note bubbles, title banners), fitted to the text's measured
bounding box (see text.text_el). All shapes are in the text's own coordinate system (it sits in a
translated/rotated <g>)."""

from markupsafe import Markup

from .circuit import hier_glyph, rounded_poly
from .palette import LINE
from .util import f2
from .svg import render, tag


def build(info, box):
    kind = info[0]
    x, y, w, h = box
    if kind == 'pill':
        hh, yy = h * .86, y + h * .1
        return tag('rect', cls='bg', x=x - .55, y=yy - .18, width=w + 1.1, height=hh + .36, rx=(hh + .36) / 2,
                   fill=info[1], stroke=LINE, stroke_width=.16)
    if kind in ('global_label', 'hierarchical_label'):
        _, col, shape, sign, off, size = info
        y0, y1 = y + h * .08 - .3, y + h * .92 + .3
        ym, d = (y0 + y1) / 2, (y1 - y0) / 2
        xa = -sign * off
        if kind == 'hierarchical_label':
            glyph = hier_glyph(xa, ym, sign, 0, shape, size, col)
            hh = h * .86
            pill = tag('rect', cls='bg', x=x - .5, y=y + h * .07 - .15, width=w + 1, height=hh + .3, rx=(hh + .3) / 2,
                       fill=col, fill_opacity=.55, stroke=LINE, stroke_width=.12, stroke_dasharray='.5 .35')
            return pill + Markup(glyph)
        far = (x + w if sign > 0 else x) + sign * .6
        pa = shape in ('input', 'bidirectional', 'tri_state')
        pf = shape in ('output', 'bidirectional', 'tri_state')
        if pf:
            far += sign * d
        top = [(xa, ym), (xa + sign * d, y0)] if pa else [(xa, y1), (xa, y0)]
        right = [(far - sign * d, y0), (far, ym), (far - sign * d, y1)] if pf else [(far, y0), (far, y1)]
        bottom = [(xa + sign * d, y1)] if pa else []
        poly = top + right + bottom
        return tag('path', cls='bg', d=rounded_poly(poly, .35), fill=col, stroke=LINE, stroke_width=.2,
                   stroke_linejoin='round')
    if kind == 'bubble':
        # a rounded box with a little tail at the bottom left
        p = 1.1
        x0, y0, x1, y1 = x - p, y - p * .7, x + w + p, y + h + p * .7
        rr = min(2.2, (y1 - y0) / 2)
        tx = x0 + min(4, (x1 - x0) * .25)
        d = (f'M{f2(x0 + rr)} {f2(y0)}H{f2(x1 - rr)}Q{f2(x1)} {f2(y0)} {f2(x1)} {f2(y0 + rr)}V{f2(y1 - rr)}'
             f'Q{f2(x1)} {f2(y1)} {f2(x1 - rr)} {f2(y1)}H{f2(tx + 2.2)}L{f2(tx - .6)} {f2(y1 + 2)}L{f2(tx + .6)} {f2(y1)}'
             f'H{f2(x0 + rr)}Q{f2(x0)} {f2(y1)} {f2(x0)} {f2(y1 - rr)}V{f2(y0 + rr)}Q{f2(x0)} {f2(y0)} {f2(x0 + rr)} {f2(y0)}Z')
        return tag('path', cls='bg', d=d, fill='#fff', stroke=LINE, stroke_width=.28, stroke_linejoin='round')
    if kind == 'banner':
        px, py, n = 3.2, .9, 1.6
        x0, x1 = x - px, x + w + px
        y0, y1 = y + h * .08 - py, y + h * .92 + py
        ym = (y0 + y1) / 2
        rib = f'M{f2(x0 - n)} {f2(y0)}H{f2(x1 + n)}L{f2(x1)} {f2(ym)}L{f2(x1 + n)} {f2(y1)}H{f2(x0 - n)}L{f2(x0)} {f2(ym)}Z'
        return render('backgrounds/banner.svg.j2', rib=rib, x0=x0, x1=x1, y0=y0, y1=y1, ym=ym,
                      sparkles=[(x0 - n - 2.6, '#ffe58f'), (x1 + n + 2.6, '#ff9cc2')])
    return ''
