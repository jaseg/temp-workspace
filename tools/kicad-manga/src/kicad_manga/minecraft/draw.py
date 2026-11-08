"""The world -> SVG, seen from straight above.

The blocks are drawn into one raster image at the pack's texture resolution (16 pixels per block by default), cut
into tiles: a PDF viewer then decodes a few large images instead of drawing thousands of small ones, and only the
tiles on screen when zoomed in. Text goes on top as vector paths traced from the pack's bitmap font, so it stays
sharp at any zoom."""

import base64
import io

from PIL import Image, ImageDraw

from ..svg import Markup, num, tag
from .circuit import PX_PER_CELL, STYLES
from .topdown import TopDown
from .world import dust_tint

PIXELATED = 'image-rendering:pixelated;image-rendering:crisp-edges'
TILE = 1024                 # raster tile size in pixels (libxml2 refuses attributes over 10 MB)
PLAQUE_H = 2                # plaques are 2/16 of a block thick


class Drawer:
    def __init__(self, world, pack, font, floor_of, tints, px=16, dust_width=2.0):
        self.w, self.pack, self.font = world, pack, font
        self.td = TopDown(pack, px)
        self.px = px
        self.floor_of = floor_of            # cell -> floor block name
        self.tints = tints                  # block name -> tint for its tintindex 0
        self.dust_width = dust_width
        self.glyph_paths = {}

    # -- textures ------------------------------------------------------------------
    def face_texture(self, block, face='up'):
        """(texture, tinted) a block shows on one face, from its model."""
        if block == 'water':                # liquids have no model
            return 'block/water_still', True
        m = self.pack.model(f'block/{block}')
        for el in m['elements']:
            f = el.get('faces', {}).get(face)
            if f:
                t = f.get('texture', '')
                t = m['textures'].get(t[1:], t) if t.startswith('#') else t
                return t, ('tintindex' in f)
        return f'block/{block}', False

    def floor_tile(self, block):
        tex, tinted = self.face_texture(block)
        tint = self.tints.get(block) if tinted else None
        return self.td.box(tex, 16, tint)[0]

    # -- sprites ---------------------------------------------------------------------
    def sprite(self, blk):
        """(image, height of its top) of a Block."""
        if blk.kind == 'state':
            name, props = blk.args
            props = dict(props)
            t = self.tints.get(name)
            return self.td.state(name, props, {0: t} if t else None)
        top, side, h, tint = blk.args
        return self.td.box(top, h, tint)

    def dust(self, ds, power):
        """Redstone dust with connections ds, its line and dot stretched across to `dust_width` times their width
        so that wires read on a printed page."""
        props = {d: ('side' if d in ds else 'none') for d in ('north', 'south', 'east', 'west')}
        props['power'] = power
        return self.td.state('redstone_wire', props, {0: dust_tint(power)}, model_hook=self.widen)[0]

    def widen(self, model):
        k = self.dust_width
        if k == 1:
            return model
        for el in model.get('elements', []):
            for f in el.get('faces', {}).values():
                t = f.get('texture', '')
                t = model['textures'].get(t[1:], t) if t.startswith('#') else t
                if 'dust' not in (t or ''):
                    continue
                u0, v0, u1, v1 = f.get('uv') or (0, 0, 16, 16)
                dot = 'dot' in t
                f['uv'] = [8 + (u0 - 8) / k, 8 + (v0 - 8) / k if dot else v0,
                           8 + (u1 - 8) / k, 8 + (v1 - 8) / k if dot else v1]
        return model

    # -- the raster ------------------------------------------------------------------------
    def raster(self, power):
        w, px = self.w, self.px
        W, H = (w.W - w.i0) * px, (w.H - w.j0) * px
        img = Image.new('RGBA', (W, H), (0, 0, 0, 255))

        def at(i, j):
            return (i - w.i0) * px, (j - w.j0) * px

        tiles = {}
        for j in range(w.j0, w.H):
            for i in range(w.i0, w.W):
                b = self.floor_of((i, j))
                if b not in tiles:
                    tiles[b] = self.floor_tile(b).convert('RGBA')
                img.paste(tiles[b], at(i, j))

        flat = [b for b in w.blocks if b.flat]
        tall = [b for b in w.blocks if not b.flat]
        for b in flat:
            img.alpha_composite(self.sprite(b)[0], at(b.i, b.j))
        for c, nets in w.dust.items():
            for net, ds in nets.items():
                img.alpha_composite(self.dust(ds, power(net)), at(*c))
        low = [pq for pq in w.plaques if not pq.meta.get('y')]
        high = [pq for pq in w.plaques if pq.meta.get('y')]
        for pq in low:
            self.plaque_base(img, pq, at)
        # standing blocks: lowest tops first, each with a soft shadow to the south-east
        items = [(b.y + self.sprite(b)[1], b) for b in tall]
        items.sort(key=lambda t: t[0])
        for top, b in items:
            spr, h = self.sprite(b)
            x, y = at(b.i, b.j)
            if h >= .25 and b.y == 0:
                off = max(1, round(px * min(h, 1) / 8))
                sh = Image.new('RGBA', (px, px), (0, 0, 0, 0))
                sh.putalpha(spr.getchannel('A').point(lambda v: 70 if v else 0))
                self.composite_clipped(img, sh, x + off, y + off)
            img.alpha_composite(spr, (x, y))
        for pq in high:
            self.plaque_base(img, pq, at)
        return img.convert('RGB')

    def composite_clipped(self, img, src, x, y):
        if x < 0 or y < 0 or x + src.width > img.width or y + src.height > img.height:
            return
        img.alpha_composite(src, (x, y))

    def plaque_base(self, img, pq, at):
        block = STYLES[pq.style][0]
        if not block:
            return
        tex, _ = self.face_texture(block)
        tile, _ = self.td.box(tex, 16)
        for a in range(pq.w):
            for b in range(pq.h):
                img.paste(tile, at(pq.i + a, pq.j + b))
        x0, y0 = at(pq.i, pq.j)
        x1, y1 = x0 + pq.w * self.px - 1, y0 + pq.h * self.px - 1
        d = ImageDraw.Draw(img)
        d.rectangle((x0, y0, x1, y1), outline=(30, 22, 14, 255))

    def tiles(self, img):
        out = []
        for y in range(0, img.height, TILE):
            for x in range(0, img.width, TILE):
                # one pixel of overlap, so that viewers don't show hairline seams between tiles
                t = img.crop((x, y, min(img.width, x + TILE + 1), min(img.height, y + TILE + 1)))
                buf = io.BytesIO()
                t = t.quantize(256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
                t.save(buf, 'PNG', optimize=False, compress_level=9)
                href = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
                out.append(tag('image', x=x, y=y, width=t.width, height=t.height, style=PIXELATED, href=href))
        return out

    # -- text --------------------------------------------------------------------------
    def glyph_rects(self, c):
        if c not in self.glyph_paths:
            g, adv, asc, _ = self.font.glyph(c)
            rects = []
            if g is not None:
                a = g.getchannel('A').load()
                for yy in range(g.height):
                    xx = 0
                    while xx < g.width:
                        if a[xx, yy]:
                            k = xx
                            while k < g.width and a[k, yy]:
                                k += 1
                            rects.append((xx, yy + 7 - asc, k - xx))
                            xx = k
                        else:
                            xx += 1
            self.glyph_paths[c] = (rects, adv)
        return self.glyph_paths[c]

    def text_d(self, text, dx=0, dy=0):
        """Path data of a text in font pixels, lines centred, its top-left at (dx, dy)."""
        lines = text.split('\n')
        width = max(self.font.width(s) for s in lines)
        parts = []
        for n, s in enumerate(lines):
            x = dx + (width - self.font.width(s)) // 2
            y = dy + 9 * n
            for c in s:
                rects, adv = self.glyph_rects(c)
                for gx, gy, gw in rects:
                    parts.append(f'M{x + gx} {y + gy}h{gw}v1h{-gw}z')
                x += adv
        return ''.join(parts)

    def text(self, text, x, y, w, h, scale, color, shadow, vertical=False):
        """A text centred in the box (x, y, w, h) (canvas pixels), `scale` font pixels per PX_PER_CELL-th block."""
        k = self.px / PX_PER_CELL * scale
        lines = text.split('\n')
        tw = max(self.font.width(s) for s in lines) + (1 if shadow else 0)
        th = 9 * (len(lines) - 1) + 8 + (1 if shadow else 0)
        parts = []
        if shadow:
            parts.append(tag('path', d=self.text_d(text, 1, 1), fill=rgb(tuple(c // 4 for c in color))))
        parts.append(tag('path', d=self.text_d(text), fill=rgb(color)))
        cx, cy = x + w / 2, y + h / 2
        rot = ' rotate(-90)' if vertical else ''
        tr = f'translate({num(cx)} {num(cy)}){rot} scale({num(k)}) translate({num(-tw / 2)} {num(-th / 2)})'
        return tag('g', parts, transform=tr)

    def texts(self):
        w, px = self.w, self.px
        out = []
        for pq in w.plaques:
            _, col, shadow = STYLES[pq.style]
            x, y = (pq.i - w.i0) * px, (pq.j - w.j0) * px
            out.append(self.text(pq.text, x, y, pq.w * px, pq.h * px, pq.scale, col, shadow, pq.vertical))
        for kind, text, origin, u, v in w.texts:          # pin names painted on bodies
            _, col, shadow = STYLES[kind]
            vertical = abs(u[2]) > abs(u[0])
            xs = [origin[0], origin[0] + u[0] + v[0]]
            zs = [origin[2], origin[2] + u[2] + v[2]]
            x0, z0 = (min(xs) + .5 - w.i0) * px, (min(zs) + .5 - w.j0) * px
            out.append(self.text(text, x0, z0, (max(xs) - min(xs)) * px, (max(zs) - min(zs)) * px, 1, col,
                                 shadow, vertical))
        return out

    # -- everything ----------------------------------------------------------------------------
    def page_box(self, block_mm, paper_cells, paper_mm):
        """(left, top, right, bottom) of the page in mm: the sheet, grown to take in what lies beside it."""
        w, b = self.w, block_mm
        left = 0 if w.i0 == 0 else (w.i0 - .5) * b
        top = 0 if w.j0 == 0 else (w.j0 - .5) * b
        right = paper_mm[0] if w.W <= paper_cells[0] else (w.W - .5) * b
        bottom = paper_mm[1] if w.H <= paper_cells[1] else (w.H - .5) * b
        return left, top, right, bottom

    def svg(self, power, block_mm, paper_cells, paper_mm):
        img = self.raster(power)
        self.image = img
        left, top, right, bottom = self.page_box(block_mm, paper_cells, paper_mm)
        k = self.px / block_mm                  # canvas pixels per mm

        def cx(x_mm, i0):
            return (x_mm / block_mm + .5 - i0) * self.px
        vb = (cx(left, self.w.i0), cx(top, self.w.j0), (right - left) * k, (bottom - top) * k)
        self.page_mm = (right - left, bottom - top)
        body = [tag('g', self.tiles(img), id='blocks'), tag('g', self.texts(), id='text')]
        return Markup('<?xml version="1.0" encoding="UTF-8"?>\n' + str(tag(
            'svg', body, xmlns='http://www.w3.org/2000/svg', viewBox=' '.join(num(v) for v in vb),
            width=f'{num(right - left)}mm', height=f'{num(bottom - top)}mm')))


def rgb(c):
    return '#%02x%02x%02x' % tuple(c[:3])
