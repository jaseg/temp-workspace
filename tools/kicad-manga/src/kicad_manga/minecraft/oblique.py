"""Blocks seen from high up in the south, as small RGBA images ("sprites") of `px` pixels per block.

The view is an oblique projection that keeps the ground exactly as on the page: a point (x, y, z) of the world (x
east, y up, z south) lands at (x, z - s y) on the page, with `s` = cot of the camera's angle above the horizon. So
every block shows its top, and below that its south side, `s` blocks tall per block of height. Nothing is turned
45 degrees, and the floor plan lines up with the sheet.

A sprite is `px` wide and `px + up` tall: its floor cell is the bottom `px` x `px` square, and whatever stands up
reaches `up` pixels above it."""

import copy
import math

from PIL import Image, ImageStat

from .topdown import crop_uv, default_uv, face_quad, rotate_element, rotate_state, tint_shade


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


class Oblique:
    def __init__(self, pack, px=16, camera_deg=60):
        self.pack = pack
        self.px = px
        self.s = 1 / math.tan(math.radians(camera_deg))
        self.cache = {}

    def texture(self, rid, tint=None, shade=1.0):
        key = ('tex', rid, tint, round(shade, 3))
        if key not in self.cache:
            img = self.pack.texture(rid)
            if 'leaves' in rid:
                img = solid_leaves(img)
            self.cache[key] = tint_shade(img, tint, shade)
        return self.cache[key]

    def shade(self, n):
        """Light from above and a little from the north-west: tops bright, south sides darker."""
        L = math.sqrt(sum(c * c for c in n)) or 1
        nx, ny, nz = (c / L for c in n)
        return max(.55, min(1.0, .8 + .2 * ny - .04 * nx - .04 * nz))

    # -- block states -----------------------------------------------------------------------
    def state(self, name, props=None, tints=None, model_hook=None):
        """(sprite, up) of a block in a state, `up` the pixels it reaches above its floor cell."""
        props = dict(props or {})
        key = ('state', name, tuple(sorted(props.items())), tuple(sorted((tints or {}).items())), model_hook)
        if key not in self.cache:
            models = []
            for m, xr, yr in self.pack.state_models(name, props):
                model = self.pack.model(m)
                if model_hook is not None:
                    model = model_hook(copy.deepcopy(model))
                models.append((model, xr, yr))
            self.cache[key] = self.compose(models, tints)
        return self.cache[key]

    def faces(self, models, tints):
        """Every face that the camera sees: (depth, corner, u, v, texture, uv, rotation, tint, shade), in model
        units (0..16 a block, y up)."""
        s = self.s
        out = []
        for model, xr, yr in models:
            tex = model['textures']
            for el in model.get('elements', []):
                er = el.get('rotation')
                fr, to = el['from'], el['to']
                for face, f in el.get('faces', {}).items():
                    t = f.get('texture', '')
                    t = tex.get(t[1:]) if t.startswith('#') else t
                    if not t:
                        continue
                    o, u, v = face_quad(face, fr, to)
                    pts = [o, tuple(o[i] + u[i] for i in range(3)), tuple(o[i] + v[i] for i in range(3))]
                    if er and er.get('angle', 0) and not (er.get('axis', 'y') == 'y' and abs(er['angle']) == 45):
                        # (crossed planes of plants stand straight up to the camera instead, like a billboard)
                        pts = [rotate_element(p, er.get('axis', 'y'), er['angle'], er.get('origin', (8, 8, 8)))
                               for p in pts]
                    pts = [rotate_state(p, xr, yr) for p in pts]
                    o = pts[0]
                    u = tuple(pts[1][i] - o[i] for i in range(3))
                    v = tuple(pts[2][i] - o[i] for i in range(3))
                    n = tuple(-c for c in cross(u, v))          # outward normal
                    if n[1] + s * n[2] <= 1e-6:                  # faces away from the camera, or edge-on
                        continue
                    c = tuple(o[i] + (u[i] + v[i]) / 2 for i in range(3))
                    depth = c[1] + s * c[2]
                    ti = f.get('tintindex')
                    tint = (tints or {}).get(ti) if ti is not None else None
                    out.append((depth, o, u, v, t, f.get('uv') or default_uv(face, fr, to), f.get('rotation', 0),
                                tint, self.shade(n)))
        return out

    def compose(self, models, tints):
        px, s = self.px, self.s
        faces = self.faces(models, tints)
        top = max([max(o[1], o[1] + u[1], o[1] + v[1], o[1] + u[1] + v[1]) for _, o, u, v, *_ in faces] or [0])
        up = math.ceil(max(0, top) * s * px / 16)
        img = Image.new('RGBA', (px, px + up), (0, 0, 0, 0))
        k = px / 16

        def proj(p):
            return p[0] * k, (p[2] - s * p[1]) * k + up
        for _, o, u, v, t, uv, rot, tint, shade in sorted(faces, key=lambda f: f[0]):
            src = crop_uv(self.texture(t, tint, shade), uv, rot)
            O = proj(o)
            U = tuple(a - b for a, b in zip(proj(tuple(o[i] + u[i] for i in range(3))), O))
            V = tuple(a - b for a, b in zip(proj(tuple(o[i] + v[i] for i in range(3))), O))
            paste_affine(img, src, O, U, V)
        return img, up

    # -- boxes of block textures (bodies, plaques) --------------------------------------------
    def box(self, top, side, h=16, tint=None):
        """(sprite, up) of a box `h` 16ths of a block tall with `top` on top and `side` on its south face."""
        key = ('box', top, side, h, tint)
        if key not in self.cache:
            px, s = self.px, self.s
            up = math.ceil(h / 16 * s * px)
            img = Image.new('RGBA', (px, px + up), (0, 0, 0, 0))
            k = px / 16
            side_shade = self.shade((0, 0, 1))
            sd = crop_uv(self.texture(side, tint, side_shade), (0, 16 - h, 16, 16), 0)
            paste_affine(img, sd, (0, px + up - h * s * k), (px, 0), (0, h * s * k))
            tp = self.texture(top, tint)
            paste_affine(img, tp, (0, up - h * s * k), (px, 0), (0, px))
            self.cache[key] = (img, up)
        return self.cache[key]


def paste_affine(dst, src, o, u, v):
    """Draw src onto dst so that its corners land on o, o + u, o + v (pixels)."""
    ox, oy = o
    ux, uy = u[0] / src.width, u[1] / src.width
    vx, vy = v[0] / src.height, v[1] / src.height
    det = ux * vy - uy * vx
    if abs(det) < 1e-9:
        return
    ia, ib = vy / det, -vx / det
    ic, id_ = -uy / det, ux / det
    xs = [ox, ox + u[0], ox + v[0], ox + u[0] + v[0]]
    ys = [oy, oy + u[1], oy + v[1], oy + u[1] + v[1]]
    x0, x1 = max(0, math.floor(min(xs) + 1e-6)), min(dst.width, math.ceil(max(xs) - 1e-6))
    y0, y1 = max(0, math.floor(min(ys) + 1e-6)), min(dst.height, math.ceil(max(ys) - 1e-6))
    if x1 <= x0 or y1 <= y0:
        return
    layer = Image.new('RGBA', dst.size, (0, 0, 0, 0))
    src_px = src.load()
    out = layer.load()
    for yy in range(y0, y1):
        for xx in range(x0, x1):
            dx, dy = xx + .5 - ox, yy + .5 - oy
            sx, sy = ia * dx + ib * dy, ic * dx + id_ * dy
            if 0 <= sx < src.width and 0 <= sy < src.height:
                out[xx, yy] = src_px[int(sx), int(sy)]
    dst.alpha_composite(layer)


def solid_leaves(img):
    """Leaves with their holes filled in a darker shade of their own colour: from above, the game shows more
    leaves through the holes, not the ground under the tree."""
    img = img.convert('RGBA')
    mask = img.getchannel('A').point(lambda v: 255 if v > 128 else 0)
    if not mask.getbbox():
        return img
    r, g, b = (round(v * .55) for v in ImageStat.Stat(img.convert('RGB'), mask=mask).mean)
    back = Image.new('RGBA', img.size, (r, g, b, 255))
    back.alpha_composite(img)
    return back
