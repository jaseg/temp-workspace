"""Paper craft building blocks: colours, cast shadows, washi tape, torn and scalloped edges.

A piece of paper is drawn as its shadow (the same outline, nudged down and to the right, in a translucent
brown) and then the piece itself. Shadows use fill-opacity and stroke-opacity only, never `opacity` on a
group, so PDFs don't fill up with transparency groups."""

import colorsys
import math

from ..svg import group, num as f2, path, tag

INK = '#4b3a5a'            # plum: text and the thin paper strips symbols are drawn with
INK_SOFT = '#8a7499'
CARD = '#fbf3e4'           # the cream cardstock the page is made of
SHADOW = '#5b3f2c'         # cast shadows, translucent
SHADOW_ALPHA = .22
SH = (.32, .42)            # shadow offset on the schematic, mm
WHITE = '#fffdf8'

# Pastel papers, for stickers, confetti and the like
PAPERS = ['#f7b6c8', '#ffd59e', '#fff0a6', '#bfe8c6', '#b8dcf5', '#d4c4f5', '#f9c8a8', '#a9e2dc']


def hex_rgb(c):
    c = c.lstrip('#')
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def rgb_hex(r, g, b):
    return '#%02x%02x%02x' % tuple(max(0, min(255, round(v * 255))) for v in (r, g, b))


def shade(c, dl=0.0, ds=0.0):
    """`c` with its lightness and saturation moved by dl and ds."""
    h, l, s = colorsys.rgb_to_hls(*hex_rgb(c))
    return rgb_hex(*colorsys.hls_to_rgb(h, max(0, min(1, l + dl)), max(0, min(1, s + ds))))


def shadow(children, dx=SH[0], dy=SH[1], alpha=SHADOW_ALPHA):
    """A cast shadow: `children` are bare shapes (path data or tags without fill), filled in the shadow colour."""
    return group(children, cls='pc-shadow', transform=f'translate({f2(dx)} {f2(dy)})', fill=SHADOW,
                 fill_opacity=alpha)


def shadow_d(d, dx=SH[0], dy=SH[1], alpha=SHADOW_ALPHA):
    return path(d, transform=f'translate({f2(dx)} {f2(dy)})', fill=SHADOW, fill_opacity=alpha)


def shadow_stroke(d, width, dx=SH[0], dy=SH[1], alpha=SHADOW_ALPHA, cap='round'):
    return path(d, transform=f'translate({f2(dx)} {f2(dy)})', fill='none', stroke=SHADOW, stroke_opacity=alpha,
                stroke_width=width, stroke_linecap=cap, stroke_linejoin='round')


def piece(d, fill, edge=None, sh=SH, alpha=SHADOW_ALPHA, edge_w=.16, **attrs):
    """A cut-paper piece with its shadow. `edge`: a thin darker rim, for pieces that need to read on paper of
    a similar colour."""
    out = [shadow_d(d, sh[0], sh[1], alpha)] if sh else []
    out.append(path(d, fill=fill, stroke=edge, stroke_width=edge_w if edge else None,
                    stroke_linejoin='round' if edge else None, **attrs))
    return out


# ----------------------------------------------------------------------------
# Edges

def wobble(rng, n, amp):
    """n smooth-ish random offsets in [-amp, amp]."""
    out, v = [], 0.0
    for _ in range(n):
        v = .55 * v + rng.uniform(-amp, amp)
        out.append(max(-amp, min(amp, v)))
    return out


def torn_line(rng, x0, y0, x1, y1, step=.9, amp=.35):
    """Points along a torn edge from (x0, y0) to (x1, y1), jagged to the left and right of it."""
    L = math.hypot(x1 - x0, y1 - y0)
    n = max(2, int(L / step))
    nx, ny = -(y1 - y0) / (L or 1), (x1 - x0) / (L or 1)
    offs = wobble(rng, n + 1, amp)
    offs[0] = offs[-1] = 0
    return [(x0 + (x1 - x0) * i / n + nx * o, y0 + (y1 - y0) * i / n + ny * o) for i, o in enumerate(offs)]


def torn_rect(rng, x0, y0, x1, y1, step=.9, amp=.35, sides='tblr'):
    """A rectangle whose sides in `sides` (t, b, l, r) are torn."""
    def side(a, b, s):
        return torn_line(rng, *a, *b, step, amp)[:-1] if s in sides else [a]
    pts = side((x0, y0), (x1, y0), 't') + side((x1, y0), (x1, y1), 'r') + side((x1, y1), (x0, y1), 'b') + \
        side((x0, y1), (x0, y0), 'l')
    return 'M' + 'L'.join(f'{f2(x)} {f2(y)}' for x, y in pts) + 'Z'


def pts_d(pts, close=True):
    return 'M' + 'L'.join(f'{f2(x)} {f2(y)}' for x, y in pts) + ('Z' if close else '')


def zigzag_end(cx, cy, ux, uy, half_w, teeth=3, depth=.35):
    """Points across a tape end at (cx, cy), the tape running along (ux, uy): a zigzag torn edge, from the left
    side to the right side."""
    nx, ny = -uy, ux
    pts = []
    for i in range(teeth * 2 + 1):
        t = -half_w + 2 * half_w * i / (teeth * 2)
        o = depth / 2 if i % 2 else -depth / 2
        pts.append((cx + nx * t + ux * o, cy + ny * t + uy * o))
    return pts


def tape_strip(rng, x, y, length, width, angle, color, pattern='dots', alpha=.82, sh=(.35, .45)):
    """A short piece of washi tape centred on (x, y), with zigzag torn ends, as used to stick things down."""
    a = math.radians(angle)
    ux, uy = math.cos(a), math.sin(a)
    hl, hw = length / 2, width / 2
    start = zigzag_end(x - ux * hl, y - uy * hl, ux, uy, hw, teeth=max(2, round(width / .9)), depth=width * .12)
    end = zigzag_end(x + ux * hl, y + uy * hl, ux, uy, hw, teeth=max(2, round(width / .9)), depth=width * .12)
    pts = start + end[::-1]
    d = pts_d(pts)
    out = [shadow_d(d, sh[0], sh[1], .14), path(d, fill=color, fill_opacity=alpha)]
    out.append(tape_pattern(x, y, ux, uy, hl, hw, pattern, color))
    return group(out, cls='pc-tape')


def tape_pattern(x, y, ux, uy, hl, hw, pattern, color):
    """The print on a strip of tape running from (x, y) - u*hl to (x, y) + u*hl."""
    nx, ny = -uy, ux
    a = (x - ux * hl * .92, y - uy * hl * .92)
    b = (x + ux * hl * .92, y + uy * hl * .92)
    line = f'M{f2(a[0])} {f2(a[1])}L{f2(b[0])} {f2(b[1])}'
    if pattern == 'dots':
        return path(line, fill='none', stroke=WHITE, stroke_width=hw * .55, stroke_linecap='round',
                    stroke_dasharray=f'0 {f2(hw * 1.5)}', stroke_opacity=.9)
    if pattern == 'stripes':
        d = ''.join(f'M{f2(x + ux * t - nx * hw * .95 - ux * hw * .5)} {f2(y + uy * t - ny * hw * .95 - uy * hw * .5)}'
                    f'l{f2(nx * hw * 1.9 + ux * hw)} {f2(ny * hw * 1.9 + uy * hw)}'
                    for t in frange(-hl * .9, hl * .9, hw * 1.1))
        return path(d, fill='none', stroke=WHITE, stroke_width=hw * .28, stroke_opacity=.75)
    if pattern == 'grid':
        d = ''.join(f'M{f2(x + ux * t - nx * hw)} {f2(y + uy * t - ny * hw)}l{f2(nx * hw * 2)} {f2(ny * hw * 2)}'
                    for t in frange(-hl * .95, hl * .95, hw * .9))
        d += ''.join(f'M{f2(a[0] + nx * o)} {f2(a[1] + ny * o)}L{f2(b[0] + nx * o)} {f2(b[1] + ny * o)}'
                     for o in (-hw * .45, hw * .45))
        return path(d, fill='none', stroke=shade(color, -.18), stroke_width=hw * .1, stroke_opacity=.6)
    # 'stitch': a dashed line down the middle
    return path(line, fill='none', stroke=WHITE, stroke_width=hw * .3, stroke_dasharray=f'{f2(hw * .9)} {f2(hw * .7)}',
                stroke_opacity=.9)


def frange(a, b, step):
    out, v = [], a
    while v <= b + 1e-9:
        out.append(v)
        v += step
    return out


def scallops(x0, y0, x1, y1, r):
    """Points-free path data for a rectangle whose edges are scalloped inwards (semicircles of about radius r
    bulging into the rectangle): the inner edge of a scrapbook mat. Drawn clockwise."""
    def edge(ax, ay, bx, by):
        L = math.hypot(bx - ax, by - ay)
        n = max(1, round(L / (2 * r)))
        rr = L / n / 2
        ux, uy = (bx - ax) / L, (by - ay) / L
        out = []
        for i in range(n):
            ex, ey = ax + ux * 2 * rr * (i + 1), ay + uy * 2 * rr * (i + 1)
            out.append(f'A{f2(rr)} {f2(rr)} 0 0 0 {f2(ex)} {f2(ey)}')
        return ''.join(out)
    return (f'M{f2(x0)} {f2(y0)}' + edge(x0, y0, x1, y0) + edge(x1, y0, x1, y1) + edge(x1, y1, x0, y1)
            + edge(x0, y1, x0, y0) + 'Z')


def brad(x, y, r=.55):
    """A paper fastener: a gold dome with a highlight, for junctions."""
    return [tag('circle', cx=x + .18, cy=y + .24, r=r, fill=SHADOW, fill_opacity=.28),
            tag('circle', cx=x, cy=y, r=r, fill='#e9b949', stroke='#b98a2a', stroke_width=.1),
            tag('circle', cx=x - r * .3, cy=y - r * .32, r=r * .32, fill='#fff3c4', fill_opacity=.9)]


def spiral_d(cx, cy, r, turns=2.3, rot=0.0, steps=10):
    """A quilled paper coil: an Archimedean spiral from the centre out to radius r."""
    pts = []
    n = int(turns * steps)
    for i in range(n + 1):
        t = i / n
        a = rot + t * turns * 2 * math.pi
        rr = r * (.12 + .88 * t)
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    return 'M' + 'L'.join(f'{f2(x)} {f2(y)}' for x, y in pts)


# ----------------------------------------------------------------------------
# Hand-made geometry: shapes as point lists, cut out with a slightly unsteady hand

def sample_circle(cx, cy, r, step=.45):
    n = max(12, int(2 * math.pi * r / step))
    return [(cx + math.cos(2 * math.pi * i / n) * r, cy + math.sin(2 * math.pi * i / n) * r) for i in range(n)]


def sample_arc(s, m, e, step=.4):
    (x1, y1), (x2, y2), (x3, y3) = s, m, e
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-9:
        return [s, e]
    ux = ((x1 ** 2 + y1 ** 2) * (y2 - y3) + (x2 ** 2 + y2 ** 2) * (y3 - y1) + (x3 ** 2 + y3 ** 2) * (y1 - y2)) / d
    uy = ((x1 ** 2 + y1 ** 2) * (x3 - x2) + (x2 ** 2 + y2 ** 2) * (x1 - x3) + (x3 ** 2 + y3 ** 2) * (x2 - x1)) / d
    r = math.hypot(x1 - ux, y1 - uy)
    a1, a2, a3 = (math.atan2(y - uy, x - ux) for x, y in (s, m, e))
    span = (a3 - a1) % (2 * math.pi)
    if (a2 - a1) % (2 * math.pi) > span:        # the arc goes the other way round, through m
        span -= 2 * math.pi
    n = max(3, int(abs(span) * r / step))
    return [(ux + math.cos(a1 + span * i / n) * r, uy + math.sin(a1 + span * i / n) * r) for i in range(n + 1)]


def sample_bezier(p, n=16):
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = p[:4]
    out = []
    for i in range(n + 1):
        t = i / n
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
        out.append((a * x0 + b * x1 + c * x2 + d * x3, a * y0 + b * y1 + c * y2 + d * y3))
    return out


def resample(pts, step, closed):
    """Points along the polyline (or polygon) at most `step` apart, keeping its corners."""
    if len(pts) < 2:
        return list(pts)
    seq = pts + [pts[0]] if closed else pts
    out = []
    for (x0, y0), (x1, y1) in zip(seq, seq[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(L / step))
        out += [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n)]
    if not closed:
        out.append(pts[-1])
    return out


def _normals(pts, closed):
    out = []
    n = len(pts)
    for i in range(n):
        a = pts[i - 1] if (closed or i > 0) else pts[i]
        b = pts[(i + 1) % n] if (closed or i < n - 1) else pts[i]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1
        out.append((-dy / L, dx / L))
    return out


def _signed_area(pts):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1])) / 2


def cut_outline(rng, pts, amp=.07, step=.5):
    """A closed shape as if cut out with scissors: its edge wanders a little in and out, in short straight
    snips. Returns path data."""
    if len(pts) < 3:
        return pts_d(pts)
    q = resample(pts, step, True)
    nrm = _normals(q, True)
    offs = wobble(rng, len(q), amp)
    return pts_d([(x + nx * o, y + ny * o) for (x, y), (nx, ny), o in zip(q, nrm, offs)])


def cut_strip(rng, pts, width, closed=False, amp=.16, step=.45, end_wobble=True):
    """A strip of paper along the polyline, about `width` wide, its width varying a little as if cut by hand.
    Closed loops become a ring (two loops; fill it with the nonzero rule, they wind opposite ways). The ends
    of open strips are cut a little askew. Returns path data."""
    if len(pts) < 2:
        return ''
    q = resample(pts, step, closed)
    if closed and _signed_area(q) < 0:
        q = q[::-1]
    nrm = _normals(q, closed)
    w = [width / 2 * (1 + o) for o in wobble(rng, len(q), amp)]
    sk = [rng.uniform(-.25, .25) * width if end_wobble else 0 for _ in range(2)]
    left, right = [], []
    for i, ((x, y), (nx, ny), hw) in enumerate(zip(q, nrm, w)):
        hl = hr = hw * (1 + rng.uniform(-amp, amp) * .4)
        left.append((x + nx * hl, y + ny * hl))
        right.append((x - nx * hr, y - ny * hr))
    if not closed:
        (x0, y0), (x1, y1) = q[0], q[1]
        L = math.hypot(x1 - x0, y1 - y0) or 1
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        left[0] = (left[0][0] + ux * sk[0], left[0][1] + uy * sk[0])
        right[0] = (right[0][0] - ux * sk[0], right[0][1] - uy * sk[0])
        (x0, y0), (x1, y1) = q[-2], q[-1]
        L = math.hypot(x1 - x0, y1 - y0) or 1
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        left[-1] = (left[-1][0] + ux * sk[1], left[-1][1] + uy * sk[1])
        right[-1] = (right[-1][0] - ux * sk[1], right[-1][1] - uy * sk[1])
        return pts_d(left + right[::-1])
    return pts_d(left) + pts_d(right[::-1])


def soft_shadow(d, depth=1.0, alpha=1.0):
    """Two stacked translucent copies of the outline, a near dark one and a far faint one: a soft shadow
    without a blur filter."""
    return [path(d, transform=f'translate({f2(.16 * depth)} {f2(.22 * depth)})', fill=SHADOW,
                 fill_opacity=.13 * alpha),
            path(d, transform=f'translate({f2(.38 * depth)} {f2(.5 * depth)})', fill=SHADOW,
                 fill_opacity=.08 * alpha)]


def mute(c):
    """Real paper and ink: pastel colours lose most of their saturation and a little lightness, and drift
    warm."""
    r, g, b = hex_rgb(c)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    s *= .52
    l = .04 + l * .9
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    warm = (.78, .70, .58)
    k = .1
    return rgb_hex(r * (1 - k) + warm[0] * k, g * (1 - k) + warm[1] * k, b * (1 - k) + warm[2] * k)


def rect_pts(x0, y0, x1, y1, r=0.0, n=3):
    """A rectangle's outline as points, its corners rounded by r (sampled with n points each)."""
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
    if r <= 0:
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    out = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            out.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return out


def cut_piece(rng, pts, colour, depth=1.0, amp=.07, **attrs):
    """A piece of paper cut along `pts`, with its soft shadow."""
    d = cut_outline(rng, pts, amp=amp, step=max(.5, amp * 7))
    return soft_shadow(d, depth) + [path(d, fill=colour, **attrs)]


def area(pts):
    return abs(_signed_area(pts))
