"""Blocks seen from straight above, as small RGBA images ("sprites") of `px` pixels per block.

A sprite is made from the block's models: every face that points up after the element's and the blockstate's
rotations is drawn at its place, lowest first, a little darker the lower it is. Blocks that show almost nothing
from above (flowers, torches, lanterns, cobwebs) are drawn as their item icon instead, like on a map."""

import copy
import math

from PIL import Image

FACES = ('down', 'up', 'north', 'south', 'west', 'east')
ICON_COVERAGE = .3          # below this share of opaque pixels seen from above, a block is drawn as its icon


def default_uv(face, fr, to):
    (x0, y0, z0), (x1, y1, z1) = fr, to
    return {'up': (x0, z0, x1, z1), 'down': (x0, 16 - z1, x1, 16 - z0),
            'north': (16 - x1, 16 - y1, 16 - x0, 16 - y0), 'south': (x0, 16 - y1, x1, 16 - y0),
            'west': (z0, 16 - y1, z1, 16 - y0), 'east': (16 - z1, 16 - y1, 16 - z0, 16 - y0)}[face]


def face_quad(face, fr, to):
    """(top-left corner, u vector, v vector) of a face, in model units, so that the texture's u runs along u."""
    (x0, y0, z0), (x1, y1, z1) = fr, to
    dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
    return {'up': ((x0, y1, z0), (dx, 0, 0), (0, 0, dz)),
            'down': ((x0, y0, z1), (dx, 0, 0), (0, 0, -dz)),
            'north': ((x1, y1, z0), (-dx, 0, 0), (0, -dy, 0)),
            'south': ((x0, y1, z1), (dx, 0, 0), (0, -dy, 0)),
            'west': ((x0, y1, z0), (0, 0, dz), (0, -dy, 0)),
            'east': ((x1, y1, z1), (0, 0, -dz), (0, -dy, 0))}[face]


def rotate_element(p, axis, ang, origin):
    x, y, z = (p[i] - origin[i] for i in range(3))
    c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    if axis == 'x':
        y, z = y * c - z * s, y * s + z * c
    elif axis == 'y':
        x, z = x * c + z * s, -x * s + z * c
    else:
        x, y = x * c - y * s, x * s + y * c
    return x + origin[0], y + origin[1], z + origin[2]


def rotate_state(p, xr, yr):
    """Blockstate rotation: first about x, then about y (clockwise seen from above: north -> east)."""
    for _ in range((xr // 90) % 4):
        x, y, z = p[0] - 8, p[1] - 8, p[2] - 8
        p = (x + 8, z + 8, -y + 8)
    for _ in range((yr // 90) % 4):
        x, y, z = p[0] - 8, p[1] - 8, p[2] - 8
        p = (-z + 8, y + 8, x + 8)
    return p


def tint_shade(img, tint=None, shade=1.0):
    if tint is None and shade == 1.0:
        return img
    r, g, b, a = img.split()
    tr, tg, tb = tint or (255, 255, 255)
    r = r.point(lambda v: round(v * tr / 255 * shade))
    g = g.point(lambda v: round(v * tg / 255 * shade))
    b = b.point(lambda v: round(v * tb / 255 * shade))
    return Image.merge('RGBA', (r, g, b, a))


def crop_uv(tex, uv, rot):
    """The part of a texture a face shows, turned like the face turns it."""
    s = tex.width / 16
    u0, v0, u1, v1 = uv
    a, b = sorted((u0, u1)), sorted((v0, v1))
    box = [math.floor(a[0] * s + 1e-6), math.floor(b[0] * s + 1e-6), math.ceil(a[1] * s - 1e-6),
           math.ceil(b[1] * s - 1e-6)]
    box[2] = max(box[2], box[0] + 1)
    box[3] = max(box[3], box[1] + 1)
    img = tex.crop(box)
    if u0 > u1:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    if v0 > v1:
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    if rot:
        img = img.rotate(-rot, expand=True)
    return img


class TopDown:
    def __init__(self, pack, px=16):
        self.pack = pack
        self.px = px
        self.cache = {}

    def texture(self, rid, tint=None, shade=1.0):
        key = ('tex', rid, tint, round(shade, 3))
        if key not in self.cache:
            img = self.pack.texture(rid)
            if 'leaves' in rid:
                from .oblique import solid_leaves
                img = solid_leaves(img)
            self.cache[key] = tint_shade(img, tint, shade)
        return self.cache[key]

    # -- block states -------------------------------------------------------------
    def state(self, name, props=None, tints=None, model_hook=None):
        """(sprite, height of its top in blocks) for a block in a state."""
        props = dict(props or {})
        key = ('state', name, tuple(sorted(props.items())), tuple(sorted((tints or {}).items())), model_hook)
        if key not in self.cache:
            models = []
            for m, xr, yr in self.pack.state_models(name, props):
                model = self.pack.model(m)
                if model_hook is not None:
                    model = model_hook(copy.deepcopy(model))
                models.append((model, xr, yr))
            img, top = self.compose(models, tints)
            cov = coverage(img)
            if cov < ICON_COVERAGE and (top >= .25 or cov == 0):     # standing, but little to see from above
                icon = self.icon(name, tints)
                if icon is not None:
                    img = icon
            self.cache[key] = (img, top)
        return self.cache[key]

    def compose(self, models, tints):
        px = self.px
        faces = []
        for model, xr, yr in models:
            tex = model['textures']
            for el in model.get('elements', []):
                er = el.get('rotation')
                if er and er.get('angle', 0) and er.get('axis', 'y') != 'y':
                    continue            # tilted (wall torches, ...): not worth drawing from above
                fr, to = el['from'], el['to']
                for face, f in el.get('faces', {}).items():
                    t = f.get('texture', '')
                    t = tex.get(t[1:]) if t.startswith('#') else t
                    if not t:
                        continue
                    o, u, v = face_quad(face, fr, to)
                    pts = [o, tuple(o[i] + u[i] for i in range(3)), tuple(o[i] + v[i] for i in range(3))]
                    if er and er.get('angle', 0):
                        pts = [rotate_element(p, 'y', er['angle'], er.get('origin', (8, 8, 8))) for p in pts]
                    pts = [rotate_state(p, xr, yr) for p in pts]
                    o = pts[0]
                    u = tuple(pts[1][i] - o[i] for i in range(3))
                    v = tuple(pts[2][i] - o[i] for i in range(3))
                    ny = u[0] * v[2] - u[2] * v[0]          # y of -(u x v), the face's normal
                    if ny <= 1e-6 or abs(u[1]) > 1e-6 or abs(v[1]) > 1e-6:
                        continue
                    ti = f.get('tintindex')
                    tint = (tints or {}).get(ti) if ti is not None else None
                    faces.append((o[1], o, u, v, t, f.get('uv') or default_uv(face, fr, to), f.get('rotation', 0),
                                  tint))
        img = Image.new('RGBA', (px, px), (0, 0, 0, 0))
        top = 0
        for y, o, u, v, t, uv, rot, tint in sorted(faces, key=lambda f: f[0]):
            shade = 1.0 if y >= 16 else .78 + .22 * y / 16
            src = crop_uv(self.texture(t, tint, shade), uv, rot)
            paste_affine(img, src, o, u, v, px)
            top = max(top, y / 16)
        return img, top

    def icon(self, name, tints):
        """A block's item icon (its item model's first layer), or None."""
        m = self.pack.json('models', f'item/{name}')
        tex = None
        if m is not None:
            tex = (m.get('textures') or {}).get('layer0')
        if tex is None:
            bm = self.pack.model(f'block/{name}')
            tex = bm['textures'].get('cross') or bm['textures'].get('torch') or bm['textures'].get('particle')
        if not tex or self.pack.asset('textures', tex, '.png') is None:
            return None
        tint = (tints or {}).get(0)
        img = self.texture(tex, tint)
        return img.resize((self.px, self.px), Image.NEAREST)

    # -- boxes of block textures (bodies, plaques) -----------------------------------
    def box(self, top, h=16, tint=None):
        key = ('box', top, h, tint)
        if key not in self.cache:
            shade = 1.0 if h >= 16 else .78 + .22 * h / 16
            self.cache[key] = (self.texture(top, tint, shade).resize((self.px, self.px), Image.NEAREST), h / 16)
        return self.cache[key]


def paste_affine(dst, src, o, u, v, px):
    """Draw src onto dst so that its corners land on o, o + u, o + v (model units, x and z)."""
    k = px / 16
    ox, oz = o[0] * k, o[2] * k
    ux, uz = u[0] * k / src.width, u[2] * k / src.width
    vx, vz = v[0] * k / src.height, v[2] * k / src.height
    det = ux * vz - uz * vx
    if abs(det) < 1e-9:
        return
    # inverse: destination pixel centre -> source pixel
    ia, ib = vz / det, -vx / det
    ic, id_ = -uz / det, ux / det
    xs = [ox, ox + u[0] * k, ox + v[0] * k, ox + (u[0] + v[0]) * k]
    zs = [oz, oz + u[2] * k, oz + v[2] * k, oz + (u[2] + v[2]) * k]
    x0, x1 = max(0, math.floor(min(xs) + 1e-6)), min(px, math.ceil(max(xs) - 1e-6))
    z0, z1 = max(0, math.floor(min(zs) + 1e-6)), min(px, math.ceil(max(zs) - 1e-6))
    if x1 <= x0 or z1 <= z0:
        return
    layer = Image.new('RGBA', (px, px), (0, 0, 0, 0))
    src_px = src.load()
    out = layer.load()
    for zz in range(z0, z1):
        for xx in range(x0, x1):
            dx, dz = xx + .5 - ox, zz + .5 - oz
            sx, sy = ia * dx + ib * dz, ic * dx + id_ * dz
            if 0 <= sx < src.width and 0 <= sy < src.height:
                out[xx, zz] = src_px[int(sx), int(sy)]
    dst.alpha_composite(layer)


def coverage(img):
    a = img.getchannel('A')
    return 1 - a.histogram()[0] / (img.width * img.height)
