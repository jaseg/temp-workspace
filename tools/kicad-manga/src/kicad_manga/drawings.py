"""Hand-drawn-looking decorations for the manga schematic render.

Every function returns an SVG fragment in sheet millimetres. The shapes are
generated from a `random.Random`, so each plant, vine and cable comes out a bit
different, but the same seed always draws the same sheet.

The geometry (and every random choice) is worked out here; the elements are in
templates/drawings/ and the fixed artwork in static/deco-*.svg.
"""

import math

from markupsafe import Markup

from .palette import LINE
from .svg import env, render, tag

GREENS = ['#a6dfb5', '#bfe6a4', '#94d6bd', '#cdeeb8', '#b2e2c8']
DEEP_GREENS = ['#7cc79a', '#93cf86', '#6fc3a5']
POTS = ['#ffc7d9', '#c9d8ff', '#ffe0a8', '#d8c8ff', '#ffd2bd', '#bfeee6']
FLOWERS = ['#ffa8c8', '#ffd27f', '#c7b2ff', '#ff9fae', '#a9d8ff', '#fff2a0']
CABLES = ['#ff9fb5', '#9fcbff', '#ffd77a', '#a9e3b5', '#c8b0ff', '#ffb98a']


def f(v):
    """Numbers in path data. The drawings are written to 0.01 mm."""
    return f'{v:.2f}'.rstrip('0').rstrip('.')


def mm(v):
    """A number for a template, rounded to 0.01 mm like the path data (the templates' `f` keeps three
    decimals)."""
    return round(v, 2)


def pts_d(pts):
    return 'M' + 'L'.join(f'{f(x)} {f(y)}' for x, y in pts)


def smooth_d(pts):
    """Catmull-Rom through pts, written as cubic Beziers."""
    if len(pts) < 3:
        return pts_d(pts)
    out = [f'M{f(pts[0][0])} {f(pts[0][1])}']
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i else pts[0]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        out.append(f'C{f(c1[0])} {f(c1[1])} {f(c2[0])} {f(c2[1])} {f(p2[0])} {f(p2[1])}')
    return ''.join(out)


def leaf(x, y, ang, length, width, color, rib=True):
    """A pointed leaf whose base is at (x, y), pointing at `ang` degrees (0 = up)."""
    L, w = length, width
    d = (f'M0 0C{f(w)} {f(-L * .25)} {f(w * .8)} {f(-L * .8)} 0 {f(-L)}'
         f'C{f(-w * .8)} {f(-L * .8)} {f(-w)} {f(-L * .25)} 0 0Z')
    r = f'M0 0Q{f(w * .15)} {f(-L * .5)} 0 {f(-L * .82)}' if rib else None
    return render('drawings/leaf.svg.j2', x=mm(x), y=mm(y), ang=mm(ang), d=d, rib=r, color=color)


def heart_leaf(x, y, ang, s, color):
    d = (f'M0 0C{f(-s * .2)} {f(-s * .3)} {f(-s * .9)} {f(-s * .35)} {f(-s * .75)} {f(-s * .9)}'
         f'C{f(-s * .6)} {f(-s * 1.3)} {f(-s * .1)} {f(-s * 1.25)} 0 {f(-s * 1.05)}'
         f'C{f(s * .1)} {f(-s * 1.25)} {f(s * .6)} {f(-s * 1.3)} {f(s * .75)} {f(-s * .9)}'
         f'C{f(s * .9)} {f(-s * .35)} {f(s * .2)} {f(-s * .3)} 0 0Z')
    return render('drawings/leaf.svg.j2', x=mm(x), y=mm(y), ang=mm(ang), d=d, rib=f'M0 -.1V{f(-s * .95)}',
                  color=color)


def flower(x, y, r, color, petals=5, rot=0):
    return render('drawings/flower.svg.j2', x=mm(x), y=mm(y), rot=mm(rot), color=color,
                  angles=range(0, 360, 360 // petals), cy=mm(-r * .62), rx=mm(r * .42), ry=mm(r * .6),
                  mid=mm(r * .32))


def wrap(inner, sw=.38):
    """`inner` (SVG markup, also as a plain string from other modules) in the outline style shared by the
    drawings (templates/drawings/wrap.svg.j2)."""
    return env().get_template('drawings/wrap.svg.j2').module.wrap(sw, caller=lambda: Markup(inner))


# ----------------------------------------------------------------------------
# Pots. Base centre at (0, 0); they grow upwards (negative y).

def pot(rng, w, h, color, face):
    kind = rng.choice(['flowerpot', 'bowl', 'tin'])
    if kind == 'flowerpot':
        rim = h * .26
        body = (f'M{f(-w * .4)} {f(-h + rim)}L{f(-w * .3)} 0H{f(w * .3)}L{f(w * .4)} {f(-h + rim)}Z')
        shade = f'M{f(w * .14)} {f(-h + rim)}L{f(w * .12)} 0H{f(w * .3)}L{f(w * .4)} {f(-h + rim)}Z'
        rims = dict(x=mm(-w / 2), y=mm(-h), width=mm(w), height=mm(rim), rx=mm(rim * .3))
    elif kind == 'bowl':
        body = f'M{f(-w / 2)} {f(-h)}H{f(w / 2)}C{f(w / 2)} {f(-h * .2)} {f(w * .25)} 0 0 0C{f(-w * .25)} 0 {f(-w / 2)} {f(-h * .2)} {f(-w / 2)} {f(-h)}Z'
        shade = f'M{f(w * .18)} {f(-h)}H{f(w / 2)}C{f(w / 2)} {f(-h * .2)} {f(w * .25)} 0 {f(w * .1)} {f(-h * .02)}Z'
        rims = dict(cy=mm(-h), rx=mm(w / 2), ry=mm(h * .1))
    else:
        body = f'M{f(-w * .38)} {f(-h)}V{f(-h * .08)}Q{f(-w * .38)} 0 {f(-w * .3)} 0H{f(w * .3)}Q{f(w * .38)} 0 {f(w * .38)} {f(-h * .08)}V{f(-h)}Z'
        shade = f'M{f(w * .16)} {f(-h)}V0H{f(w * .3)}Q{f(w * .38)} 0 {f(w * .38)} {f(-h * .08)}V{f(-h)}Z'
        rims = dict(cy=mm(-h), rx=mm(w * .38), ry=mm(h * .09))
    top = -h
    svg = render('drawings/pot.svg.j2', kind=kind, color=color, body=body, shade=shade, rim=rims,
                 shadow_rx=mm(w * .45), shadow_ry=mm(h * .07 + .3),
                 face=rng.choice(['happy', 'cat', 'smile']) if face else None,
                 face_y=mm(-h * .45), face_k=mm(w / 22))
    return svg, top


def plant_leafy(rng, h):
    w = h * rng.uniform(.38, .48)
    ph = h * .3
    p, top = pot(rng, w, ph, rng.choice(POTS), rng.random() < .6)
    stems = []
    n = rng.randint(6, 9)
    heart = rng.random() < .5
    for i in range(n):
        a = -70 + 140 * (i + rng.uniform(-.3, .3)) / (n - 1)
        L = (h - ph) * rng.uniform(.55, .95) * (1 - abs(a) / 260)
        ex = math.sin(math.radians(a)) * L
        ey = top - math.cos(math.radians(a)) * L
        cx = ex * .3
        stem = f'M{f(rng.uniform(-w * .1, w * .1))} {f(top + 1)}Q{f(cx)} {f(top - L * .6)} {f(ex)} {f(ey)}'
        col = rng.choice(GREENS)
        s = rng.uniform(.17, .24) * h
        stems.append((stem, heart_leaf(ex, ey, a * 1.2, s * .62, col) if heart
                      else leaf(ex, ey + s * .1, a * 1.15, s, s * .42, col)))
    return render('drawings/plant_leafy.svg.j2', stems=stems, pot=p)


def plant_snake(rng, h):
    w = h * .34
    ph = h * .28
    p, top = pot(rng, w, ph, rng.choice(POTS), rng.random() < .5)
    blades = []
    n = rng.randint(4, 6)
    for i in range(n):
        x = (i - (n - 1) / 2) * w * .14
        L = (h - ph) * rng.uniform(.6, 1)
        a = (i - (n - 1) / 2) * rng.uniform(5, 10)
        col = rng.choice(DEEP_GREENS + GREENS)
        bw = w * .11
        d = f'M{f(-bw)} 0C{f(-bw * 1.4)} {f(-L * .5)} {f(-bw * .4)} {f(-L * .9)} 0 {f(-L)}C{f(bw * .4)} {f(-L * .9)} {f(bw * 1.4)} {f(-L * .5)} {f(bw)} 0Z'
        stripes = [f'M{f(-bw * .8)} {f(-L * t)}q{f(bw * .8)} {f(-bw * .5)} {f(bw * 1.6)} 0' for t in (.25, .45, .65)]
        blades.append((mm(x), mm(top + 1), mm(a), d, col, stripes))
    return render('drawings/plant_snake.svg.j2', blades=blades, pot=p)


def cactus(rng, h):
    w = h * .4
    ph = h * .32
    p, top = pot(rng, w, ph, rng.choice(POTS), rng.random() < .5)
    bh = h - ph
    bw = w * .36
    col = rng.choice(GREENS)
    body = (f'M{f(-bw / 2)} {f(top + 1)}V{f(top - bh + bw / 2)}A{f(bw / 2)} {f(bw / 2)} 0 0 1 {f(bw / 2)} {f(top - bh + bw / 2)}V{f(top + 1)}Z')
    arms = []
    for side in (-1, 1):
        if rng.random() < .8:
            ay = top - bh * rng.uniform(.35, .55)
            ah = bh * rng.uniform(.25, .4)
            aw = bw * .62
            ax = side * (bw / 2 + aw * .9)
            arms.append((f'M{f(side * bw * .4)} {f(ay)}H{f(ax)}V{f(ay - ah)}', mm(aw + .76), mm(aw)))
    spines = [(mm(rng.uniform(-bw * .35, bw * .35)), mm(top - rng.uniform(1, bh - 1))) for _ in range(10)]
    flw = flower(0, top - bh, bw * .45, rng.choice(FLOWERS))
    return render('drawings/cactus.svg.j2', color=col, arms=arms, body=body, top=mm(top),
                  line_top=mm(top - bh + 1.5), spines=spines, flower=flw, pot=p)


def succulent(rng, h):
    w = h * .9
    ph = h * .4
    p, top = pot(rng, w * .8, ph, rng.choice(POTS), rng.random() < .6)
    leaves = []
    for layer, (n, L) in enumerate(((9, h * .55), (7, h * .42), (5, h * .3))):
        col = GREENS[(layer + 1) % len(GREENS)] if layer else rng.choice(DEEP_GREENS)
        for i in range(n):
            a = -80 + 160 * i / (n - 1)
            leaves.append(leaf(0, top + 1, a * (1 - layer * .2), L, L * .32, col, rib=False))
    stalk = flw = None
    if rng.random() < .5:
        stalk = f'M0 {f(top - h * .25)}Q{f(h * .15)} {f(top - h * .55)} {f(h * .2)} {f(top - h * .75)}'
        flw = flower(h * .2, top - h * .75, h * .07, rng.choice(FLOWERS))
    return render('drawings/succulent.svg.j2', leaves=leaves, stalk=stalk, flower=flw, pot=p)


def tulips(rng, h):
    w = h * .42
    ph = h * .3
    p, top = pot(rng, w, ph, rng.choice(POTS), rng.random() < .5)
    out = []
    col = rng.choice(FLOWERS)
    n = rng.randint(3, 4)
    s = h * .09
    head = (f'M{f(-s)} {f(-s * 1.6)}L{f(-s * .5)} {f(-s * .9)} 0 {f(-s * 1.7)} {f(s * .5)} {f(-s * .9)} {f(s)} {f(-s * 1.6)}'
            f'C{f(s * 1.1)} {f(-s * .3)} {f(s * .5)} 0 0 0C{f(-s * .5)} 0 {f(-s * 1.1)} {f(-s * .3)} {f(-s)} {f(-s * 1.6)}Z')
    for i in range(n):
        x = (i - (n - 1) / 2) * w * .22
        L = (h - ph) * rng.uniform(.7, .95)
        tx = x * 1.8
        ty = top - L
        stem = f'M{f(x)} {f(top + 1)}Q{f(x)} {f(top - L * .5)} {f(tx)} {f(ty)}'
        out.append((stem, leaf(x, top + .5, (i - (n - 1) / 2) * 25, L * .45, L * .1, rng.choice(GREENS)),
                    mm(tx), mm(ty)))
    return render('drawings/tulips.svg.j2', tulips=out, stem_color=DEEP_GREENS[0], head=head, color=col, pot=p)


def mug(rng, h):
    w = h * .8
    col = rng.choice(POTS)
    body = f'M{f(-w * .4)} {f(-h * .62)}V{f(-h * .08)}Q{f(-w * .4)} 0 {f(-w * .3)} 0H{f(w * .2)}Q{f(w * .3)} 0 {f(w * .3)} {f(-h * .08)}V{f(-h * .62)}Z'
    handle = f'M{f(w * .3)} {f(-h * .5)}c{f(w * .25)} 0 {f(w * .25)} {f(h * .32)} 0 {f(h * .32)}'
    steam = [f'M{f(x)} {f(-h * .7)}c{f(-h * .1)} {f(-h * .1)} {f(h * .1)} {f(-h * .18)} 0 {f(-h * .3)}'
             for x in (-w * .15, w * .05)]
    return render('drawings/mug.svg.j2', color=col, shadow_rx=mm(w * .45), handle=handle,
                  handle_outline=mm(h * .1), handle_w=mm(h * .06), body=body,
                  coffee_cx=mm(-w * .05), coffee_cy=mm(-h * .62), coffee_rx=mm(w * .35), coffee_ry=mm(h * .06),
                  heart_x=mm(-w * .05), heart_y=mm(-h * .3), heart_k=mm(h * .022), steam=steam)


def books(rng, h):
    out, y = [], 0
    n = rng.randint(2, 4)
    bh = h / n
    for i in range(n):
        bw = h * rng.uniform(1.1, 1.5)
        x = rng.uniform(-1.2, 1.2)
        col = rng.choice(POTS)
        spines = f'M{f(x - bw / 2 + 1.2)} {f(y - bh)}v{f(bh)}M{f(x + bw / 2 - 1.2)} {f(y - bh)}v{f(bh)}'
        out.append((mm(x - bw / 2), mm(y - bh), mm(bw), mm(bh), col, spines,
                    mm(x + bw / 2 - .9), mm(y - bh + .4), mm(bh - .8)))
        y -= bh
    return render('drawings/books.svg.j2', books=out, heart_x=mm(rng.uniform(-2, 2)), heart_y=mm(y - 1.2))


def cat(rng, h):
    """A curled-up sleeping cat, about 2h wide."""
    col = rng.choice(['#fff', '#ffe9d6', '#e9e3f2'])
    patch = rng.choice(['#ffc9a3', '#cdbfe6', '#b9b0c4'])
    return render('drawings/cat.svg.j2', k=mm(h / 10), color=col, patch=patch)


GROUND_ITEMS = [
    # (draw, min h, max h, width/height)
    (plant_leafy, 22, 52, .95),
    (plant_snake, 24, 48, .5),
    (cactus, 18, 38, .7),
    (succulent, 10, 18, 1.1),
    (tulips, 18, 32, .6),
    (mug, 9, 12, 1.1),
    (books, 8, 12, 1.6),
    (cat, 9, 11, 2.2),
]



def grass(rng, x, y, w):
    """Neat cartoon grass tufts (three rounded blades each), with the odd flower."""
    tufts, flowers = [], []
    n = max(1, int(w / 4.2))
    for i in range(n):
        cx = x + (i + .5) * w / n + rng.uniform(-.5, .5)
        hgt = rng.uniform(2.2, 3.4)
        col = rng.choice(GREENS)
        tufts.append([leaf(cx + dx, y + .1, a + rng.uniform(-6, 6), hgt * k, .62, col, rib=False)
                      for dx, a, k in ((-.5, -30, .72), (0, 0, 1), (.5, 30, .78))])
    if w > 6 and rng.random() < .7:
        for _ in range(rng.randint(1, 2)):
            fx = x + rng.uniform(1, w - 1)
            fh = rng.uniform(3.5, 5.5)
            flowers.append((f'M{f(fx)} {f(y)}Q{f(fx + .4)} {f(y - fh / 2)} {f(fx)} {f(y - fh)}',
                            wrap(flower(fx, y - fh, rng.uniform(.9, 1.3), rng.choice(FLOWERS)), .25)))
    return render('drawings/grass.svg.j2', tufts=tufts, flowers=flowers)


# ----------------------------------------------------------------------------
# Vines: a stem along a guide path with alternating leaves, buds and curls

def vine(rng, pts, leaf_gap=3.2, size=1.0):
    nodes = []
    acc, side = 0, 1
    for i in range(1, len(pts)):
        (x0, y0), (x1, y1) = pts[i - 1], pts[i]
        seg = math.hypot(x1 - x0, y1 - y0)
        acc += seg
        if acc < leaf_gap or seg == 0:
            continue
        acc = 0
        ang = math.degrees(math.atan2(x1 - x0, -(y1 - y0)))
        side = -side
        r = rng.random()
        if r < .1:
            nodes.append(('piece', wrap(flower(x1, y1, 1.5 * size, rng.choice(FLOWERS), rot=rng.uniform(0, 72)), .3)))
        elif r < .2:
            sx, sy = x1, y1
            a0 = math.radians(ang + side * 70)
            curl = [(sx + math.sin(a0 + side * t * .9) * (2.4 - t * .35) * size * .8,
                     sy - math.cos(a0 + side * t * .9) * (2.4 - t * .35) * size * .8) for t in range(0, 7)]
            nodes.append(('curl', smooth_d([(sx, sy)] + curl)))
        else:
            L = rng.uniform(2.6, 3.8) * size
            nodes.append(('piece', wrap(leaf(x1, y1, ang + side * rng.uniform(45, 75), L, L * .42, rng.choice(GREENS)), .3)))
    return render('drawings/vine.svg.j2', d=smooth_d(pts), outline=mm(.9 * size), color=DEEP_GREENS[1],
                  core=mm(.45 * size), nodes=nodes)


def garland_pts(x0, x1, y, sag):
    n = max(8, int((x1 - x0) / 1.5))
    return [(x0 + (x1 - x0) * t / n, y + sag * 4 * (t / n) * (1 - t / n)) for t in range(n + 1)]


def bow(x, y, color):
    return render('drawings/bow.svg.j2', x=mm(x), y=mm(y), color=color)


def charm(rng, x, y, length):
    """A dangling string with a heart, star or tiny hanging planter."""
    kind = rng.choice(['heart-d', 'star', 'planter', 'sparkle'])
    ey = y + length
    if kind == 'planter':
        col = rng.choice(POTS)
        leaves = [leaf(x + dx, ey - .2, a, 2.8, 1.2, rng.choice(GREENS)) for dx, a in ((-1, -40), (0, 0), (1, 40))]
        trail = vine(rng, [(x + 1.6, ey + .5), (x + 2.4, ey + 3), (x + 1.8, ey + 6), (x + 2.6, ey + 9)], leaf_gap=2.2, size=.7)
        pot_d = f'M{f(x - 2.4)} {f(ey)}H{f(x + 2.4)}Q{f(x + 2.4)} {f(ey + 3.2)} {f(x)} {f(ey + 3.2)}Q{f(x - 2.4)} {f(ey + 3.2)} {f(x - 2.4)} {f(ey)}Z'
        hanger = f'M{f(x - 2.4)} {f(ey)}L{f(x)} {f(y + length * .4)}L{f(x + 2.4)} {f(ey)}'
        return render('drawings/charm.svg.j2', x=mm(x), y=mm(y), length=mm(length), planter=True, trail=trail,
                      leaves=leaves, pot=pot_d, hanger=hanger, color=col)
    s = 3.2 if kind != 'sparkle' else 4
    return render('drawings/charm.svg.j2', x=mm(x), y=mm(y), length=mm(length), planter=False, kind=kind,
                  use_y=mm(ey + s * .5), k=mm(s / 10), fill=rng.choice(FLOWERS))


# ----------------------------------------------------------------------------
# Loose cables

def plug(rng, x, y, ang, color):
    kind = rng.choice(['dupont', 'dupont', 'alligator', 'stripped', 'banana'])
    strands = []
    if kind == 'stripped':
        strands = [(mm(o * .25), mm(rng.uniform(2, 3)), mm(o * rng.uniform(.3, .7))) for o in (-2, -1, 0, 1, 2)]
    return render('drawings/plug.svg.j2', x=mm(x), y=mm(y), ang=mm(ang), kind=kind, color=color, strands=strands)


def cable(rng, pts, color):
    (x0, y0), (x1, y1) = pts[-2], pts[-1]
    ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
    return render('drawings/cable.svg.j2', d=smooth_d(pts), color=color, plug=plug(rng, x1, y1, ang, color))


# ----------------------------------------------------------------------------
# Little parts lying around, centred at (0, 0), about 14 mm long

def resistor(rng):
    bands = rng.sample(['#a0522d', '#ff6b6b', '#ffa94d', '#ffe066', '#69db7c', '#74c0fc', '#b197fc'], 3)
    return render('drawings/resistor.svg.j2', bands=[(mm(-2.2 + i * 1.5), c) for i, c in enumerate(bands)])


def led(rng):
    return render('drawings/led.svg.j2', color=rng.choice(['#ff9fb5', '#9fcbff', '#a9e3b5', '#ffd77a']))


def electrolytic(rng):
    return render('drawings/electrolytic.svg.j2', color=rng.choice(['#c9d8ff', '#d8c8ff', '#bfeee6']))


def chip(rng):
    return render('drawings/chip.svg.j2', color=rng.choice(['#6c5a7c', '#7d6b8f']),
                  legs=[mm(-3.75 + i * 2.5) for i in range(4)])


def ceramic(rng):
    return tag('use', href='#deco-ceramic', stroke=LINE, stroke_width=.3, stroke_linejoin='round',
               stroke_linecap='round')


PARTS = [resistor, led, electrolytic, chip, ceramic, resistor, led]


def cloud(w):
    h = w * .45
    d = (f'M{f(-w * .45)} 0C{f(-w * .6)} 0 {f(-w * .6)} {f(-h * .55)} {f(-w * .38)} {f(-h * .5)}'
         f'C{f(-w * .38)} {f(-h * 1.05)} {f(-w * .05)} {f(-h * 1.1)} {f(w * .02)} {f(-h * .75)}'
         f'C{f(w * .12)} {f(-h * 1.2)} {f(w * .45)} {f(-h * 1)} {f(w * .38)} {f(-h * .5)}'
         f'C{f(w * .6)} {f(-h * .5)} {f(w * .6)} 0 {f(w * .45)} 0Z')
    return render('drawings/cloud.svg.j2', d=d)


def shelf(x0, y, w):
    """A little wall shelf; y is the top of the plank."""
    brackets = [f'M{f(bx - 1.6)} {f(y + 1.8)}H{f(bx + 1.6)}L{f(bx)} {f(y + 6)}Z' for bx in (x0 + 7, x0 + w - 7)]
    return render('drawings/shelf.svg.j2', x=mm(x0), y=mm(y), w=mm(w), shadow_x=mm(x0 + .9), shadow_y=mm(y + .9),
                  brackets=brackets, grain=f'M{f(x0 + 2)} {f(y + .7)}h{f(w * .3)}M{f(x0 + w * .55)} {f(y + 1.1)}h{f(w * .25)}')


def twining_vine(rng, ex, y_start, y_end, lead_in=None):
    """A vine wound around the vertical frame line at x = ex, from y_start to y_end.

    Returns (behind, in_front): the stem passes behind the frame line on every other
    half-turn, so `behind` belongs under the frame and `in_front` over it.
    `lead_in` is an optional list of points the stem follows before it reaches the frame."""
    amp, wl = 1.7, rng.uniform(7, 9)
    ph = rng.uniform(0, 2 * math.pi)
    dirn = 1 if y_end > y_start else -1
    pts, front = [], []
    n = int(abs(y_end - y_start) / .5)
    for i in range(n + 1):
        y = y_start + dirn * i * .5
        a = ph + 2 * math.pi * i * .5 / wl
        pts.append((ex + amp * math.sin(a), y))
        front.append(math.cos(a) > 0)
    behind_d, front_d = [], []
    run, cur = [pts[0]], front[0]
    for p, fr in zip(pts[1:], front[1:]):
        run.append(p)
        if fr != cur:
            (front_d if cur else behind_d).append(smooth_d(run))
            run, cur = [p], fr
    (front_d if cur else behind_d).append(smooth_d(run))

    def stem(ds, light):
        return render('drawings/twining_stem.svg.j2', d=''.join(ds), color=light)

    behind = stem(behind_d, DEEP_GREENS[2])
    lead = vine(rng, lead_in + [pts[0]], leaf_gap=2.6) if lead_in else None
    nodes = []
    side = 1
    for i in range(6, len(pts), 5):
        if not front[i]:
            continue
        x, y = pts[i]
        side = -side
        r = rng.random()
        if r < .1:
            nodes.append(wrap(flower(x + side * 1.2, y, 1.4, rng.choice(FLOWERS), rot=rng.uniform(0, 72)), .3))
        else:
            L = rng.uniform(2.6, 3.8)
            nodes.append(wrap(leaf(x, y, side * rng.uniform(55, 100) + (0 if dirn > 0 else 180) * 0, L, L * .42, rng.choice(GREENS)), .3))
    # a curl at the growing tip
    x, y = pts[-1]
    tip = smooth_d([(x, y), (x + 1.2, y + dirn * 1), (x + .6, y + dirn * 2), (x - .2, y + dirn * 1.4), (x + .2, y + dirn * 1)])
    in_front = render('drawings/twining_vine.svg.j2', lead_in=lead, stem=stem(front_d, DEEP_GREENS[1]),
                      nodes=nodes, tip=tip)
    # plain strings: page.py appends its own markup to these with +
    return str(behind), str(in_front)


# ----------------------------------------------------------------------------
# Cables that obey gravity

def cable_clip(x, y):
    return render('drawings/cable_clip.svg.j2', x=mm(x), rx=mm(x - 1.3), ry=mm(y - 1.6), rivet_y=mm(y - .6))


def hanging_cable(rng, ax, ay, side, drop, color):
    """Clipped to the side frame line at (ax, ay); it bends inwards and falls straight down."""
    reach = rng.uniform(8, 11)          # clear of the vines wound round the frame
    sway = rng.uniform(-1.2, 1.2)
    pts = [(ax, ay), (ax + side * reach * .55, ay + .4), (ax + side * reach, ay + reach * .55)]
    x0, y0 = pts[-1]
    n = max(3, int(drop / 3))
    for i in range(1, n + 1):
        t = i / n
        pts.append((x0 + side * .6 * t + sway * math.sin(t * math.pi) * (1 - t * .5), y0 + drop * t))
    return cable(rng, pts, color) + cable_clip(ax, ay)


def draped_cable(rng, edge_x, plank_y, side, drop, color):
    """Lying on a shelf, slipping over its end (side=+1: right end) and hanging down."""
    r = .75
    lie = [(edge_x - side * rng.uniform(6, 10), plank_y - r), (edge_x - side * 2.5, plank_y - r),
           (edge_x - side * .2, plank_y - r * .8), (edge_x + side * .7, plank_y + .6), (edge_x + side * 1.0, plank_y + 2.5)]
    x0, y0 = lie[-1]
    n = max(3, int(drop / 3))
    sway = rng.uniform(-.8, .8)
    pts = lie + [(x0 + sway * math.sin(i / n * math.pi), y0 + drop * i / n) for i in range(1, n + 1)]
    end = (pts[0][0] - side * 1, pts[0][1])
    return cable(rng, pts, color) + plug(rng, end[0], end[1], 0 if side < 0 else 180, color)


def floor_cable(rng, x0, base, w, color):
    """Lying on the bottom of the frame between x0 and x0 + w: a plug at each end lying flat,
    and a loose coil in the middle."""
    y = base - 1.1
    a, b = x0 + 11, x0 + w - 11          # leave room for the plugs
    cx = (a + b) / 2 + rng.uniform(-2, 2)
    rx, ry = rng.uniform(3.6, 4.6), rng.uniform(2.1, 2.8)
    lead_end = cx - .9
    pts = [(a + (lead_end - a) * i / 4, y - .25 * (i % 2)) for i in range(4)] + [(lead_end, y)]
    for k in range(1, 25):
        t = 2 * math.pi * k / 24
        pts.append((cx - .9 + 1.8 * k / 24 - rx * math.sin(t) * .95, y - ry + ry * math.cos(t)))
    lx = pts[-1][0]
    pts += [(lx + (b - lx) * i / 3, y - .25 * (i % 2)) for i in range(1, 3)] + [(b - 1, y), (b, y)]
    return cable(rng, pts, color) + plug(rng, a, y, 180, color)


def standing(fn, foot, height):
    """Turn one of the loose-part drawings into an item that stands on a surface."""
    def draw(rng, h):
        k = h / height
        return tag('g', [fn(rng)], transform=f'scale({f(k)}) translate(0 {f(-foot)})')
    draw.__name__ = 'part_' + fn.__name__
    return draw


PART_ITEMS = [
    (standing(resistor, 1.5, 3.2), 3.4, 4.2, 14 / 3.2),
    (standing(led, 7.5, 11.1), 7, 10, 6.5 / 11.1),
    (standing(electrolytic, 8.5, 13.1), 8, 11, 5.8 / 13.1),
    (standing(chip, 4, 8), 5, 7, 10.5 / 8),
    (standing(ceramic, 6.5, 8.6), 6, 8, 5 / 8.6),
]
