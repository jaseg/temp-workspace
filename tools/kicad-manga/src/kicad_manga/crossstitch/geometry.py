"""Flattening gerbonara's SVG export into plain geometry.

gerbonara's `to_svg()` draws every schematic item like KiCad does, text included (in KiCad's stroke font). This
module walks the `Tag` trees it returns, applies their transforms, and hands back polylines and circles in sheet
millimetres, so the cross-stitch style can embroider exactly what KiCad would draw."""

import math
import re
from dataclasses import dataclass, field

NUM = r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?'


class Affine:
    """A 2D affine map (a c e / b d f)."""

    def __init__(self, a=1., b=0., c=0., d=1., e=0., f=0.):
        self.m = (a, b, c, d, e, f)

    def __matmul__(self, o):
        a, b, c, d, e, f = self.m
        A, B, C, D, E, F = o.m
        return Affine(a * A + c * B, b * A + d * B, a * C + c * D, b * C + d * D, a * E + c * F + e, b * E + d * F + f)

    def __call__(self, x, y):
        a, b, c, d, e, f = self.m
        return a * x + c * y + e, b * x + d * y + f

    @property
    def scale(self):
        a, b, c, d, _, _ = self.m
        return math.sqrt(abs(a * d - b * c))

    @classmethod
    def parse(cls, s):
        out = cls()
        for name, args in re.findall(r'(\w+)\s*\(([^)]*)\)', s or ''):
            v = [float(x) for x in re.findall(NUM, args)]
            if not v:
                continue
            if name == 'translate':
                t = cls(e=v[0], f=v[1] if len(v) > 1 else 0)
            elif name == 'scale':
                t = cls(a=v[0], d=v[1] if len(v) > 1 else v[0])
            elif name == 'rotate':
                r = math.radians(v[0])
                t = cls(math.cos(r), math.sin(r), -math.sin(r), math.cos(r))
                if len(v) == 3:
                    t = cls(e=v[1], f=v[2]) @ t @ cls(e=-v[1], f=-v[2])
            elif name == 'matrix':
                t = cls(*v)
            else:
                continue
            out = out @ t
        return out


@dataclass
class Prim:
    """A polyline (`pts`, `closed`) or a circle (`center`, `r`), with the stroke and fill it was drawn with."""
    kind: str                  # 'line' or 'circle'
    pts: list = field(default_factory=list)
    closed: bool = False
    center: tuple = None
    r: float = 0.
    width: float = 0.
    stroke: str = None
    fill: str = None


def arc_points(x1, y1, rx, ry, rot, large, sweep, x2, y2, step_deg=10):
    """An SVG elliptical arc as points (without the start point)."""
    if rx == 0 or ry == 0:
        return [(x2, y2)]
    phi = math.radians(rot)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    rx, ry = abs(rx), abs(ry)
    lam = x1p ** 2 / rx ** 2 + y1p ** 2 / ry ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    co = math.sqrt(max(0, num / den)) if den else 0
    if large == sweep:
        co = -co
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx, cy = cp * cxp - sp * cyp + (x1 + x2) / 2, sp * cxp + cp * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a
    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    n = max(2, int(abs(math.degrees(dt)) / step_deg))
    out = []
    for k in range(1, n + 1):
        t = t1 + dt * k / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        out.append((cp * x - sp * y + cx, sp * x + cp * y + cy))
    return out


def path_polylines(d):
    """SVG path data (M, L, H, V, A, C, Q, Z, absolute or relative) as [(points, closed)]."""
    toks = re.findall(r'[MmLlHhVvAaCcQqZz]|' + NUM, d)
    out, cur, x, y, sx, sy, cmd, i = [], [], 0., 0., 0., 0., 'M', 0

    def nums(n):
        nonlocal i
        v = [float(t) for t in toks[i:i + n]]
        i += n
        return v
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t
            i += 1
            if cmd in 'Zz':
                if cur:
                    out.append((cur, True))
                cur = []
                x, y = sx, sy
                continue
        rel = cmd.islower()
        c = cmd.upper()
        ox, oy = (x, y) if rel else (0., 0.)
        if c == 'M':
            px, py = nums(2)
            if cur:
                out.append((cur, False))
            x, y = ox + px, oy + py
            sx, sy = x, y
            cur = [(x, y)]
            cmd = 'l' if rel else 'L'
        elif c == 'L':
            px, py = nums(2)
            x, y = ox + px, oy + py
            cur.append((x, y))
        elif c == 'H':
            px, = nums(1)
            x = ox + px
            cur.append((x, y))
        elif c == 'V':
            py, = nums(1)
            y = oy + py
            cur.append((x, y))
        elif c == 'A':
            rx, ry, rot, large, sweep, px, py = nums(7)
            nx, ny = ox + px, oy + py
            cur.extend(arc_points(x, y, rx, ry, rot, int(large), int(sweep), nx, ny))
            x, y = nx, ny
        elif c in 'CQ':
            n = 6 if c == 'C' else 4
            v = nums(n)
            ctrl = [(ox + v[k], oy + v[k + 1]) for k in range(0, n, 2)]
            p0 = (x, y)
            for k in range(1, 13):
                tt = k / 12
                if c == 'C':
                    (ax, ay), (bx, by), (ex, ey) = ctrl
                    u = 1 - tt
                    px = u ** 3 * p0[0] + 3 * u * u * tt * ax + 3 * u * tt * tt * bx + tt ** 3 * ex
                    py = u ** 3 * p0[1] + 3 * u * u * tt * ay + 3 * u * tt * tt * by + tt ** 3 * ey
                else:
                    (ax, ay), (ex, ey) = ctrl
                    u = 1 - tt
                    px = u * u * p0[0] + 2 * u * tt * ax + tt * tt * ex
                    py = u * u * p0[1] + 2 * u * tt * ay + tt * tt * ey
                cur.append((px, py))
            x, y = ctrl[-1]
        else:
            i += 1
    if cur:
        out.append((cur, False))
    return out


def inherit(attrs, ctx):
    ctx = dict(ctx)
    for k in ('fill', 'stroke', 'stroke_width', 'stroke-width'):
        if k in attrs:
            ctx[k.replace('-', '_')] = attrs[k]
    return ctx


def flatten(tags, xf=None, ctx=None):
    """Prims for gerbonara `Tag`s (or an iterable of them), in the coordinates of the outermost one."""
    xf = xf or Affine()
    ctx = ctx or {'fill': 'black', 'stroke': None, 'stroke_width': 0}
    out = []
    if hasattr(tags, 'name'):
        tags = [tags]
    for t in tags:
        if t is None or isinstance(t, str):
            continue
        a = t.attrs
        m = xf @ Affine.parse(a.get('transform', ''))
        c = inherit(a, ctx)
        width = float(c.get('stroke_width') or 0) * m.scale
        stroke = c.get('stroke')
        fill = c.get('fill')
        fill = None if fill in (None, 'none') else fill
        stroke = None if stroke in (None, 'none') else stroke
        if t.name == 'g' or t.name == 'svg':
            out += flatten(t.children, m, c)
        elif t.name == 'path':
            for pts, closed in path_polylines(str(a.get('d', ''))):
                out.append(Prim('line', [m(*p) for p in pts], closed, width=width, stroke=stroke, fill=fill))
        elif t.name in ('polyline', 'polygon'):
            v = [float(x) for x in re.findall(NUM, str(a.get('points', '')))]
            pts = [m(v[k], v[k + 1]) for k in range(0, len(v) - 1, 2)]
            out.append(Prim('line', pts, t.name == 'polygon', width=width, stroke=stroke, fill=fill))
        elif t.name == 'line':
            p = [m(float(a.get('x1', 0)), float(a.get('y1', 0))), m(float(a.get('x2', 0)), float(a.get('y2', 0)))]
            out.append(Prim('line', p, width=width, stroke=stroke))
        elif t.name == 'circle':
            cx, cy, r = (float(a.get(k, 0)) for k in ('cx', 'cy', 'r'))
            out.append(Prim('circle', center=m(cx, cy), r=r * m.scale, width=width, stroke=stroke, fill=fill))
        elif t.name == 'rect':
            x, y, w, h = (float(a.get(k, 0)) for k in ('x', 'y', 'width', 'height'))
            pts = [m(x, y), m(x + w, y), m(x + w, y + h), m(x, y + h)]
            out.append(Prim('line', pts, True, width=width, stroke=stroke, fill=fill))
        else:
            out += flatten(t.children, m, c)
    return out


def bbox(prims, pad=0.):
    xs, ys = [], []
    for p in prims:
        if p.kind == 'circle':
            xs += [p.center[0] - p.r, p.center[0] + p.r]
            ys += [p.center[1] - p.r, p.center[1] + p.r]
        else:
            xs += [q[0] for q in p.pts]
            ys += [q[1] for q in p.pts]
    if not xs:
        return None
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    for k in range(n):
        (x1, y1), (x2, y2) = poly[k], poly[(k + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 or 1e-12) + x1:
            inside = not inside
    return inside
