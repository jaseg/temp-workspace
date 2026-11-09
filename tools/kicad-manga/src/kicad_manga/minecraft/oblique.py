"""Blocks seen from high up in the south-east, as small RGBA images ("sprites") of `px` pixels per block.

The view is an oblique projection that keeps the ground exactly as on the page: a point (x, y, z) of the world (x
east, y up, z south) lands at (x + h y, z - s y) on the page. For a camera `camera_deg` above the horizon and
turned `yaw_deg` from due south towards the east, s = cot(camera_deg) cos(yaw_deg) and h = -cot(camera_deg)
sin(yaw_deg): things lean a little to the north-west, away from the camera, and every block shows its top, its
south side and a sliver of its east side. Nothing is turned 45 degrees, and the floor plan lines up with the
sheet.

A sprite's floor cell starts `left` pixels from its left and `up` pixels from its top: whatever stands up reaches
that far above and to the west of the cell. For blocks the cell is the sprite's bottom right `px` x `px` square;
mobs may reach out of their cell on every side."""

import copy
import math

from PIL import Image

from .topdown import crop_uv, default_uv, face_quad, rotate_element, rotate_state, tint_shade


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


class Oblique:
    def __init__(self, pack, px=16, camera_deg=55, yaw_deg=30):
        self.pack = pack
        self.px = px
        c = 1 / math.tan(math.radians(camera_deg))
        self.s = c * math.cos(math.radians(yaw_deg))        # page y per block of height (up)
        self.h = -c * math.sin(math.radians(yaw_deg))       # page x per block of height (west when negative)
        self.view = (-self.h, 1, self.s)                    # towards the camera
        self.cache = {}

    def texture(self, rid, tint=None, shade=1.0):
        key = ('tex', rid, tint, round(shade, 3))
        if key not in self.cache:
            self.cache[key] = tint_shade(self.pack.texture(rid), tint, shade)
        return self.cache[key]

    def shade(self, n):
        """The game's flat face shading: tops full, north and south sides 80 %, east and west 60 %, bottoms 50 %
        (in between for faces that are turned)."""
        L = math.sqrt(sum(c * c for c in n)) or 1
        nx, ny, nz = (c / L for c in n)
        return nx * nx * .6 + ny * ny * (1.0 if ny > 0 else .5) + nz * nz * .8

    # -- block states -----------------------------------------------------------------------
    def state(self, name, props=None, tints=None, model_hook=None):
        """(sprite, up, left) of a block in a state: how far it reaches above and to the west of its floor cell."""
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
        view = self.view
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
                    if er and er.get('angle', 0):
                        pts = [rotate_element(p, er.get('axis', 'y'), er['angle'], er.get('origin', (8, 8, 8)))
                               for p in pts]
                    pts = [rotate_state(p, xr, yr) for p in pts]
                    o = pts[0]
                    u = tuple(pts[1][i] - o[i] for i in range(3))
                    v = tuple(pts[2][i] - o[i] for i in range(3))
                    n = tuple(-c for c in cross(u, v))          # outward normal
                    facing = sum(n[i] * view[i] for i in range(3))
                    if facing <= 1e-6 and not ('leaves' in t and facing < -1e-6):
                        # faces away from the camera, or edge-on; leaves show their back faces through their
                        # holes, as in the game
                        continue
                    c = tuple(o[i] + (u[i] + v[i]) / 2 for i in range(3))
                    depth = sum(c[i] * view[i] for i in range(3))
                    ti = f.get('tintindex')
                    tint = (tints or {}).get(ti) if ti is not None else None
                    out.append((depth, o, u, v, t, f.get('uv') or default_uv(face, fr, to), f.get('rotation', 0),
                                tint, self.shade(n)))
        return out

    def compose(self, models, tints):
        px, s, h = self.px, self.s, self.h
        faces = self.faces(models, tints)
        k = px / 16
        # the canvas: the floor cell, and whatever reaches out of it (up, or beyond its sides for mobs)
        xs, ys = [0, px], [0, px]
        for _, o, u, v, *_ in faces:
            for p in (o, [o[i] + u[i] for i in range(3)], [o[i] + v[i] for i in range(3)],
                      [o[i] + u[i] + v[i] for i in range(3)]):
                xs.append((p[0] + h * p[1]) * k)
                ys.append((p[2] - s * p[1]) * k)
        left, up = math.ceil(-min(xs) - 1e-6), math.ceil(-min(ys) - 1e-6)
        img = Image.new('RGBA', (left + math.ceil(max(xs) - 1e-6), up + math.ceil(max(ys) - 1e-6)), (0, 0, 0, 0))

        def proj(p):
            return (p[0] + h * p[1]) * k + left, (p[2] - s * p[1]) * k + up
        # a depth buffer: centre sorting alone gets small faces in front of big ones wrong (the hopper's bowl)
        zbuf = [[-math.inf] * img.width for _ in range(img.height)]
        view = self.view
        for _, o, u, v, t, uv, rot, tint, shade in sorted(faces, key=lambda f: f[0]):
            src = crop_uv(self.texture(t, tint, shade), uv, rot)
            O = proj(o)
            U = tuple(a - b for a, b in zip(proj(tuple(o[i] + u[i] for i in range(3))), O))
            V = tuple(a - b for a, b in zip(proj(tuple(o[i] + v[i] for i in range(3))), O))
            d0 = sum(o[i] * view[i] for i in range(3))
            du = sum(u[i] * view[i] for i in range(3))
            dv = sum(v[i] * view[i] for i in range(3))
            paste_affine(img, src, O, U, V, depth=(zbuf, d0, du, dv))
        return img, up, left

    # -- boxes of block textures (bodies, plaques) --------------------------------------------
    def box(self, top, side, h=16, tint=None):
        """(sprite, up, left) of a box `h` 16ths of a block tall, `top` on top and `side` on its sides."""
        key = ('box', top, side, h, tint)
        if key not in self.cache:
            faces = {f: {'texture': side, 'uv': [0, 16 - h, 16, 16]} for f in ('north', 'south', 'east', 'west')}
            faces['up'] = {'texture': top}
            if tint:
                for f in faces.values():
                    f['tintindex'] = 0
            model = {'textures': {}, 'elements': [{'from': [0, 0, 0], 'to': [16, h, 16], 'faces': faces}]}
            self.cache[key] = self.compose([(model, 0, 0)], {0: tint} if tint else None)
        return self.cache[key]


def paste_affine(dst, src, o, u, v, depth=None):
    """Draw src onto dst so that its corners land on o, o + u, o + v (pixels). With `depth` = (buffer, d0, du,
    dv), a pixel at (a, b) of the texture (0..1 each) lies at depth d0 + a du + b dv, and is drawn only where
    nothing nearer to the camera was drawn yet."""
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
    src_px = src.load()
    out = dst.load()
    W, H = src.width, src.height
    for yy in range(y0, y1):
        for xx in range(x0, x1):
            dx, dy = xx + .5 - ox, yy + .5 - oy
            sx, sy = ia * dx + ib * dy, ic * dx + id_ * dy
            if not (0 <= sx < W and 0 <= sy < H):
                continue
            c = src_px[int(sx), int(sy)]
            if not c[3]:
                continue
            if depth is not None:
                zbuf, d0, du, dv = depth
                z = d0 + du * sx / W + dv * sy / H
                if z < zbuf[yy][xx] - 1e-3:
                    continue
            if c[3] == 255:
                out[xx, yy] = c
                if depth is not None:
                    zbuf[yy][xx] = z
            else:
                b = out[xx, yy]
                a = c[3] / 255
                ab = b[3] / 255 * (1 - a)
                ao = a + ab
                out[xx, yy] = tuple(round((c[i] * a + b[i] * ab) / ao) for i in range(3)) + (round(ao * 255),)
