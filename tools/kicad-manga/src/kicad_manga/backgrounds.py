"""Backgrounds behind text (label pills and flags, note bubbles, title banners).

They depend on the real text extents in the embedded fonts, so the renderer leaves a
`<!--bg:ID-->` marker in front of each such text and `fill()` swaps it for a shape
built from the bounding box the browser measured. All shapes are in the text's own
coordinate system (it sits in a translated/rotated <g>)."""

import re

from .circuit import hier_glyph, rounded_poly
from .palette import LINE
from .sexp import f2

MARKER = re.compile(r'<!--bg:(t\d+)-->')


def fill(svg, bgs, boxes):
    """Replace every marker; markers without a measurement are just dropped."""
    def sub(m):
        tid = m.group(1)
        if tid not in bgs or tid not in boxes:
            return ''
        return build(bgs[tid], boxes[tid])
    return MARKER.sub(sub, svg)


def build(info, box):
    kind = info[0]
    x, y, w, h = box
    if kind == 'pill':
        hh, yy = h * .86, y + h * .1
        return (f'<rect class="bg" x="{f2(x - .55)}" y="{f2(yy - .18)}" width="{f2(w + 1.1)}" height="{f2(hh + .36)}" '
                f'rx="{f2((hh + .36) / 2)}" fill="{info[1]}" stroke="{LINE}" stroke-width=".16"/>')
    if kind in ('global_label', 'hierarchical_label'):
        _, col, shape, sign, off, size = info
        y0, y1 = y + h * .08 - .3, y + h * .92 + .3
        ym, d = (y0 + y1) / 2, (y1 - y0) / 2
        xa = -sign * off
        if kind == 'hierarchical_label':
            glyph = hier_glyph(xa, ym, sign, 0, shape, size, col)
            hh = h * .86
            pill = (f'<rect class="bg" x="{f2(x - .5)}" y="{f2(y + h * .07 - .15)}" width="{f2(w + 1)}" height="{f2(hh + .3)}" '
                    f'rx="{f2((hh + .3) / 2)}" fill="{col}" fill-opacity=".55" stroke="{LINE}" stroke-width=".12" stroke-dasharray=".5 .35"/>')
            return pill + glyph
        far = (x + w if sign > 0 else x) + sign * .6
        pa = shape in ('input', 'bidirectional', 'tri_state')
        pf = shape in ('output', 'bidirectional', 'tri_state')
        if pf:
            far += sign * d
        top = [(xa, ym), (xa + sign * d, y0)] if pa else [(xa, y1), (xa, y0)]
        right = [(far - sign * d, y0), (far, ym), (far - sign * d, y1)] if pf else [(far, y0), (far, y1)]
        bottom = [(xa + sign * d, y1)] if pa else []
        poly = top + right + bottom
        return f'<path class="bg" d="{rounded_poly(poly, .35)}" fill="{col}" stroke="{LINE}" stroke-width=".2" stroke-linejoin="round"/>'
    if kind == 'bubble':
        p = 1.1
        x0, y0, x1, y1 = x - p, y - p * .7, x + w + p, y + h + p * .7
        rr = min(2.2, (y1 - y0) / 2)
        tx = x0 + min(4, (x1 - x0) * .25)
        d = (f'M{f2(x0 + rr)} {f2(y0)}H{f2(x1 - rr)}Q{f2(x1)} {f2(y0)} {f2(x1)} {f2(y0 + rr)}V{f2(y1 - rr)}'
             f'Q{f2(x1)} {f2(y1)} {f2(x1 - rr)} {f2(y1)}H{f2(tx + 2.2)}L{f2(tx - .6)} {f2(y1 + 2)}L{f2(tx + .6)} {f2(y1)}'
             f'H{f2(x0 + rr)}Q{f2(x0)} {f2(y1)} {f2(x0)} {f2(y1 - rr)}V{f2(y0 + rr)}Q{f2(x0)} {f2(y0)} {f2(x0 + rr)} {f2(y0)}Z')
        return f'<path class="bg" d="{d}" fill="#fff" stroke="{LINE}" stroke-width=".28" stroke-linejoin="round"/>'
    if kind == 'banner':
        px, py, n = 3.2, .9, 1.6
        x0, x1 = x - px, x + w + px
        y0, y1 = y + h * .08 - py, y + h * .92 + py
        ym = (y0 + y1) / 2
        rib = f'M{f2(x0 - n)} {f2(y0)}H{f2(x1 + n)}L{f2(x1)} {f2(ym)}L{f2(x1 + n)} {f2(y1)}H{f2(x0 - n)}L{f2(x0)} {f2(ym)}Z'
        out = [f'<path d="{rib}" transform="translate(.7 .7)" fill="url(#tone-ink)" opacity=".6" data-shadow=".7 .7"/>',
               f'<path class="bg" d="{rib}" fill="url(#banner-grad)" stroke="{LINE}" stroke-width=".35" stroke-linejoin="round"/>',
               f'<path d="M{f2(x0 + .6)} {f2(y0 + .7)}H{f2(x1 - .6)}M{f2(x0 + .6)} {f2(y1 - .7)}H{f2(x1 - .6)}" '
               f'stroke="#fff" stroke-width=".25" stroke-dasharray=".8 .6" fill="none"/>']
        for sx, c in ((x0 - n - 2.6, '#ffe58f'), (x1 + n + 2.6, '#ff9cc2')):
            out.append(f'<use href="#sparkle" transform="translate({f2(sx)} {f2(ym)}) scale(.36)" fill="{c}"/>')
        return ''.join(out)
    return ''
