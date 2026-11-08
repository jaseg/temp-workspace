"""The world -> SVG: floor, flat things, text on plaques, standing blocks, in back-to-front order."""

import copy

from ..svg import Markup, num, tag
from .circuit import PX_PER_CELL, STYLES
from .iso import PIXELATED, UNIT, Atlas, Sprites, color, matrix, png_uri, proj, use
from .world import dust_tint

PLAQUE_H = 2            # plaques are 2/16 of a block thick


class Drawer:
    def __init__(self, world, pack, font, floor_of, tints):
        self.w, self.pack, self.font = world, pack, font
        self.atlas = Atlas(pack)
        self.sprites = Sprites(pack, self.atlas)
        self.floor_of = floor_of            # cell -> floor block name
        self.tints = tints                  # block name -> tint for its tintindex 0
        self.patterns = {}
        self.dust_width = 2.0
        self.pattern_defs = []

    # -- floor ---------------------------------------------------------------------
    def top_texture(self, block):
        m = self.pack.model(f'block/{block}')
        for el in m['elements']:
            f = el.get('faces', {}).get('up')
            if f:
                t = f.get('texture', '')
                t = m['textures'].get(t[1:], t) if t.startswith('#') else t
                return t, ('tintindex' in f)
        return f'block/{block}', False

    def pattern(self, tex, tint=None, shade=1.0, face='up', origin=(0, 0, 0)):
        key = (tex, tint, shade, face, origin)
        if key in self.patterns:
            return self.patterns[key]
        img = color(self.pack.texture(tex), tint, shade)
        s = img.width / 16 or 1
        pid = f'p{len(self.patterns)}'
        ox, oy = proj(*origin)
        ex = {'up': ((1, .5), (-1, .5)), 'south': ((1, .5), (0, 1)), 'east': ((1, -.5), (0, 1))}[face]
        (a, b), (c, d) = ex
        self.pattern_defs.append(tag('pattern', [tag('image', width=img.width, height=img.height, style=PIXELATED,
                                                     href=png_uri(img))],
                                     id=pid, width=img.width, height=img.height, patternUnits='userSpaceOnUse',
                                     patternTransform=f'matrix({num(a / s)} {num(b / s)} {num(c / s)} {num(d / s)} '
                                                      f'{num(ox)} {num(oy)})'))
        self.patterns[key] = pid
        return pid

    def floor(self):
        """The floor, as one parallelogram per run of cells of the same block in a row, filled with a pattern."""
        out = {}
        W, H = self.w.W, self.w.H
        for j in range(H):
            i = 0
            while i < W:
                b = self.floor_of((i, j))
                k = i
                while k + 1 < W and self.floor_of((k + 1, j)) == b:
                    k += 1
                out.setdefault(b, []).append(quad((i - .5, 0, j - .5), (k - i + 1, 0, 0), (0, 0, 1)))
                i = k + 1
        parts = []
        for b, ds in out.items():
            tex, tinted = self.top_texture(b)
            pid = self.pattern(tex, self.tints.get(b) if tinted else None, origin=(-.5, 0, -.5))
            parts.append(tag('path', d=''.join(ds), fill=f'url(#{pid})'))
        return parts

    def cliff(self, depth=3):
        """The sides of the ground along the front edges: grass, then dirt, then stone."""
        W, H = self.w.W, self.w.H
        parts = []
        layers = [('block/grass_block_side', 0, 1), ('block/dirt', 1, depth - 1), ('block/stone', depth - 1, depth)]
        for tex, y0, y1 in layers:
            ps = self.pattern(tex, None, .8, 'south', (-.5, -y0, H - .5))
            pe = self.pattern(tex, None, .6, 'east', (W - .5, -y0, H - .5))
            parts.append(tag('path', d=quad((-.5, -y0, H - .5), (W, 0, 0), (0, -(y1 - y0), 0)), fill=f'url(#{ps})'))
            parts.append(tag('path', d=quad((W - .5, -y0, H - .5), (0, 0, -H), (0, -(y1 - y0), 0)),
                             fill=f'url(#{pe})'))
        return parts

    # -- blocks ------------------------------------------------------------------------
    def sprite(self, blk, cull=()):
        if blk.kind == 'state':
            name, props = blk.args
            return self.sprites.state(name, dict(props), self.state_tints(name, dict(props)), cull)
        if blk.kind == 'box':
            top, side, h, tint = blk.args
            return self.sprites.box(top, side, h, {0: tint} if tint else None, cull)
        return blk.args[0]

    def state_tints(self, name, props):
        if name == 'redstone_wire':
            return {0: dust_tint(int(props.get('power', 15)))}
        t = self.tints.get(name)
        return {0: t} if t else None

    def dust_blocks(self):
        out = []
        for c, nets in self.w.dust.items():
            for net, ds in nets.items():
                props = {d: ('side' if d in ds else 'none') for d in ('north', 'south', 'east', 'west')}
                props['power'] = self.power(net)
                sid = self.dust_sprite(props)
                out.append((c[0] + c[1], use(sid, c[0] - .5, 0, c[1] - .5)))
        return out

    def dust_sprite(self, props):
        """Redstone dust, with its line and dot textures stretched across to `dust_width` times their width so
        that wires read well on a printed page."""
        key = ('dust', tuple(sorted(props.items())), self.dust_width)
        if (key, ()) in self.sprites.ids:
            return self.sprites.ids[(key, ())]
        k = self.dust_width
        models = []
        for m, x, y in self.pack.state_models('redstone_wire', props):
            model = copy.deepcopy(self.pack.model(m))
            for el in model['elements']:
                for f in el.get('faces', {}).values():
                    t = f.get('texture', '')
                    t = model['textures'].get(t[1:], t) if t.startswith('#') else t
                    if k != 1 and 'dust' in (t or ''):
                        u0, v0, u1, v1 = f.get('uv') or (0, 0, 16, 16)
                        dot = 'dot' in t
                        f['uv'] = [8 + (u0 - 8) / k, 8 + (v0 - 8) / k if dot else v0,
                                   8 + (u1 - 8) / k, 8 + (v1 - 8) / k if dot else v1]
            models.append((model, x, y))
        return self.sprites.get(key, models, {0: dust_tint(int(props['power']))})

    def blocks(self, flat):
        boxes = {}
        for b in self.w.blocks:
            if b.kind == 'box':
                boxes[(b.i, b.y, b.j)] = (b.owner, b.args[2])
        out = []
        for b in self.w.blocks:
            if b.flat != flat:
                continue
            cull = ()
            if b.kind == 'box':
                me = (b.owner, b.args[2])
                cull = tuple(d for d, n in (('east', (b.i + 1, b.y, b.j)), ('south', (b.i, b.y, b.j + 1)))
                             if boxes.get(n) == me)
                if boxes.get((b.i, b.y + 1, b.j)) is not None and b.args[2] == 16:
                    cull += ('up',)
            out.append((b.i + b.j + b.y + (.5 if not flat else 0), use(self.sprite(b, cull), b.i - .5, b.y, b.j - .5)))
        return out

    # -- text ----------------------------------------------------------------------------
    def text_use(self, text, color_, shadow, origin, u_dir, v_dir, scale):
        img = self.font.render(text, color_, shadow)
        iid, w, h = self.atlas.raw(img, ('text', text, color_, shadow))
        tw, th = w * scale / PX_PER_CELL, h * scale / PX_PER_CELL
        u = tuple(c * tw for c in u_dir)
        v = tuple(c * th for c in v_dir)
        return tag('use', href=f'#{iid}', transform=matrix(origin, u, v, w, h)), tw, th

    def plaques(self):
        flat, texts = [], []
        for pq in self.w.plaques:
            block, col, shadow = STYLES[pq.style]
            y = PLAQUE_H / 16
            if block:
                tex, _ = self.top_texture(block)
                side = self.side_texture(block)
                for a in range(pq.w):
                    for b in range(pq.h):
                        cull = tuple(d for d, ok in (('east', a + 1 < pq.w), ('south', b + 1 < pq.h)) if ok)
                        sid = self.sprites.box(tex, side, PLAQUE_H, None, cull)
                        i, j = pq.i + a, pq.j + b
                        flat.append((i + j, use(sid, i - .5, 0, j - .5)))
            x0, z0 = pq.i - .5, pq.j - .5
            img = self.font.render(pq.text, col, shadow)
            tw, th = img.width * pq.scale / PX_PER_CELL, img.height * pq.scale / PX_PER_CELL
            if not pq.vertical:
                origin = (x0 + (pq.w - tw) / 2, y, z0 + (pq.h - th) / 2)
                t, _, _ = self.text_use(pq.text, col, shadow, origin, (1, 0, 0), (0, 0, 1), pq.scale)
            else:
                origin = (x0 + (pq.w - th) / 2, y, z0 + pq.h - (pq.h - tw) / 2)
                t, _, _ = self.text_use(pq.text, col, shadow, origin, (0, 0, -1), (1, 0, 0), pq.scale)
            texts.append(t)
        return flat, texts

    def side_texture(self, block):
        m = self.pack.model(f'block/{block}')
        for el in m['elements']:
            f = el.get('faces', {}).get('south')
            if f:
                t = f.get('texture', '')
                return m['textures'].get(t[1:], t) if t.startswith('#') else t
        return f'block/{block}'

    def free_texts(self):
        out = []
        for kind, text, origin, u, v in self.w.texts:
            _, col, shadow = STYLES[kind]
            img = self.font.render(text, col, shadow)
            iid, w, h = self.atlas.raw(img, ('text', text, col, shadow))
            # u, v: the vectors for the text's own size (without the shadow pixel)
            un = self.font.width(text) or 1
            scale_u = w / un
            uu = tuple(c * scale_u for c in u)
            vv = tuple(c * h / PX_PER_CELL for c in v)
            out.append(tag('use', href=f'#{iid}', transform=matrix(origin, uu, vv, w, h)))
        return out

    # -- everything ------------------------------------------------------------------------
    def svg(self, power, sky, extra_tall=(), extra_flat=(), page_mm=None, background=()):
        self.power = power
        floor = self.floor()
        cliff = self.cliff()
        flat = self.blocks(True) + self.dust_blocks() + list(extra_flat)
        pflat, ptexts = self.plaques()
        flat += pflat
        flat.sort(key=lambda t: t[0])
        tall = self.blocks(False) + list(extra_tall)
        tall.sort(key=lambda t: t[0])
        texts2 = self.free_texts()

        W, H = self.w.W, self.w.H
        x0 = proj(-.5, 0, H - .5)[0] - UNIT
        x1 = proj(W - .5, 0, -.5)[0] + UNIT
        y0 = proj(-.5, 0, -.5)[1] - UNIT * 8
        y1 = proj(W - .5, -3, H - .5)[1] + UNIT
        vw, vh = x1 - x0, y1 - y0
        if page_mm:
            pw, ph = page_mm
            s = min(pw / vw, ph / vh)
            # centre the scene on the page
            x0 -= (pw / s - vw) / 2
            y0 -= (ph / s - vh) / 2
            vw, vh = pw / s, ph / s
            size = dict(width=f'{num(pw)}mm', height=f'{num(ph)}mm')
        else:
            size = dict(width=num(vw), height=num(vh))
        defs = tag('defs', [Markup(''.join(self.pattern_defs)), Markup(''.join(self.atlas.defs)),
                            Markup(''.join(self.sprites.defs)), *sky.get('defs', [])])
        body = [tag('rect', x=x0, y=y0, width=vw, height=vh, fill=sky.get('fill', '#9ec6ff')), *background,
                tag('g', floor + cliff, id='floor'),
                tag('g', [m for _, m in flat], id='flat'),
                tag('g', ptexts, id='plaques-text'),
                tag('g', [m for _, m in tall], id='blocks'),
                tag('g', texts2, id='painted-text')]
        return Markup('<?xml version="1.0" encoding="UTF-8"?>\n' + str(tag(
            'svg', [defs, *body], xmlns='http://www.w3.org/2000/svg', viewBox=f'{num(x0)} {num(y0)} {num(vw)} {num(vh)}',
            **size)))


def quad(o, u, v):
    p0 = proj(*o)
    p1 = proj(o[0] + u[0], o[1] + u[1], o[2] + u[2])
    p2 = proj(o[0] + u[0] + v[0], o[1] + u[1] + v[1], o[2] + u[2] + v[2])
    p3 = proj(o[0] + v[0], o[1] + v[1], o[2] + v[2])
    return 'M' + 'L'.join(f'{num(x)} {num(y)}' for x, y in (p0, p1, p2, p3)) + 'Z'
