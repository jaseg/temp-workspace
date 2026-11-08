"""The chart as an SVG: the cloth as one raster, the stitches as vector paths.

Kept quick to open in a PDF viewer:

- The aida cloth is a single image of the whole page. It is built from one patch of cloth repeated, in a few dozen
  colours, so it compresses to a few hundred kB.
- Stitches are grouped into one path per thread colour and layer (under leg, over leg, sheen), so a sheet with
  tens of thousands of stitches is a few hundred paths. Nothing is transparent: no soft masks or groups."""

import base64
import io
import math
import random

from PIL import Image, ImageDraw

from . import threads as th

def fmt(v):
    s = f'{v:.2f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def cloth_png(cols, rows, px, seed=1):
    """Aida cloth, `px` pixels per cell, as PNG bytes. Holes sit on the cell corners."""
    rng = random.Random(seed)
    n = 24                                  # the patch that is repeated, in cells
    cloth, hole = th.CLOTH, th.CLOTH_HOLE
    gap = tuple((a * 2 + b) // 3 for a, b in zip(cloth, hole))
    patch = Image.new('RGB', (n * px, n * px), gap)
    d = ImageDraw.Draw(patch)
    for i in range(n):
        for j in range(n):
            v = rng.uniform(-4, 4) + 3 * math.sin((i + j * .7) / n * 2 * math.pi)
            base = tuple(round(c + v) for c in cloth)
            hi = tuple(min(255, c + 6) for c in base)
            lo = tuple(c - 9 for c in base)
            x, y = i * px, j * px
            d.rectangle([x + 1, y + 1, x + px - 1, y + px - 1], fill=base)
            d.line([x + 2, y + 1, x + px - 2, y + 1], fill=hi)
            d.line([x + 1, y + 2, x + 1, y + px - 2], fill=hi)
            d.line([x + 2, y + px - 1, x + px - 1, y + px - 1], fill=lo)
            d.line([x + px - 1, y + 2, x + px - 1, y + px - 1], fill=lo)
            d.rectangle([x, y, x, y], fill=hole)          # the hole at the cell's top-left corner
    img = Image.new('RGB', (cols * px, rows * px))
    for x in range(0, img.width, patch.width):
        for y in range(0, img.height, patch.height):
            img.paste(patch, (x, y))
    img = img.quantize(64, dither=Image.Dither.NONE)
    buf = io.BytesIO()
    img.save(buf, 'PNG', compress_level=9)
    return buf.getvalue()


class Paths:
    """Path data collected per (layer, colour, width, extra attributes)."""

    def __init__(self):
        self.d = {}

    def add(self, layer, color, width, d, **extra):
        k = (layer, color, round(width, 3), tuple(sorted(extra.items())))
        self.d.setdefault(k, []).append(d)

    def svg(self, layers):
        out = []
        for layer in layers:
            for (ly, color, width, extra), ds in sorted((k, v) for k, v in self.d.items() if k[0] == layer):
                extra = dict(extra)
                cap = extra.pop('stroke_linecap', 'round')
                attrs = ''.join(f' {a.replace("_", "-")}="{v}"' for a, v in extra.items())
                if width:
                    out.append(f'<path d="{"".join(ds)}" fill="none" stroke="{color}" stroke-width="{fmt(width)}" '
                               f'stroke-linecap="{cap}" stroke-linejoin="round"{attrs}/>')
                else:
                    out.append(f'<path d="{"".join(ds)}" fill="{color}"{attrs}/>')
        return '\n'.join(out)


SHADOW = th.rgb_hex(tuple(c - 38 for c in th.CLOTH))
LAYERS = ['shadow', 'satin', 'under', 'over', 'sheen', 'back', 'back_sheen', 'text', 'knot', 'knot_sheen']

WEIGHTS = {            # thread width in mm, sheen width
    'wire': (.42, .12),
    'bus': (.8, .2),
    'line': (.30, .09),
    'fine': (.22, 0),
}


class Drawer:
    def __init__(self, chart, px_per_cell=8):
        self.c = chart
        self.px = px_per_cell
        self.paths = Paths()

    # -- stitches ----------------------------------------------------------------------
    def cross(self, i, j, col, inset=.08, w=.6):
        b = self.c.hole
        x0, y0, x1, y1 = i * b + inset, j * b + inset, (i + 1) * b - inset, (j + 1) * b - inset
        self.cross_at(x0, y0, x1, y1, col, w)

    def cross_at(self, x0, y0, x1, y1, col, w):
        """A cross stitch: the under leg (/) a shade darker, the over leg (\\) with a sliver of sheen."""
        p = self.paths
        p.add('under', th.shade(col, -.2), 0, rhomb(x0, y1, x1, y0, w))
        p.add('over', col, 0, rhomb(x0, y0, x1, y1, w))
        mx, my = (x1 - x0) * .25, (y1 - y0) * .25
        o = w * .13
        p.add('sheen', th.shade(col, .45), w * .2, f'M{fmt(x0 + mx + o)} {fmt(y0 + my - o)}'
                                                   f'L{fmt(x1 - mx + o)} {fmt(y1 - my - o)}')

    def backstitch(self, s):
        """Backstitch as a dashed thread: each dash one stitch, the gaps where the needle goes through the cloth.
        Wires start on a hole and run in whole grid steps, so their stitches end on the holes."""
        if s.weight == 'text':
            return self.text(s)
        w, sheen = WEIGHTS.get(s.weight, WEIGHTS['line'])
        p = self.paths
        d = 'M' + 'L'.join(f'{fmt(x)} {fmt(y)}' for x, y in s.pts)
        sh = .06
        if s.weight == 'bus':          # couched: a thick laid thread, tied down at every hole
            p.add('shadow', SHADOW, w + .04, d, transform=f'translate({sh} {sh})')
            p.add('back', s.color, w, d)
            p.add('back_sheen', th.shade(s.color, .35), w * .25, d, transform=f'translate({-w * .18:.2f} '
                                                                               f'{-w * .18:.2f})')
            t = .16
            p.add('back_sheen', th.shade(s.color, .6), w + .3, d, stroke_linecap='butt',
                  stroke_dasharray=f'{fmt(t)} {fmt(s.length - t)}', stroke_dashoffset=fmt(t / 2))
            return
        if not s.length:
            dash = {}
            sheen_dash = {}
        else:
            L, g = s.length, .1
            dl = max(.05, L - g - w)
            start = g / 2 + w / 2
            dash = dict(stroke_dasharray=f'{fmt(dl)} {fmt(L - dl)}', stroke_dashoffset=fmt(L - start))
            sl = dl * .55
            sheen_dash = dict(stroke_dasharray=f'{fmt(sl)} {fmt(L - sl)}',
                              stroke_dashoffset=fmt(L - start - (dl - sl) / 2))
        p.add('shadow', SHADOW, w + .04, d, transform=f'translate({sh} {sh})', **dash)
        p.add('back', s.color, w, d, **dash)
        if sheen:
            o = w * .17
            p.add('back_sheen', th.shade(s.color, .42), sheen, d, transform=f'translate({-o:.2f} {-o:.2f})',
                  **sheen_dash)

    def text(self, s):
        """Backstitched lettering: the stroke font's lines, as a dashed thread."""
        w = max(.17, min(.5, s.width * 1.35 if s.width else .2))
        d = 'M' + 'L'.join(f'{fmt(x)} {fmt(y)}' for x, y in s.pts)
        dash = f'{fmt(max(.18, w * 1.1))} {fmt(w * 1.25)}'
        self.paths.add('text', s.color, w, d, stroke_dasharray=dash)

    def knot(self, x, y, r, col):
        p = self.paths
        p.add('shadow', SHADOW, 0, circle(x + .07, y + .08, r * 1.02))
        p.add('knot', th.shade(col, -.12), 0, circle(x, y, r))
        # the wraps of the knot: a little swirl of sheen
        p.add('knot_sheen', th.shade(col, .35), r * .22,
              f'M{fmt(x - r * .55)} {fmt(y - r * .05)}A{fmt(r * .55)} {fmt(r * .55)} 0 0 1 {fmt(x + r * .3)} '
              f'{fmt(y - r * .45)}')
        p.add('knot_sheen', th.shade(col, .15), r * .18,
              f'M{fmt(x + r * .5)} {fmt(y + r * .1)}A{fmt(r * .5)} {fmt(r * .5)} 0 0 1 {fmt(x - r * .2)} '
              f'{fmt(y + r * .48)}')

    def satin(self, pts, col):
        """A small filled shape: flat thread colour, its outline a shade darker."""
        d = 'M' + 'L'.join(f'{fmt(x)} {fmt(y)}' for x, y in pts) + 'Z'
        self.paths.add('satin', col, 0, d)
        # satin stitches run across the shape: a few parallel sheen lines
        xs = [q[0] for q in pts]
        x0, x1 = min(xs), max(xs)
        lines = []
        step = .3
        k = x0 + step / 2
        while k < x1:
            seg = clip_vertical(pts, k)
            for a, b in seg:
                if b - a > .15:
                    lines.append(f'M{fmt(k)} {fmt(a + .05)}L{fmt(k)} {fmt(b - .05)}')
            k += step
        if lines:
            self.paths.add('satin', th.shade(col, .3), .07, ''.join(lines))

    # -- page --------------------------------------------------------------------------------
    def svg(self, W, H, extra=''):
        c = self.c
        for (i, j), col in sorted(c.crosses.items()):
            self.cross(i, j, col)
        for pts, col in c.satin:
            self.satin(pts, col)
        for s in c.stitches:
            self.backstitch(s)
        for x, y, sz, col in c.petite:
            ins = sz * .08
            self.cross_at(x + ins, y + ins, x + sz - ins, y + sz - ins, col, sz * .42)
        for x, y, h, col in c.big_crosses:
            self.cross_at(x - h, y - h, x + h, y + h, col, .4)
        for x, y, r, col in c.knots:
            self.knot(x, y, r, col)
        b = c.hole
        cols, rows = math.ceil(W / b), math.ceil(H / b)
        png = cloth_png(cols, rows, self.px)
        href = 'data:image/png;base64,' + base64.b64encode(png).decode()
        return (f'<?xml version="1.0" encoding="utf-8"?>\n'
                f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'width="{fmt(W)}mm" height="{fmt(H)}mm" viewBox="0 0 {fmt(W)} {fmt(H)}">\n'
                f'<rect width="{fmt(W)}" height="{fmt(H)}" fill="{th.rgb_hex(th.CLOTH)}"/>\n'
                f'<image x="0" y="0" width="{fmt(cols * b)}" height="{fmt(rows * b)}" preserveAspectRatio="none" '
                f'xlink:href="{href}"/>\n'
                f'<g id="stitches">\n{self.paths.svg(LAYERS)}\n</g>\n{extra}</svg>\n')


def rhomb(ax, ay, bx, by, w):
    """A thread from a to b as a narrow rhombus: w wide in the middle, pointed at the holes."""
    L = math.hypot(bx - ax, by - ay) or 1
    nx, ny = -(by - ay) / L * w / 2, (bx - ax) / L * w / 2
    mx, my = (ax + bx) / 2, (ay + by) / 2
    return f'M{fmt(ax)} {fmt(ay)}L{fmt(mx + nx)} {fmt(my + ny)}L{fmt(bx)} {fmt(by)}L{fmt(mx - nx)} {fmt(my - ny)}Z'


def lens(ax, ay, bx, by, w, tip=0.):
    """A thread lying from a to b: widest (w) in the middle, pinched to `tip` at the holes."""
    L = math.hypot(bx - ax, by - ay) or 1
    nx, ny = -(by - ay) / L, (bx - ax) / L
    mx, my = (ax + bx) / 2, (ay + by) / 2
    if tip:
        h, t = w / 2, tip / 2
        ux, uy = (bx - ax) / L, (by - ay) / L
        c = min(L * .3, w)
        return (f'M{fmt(ax + nx * t)} {fmt(ay + ny * t)}'
                f'C{fmt(ax + ux * c + nx * h)} {fmt(ay + uy * c + ny * h)} {fmt(bx - ux * c + nx * h)} '
                f'{fmt(by - uy * c + ny * h)} {fmt(bx + nx * t)} {fmt(by + ny * t)}'
                f'A{fmt(t)} {fmt(t)} 0 0 0 {fmt(bx - nx * t)} {fmt(by - ny * t)}'
                f'C{fmt(bx - ux * c - nx * h)} {fmt(by - uy * c - ny * h)} {fmt(ax + ux * c - nx * h)} '
                f'{fmt(ay + uy * c - ny * h)} {fmt(ax - nx * t)} {fmt(ay - ny * t)}'
                f'A{fmt(t)} {fmt(t)} 0 0 0 {fmt(ax + nx * t)} {fmt(ay + ny * t)}Z')
    return (f'M{fmt(ax)} {fmt(ay)}Q{fmt(mx + nx * w)} {fmt(my + ny * w)} {fmt(bx)} {fmt(by)}'
            f'Q{fmt(mx - nx * w)} {fmt(my - ny * w)} {fmt(ax)} {fmt(ay)}Z')


def circle(x, y, r):
    return (f'M{fmt(x - r)} {fmt(y)}A{fmt(r)} {fmt(r)} 0 1 0 {fmt(x + r)} {fmt(y)}'
            f'A{fmt(r)} {fmt(r)} 0 1 0 {fmt(x - r)} {fmt(y)}Z')


def clip_vertical(pts, x):
    """The spans (y0, y1) where the vertical line at x is inside a polygon."""
    ys = []
    n = len(pts)
    for k in range(n):
        (x1, y1), (x2, y2) = pts[k], pts[(k + 1) % n]
        if (x1 <= x) != (x2 <= x):
            ys.append(y1 + (y2 - y1) * (x - x1) / (x2 - x1))
    ys.sort()
    return list(zip(ys[0::2], ys[1::2]))
