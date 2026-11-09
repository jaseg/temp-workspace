"""The chart as an SVG: the cloth as a tiled bitmap, the stitches as vector paths.

Kept quick to open in a PDF viewer:

- The linen is one bitmap tile, 96 cells square, with slubby threads, mottling, tea stains and flax specks that
  wrap around its edges. It fills the page as a pattern of about a hundred tiles, and is stored once (a JPEG of
  about 200 kB).
- Stitches are grouped into one path per thread colour and layer (under leg, over leg, sheen), so a sheet with
  tens of thousands of stitches is a few hundred paths. Nothing is transparent: no soft masks or groups."""

import base64
import io
import math
import random

from PIL import Image, ImageDraw, ImageFilter

from . import threads as th

TILE_CELLS = 96

def fmt(v):
    s = f'{v:.2f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def wrapped_noise(size, cell, seed, blur):
    """Smooth noise that tiles seamlessly: a coarse random grid, enlarged on a 3x3 repeat and cut from the middle."""
    rng = random.Random(seed)
    n = max(2, size // cell)
    small = Image.new('L', (n, n))
    small.putdata([rng.randrange(256) for _ in range(n * n)])
    big = Image.new('L', (3 * n, 3 * n))
    for dx in range(3):
        for dy in range(3):
            big.paste(small, (dx * n, dy * n))
    big = big.resize((3 * size, 3 * size), Image.BICUBIC).filter(ImageFilter.GaussianBlur(blur))
    return big.crop((size, size, 2 * size, 2 * size))


def linen_tile(px, cells=TILE_CELLS, seed=3):
    """A seamless tile of rustic linen, `px` pixels per cell, as JPEG bytes. Holes sit on the cell corners."""
    rng = random.Random(seed)
    cloth, hole = th.CLOTH, th.CLOTH_HOLE
    T = cells * px
    gap = tuple(round(a * .6 + b * .4) for a, b in zip(cloth, hole))
    img = Image.new('RGB', (T, T), gap)
    d = ImageDraw.Draw(img)
    rowv = [rng.gauss(0, 4) for _ in range(cells)]          # slubby, uneven weft and warp threads
    colv = [rng.gauss(0, 4) for _ in range(cells)]
    for k in rng.sample(range(cells), cells // 12):
        rowv[k] += rng.choice((-1, 1)) * 6
    for k in rng.sample(range(cells), cells // 12):
        colv[k] += rng.choice((-1, 1)) * 6
    for i in range(cells):
        for j in range(cells):
            v = rowv[j] + colv[i] + rng.gauss(0, 2.5)
            base = tuple(round(c + v) for c in cloth)
            hi = tuple(min(255, c + 8) for c in base)
            lo = tuple(c - 10 for c in base)
            x, y = i * px, j * px
            d.rectangle([x + 1, y + 1, x + px - 1, y + px - 1], fill=base)
            d.line([x + 2, y + 1, x + px - 2, y + 1], fill=hi)
            d.line([x + 1, y + 2, x + 1, y + px - 2], fill=hi)
            d.line([x + 2, y + px - 1, x + px - 1, y + px - 1], fill=lo)
            d.line([x + px - 1, y + 2, x + px - 1, y + px - 1], fill=lo)
            for k in (px * 3 // 8, px * 5 // 8):            # fibres, alternating direction like a weave
                c2 = tuple(c + rng.choice((-6, -3, 4)) for c in base)
                if (i + j) % 2:
                    d.line([x + 2, y + k, x + px - 2, y + k], fill=c2)
                else:
                    d.line([x + k, y + 2, x + k, y + px - 2], fill=c2)
            hs = rng.choice((1, 1, 2))
            d.rectangle([x, y, x + hs - 1, y + hs - 1], fill=hole)
    # mottling and tea stains
    dark = Image.new('RGB', (T, T), (118, 88, 48))
    mott = wrapped_noise(T, 4 * px, seed + 1, px)
    stain = wrapped_noise(T, 12 * px, seed + 2, 3 * px).point(lambda v: 0 if v < 140 else min(255, (v - 140) * 3))
    img = Image.composite(dark, img, mott.point(lambda v: v * 40 // 255))
    img = Image.composite(dark, img, stain.point(lambda v: v * 40 // 255))
    d = ImageDraw.Draw(img)
    for _ in range(cells * cells // 64):                     # specks of flax
        x, y = rng.randrange(T), rng.randrange(T)
        L, a = rng.randrange(2, px), rng.random() * math.pi
        d.line([x, y, x + L * math.cos(a), y + L * math.sin(a)], fill=(104, 80, 50))
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=85)
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


SHADOW = th.rgb_hex(tuple(c - 50 for c in th.CLOTH))
LAYERS = ['shadow', 'satin', 'under', 'over', 'sheen', 'back', 'back_sheen', 'text', 'knot', 'knot_sheen']

THREAD = .24           # one strand of floss, in mm: every stitch is made of these
STRANDS = {            # strands laid side by side, for lines that should look heavier
    'wire': 2,
    'bus': 4,
    'line': 1,
    'fine': 1,
    'text': 1,
    'bold': 2,
}
PITCH = THREAD * .95   # strands laid side by side, just touching


def offset_polyline(pts, off):
    """A polyline moved sideways by `off` (to the left of its direction), with mitred corners."""
    if not off:
        return pts
    out = []
    n = len(pts)
    normals = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0) or 1
        normals.append(((y1 - y0) / L, -(x1 - x0) / L))
    for k, (x, y) in enumerate(pts):
        if k == 0:
            nx, ny = normals[0]
        elif k == n - 1:
            nx, ny = normals[-1]
        else:
            (ax, ay), (bx, by) = normals[k - 1], normals[k]
            mx, my = ax + bx, ay + by
            m = math.hypot(mx, my)
            if m < 1e-6:
                nx, ny = bx, by
            else:
                mx, my = mx / m, my / m
                cos = mx * ax + my * ay
                scale = 1 / max(cos, .35)
                nx, ny = mx * scale, my * scale
        out.append((x + nx * off, y + ny * off))
    return out


def strand_offsets(n):
    return [(k - (n - 1) / 2) * PITCH for k in range(n)]


def poly_d(pts):
    return 'M' + 'L'.join(f'{fmt(x)} {fmt(y)}' for x, y in pts)


class Drawer:
    def __init__(self, chart, px_per_cell=8):
        self.c = chart
        self.px = px_per_cell
        self.paths = Paths()

    # -- stitches ----------------------------------------------------------------------
    def cross(self, i, j, col, inset=.2):
        """A cross stitch in cell (i, j), a little uneven, as if stitched by hand."""
        b = self.c.hole
        h = (i * 73856093) ^ (j * 19349663)
        jx = [((h >> (5 * k)) % 9 - 4) * .012 for k in range(4)]
        x0, y0, x1, y1 = i * b + inset, j * b + inset, (i + 1) * b - inset, (j + 1) * b - inset
        self.cross_at(x0 + jx[0], y0 + jx[1], x1 + jx[2], y1 + jx[3], col, 2)

    def cross_at(self, x0, y0, x1, y1, col, strands):
        """A cross stitch, each leg `strands` strands of floss that share the holes at its ends and lie side by side
        in between: the under leg (/) a shade darker, the over leg (\\) on top with a little sheen."""
        p = self.paths
        sh = .06
        for (ax, ay, bx, by), layer, c in (((x0, y1, x1, y0), 'under', th.shade(col, -.2)),
                                           ((x0, y0, x1, y1), 'over', col)):
            L = math.hypot(bx - ax, by - ay)
            nx, ny = (by - ay) / L, -(bx - ax) / L
            mx, my = (ax + bx) / 2, (ay + by) / 2
            if layer == 'over':
                p.add('shadow', SHADOW, strands * PITCH + .04,
                      f'M{fmt(ax + sh)} {fmt(ay + sh)}L{fmt(bx + sh)} {fmt(by + sh)}')
            for off in strand_offsets(strands):
                cx, cy = mx + nx * off * 1.3, my + ny * off * 1.3
                p.add(layer, c, THREAD, f'M{fmt(ax)} {fmt(ay)}L{fmt(cx)} {fmt(cy)}L{fmt(bx)} {fmt(by)}')
                if layer == 'over':
                    o = THREAD * .15
                    p.add('sheen', th.shade(col, .28), THREAD * .3,
                          f'M{fmt((ax + cx) / 2 + o)} {fmt((ay + cy) / 2 - o)}L{fmt(cx + o)} {fmt(cy - o)}')

    def backstitch(self, s):
        """Backstitch as dashed strands of floss: each dash one stitch, the gaps where the needle goes through the
        cloth. Wires start on a hole and run in whole grid steps, so their stitches end on the holes. Heavier lines
        are several strands side by side, never a thicker thread."""
        weight = s.weight
        if weight == 'text' and s.width > .3:
            weight = 'bold'
        n = STRANDS.get(weight, 1)
        p = self.paths
        w = THREAD
        if weight in ('text', 'bold'):
            dash = dict(stroke_dasharray=f'{fmt(.3)} {fmt(.3)}')
            sheen_dash = None
        elif not s.length:
            dash, sheen_dash = {}, {}
        else:
            L, g = s.length, .12
            dl = max(.05, L - g - w)
            start = g / 2 + w / 2
            dash = dict(stroke_dasharray=f'{fmt(dl)} {fmt(L - dl)}', stroke_dashoffset=fmt(L - start))
            sl = dl * .55
            sheen_dash = dict(stroke_dasharray=f'{fmt(sl)} {fmt(L - sl)}',
                              stroke_dashoffset=fmt(L - start - (dl - sl) / 2))
        if weight == 'bus':            # couched: four laid strands, tied down at every hole
            dash, sheen_dash = {}, {}
        sh = .05
        layer = 'text' if weight in ('text', 'bold') else 'back'
        for off in strand_offsets(n):
            d = poly_d(offset_polyline(s.pts, off))
            if layer == 'back':
                p.add('shadow', SHADOW, w + .04, d, transform=f'translate({sh} {sh})', **dash)
            p.add(layer, s.color, w, d, **dash)
            if sheen_dash is not None:
                o = w * .18
                p.add('back_sheen', th.shade(s.color, .26), w * .3, d, transform=f'translate({-o:.2f} {-o:.2f})',
                      **sheen_dash)
        if weight == 'bus':
            # the couching: single-strand tie-down stitches across the laid strands, one per hole
            span = n * PITCH + .3
            t = THREAD
            p.add('back_sheen', th.shade(s.color, .5), span, poly_d(s.pts), stroke_linecap='butt',
                  stroke_dasharray=f'{fmt(t)} {fmt(s.length - t)}', stroke_dashoffset=fmt(t / 2))

    def knot(self, x, y, r, col):
        p = self.paths
        p.add('shadow', SHADOW, 0, circle(x + .07, y + .08, r * 1.02))
        p.add('knot', th.shade(col, -.12), 0, circle(x, y, r))
        # the wraps of the knot: a little swirl of sheen
        p.add('knot_sheen', th.shade(col, .35), THREAD * .45,
              f'M{fmt(x - r * .55)} {fmt(y - r * .05)}A{fmt(r * .55)} {fmt(r * .55)} 0 0 1 {fmt(x + r * .3)} '
              f'{fmt(y - r * .45)}')
        p.add('knot_sheen', th.shade(col, .15), THREAD * .35,
              f'M{fmt(x + r * .5)} {fmt(y + r * .1)}A{fmt(r * .5)} {fmt(r * .5)} 0 0 1 {fmt(x - r * .2)} '
              f'{fmt(y + r * .48)}')

    def satin(self, pts, col):
        """A small filled shape, satin stitched: single strands laid side by side across it."""
        xs = [q[0] for q in pts]
        x0, x1 = min(xs), max(xs)
        lines = []
        k = x0 + PITCH / 2
        while k < x1:
            for a, b in clip_vertical(pts, k):
                if b - a > .05:
                    lines.append(f'M{fmt(k)} {fmt(a + THREAD / 2)}L{fmt(k)} {fmt(max(a + THREAD / 2, b - THREAD / 2))}')
            k += PITCH
        if lines:
            self.paths.add('satin', col, THREAD, ''.join(lines))
            self.paths.add('shadow', SHADOW, THREAD + .04, ''.join(lines), transform='translate(.05 .05)')

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
            ins = THREAD * .7
            self.cross_at(x + ins, y + ins, x + sz - ins, y + sz - ins, col, 1)
        for x, y, h, col in c.big_crosses:
            self.cross_at(x - h, y - h, x + h, y + h, col, 2)
        for x, y, r, col in c.knots:
            self.knot(x, y, r, col)
        b = c.hole
        tile = TILE_CELLS * b
        href = 'data:image/jpeg;base64,' + base64.b64encode(linen_tile(self.px)).decode()
        return (f'<?xml version="1.0" encoding="utf-8"?>\n'
                f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'width="{fmt(W)}mm" height="{fmt(H)}mm" viewBox="0 0 {fmt(W)} {fmt(H)}">\n'
                f'<defs><pattern id="linen" patternUnits="userSpaceOnUse" width="{fmt(tile)}" height="{fmt(tile)}">'
                f'<image width="{fmt(tile)}" height="{fmt(tile)}" preserveAspectRatio="none" xlink:href="{href}"/>'
                f'</pattern></defs>\n'
                f'<rect width="{fmt(W)}" height="{fmt(H)}" fill="url(#linen)"/>\n'
                f'<g id="stitches">\n{self.paths.svg(LAYERS)}\n</g>\n{extra}</svg>\n')


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
