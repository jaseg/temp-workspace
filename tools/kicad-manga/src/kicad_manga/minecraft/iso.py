"""Isometric drawing of block models into SVG.

World coordinates are in blocks: x east, y up, z south. The camera looks from the south-east, from above, in the
2:1 pixel-art isometric projection: one block is 32 units wide on screen, its top face 16 units high and its
sides 16 units tall, so a 16-pixel texture lands on whole units.

Every face of a model is one texture, cropped to its UV rectangle, turned, tinted and shaded once (`Atlas`), and
drawn as an <image> transformed onto the face's parallelogram. A block in a state is drawn once into the
<defs> (`Sprites`) and placed with <use>. Images are drawn pixelated, so the PDF stays crisp at any zoom."""

import base64
import io
import math

from PIL import Image

from ..svg import Markup, num, tag

UNIT = 16                               # screen units per block, half the width of a block's top face
VIEW = (1.0, 1.0, 1.0)                  # towards the camera
SHADE = {'up': 1.0, 'down': .5, 'north': .8, 'south': .8, 'west': .6, 'east': .6}
FACES = ('down', 'up', 'north', 'south', 'west', 'east')
NORMAL = {'down': (0, -1, 0), 'up': (0, 1, 0), 'north': (0, 0, -1), 'south': (0, 0, 1), 'west': (-1, 0, 0),
          'east': (1, 0, 0)}
PIXELATED = 'image-rendering:pixelated;image-rendering:crisp-edges'


def proj(x, y, z):
    """World point (blocks) -> screen point (units)."""
    return UNIT * (x - z), UNIT / 2 * (x + z) - UNIT * y


def depth(x, y, z):
    return x * VIEW[0] + y * VIEW[1] + z * VIEW[2]


def png_uri(img):
    buf = io.BytesIO()
    img.save(buf, 'PNG', optimize=True)
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


def matrix(origin, u, v, w, h):
    """The SVG transform taking a w x h image onto the parallelogram origin + s*u + t*v (world vectors)."""
    ox, oy = proj(*origin)
    ux, uy = proj(*u)
    vx, vy = proj(*v)
    return f'matrix({num(ux / w)} {num(uy / w)} {num(vx / h)} {num(vy / h)} {num(ox)} {num(oy)})'


# ----------------------------------------------------------------------------
# Face geometry, in sixteenths of a block like model files

def default_uv(face, fr, to):
    (x0, y0, z0), (x1, y1, z1) = fr, to
    return {'up': (x0, z0, x1, z1), 'down': (x0, 16 - z1, x1, 16 - z0),
            'north': (16 - x1, 16 - y1, 16 - x0, 16 - y0), 'south': (x0, 16 - y1, x1, 16 - y0),
            'west': (z0, 16 - y1, z1, 16 - y0), 'east': (16 - z1, 16 - y1, 16 - z0, 16 - y0)}[face]


def face_quad(face, fr, to):
    """(top-left corner, u vector, v vector) of a face, so that the texture's u runs along u and v along v."""
    (x0, y0, z0), (x1, y1, z1) = fr, to
    dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
    return {'up': ((x0, y1, z0), (dx, 0, 0), (0, 0, dz)),
            'down': ((x0, y0, z1), (dx, 0, 0), (0, 0, -dz)),
            'north': ((x1, y1, z0), (-dx, 0, 0), (0, -dy, 0)),
            'south': ((x0, y1, z1), (dx, 0, 0), (0, -dy, 0)),
            'west': ((x0, y1, z0), (0, 0, dz), (0, -dy, 0)),
            'east': ((x1, y1, z1), (0, 0, -dz), (0, -dy, 0))}[face]


def _rot(p, axis, ang, origin=(8, 8, 8), scale=1.0):
    x, y, z = (p[i] - origin[i] for i in range(3))
    c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    if axis == 'x':
        y, z = y * c - z * s, y * s + z * c
        y, z = y * scale, z * scale
    elif axis == 'y':
        x, z = x * c + z * s, -x * s + z * c
        x, z = x * scale, z * scale
    else:
        x, y = x * c - y * s, x * s + y * c
        x, y = x * scale, y * scale
    return x + origin[0], y + origin[1], z + origin[2]


def _state_rot(p, xr, yr):
    """Blockstate rotation: first about x, then about y (clockwise seen from above, north -> east)."""
    for _ in range((xr // 90) % 4):
        x, y, z = p[0] - 8, p[1] - 8, p[2] - 8
        p = (x + 8, z + 8, -y + 8)
    for _ in range((yr // 90) % 4):
        x, y, z = p[0] - 8, p[1] - 8, p[2] - 8
        p = (-z + 8, y + 8, x + 8)
    return p


def _cross(a, b):
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _dir(n):
    ax = max(range(3), key=lambda i: abs(n[i]))
    return [('west', 'east'), ('down', 'up'), ('north', 'south')][ax][n[ax] > 0]


# ----------------------------------------------------------------------------

class Atlas:
    """Baked face images: (texture, uv, rotation, tint, shade) -> an <image> in the <defs>."""

    def __init__(self, pack):
        self.pack = pack
        self.ids = {}
        self.defs = []

    def image(self, tex, uv, rot=0, tint=None, shade=1.0, flip=False):
        key = (tex, tuple(round(v, 3) for v in uv), rot, tint, round(shade, 3), flip)
        if key in self.ids:
            return self.ids[key]
        img = self.pack.texture(tex)
        s = img.width / 16
        u0, v0, u1, v1 = uv
        fx, fy = u0 > u1, v0 > v1
        a, b = sorted((u0, u1)), sorted((v0, v1))
        box = [round(a[0] * s), round(b[0] * s), round(a[1] * s), round(b[1] * s)]
        if box[2] <= box[0]:
            box[2] = box[0] + 1
        if box[3] <= box[1]:
            box[3] = box[1] + 1
        img = img.crop(box)
        if fx:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        if fy:
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
        if rot:
            img = img.rotate(-rot, expand=True)
        if flip:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        img = color(img, tint, shade)
        iid = f'i{len(self.ids)}'
        self.ids[key] = (iid, img.width, img.height)
        self.defs.append(tag('image', id=iid, width=img.width, height=img.height, style=PIXELATED,
                             href=png_uri(img)))
        return self.ids[key]

    def raw(self, img, key):
        """An image made elsewhere (text), by key."""
        if key in self.ids:
            return self.ids[key]
        iid = f'i{len(self.ids)}'
        self.ids[key] = (iid, img.width, img.height)
        self.defs.append(tag('image', id=iid, width=img.width, height=img.height, style=PIXELATED,
                             href=png_uri(img)))
        return self.ids[key]


def color(img, tint=None, shade=1.0):
    if tint is None and shade == 1.0:
        return img
    r, g, b, a = img.split()
    tr, tg, tb = tint or (255, 255, 255)
    r = r.point(lambda v: round(v * tr / 255 * shade))
    g = g.point(lambda v: round(v * tg / 255 * shade))
    b = b.point(lambda v: round(v * tb / 255 * shade))
    return Image.merge('RGBA', (r, g, b, a))


class Sprites:
    """Blocks drawn once into the <defs>, each a <g> of its visible faces, placed with `use()`."""

    def __init__(self, pack, atlas):
        self.pack = pack
        self.atlas = atlas
        self.ids = {}
        self.defs = []

    def faces(self, models, tints=None, cull=()):
        """[(depth, markup)] of the visible faces of [(model dict, x rot, y rot)], relative to the block's corner.
        `tints` maps tint indices to RGB; `cull` lists directions whose faces with that cullface are hidden."""
        out = []
        for model, xr, yr in models:
            tex = model['textures']
            for el in model['elements']:
                fr, to = el['from'], el['to']
                er = el.get('rotation')
                for face, f in el.get('faces', {}).items():
                    cf = f.get('cullface')
                    if cf and _dir([c - 8 for c in _state_rot(_rot_n(NORMAL[cf]), xr, yr)]) in cull:
                        continue
                    t = f.get('texture', '')
                    t = tex.get(t[1:]) if t.startswith('#') else t
                    if not t:
                        continue
                    o, u, v = face_quad(face, fr, to)
                    pts = [o, tuple(o[i] + u[i] for i in range(3)), tuple(o[i] + v[i] for i in range(3))]
                    if er:
                        ang = er.get('angle', 0)
                        sc = 1 / math.cos(math.radians(ang)) if er.get('rescale') and ang else 1.0
                        pts = [_rot(p, er.get('axis', 'y'), ang, er.get('origin', (8, 8, 8)), sc) for p in pts]
                    pts = [_state_rot(p, xr, yr) for p in pts]
                    o = pts[0]
                    u = tuple(pts[1][i] - o[i] for i in range(3))
                    v = tuple(pts[2][i] - o[i] for i in range(3))
                    n = tuple(-c for c in _cross(u, v))
                    if _dot(n, VIEW) <= 1e-6:
                        continue
                    shade = SHADE[_dir(n)] if el.get('shade', True) else 1.0
                    ti = f.get('tintindex')
                    tint = (tints or {}).get(ti) if ti is not None else None
                    uv = f.get('uv') or default_uv(face, fr, to)
                    iid, w, h = self.atlas.image(t, tuple(uv), f.get('rotation', 0), tint, shade)
                    o, u, v = (tuple(c / 16 for c in p) for p in (o, u, v))
                    cen = tuple(o[i] + (u[i] + v[i]) / 2 for i in range(3))
                    out.append((depth(*cen) + 1e-3 * _dot(n, VIEW),
                                tag('use', href=f'#{iid}', transform=matrix(o, u, v, w, h))))
        out.sort(key=lambda d: d[0])
        return out

    def get(self, key, models, tints=None, cull=()):
        """The id of a sprite, drawing it into the defs on first use."""
        k = (key, tuple(sorted(cull)))
        if k not in self.ids:
            sid = f's{len(self.ids)}'
            self.ids[k] = sid
            self.defs.append(tag('g', [m for _, m in self.faces(models, tints, cull)], id=sid))
        return self.ids[k]

    def state(self, name, props=None, tints=None, cull=()):
        props = dict(props or {})
        key = ('state', name, tuple(sorted(props.items())), tuple(sorted((tints or {}).items())))
        if (key, tuple(sorted(cull))) in self.ids:
            return self.ids[(key, tuple(sorted(cull)))]
        models = [(self.pack.model(m), x, y) for m, x, y in self.pack.state_models(name, props)]
        return self.get(key, models, tints, cull)

    def box(self, top, side, h=16, tints=None, cull=(), bottom=0):
        """A box of block textures from `bottom` to `h` sixteenths high."""
        key = ('box', top, side, h, bottom, tuple(sorted((tints or {}).items())))
        model = {'textures': {}, 'elements': [
            {'from': [0, bottom, 0], 'to': [16, h, 16],
             'faces': {'up': {'texture': top, 'cullface': 'up', **({'tintindex': 0} if tints and 0 in tints else {})},
                       'south': {'texture': side, 'cullface': 'south', 'uv': [0, 16 - h, 16, 16 - bottom]},
                       'east': {'texture': side, 'cullface': 'east', 'uv': [0, 16 - h, 16, 16 - bottom]}}}]}
        return self.get(key, [(model, 0, 0)], tints, cull)


def _rot_n(n):
    return tuple(8 + 8 * c for c in n)


def use(sid, x, y, z):
    ox, oy = proj(x, y, z)
    return Markup(f'<use href="#{sid}" x="{num(ox)}" y="{num(oy)}"/>')
