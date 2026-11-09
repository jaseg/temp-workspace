"""The world -> SVG, seen from high up in the south (see `oblique`), with the page frame and all text drawn flat
on top.

The blocks are drawn into one raster image at the pack's texture resolution (16 pixels per block by default), cut
into tiles: a PDF viewer then decodes a few large images instead of drawing thousands of small ones, and only the
tiles on screen when zoomed in. Text goes on top as vector paths traced from the pack's bitmap font, so it stays
sharp at any zoom."""

import base64
import io
import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..svg import Markup, num, tag
from . import mobs
from .circuit import STYLES
from .oblique import Oblique
from .topdown import TopDown, default_uv
from .world import dust_tint

PIXELATED = 'image-rendering:pixelated;image-rendering:crisp-edges'
TILE = 1024                 # raster tile size in pixels (libxml2 refuses attributes over 10 MB)
PLAQUE_H = 2                # plaques are 2/16 of a block thick


class Drawer:
    def __init__(self, world, pack, font, page, px=16, dust_width=2.0, fpx=20, camera_deg=65, yaw_deg=30):
        self.w, self.pack, self.font = world, pack, font
        if not getattr(pack, 'print_ready', False):         # see `printable`
            raw, done = pack.texture, {}

            def texture(rid):
                if rid not in done:
                    done[rid] = printable(rid, raw(rid))
                return done[rid]
            pack.texture = texture
            pack.print_ready = True
        self.td = TopDown(pack, px)                 # flat things, and the frame overlay
        self.ob = Oblique(pack, px, camera_deg, yaw_deg)    # everything that stands up
        self.px = px
        self.page = page
        self.floor_of = page.floor_of               # cell -> floor block name
        self.tints = page.tints                     # block name -> tint for its tintindex 0
        self.dust_width = dust_width
        self.fpx = fpx                              # font pixels per block
        self.glyph_paths = {}

    def shift(self, h):
        """(dx, dy) in pixels by which a height of h blocks moves things on the page (up and a little west)."""
        return round(h * self.ob.h * self.px), -round(h * self.ob.s * self.px)

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
        """A floor tile; 'name|tag' is block `name` in the tint registered for the whole key (a biome's grass)."""
        name, _, tag = block.partition('|')
        tag = tag.split('|')[0]
        if name == 'water' and tag:         # clear water: the lake bed (`tag`) seen through it
            bed = self.floor_tile(tag).convert('RGBA')
            tex, _ = self.face_texture('water')
            water = self.td.box(tex, 16, self.tints.get('water'))[0].convert('RGBA')
            water.putalpha(water.getchannel('A').point(lambda v: min(255, v * 215 // 255 + 40)))
            bed = Image.merge('RGBA', [c.point(lambda v: v * 3 // 4) for c in bed.split()[:3]] +
                              [bed.getchannel('A')])                    # dimmer under water
            bed.alpha_composite(water)
            return bed
        tex, tinted = self.face_texture(name)
        tint = self.tints.get(block, self.tints.get(name)) if tinted else None
        return self.td.box(tex, 16, tint)[0]

    # -- sprites ---------------------------------------------------------------------
    def tint_of(self, name, args=()):
        """Tints for a block state: its own (a third entry of a Block's args), or the page's for its name."""
        t = args[2] if len(args) > 2 else self.tints.get(name)
        return {0: t} if t else None

    @staticmethod
    def plates_model(d, textures, h=12):
        """Two upright plates across direction d (a cell step), the first one nearer the start of d."""
        els = []
        for (a, b), t in zip(((2, 6), (10, 14)), textures):
            if d[0] + d[1] < 0:
                a, b = 16 - b, 16 - a
            fr, to = ([a, 0, 1], [b, h, 15]) if d[0] else ([1, 0, a], [15, h, b])
            els.append({'from': fr, 'to': to, 'faces': {f: {'texture': t} for f in
                                                        ('up', 'north', 'south', 'east', 'west')}})
        return {'textures': {}, 'elements': els}

    def flat_sprite(self, blk):
        """Top-down image of a Block."""
        if blk.kind == 'plates':
            return self.td.compose([(self.plates_model(*blk.args), 0, 0)], None)[0]
        if blk.kind == 'state':
            name, props = blk.args[:2]
            return self.td.state(name, dict(props), self.tint_of(name, blk.args))[0]
        if blk.kind == 'mob':
            key = ('mob', blk.args)
            if key not in self.td.cache:
                self.td.cache[key] = self.td.compose([(mobs.model(blk.args[0]), 0, blk.args[1])], None)
            return self.td.cache[key][0]
        top, side, h, tint = blk.args
        return self.td.box(top, h, tint)[0]

    def sprite(self, blk):
        """(image, up, left) of a standing Block seen from the camera."""
        if blk.kind == 'plates':
            key = ('plates', blk.args)
            if key not in self.ob.cache:
                self.ob.cache[key] = self.ob.compose([(self.plates_model(*blk.args), 0, 0)], None)
            return self.ob.cache[key]
        if blk.kind == 'state':
            name, props = blk.args[:2]
            return self.ob.state(name, dict(props), self.tint_of(name, blk.args), model_hook=SUNK.get(name))
        if blk.kind == 'mob':
            key = ('mob', blk.args)
            if key not in self.ob.cache:
                self.ob.cache[key] = self.ob.compose([(mobs.model(blk.args[0]), 0, blk.args[1])], None)
            return self.ob.cache[key]
        top, side, h, tint = blk.args
        return self.ob.box(top, side, h, tint)

    def dust(self, ds, power):
        """Redstone dust with connections ds. Its lines are stretched across to `dust_width` times their width so
        that wires read on a printed page; the dot keeps its size and only marks junctions and lone ends, not
        plain corners."""
        props = {d: ('side' if d in ds else 'none') for d in ('north', 'south', 'east', 'west')}
        props['power'] = power
        corner = len(ds) == 2 and not ({'north', 'south'} == set(ds) or {'east', 'west'} == set(ds))
        hook = self.widen_corner if corner else self.widen
        return self.td.state('redstone_wire', props, {0: dust_tint(power)}, model_hook=hook)[0]

    def ponds(self, img, pond):
        """Ponds as pits seen through clear water: a bed of sand, gravel, clay or dirt one or two blocks down, the
        dirt walls around it where they face the camera, all of it seen only through the pond's surface."""
        px = self.px
        depth = {c: int(b.split('|')[2]) for c, b in pond.items()}
        xs = [self.at(*c)[0] for c in pond]
        ys = [self.at(*c)[1] for c in pond]
        x0, y0 = min(xs) - 2 * px, min(ys) - 2 * px
        pit = Image.new('RGBA', (max(xs) + 3 * px - x0, max(ys) + 3 * px - y0), (0, 0, 0, 0))
        opening = Image.new('L', pit.size, 0)
        for (i, j), b in sorted(pond.items(), key=lambda t: (t[0][1], t[0][0])):
            x, y = self.at(i, j)
            x, y = x - x0, y - y0
            D = depth[(i, j)]
            bed = self.floor_tile(b.split('|')[1]).convert('RGBA')
            bed = Image.merge('RGBA', [c.point(lambda v, k=D: v * (10 - 2 * k) // 10) for c in bed.split()[:3]] +
                              [bed.getchannel('A')])
            dx, dy = self.shift(-D)
            blit(pit, bed, x + dx, y + dy)
            opening.paste(255, (x, y, x + px, y + px))
        # then the walls behind each cell (the south face of the cell north of it, the east face of the one west
        # of it), over the beds, which never reach up the walls
        for (i, j) in sorted(pond, key=lambda c: (c[1], c[0])):
            x, y = self.at(i, j)
            x, y = x - x0, y - y0
            D = depth[(i, j)]
            for (a, bb), face in (((0, -1), 'south'), ((-1, 0), 'east')):
                top = depth.get((i + a, j + bb), 0)
                if top < D:
                    spr, up, left = self.wall(face, D - top, top == 0)
                    dx, dy = self.shift(-D)
                    blit(pit, spr, x + a * px - left + dx, y + bb * px - up + dy)
        water = self.td.box(self.face_texture('water')[0], 16, self.tints.get('water'))[0].convert('RGBA')
        water.putalpha(water.getchannel('A').point(lambda v: min(255, v * 170 // 255 + 30)))
        for (i, j) in pond:
            x, y = self.at(i, j)
            pit.alpha_composite(water, (x - x0, y - y0))
        clear = Image.new('RGBA', pit.size, (0, 0, 0, 0))
        img.paste(Image.composite(pit, clear, opening), (x0, y0), opening)

    def wall(self, face, h, top):
        """A pit wall facing `face`, h blocks high: dirt, with the grass's side under the rim."""
        key = ('wall', face, h, top)
        if key not in self.ob.cache:
            els = []
            for k in range(h):
                tex = 'block/dirt'
                els.append({'from': [0, 16 * k, 0], 'to': [16, 16 * (k + 1), 16],
                            'faces': {face: {'texture': tex, 'uv': [0, 0, 16, 16]}}})
            self.ob.cache[key] = self.ob.compose([({'textures': {}, 'elements': els}, 0, 0)], None)
        return self.ob.cache[key]

    @staticmethod
    def crossing(nets):
        """Where two wires cross without joining (one straight east-west, the other straight north-south), the
        east-west one jumps over the other: returns that net, or None."""
        if len(nets) != 2:
            return None
        (a, da), (b, db) = nets.items()
        ew, ns = {'east', 'west'}, {'north', 'south'}
        if set(da) == ew and set(db) == ns:
            return a
        if set(db) == ew and set(da) == ns:
            return b
        return None

    HOP_H = .5          # how high (blocks) a wire jumps over another

    def hop(self, east_west, power):
        """A wire jumping over a crossing one, like the little arcs on old schematics, here lifted into the
        third dimension: it rises from the ground at the cell's edges to HOP_H in the middle, with its shadow
        on the ground below. Returns (image, x, y) with (x, y) the cell's top-left corner in the image."""
        key = ('hop', east_west, power)
        if key in self.td.cache:
            return self.td.cache[key]
        px, S = self.px, 4                      # drawn 4x larger, then scaled down for smooth edges
        m = px // 2
        size = (px + 2 * m) * S
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        a = .1                                  # flat bit at each end, where it meets the wire next to it

        def lift(t):
            u = min(1, max(0, (t - a) / (1 - 2 * a)))
            return self.HOP_H * math.sin(math.pi * u)

        def at(t, h, sun=False):
            g = (t * px, px / 2) if east_west else (px / 2, t * px)
            if sun:
                dx, dy = self.SUN[0] * h * px, self.SUN[1] * h * px
            else:
                dx, dy = h * self.ob.h * px, -h * self.ob.s * px
            return ((g[0] + dx + m) * S, (g[1] + dy + m) * S)
        ts = [k / 40 for k in range(41)]
        shadow = [at(t, lift(t), sun=True) for t in ts if lift(t) > .02]
        line = [at(t, lift(t)) for t in ts]
        w = max(2, round(px * .22))
        if len(shadow) > 1:
            d.line(shadow, fill=(10, 10, 25, 90), width=w * S, joint='curve')
        r, g, b = dust_tint(power)
        d.line(line, fill=(40, 6, 6, 255), width=(w + 2) * S, joint='curve')
        d.line(line, fill=(min(255, r + 40), min(255, g + 20), min(255, b + 20), 255), width=w * S, joint='curve')
        img = img.resize((px + 2 * m, px + 2 * m), Image.LANCZOS)
        self.td.cache[key] = (img, m, m)
        return self.td.cache[key]

    def widen(self, model, dot=True):
        k = self.dust_width
        for el in model.get('elements', []):
            faces = el.get('faces', {})
            for name, f in list(faces.items()):
                t = f.get('texture', '')
                t = model['textures'].get(t[1:], t) if t.startswith('#') else t
                if 'dust' not in (t or ''):
                    continue
                if 'dot' in t:
                    if not dot:
                        del faces[name]
                    continue
                u0, v0, u1, v1 = f.get('uv') or (0, 0, 16, 16)
                f['uv'] = [8 + (u0 - 8) / k, v0, 8 + (u1 - 8) / k, v1]
        return model

    def widen_corner(self, model):
        return self.widen(model, dot=False)

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
        pond = {}
        for j in range(w.j0, w.H):
            for i in range(w.i0, w.W):
                b = self.floor_of((i, j))
                if b.startswith('water|') and b.count('|') == 2:
                    pond[(i, j)] = b
                    continue
                if b not in tiles:
                    tiles[b] = self.floor_tile(b).convert('RGBA')
                img.paste(tiles[b], at(i, j))
        if pond:
            self.ponds(img, pond)

        world = [b for b in w.blocks if not b.overlay]
        self.lift_hidden_plaques(world)
        for b in world:
            if b.flat:
                blit(img, self.flat_sprite(b), *at(b.i, b.j))
        hops = []
        for c, nets in w.dust.items():
            over = self.crossing(nets)
            for net, ds in nets.items():
                if net == over:
                    hops.append((c, net, ds))
                else:
                    blit(img, self.dust(ds, power(net)), *at(*c))
        for c, net, ds in hops:         # after all the flat dust, so nothing is drawn over a bridge
            spr, ox, oy = self.hop('east' in ds, power(net))
            x, y = at(*c)
            blit(img, spr, x - ox, y - oy)

        # everything that stands up, and the plaques, from the back (north) to the front, lowest first
        items = [((b.j, b.y, b.i, 0), 'block', b) for b in world if not b.flat]
        items += [((pq.j + pq.h - 1, pq.meta.get('y', 0), pq.i, 0), 'plaque', pq)
                  for pq in w.plaques if not pq.meta.get('overlay')]
        items += self.occlusion(world)
        items.sort(key=lambda t: t[0])
        items += self.edges(world)
        items.sort(key=lambda t: t[0])
        top_shadow = self.shadows(img, [b for b in world if not b.flat])
        dark = Image.new('RGBA', (self.px, self.px), (16, 20, 40, 255))
        for _, kind, it in items:
            if kind == 'block':
                spr, up, left = self.sprite(it)
                x, y = at(it.i, it.j)
                dx, dy = self.shift(it.y)
                blit(img, spr, x - left + dx, y - up + dy)
                m = top_shadow.get((it.i, it.j)) if it.owner == 'hill' else None
                if m is not None and it.y + 1 == self.column_top.get((it.i, it.j)):
                    ddx, ddy = self.shift(it.y + 1)
                    sh = dark.copy()
                    sh.putalpha(m)
                    blit(img, sh, x + ddx, y + ddy)
            elif kind == 'edge':
                (i, j), h, sides = it
                x, y = at(i, j)
                dx, dy = self.shift(h)
                for side in sides:
                    blit(img, self.edge_strip(side), x + dx, y + dy)
            elif kind == 'ao':
                (i, j), h, sides = it
                x, y = at(i, j)
                dx, dy = self.shift(h)
                for side in sides:
                    blit(img, self.ao_strip(side), x + dx, y + dy)
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

    def lift_hidden_plaques(self, blocks):
        """Plaques that something standing south or east of them leans over (a house, a tree, a hill) would be
        hidden or have their text land on a busy roof: those are drawn flat on top of everything instead."""
        covered = {}
        s, h, px = self.ob.s, self.ob.h, self.px
        if not s:
            return
        for b in blocks:
            if b.flat:
                continue
            up = self.sprite(b)[1]
            top = b.y + up / (s * px)
            if top <= .3:
                continue
            t = max(b.y, .3)
            while t <= top + 1e-6:
                x, z = b.i + h * t, b.j - s * t
                for i in {math.floor(x), math.ceil(x)}:
                    for j in {math.floor(z), math.ceil(z)}:
                        covered[(i, j)] = max(covered.get((i, j), 0), t)
                t += .5
        for pq in self.w.plaques:
            if pq.meta.get('overlay'):
                continue
            y = pq.meta.get('y', 0) + PLAQUE_H / 16
            if any(covered.get((pq.i + a, pq.j + b), 0) > y for a in range(pq.w) for b in range(pq.h)):
                pq.meta['overlay'] = True
                pq.meta['lifted'] = True

    SUN = (-1.0, -1.45)             # how far a shadow moves (east, south) per block of height: a low sun, ~35 deg up

    # Soft shadows: the sun is a disc, not a point, so a shadow's edge blurs the more, the farther it falls from
    # what casts it. The sweep is cut into bands by the height of the casting part, each blurred by its own radius
    # (in blocks).
    SHADOW_BANDS = ((0, .5, .12), (.5, 1.5, .3), (1.5, 3, .55), (3, math.inf, .85))
    SHADOW_ALPHA = 64

    def casters(self, blocks):
        """What throws shadows: (x, y, bottom, top, mask) with (x, y) the cell's corner on the page. Hills throw
        theirs as whole columns from the ground up (only their outer blocks are drawn)."""
        px = self.px
        full = Image.new('L', (px, px), 255)
        out, cols = [], {}
        for b in blocks:
            if b.owner == 'hill':
                c = (b.i, b.j)
                cols[c] = max(cols.get(c, 0), b.y + 1)
                continue
            up = self.sprite(b)[1]
            top = up / (self.ob.s * px) if self.ob.s else 0
            if top < .2:
                continue
            mask = self.footprint(b)
            if mask is None:
                continue
            out.append((*self.at(b.i, b.j), b.y, b.y + top, mask))
        for c, h in cols.items():
            out.append((*self.at(*c), 0, h, full))
        return out, cols

    def shadow_layer(self, casters, g, box):
        """The shadow (an 'L' mask) on a surface at height g, over the page area box = (x0, y0, x1, y1): each
        caster's outline swept from where it rises above g to its top, along the sun, softer the farther it
        falls."""
        px = self.px
        x0, y0, x1, y1 = box
        bands = [Image.new('L', (x1 - x0, y1 - y0), 0) for _ in self.SHADOW_BANDS]
        reach = 12 * px
        for x, y, bot, top, mask in casters:
            if top <= g + .05:
                continue
            if x + px < x0 - reach or x > x1 + reach or y + px < y0 - reach or y > y1 + reach:
                continue
            lo = max(bot, g)
            n = max(2, math.ceil((top - lo) * math.hypot(*self.SUN) * px / 2))  # a step every 2 px: no gaps
            for k in range(n + 1):
                t = lo + (top - lo) * k / n
                d = t - g                                                   # how far above the surface
                sx, sy = round(x + d * self.SUN[0] * px) - x0, round(y + d * self.SUN[1] * px) - y0
                if sx > x1 - x0 or sy > y1 - y0 or sx + px < 0 or sy + px < 0:
                    continue
                band = next(i for i, (_, hi, _) in enumerate(self.SHADOW_BANDS) if t - bot < hi)
                bands[band].paste(255, (sx, sy, sx + px, sy + px), mask)
        layer = Image.new('L', bands[0].size, 0)
        for band, (_, _, r) in zip(bands, self.SHADOW_BANDS):
            if band.getbbox():
                layer = ImageChops.lighter(layer, band.filter(ImageFilter.GaussianBlur(r * px)))
        return layer.point(lambda v: v * self.SHADOW_ALPHA // 255)

    def shadows(self, img, blocks):
        """Sun shadows (from the south-east, low in the sky, so they fall to the north-west), with soft edges
        that widen with distance, on the ground and on the hill tops. Leaves let light through their holes.
        The ground's are laid on the page now; the hill tops' are returned, {cell: mask}, to lay on each top
        as it is drawn."""
        px = self.px
        casters, cols = self.casters(blocks)
        alpha = self.shadow_layer(casters, 0, (0, 0) + img.size)
        shade = Image.new('RGBA', img.size, (16, 20, 40, 255))
        shade.putalpha(alpha)
        img.alpha_composite(shade)
        tops = {}
        levels = {}
        for c, h in cols.items():
            levels.setdefault(h, []).append(c)
        for g, cells in levels.items():
            xs = [self.at(*c)[0] for c in cells]
            ys = [self.at(*c)[1] for c in cells]
            box = (min(xs), min(ys), max(xs) + px, max(ys) + px)
            layer = self.shadow_layer(casters, g, box)
            for c in cells:
                x, y = self.at(*c)
                m = layer.crop((x - box[0], y - box[1], x - box[0] + px, y - box[1] + px))
                if m.getbbox():
                    tops[c] = m
        return tops

    def footprint(self, b):
        """What of a Block the sun can't shine through, seen from above (a mask), or None for plants and other
        small things, whose shadows would only be noise."""
        key = ('footprint', b.kind, b.args)
        if key not in self.td.cache and b.kind == 'mob':        # mobs cast the game's round blob shadow
            m = Image.new('L', (self.px, self.px), 0)
            r = self.px * .45
            ImageDraw.Draw(m).ellipse((self.px / 2 - r, self.px / 2 - r, self.px / 2 + r, self.px / 2 + r), fill=255)
            self.td.cache[key] = m
        if key not in self.td.cache:
            if b.kind == 'state':
                name, props = b.args[:2]
                models = [(self.pack.model(m), xr, yr) for m, xr, yr in self.pack.state_models(name, dict(props))]
                img = self.td.compose(models, None)[0]      # its real faces, not the icon used for plants
            else:
                img = self.flat_sprite(b)
            a = img.getchannel('A')
            cov = 1 - a.histogram()[0] / (img.width * img.height)
            self.td.cache[key] = a.point(lambda v: 255 if v > 0 else 0) if cov >= .2 else None
        return self.td.cache[key]

    def solid(self, b):
        """How high a Block stands as a solid lump (in blocks, from its cell's floor), or 0 for things that
        hardly cover their cell (plants, torches, fences)."""
        key = ('solid', b.kind, b.args)
        if key not in self.td.cache:
            spr = self.flat_sprite(b)
            cov = 1 - spr.getchannel('A').histogram()[0] / (spr.width * spr.height)
            up = self.sprite(b)[1]
            self.td.cache[key] = up / (self.ob.s * self.px) if cov > .7 and self.ob.s else 0
        return self.td.cache[key]

    def occlusion(self, blocks):
        """Ambient occlusion like the game's smooth lighting: the ground (or a hill top) gets darker along the
        sides where a block stands next to it. Returns draw items: ((row, height, column, 1), 'ao', ...), each
        drawn just after the surface it darkens."""
        ground, top = {}, {}
        for b in blocks:
            c = (b.i, b.j)
            if b.owner == 'hill':
                ground[c] = max(ground.get(c, 0), b.y + 1)
        for b in blocks:
            if b.flat:
                continue
            h = self.solid(b)
            if h >= .4:
                c = (b.i, b.j)
                top[c] = max(top.get(c, 0), b.y + h)
        out = []
        cells = set(ground) | {(i + a, j + b) for (i, j) in top for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1))}
        for (i, j) in cells:
            g = ground.get((i, j), 0)
            if top.get((i, j), 0) > g + .4 or not self.w.inside((i, j)):
                continue            # something stands on it: nothing to darken
            # only on the sides away from the sun (south and east of the cell): a dark seam on the sunny side
            # of a block reads as a shadow cast the wrong way, and makes hills look like they float
            sides = tuple(d for d, (a, b) in (('south', (0, 1)), ('east', (1, 0)))
                          if max(top.get((i + a, j + b), 0), ground.get((i + a, j + b), 0)) > g + .4)
            if sides:
                out.append(((j, g - 1 if g else -1, i, 1), 'ao', ((i, j), g, sides)))
        return out

    def edges(self, blocks):
        """Thin dark rims along the north and west edges of block tops where the land drops away behind them, so
        a block's top doesn't run straight into the shadow behind it. Returns draw items, each drawn just after
        the top it rims."""
        top, key = {}, {}
        cols = {}
        for b in blocks:
            if b.flat:
                continue
            h = self.solid(b)
            if h < .4:
                continue
            c = (b.i, b.j)
            if b.y + h > top.get(c, 0):
                top[c] = b.y + h
                key[c] = (b.j, b.y, b.i, 0.5)
            if b.owner == 'hill':
                cols[c] = max(cols.get(c, 0), b.y + 1)
        self.column_top = cols
        out = []
        for (i, j), h in top.items():
            sides = tuple(d for d, (a, b) in (('north', (0, -1)), ('west', (-1, 0)))
                          if top.get((i + a, j + b), 0) < h - .3)
            if sides:
                out.append((key[(i, j)], 'edge', ((i, j), h, sides)))
        return out

    def edge_strip(self, side):
        key = ('edge', side)
        if key not in self.td.cache:
            px = self.px
            strip = Image.new('RGBA', (px, px), (0, 0, 0, 0))
            w = max(1, px // 16)
            for k, a in ((0, 150), (w, 60)):
                box = {'north': (0, k, px, k + w), 'west': (k, 0, k + w, px)}[side]
                strip.paste((30, 24, 20, a), box)
            self.td.cache[key] = strip
        return self.td.cache[key]

    def ao_strip(self, side):
        key = ('ao', side)
        if key not in self.td.cache:
            px = self.px
            n = max(3, px * 3 // 8)
            strip = Image.new('RGBA', (px, px), (0, 0, 0, 0))
            for k in range(n):
                a = round(120 * (1 - k / n) ** 1.3)
                box = {'north': (0, k, px, k + 1), 'south': (0, px - 1 - k, px, px - k),
                       'west': (k, 0, k + 1, px), 'east': (px - 1 - k, 0, px - k, px)}[side]
                strip.paste((10, 10, 20, a), box)
            self.td.cache[key] = strip
        return self.td.cache[key]

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
        spr, up, left = self.ob.box(top, side, PLAQUE_H)
        dx, dy = self.shift(pq.meta.get('y', 0))
        for b in range(pq.h):
            for a in range(pq.w):
                blit(img, spr, x0 + a * px - left + dx, y0 + b * px - up + dy)
        tx, ty = self.shift(pq.meta.get('y', 0) + PLAQUE_H / 16)
        ImageDraw.Draw(img).rectangle((x0 + tx, y0 + ty, x0 + pq.w * px - 1 + tx, y0 + pq.h * px - 1 + ty),
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
                dx, dy = self.shift(pq.meta.get('y', 0) + PLAQUE_H / 16)
                x, y = x + dx, y + dy
            out.append(self.text(pq.text, x, y, pq.w * px, pq.h * px, pq.scale, col, shadow, pq.vertical))
        for kind, text, origin, u, v in w.texts:          # pin names painted on bodies
            _, col, shadow = STYLES[kind]
            dx, dy = self.shift(origin[1])
            vertical = abs(u[2]) > abs(u[0])
            xs = [origin[0], origin[0] + u[0] + v[0]]
            zs = [origin[2], origin[2] + u[2] + v[2]]
            x0, z0 = (min(xs) + .5 - w.i0) * px + dx, (min(zs) + .5 - w.j0) * px + dy
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


SNOWY = ('block/snow', 'block/powder_snow')


def printable(rid, img):
    """Textures as they should look on paper. Snow is nearly white with a faint pattern that shows in the game's
    lighting but vanishes in print: it gets more contrast and a cool tint."""
    if rid.split(':')[-1] not in SNOWY:
        return img
    from PIL import ImageEnhance
    rgb = ImageEnhance.Contrast(img.convert('RGB')).enhance(3.2)
    rgb = Image.merge('RGB', [c.point(lambda v, k=k: round(v * k)) for c, k in zip(rgb.split(), (.9, .93, 1.0))])
    out = rgb.convert('RGBA')
    out.putalpha(img.getchannel('A'))
    return out


def sink_hopper(model):
    """A hopper let into the ground: its funnel (below 10/16) is buried, and its bowl rests on the ground, so it
    doesn't seem to float when seen from above."""
    els = []
    for el in model.get('elements', []):
        if el['to'][1] <= 10:
            continue
        for face, f in el.get('faces', {}).items():
            if not f.get('uv'):         # keep the texture where it was before the move
                f['uv'] = list(default_uv(face, el['from'], el['to']))
        el['from'] = [el['from'][0], el['from'][1] - 10, el['from'][2]]
        el['to'] = [el['to'][0], el['to'][1] - 10, el['to'][2]]
        els.append(el)
    model['elements'] = els
    return model


SUNK = {'hopper': sink_hopper}      # blocks drawn partly let into the ground


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
