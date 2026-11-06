"""Passive components as little characters.

Each function draws in place of the symbol it replaces (the inductor's core lines
are drawn back on top). The pin ends stay visible so you can see where the wires
attach. Faces are always drawn upright.
"""

import math

from markupsafe import Markup

from .util import parse_si
from .svg import num as f, render, tag

INK = '#4b3a5a'
FUR = [('#ffffff', '#ffd0a8'), ('#fff1dc', '#ffb98a'), ('#e9e3f2', '#b9adc9'), ('#ffd9b3', '#f7a86b'),
       ('#f2f0f5', '#4b3a5a'), ('#fde7ef', '#d9b8c9')]
BODY = ['#ffe3c2', '#ffd6e5', '#d9f2e6', '#dfe8ff', '#fff0b8', '#eadcff']


# ----------------------------------------------------------------------------
# Capacitor cats

def cat_capacitor(rng, cx, cy, vertical, value, plates, plus=None):
    """`plates`: the two plate lines in sheet coordinates, redrawn on top."""
    c = parse_si(value)
    if c is None:
        chub = .45
    else:   # 1n -> .03, 100n -> .2, 1u -> .41, 4u7 -> .63, 10u -> .75, 22u -> .92
        chub = max(0, min(1, (math.log10(c) + 12) / 7.5)) ** 4
    fur, patch = rng.choice(FUR)
    rot = 0 if vertical else -90
    # body: narrow at the neck, wide and flat at the bottom; slim cats are a column,
    # fat cats a bottom-heavy loaf
    n = .42 + .5 * chub                # shoulder half-width: broad on the chonky ones
    b = .5 + 1.95 * chub               # base half-width
    yb = 1.72                          # flat bottom
    r = .3 + .5 * chub                 # bottom corner radius
    hr = .78 + .22 * chub              # head radius (x)
    hy = hr * (.9 - .18 * chub)        # fat cats have wide, squashed heads
    ear = 1.15 - .35 * chub            # big ears on the slim ones
    tail_side = rng.choice((-1, 1))
    ts = tail_side
    if chub < .35:   # slim: tail standing up in a hook
        tail = f'M{f(ts * b * .8)} 1.55C{f(ts * (b + 1.3))} 1.6 {f(ts * (b + 1.1))} .2 {f(ts * (b + 1.25))} -.5'
    else:            # fat: short tail wrapped along the floor
        tail = f'M{f(ts * b * .7)} 1.55C{f(ts * (b + .7))} 1.75 {f(ts * (b + .8))} 1.1 {f(ts * (b + .35))} .8'
    # the sides bulge out right below the shoulders, so big cats come out as a plump
    # mochi/loaf rather than a bottle
    k1 = .15 + .8 * chub
    y1, y2 = -.45 + .55 * (1 - chub), .55 - .45 * chub
    body = (f'M{f(-n)} -.5Q0 -.78 {f(n)} -.5C{f(n + (b - n) * k1)} {f(y1)} {f(b)} {f(y2)} {f(b)} {f(yb - r)}'
            f'Q{f(b)} {f(yb)} {f(b - r)} {f(yb)}H{f(-b + r)}Q{f(-b)} {f(yb)} {f(-b)} {f(yb - r)}'
            f'C{f(-b)} {f(y2)} {f(-n - (b - n) * k1)} {f(y1)} {f(-n)} -.5Z')
    head_patch = rng.random() < .45
    eyes = rng.choice(['dot', 'happy', 'sleepy'])
    if plus:   # polarised: a little "+" badge by the positive end
        ox, oy = (1.9, 0) if vertical else (0, -1.9)
        plus = (plus[0] + ox, plus[1] + oy)
    return render('characters/cat_capacitor.svg.j2', cx=cx, cy=cy, rot=rot, fur=fur, patch=patch, chub=chub,
                  tail=tail, body=body, b=b, yb=yb, pw=max(.42, b - .45), hr=hr, hy=hy, ear=ear,
                  head_patch=head_patch, eyes=eyes, ex=hr * .4, ey=-1.02, unknown=c is None, qx=max(b, hr) + .2,
                  plates=plates, plus=plus)


# ----------------------------------------------------------------------------
# Resistors: grumpy little boxes that throw things

def brick(x, y, ang, k=1.5):
    return tag('use', href='#brick', transform=f'translate({f(x)} {f(y)}) rotate({f(ang)}) scale({f(k)})',
               stroke=INK, stroke_width=.12, stroke_linejoin='round')


def molotov(x, y, ang, k=1.35):
    return tag('use', href='#molotov', transform=f'translate({f(x)} {f(y)}) rotate({f(ang)}) scale({f(k)})',
               stroke=INK, stroke_width=.12, stroke_linejoin='round')


def resistor_guy(rng, cx, cy, vertical, half_len, mood, throw):
    """Draw the resistor box itself (a bit chubbier) with a face and arms.

    `throw` is None or (dx, dy, kind): where the projectile flies, relative to the centre."""
    hw = 1.25
    if vertical:
        x0, y0, x1, y1 = cx - hw, cy - half_len, cx + hw, cy + half_len
    else:
        x0, y0, x1, y1 = cx - half_len, cy - hw, cx + half_len, cy + hw
    col = rng.choice(BODY)
    arms, thrown = [], None
    if throw:
        dx, dy, kind = throw
        n = math.hypot(dx, dy)
        ux, uy = dx / n, dy / n
        # hand on the body edge facing the target, raised a little
        if vertical:
            hx, hy = (x1 if ux > 0 else x0), cy - .4
        else:
            hx, hy = cx + ux * .6, (y1 if uy > 0 else y0)
        tx, ty = hx + ux * 1.1 - .2 * (1 if uy <= 0 else -1) * abs(uy), hy + uy * 1.1 - .5 * abs(ux)
        px, py = cx + dx, cy + dy
        mx, my = (tx + px) / 2 - uy * .9 * 0 , min(ty, py) - 1.1
        ang = rng.uniform(-35, 35)
        # the other arm on its hip
        ox, oy = (x0, cy + .3) if vertical and ux > 0 else (x1, cy + .3) if vertical else (cx - ux * .6, y0 if uy > 0 else y1)
        sgn = -1 if (vertical and ux > 0) else 1
        thrown = dict(hx=hx, hy=hy, cx=hx + ux * .3, cy=hy - .8, tx=tx, ty=ty, mx=mx, my=my, px=px, py=py,
                      projectile=brick(px, py, ang) if kind == 'brick' else molotov(px, py, ang * .6),
                      speed=[(px - ux * 1.4 + i * uy * .4, py - uy * 1.4 - i * ux * .4) for i in (-1, 1)],
                      dx=-ux * .5, dy=-uy * .5, hip=(ox, oy, sgn) if vertical else None)
    elif vertical:
        arms = [(x1 if sx > 0 else x0, cy, sx) for sx in (-1, 1)]
    return render('characters/resistor_guy.svg.j2', x0=x0, y0=y0, x1=x1, y1=y1, col=col, arms=arms, throw=thrown,
                  mood=mood, fx=cx, fy=cy - (.25 if vertical else 0))


def resistor_face_defs():
    """The faces (#rface-grumpy, -yell, -smug, -pout) are in static/char-resistor-faces.svg now, whose <defs>
    go into the document's <defs> by themselves; kept for styles.py."""
    return Markup('')


# ----------------------------------------------------------------------------
# Ferrite bead caterpillar

def caterpillar(rng, a, b, core_lines):
    """Segments from sheet point a to b, head at a; core lines redrawn on top."""
    (ax, ay), (bx, by) = a, b
    L = math.hypot(bx - ax, by - ay)
    ux, uy = (bx - ax) / L, (by - ay) / L
    nx, ny = -uy, ux
    col = rng.choice(['#bfe6a4', '#a6dfb5', '#cdeeb8'])
    n = 5
    segments = []
    for i in reversed(range(n)):
        t = (i + .5) / n
        px, py = ax + ux * L * t, ay + uy * L * t
        legs = [(px + nx * s * .55, py + ny * s * .55, nx * s * .3, ny * s * .3) for s in (-1, 1)] if i else []
        segments.append((px, py, .62 if i else .78, col if i else '#d9f5c4', legs))
    hx, hy = ax + ux * L * .5 / n, ay + uy * L * .5 / n
    antennae = [(hx - ux * .5 + nx * s * .25, hy - uy * .5 + ny * s * .25,
                 hx - ux * .9 + nx * s * .55, hy - uy * .9 + ny * s * .55) for s in (-1, 1)]
    return render('characters/caterpillar.svg.j2', segments=segments, antennae=antennae, hx=hx, hy=hy,
                  core_lines=core_lines)


# ----------------------------------------------------------------------------
# Dancing crystal

NOTES = [(-3.2, -3.6, 1.6, '♪'), (2.8, -3.9, 1.9, '♫'), (4.3, -2.2, 1.3, '♪'), (-4.4, -2.0, 1.2, '♬'),
         (-3.4, 3.2, 1.5, '♫'), (3.6, 3.0, 1.5, '♪'), (-5.5, .6, 1.3, '♪'), (5.6, .4, 1.3, '♬'),
         (-7.5, -1.8, 1.7, '♫'), (-9.2, .8, 1.4, '♪'), (-7, 3.4, 1.3, '♬'), (-10.5, -2.6, 1.2, '♪')]
NOTE_COLOURS = ['#ff8fbf', '#8fc3ff', '#b79cff', '#7fd8c0']


def dancing_crystal(rng, cx, cy, body, free=lambda x, y: True):
    """`body` = the crystal's box (x0, y0, x1, y1) in sheet coordinates."""
    x0, y0, x1, y1 = body
    notes = []
    for i, (dx, dy, s, ch) in enumerate(NOTES):
        if not free(cx + dx + s * .3, cy + dy - s * .4):
            continue
        notes.append((cx + dx, cy + dy, s, NOTE_COLOURS[i % 4], f'{rng.uniform(-20, 20):.0f}', ch))
    return render('characters/dancing_crystal.svg.j2', cx=cx, cy=cy, x0=x0, y0=y0, x1=x1, y1=y1, notes=notes)


def legend(rng, cast):
    """The cast of characters on this sheet, as (svg, width, height), origin top left.
    `cast`: {'cap': True, 'res': True, 'ind': 'inductor' | 'ferrite bead', 'xtal': True}."""
    cats, cats_y, y = [], None, 12
    if cast.get('cap'):       # a row of cats from slim to chonky
        cats_y = y
        for i, v in enumerate(['10p', '1n', '100n', '1u', '4u7', '22u']):
            cx = 12 + i * 13.5
            cats.append((cx, cat_capacitor(rng, cx, y + 9, True, v, []), v.replace('u', 'µ') + 'F'))
        y += 22
    # the other characters in a row of slots, each drawn around the origin (the bus in place)
    others = []
    for i, kind in enumerate(k for k in ('res', 'ind', 'xtal', 'bus') if cast.get(k)):
        x, oy = 6 + i * 50, y + 6
        if kind == 'res':
            svg = resistor_guy(rng, 0, 0, True, 1.778, 'grumpy', (3.6, -.6, 'brick'))
        elif kind == 'ind':
            svg = caterpillar(rng, (-2.6, 0), (2.6, 0), [])
        elif kind == 'xtal':
            svg = dancing_crystal(rng, 0, 0, (-.762, -1.524, .762, 1.524), lambda a, b: b < -1 and abs(a) < 5)
        else:
            svg = _cat_bus([((x + 4, oy + 5), (x + 13, oy + 5))], (x + 13, oy + 5, 1, 0), (x + 4, oy + 5, -1, 0),
                           [(x + 6.5, oy + 5, 0, 1), (x + 10.5, oy + 5, 0, 1)], (), tagged=False)
        others.append((kind, x, oy, svg))
    w = max(150, 12 + 50 * len(others))
    if others:
        y += 18
    h = y + 2
    svg = render('characters/legend.svg.j2', w=w, h=h, cats=cats, cats_y=cats_y, others=others, ind=cast.get('ind'))
    return svg, w, h


# ----------------------------------------------------------------------------
# Buses: one long fluffy tabby per connected bus, with lots of little legs

BUS_FUR, BUS_STRIPE = '#ffd6a8', '#efae78'   # also in static/char-bus.svg
BUS_LINE = '#7a6888'


def cat_bus(segments, head, tail, legs, entries=()):
    """`segments`: [(a, b)] in sheet coordinates (each one a <path data-kind="bus">);
    `head`/`tail`: (x, y, ux, uy), an end point and the direction pointing out of the bus;
    `legs`: [(x, y, nx, ny)] where a leg starts and which side it hangs to;
    `entries`: [(point on the bus, point on the wire, colour, is_leg)] bus entries: on the
    legs' side they are legs (the wire leaves from the paw), otherwise slightly squiggly
    wires coming in through a window."""
    return _cat_bus(segments, head, tail, legs, entries)


def _cat_bus(segments, head, tail, legs, entries, tagged=True):
    """`tagged`: mark the segments data-kind="bus" (not in the legend)."""
    half = 1.45                     # half the body's thickness
    leg_entries = []
    for p, q, col, is_leg in entries:      # entries that are legs: wire from the paw outwards
        if not is_leg:
            continue
        vx, vy = q[0] - p[0], q[1] - p[1]
        paw = (p[0] + vx * .84, p[1] + vy * .84)
        leg = ((p[0] + vx * .38, p[1] + vy * .38), (p[0] + vx * .79, p[1] + vy * .79))
        leg_entries.append((paw, q, col, leg, math.degrees(math.atan2(vy, vx)) + 90))
    # legs first, the body covers their tops
    plain_legs = [((x + nx * .9, y + ny * .9), (x + nx * 2.6, y + ny * 2.6), (x + nx * 2.75, y + ny * 2.75))
                  for x, y, nx, ny in legs]
    tx, ty, tux, tuy = tail        # a fluffy tail curling up
    tail_curve = ((tx, ty), (tx + tux * 2.8, ty + tuy * 2.8), (tx + tux * 3.8, ty + tuy * 3.8 - 2.6),
                  (tx + tux * 2.2, ty + tuy * 2.2 - 3.1))
    stripes, windows = [], []
    hx, hy = head[0], head[1]
    taps = [p for p, _, _, is_leg in entries if not is_leg]
    for a, b in segments:          # windows along the back, tabby stripes between them
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1:
            continue
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        nx, ny = -uy, ux
        t, k = 1.4, 0
        while t < L - 1:
            px, py = a[0] + ux * t, a[1] + uy * t
            near_tap = min((math.hypot(px - q[0], py - q[1]) for q in taps), default=99)
            if math.hypot(px - hx, py - hy) > 3.5 and near_tap > 1.6:
                if k % 2:
                    windows.append((px, py, math.degrees(math.atan2(uy, ux))))
                else:
                    stripes.append(((px + nx * 1.05, py + ny * 1.05), (px + ux * .4, py + uy * .4),
                                    (px - nx * 1.05, py - ny * 1.05)))
            t += 1.9
            k += 1
        for q in taps:             # a window wherever a bus entry comes in
            if on_seg(q, a, b):
                windows.append((q[0], q[1], math.degrees(math.atan2(uy, ux))))
    wires = []
    for p, q, col, is_leg in entries:      # the others: ordinary wires with a little wiggle, into a window
        if is_leg:
            continue
        dx, dy = p[0] - q[0], p[1] - q[1]
        n = math.hypot(dx, dy) or 1
        nx, ny = -dy / n * .55, dx / n * .55
        wires.append((q, (q[0] + dx * .35 + nx, q[1] + dy * .35 + ny), (q[0] + dx * .7 - nx, q[1] + dy * .7 - ny),
                      p, col))
    # the head, upright, just past the end of the bus: headlight eyes and a big grin
    ux, uy = head[2], head[3]
    return render('characters/cat_bus.svg.j2', segments=segments, half=half, tagged=tagged, line=BUS_LINE,
                  fur=BUS_FUR, stripe=BUS_STRIPE, leg_entries=leg_entries, legs=plain_legs, tail=tail_curve,
                  stripes=stripes, wires=wires, windows=windows, head=(hx + ux * 3.1, hy + uy * 3.1))


def on_seg(p, a, b, eps=0.01):
    (px, py), (ax, ay), (bx, by) = p, a, b
    if abs((bx - ax) * (py - ay) - (by - ay) * (px - ax)) > eps * max(1, math.hypot(bx - ax, by - ay)):
        return False
    return min(ax, bx) - eps <= px <= max(ax, bx) + eps and min(ay, by) - eps <= py <= max(ay, by) + eps
