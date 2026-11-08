"""The world -> SVG, seen from high up in the south (see `oblique`), with the page frame and all text drawn flat
on top.

The blocks are drawn into one raster image at the pack's texture resolution (16 pixels per block by default), cut
into tiles: a PDF viewer then decodes a few large images instead of drawing thousands of small ones, and only the
tiles on screen when zoomed in. Text goes on top as vector paths traced from the pack's bitmap font, so it stays
sharp at any zoom."""

import base64
import io

from PIL import Image, ImageDraw

from ..svg import Markup, num, tag
from .circuit import STYLES
from .oblique import Oblique
from .topdown import TopDown
from .world import dust_tint

PIXELATED = 'image-rendering:pixelated;image-rendering:crisp-edges'
TILE = 1024                 # raster tile size in pixels (libxml2 refuses attributes over 10 MB)
PLAQUE_H = 2                # plaques are 2/16 of a block thick


class Drawer:
    def __init__(self, world, pack, font, page, px=16, dust_width=2.0, fpx=20, camera_deg=60):
        self.w, self.pack, self.font = world, pack, font
        self.td = TopDown(pack, px)                 # flat things, and the frame overlay
        self.ob = Oblique(pack, px, camera_deg)     # everything that stands up
        self.px = px
        self.page = page
        self.floor_of = page.floor_of               # cell -> floor block name
        self.tints = page.tints                     # block name -> tint for its tintindex 0
        self.dust_width = dust_width
        self.fpx = fpx                              # font pixels per block
        self.glyph_paths = {}

    def lift(self, h):
        """Pixels by which a height of h blocks shows up on the page."""
        return h * self.ob.s * self.px

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
    def tint_of(self, name):
        t = self.tints.get(name)
        return {0: t} if t else None

    def flat_sprite(self, blk):
        """Top-down image of a Block."""
        if blk.kind == 'state':
            name, props = blk.args
            return self.td.state(name, dict(props), self.tint_of(name))[0]
        top, side, h, tint = blk.args
        return self.td.box(top, h, tint)[0]

    def sprite(self, blk):
        """(image, up) of a standing Block seen from the camera."""
        if blk.kind == 'state':
            name, props = blk.args
            return self.ob.state(name, dict(props), self.tint_of(name))
        top, side, h, tint = blk.args
        return self.ob.box(top, side, h, tint)

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
    def at(self, i, j):
        w = self.w
        return (i - w.i0) * self.px, (j - w.j0) * self.px

    def raster(self, power):
        w, px = self.w, self.px
        W, H = (w.W - w.i0) * px, (w.H - w.j0) * px
        img = Image.new('RGBA', (W, H), (0, 0, 0, 255))
        at = self.at

        tiles = {}
        for j in range(w.j0, w.H):
            for i in range(w.i0, w.W):
                b = self.floor_of((i, j))
                if b not in tiles:
                    tiles[b] = self.floor_tile(b).convert('RGBA')
                img.paste(tiles[b], at(i, j))

        world = [b for b in w.blocks if not b.overlay]
        for b in world:
            if b.flat:
                blit(img, self.flat_sprite(b), *at(b.i, b.j))
        for c, nets in w.dust.items():
            for net, ds in nets.items():
                blit(img, self.dust(ds, power(net)), *at(*c))

        # everything that stands up, and the plaques, from the back (north) to the front, lowest first
        items = [((b.j, b.y, b.i), 'block', b) for b in world if not b.flat]
        items += [((pq.j + pq.h - 1, pq.meta.get('y', 0), pq.i), 'plaque', pq)
                  for pq in w.plaques if not pq.meta.get('overlay')]
        items.sort(key=lambda t: t[0])
        self.shadows(img, [b for _, kind, b in items if kind == 'block'])
        for _, kind, it in items:
            if kind == 'block':
                spr, up = self.sprite(it)
                x, y = at(it.i, it.j)
                blit(img, spr, x, y - up - round(self.lift(it.y)))
            else:
                self.plaque(img, it)

        # the page frame, flat on top
        for c in self.page.overlay_cells:
            if w.inside(c):
                b = self.floor_of(c)
                if b not in tiles:
                    tiles[b] = self.floor_tile(b).convert('RGBA')
                img.paste(tiles[b], at(*c))
        for b in sorted((b for b in w.blocks if b.overlay), key=lambda b: b.y):
            blit(img, self.flat_sprite(b), *at(b.i, b.j))
        for pq in w.plaques:
            if pq.meta.get('overlay'):
                self.plaque(img, pq)
        return img.convert('RGB')

    def shadows(self, img, blocks):
        """A soft shadow to the south-east of whatever stands on the ground, under all of it."""
        px = self.px
        layer = Image.new('L', img.size, 0)
        for b in blocks:
            if b.y:
                continue
            spr = self.flat_sprite(b)
            h = self.sprite(b)[1] / (self.ob.s * px) if self.ob.s else 0
            if h < .25:
                continue
            off = max(1, round(px * min(h, 1.5) / 6))
            x, y = self.at(b.i, b.j)
            a = spr.getchannel('A').point(lambda v: 80 if v else 0)
            if 0 <= x + off and x + off + px <= img.width and 0 <= y + off // 2 and y + off // 2 + px <= img.height:
                region = (x + off, y + off // 2, x + off + px, y + off // 2 + px)
                layer.paste(Image.composite(a, layer.crop(region), a), region)
        black = Image.new('RGBA', img.size, (20, 16, 10, 255))
        black.putalpha(layer)
        img.alpha_composite(black)

    def plaque(self, img, pq):
        """A plaque's base: a thin slab of block texture, outlined, raised on top of the blocks under it when it
        has a height."""
        block = STYLES[pq.style][0]
        if not block:
            return
        px = self.px
        x0, y0 = self.at(pq.i, pq.j)
        if pq.meta.get('overlay'):
            tex, _ = self.face_texture(block)
            tile, _ = self.td.box(tex, 16)
            for a in range(pq.w):
                for b in range(pq.h):
                    img.paste(tile, (x0 + a * px, y0 + b * px))
            ImageDraw.Draw(img).rectangle((x0, y0, x0 + pq.w * px - 1, y0 + pq.h * px - 1),
                                          outline=(60, 40, 30, 255))
            return
        top, _ = self.face_texture(block)
        side, _ = self.face_texture(block, 'south')
        spr, up = self.ob.box(top, side, PLAQUE_H)
        dy = round(self.lift(pq.meta.get('y', 0)))
        for b in range(pq.h):
            for a in range(pq.w):
                blit(img, spr, x0 + a * px, y0 + b * px - up - dy)
        lift = up + dy
        ImageDraw.Draw(img).rectangle((x0, y0 - lift, x0 + pq.w * px - 1, y0 + pq.h * px - 1 - lift),
                                      outline=(60, 40, 30, 255))

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
        """A text centred in the box (x, y, w, h) (canvas pixels), `scale` font pixels per `fpx`-th block."""
        k = self.px / self.fpx * scale
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
            if not pq.meta.get('overlay') and STYLES[pq.style][0]:
                y -= self.ob.box(*(self.face_texture(STYLES[pq.style][0], f)[0] for f in ('up', 'south')),
                                 PLAQUE_H)[1] + round(self.lift(pq.meta.get('y', 0)))
            out.append(self.text(pq.text, x, y, pq.w * px, pq.h * px, pq.scale, col, shadow, pq.vertical))
        for kind, text, origin, u, v in w.texts:          # pin names painted on bodies
            _, col, shadow = STYLES[kind]
            lift = self.lift(origin[1]) / px
            vertical = abs(u[2]) > abs(u[0])
            xs = [origin[0], origin[0] + u[0] + v[0]]
            zs = [origin[2], origin[2] + u[2] + v[2]]
            x0, z0 = (min(xs) + .5 - w.i0) * px, (min(zs) + .5 - w.j0 - lift) * px
            out.append(self.text(text, x0, z0, (max(xs) - min(xs)) * px, (max(zs) - min(zs)) * px, 1, col,
                                 shadow, vertical))
        return out

    # -- everything ----------------------------------------------------------------------------
    def page_box(self, cell_of, paper_cells, paper_mm):
        """(left, top, right, bottom) of the page in mm: the sheet, grown to take in what lies beside it.
        `cell_of` maps a cell to its centre in mm."""
        w = self.w
        (x0, y0), (x1, y1) = cell_of(w.i0 - .5, w.j0 - .5), cell_of(w.W - .5, w.H - .5)
        left = 0 if w.i0 >= 0 else x0
        top = 0 if w.j0 >= 0 else y0
        right = paper_mm[0] if w.W <= paper_cells[0] else x1
        bottom = paper_mm[1] if w.H <= paper_cells[1] else y1
        return left, top, right, bottom

    def svg(self, power, cell_of, block_mm, paper_cells, paper_mm):
        img = self.raster(power)
        self.image = img
        left, top, right, bottom = self.page_box(cell_of, paper_cells, paper_mm)
        k = self.px / block_mm                  # canvas pixels per mm
        ox, oy = cell_of(self.w.i0 - .5, self.w.j0 - .5)     # mm of the canvas's top-left corner
        vb = ((left - ox) * k, (top - oy) * k, (right - left) * k, (bottom - top) * k)
        self.page_mm = (right - left, bottom - top)
        body = [tag('g', self.tiles(img), id='blocks'), tag('g', self.texts(), id='text')]
        return Markup('<?xml version="1.0" encoding="UTF-8"?>\n' + str(tag(
            'svg', body, xmlns='http://www.w3.org/2000/svg', viewBox=' '.join(num(v) for v in vb),
            width=f'{num(right - left)}mm', height=f'{num(bottom - top)}mm')))


def rgb(c):
    return '#%02x%02x%02x' % tuple(c[:3])


def blit(dst, src, x, y):
    """alpha_composite that clips at the edges."""
    if x >= dst.width or y >= dst.height or x + src.width <= 0 or y + src.height <= 0:
        return
    cx, cy = max(0, -x), max(0, -y)
    if cx or cy or x + src.width > dst.width or y + src.height > dst.height:
        src = src.crop((cx, cy, min(src.width, dst.width - x), min(src.height, dst.height - y)))
    dst.alpha_composite(src, (x + cx, y + cy))
