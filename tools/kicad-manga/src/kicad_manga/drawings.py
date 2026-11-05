"""Hand-drawn-looking decorations for the manga schematic render.

Every function returns an SVG fragment in sheet millimetres. The shapes are
generated from a `random.Random`, so each plant, vine and cable comes out a bit
different, but the same seed always draws the same sheet.
"""

import math

LINE = '#7a6888'          # softer than the circuit ink, so drawings stay in the background
GREENS = ['#a6dfb5', '#bfe6a4', '#94d6bd', '#cdeeb8', '#b2e2c8']
DEEP_GREENS = ['#7cc79a', '#93cf86', '#6fc3a5']
GRASS_LINE = '#5f9f78'
POTS = ['#ffc7d9', '#c9d8ff', '#ffe0a8', '#d8c8ff', '#ffd2bd', '#bfeee6']
FLOWERS = ['#ffa8c8', '#ffd27f', '#c7b2ff', '#ff9fae', '#a9d8ff', '#fff2a0']
CABLES = ['#ff9fb5', '#9fcbff', '#ffd77a', '#a9e3b5', '#c8b0ff', '#ffb98a']


def f(v):
    return f'{v:.2f}'.rstrip('0').rstrip('.')


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
    r = f'<path d="M0 0Q{f(w * .15)} {f(-L * .5)} 0 {f(-L * .82)}" fill="none" stroke-width=".22"/>' if rib else ''
    return (f'<g transform="translate({f(x)} {f(y)}) rotate({f(ang)})">'
            f'<path d="{d}" fill="{color}"/>{r}</g>')


def heart_leaf(x, y, ang, s, color):
    d = (f'M0 0C{f(-s * .2)} {f(-s * .3)} {f(-s * .9)} {f(-s * .35)} {f(-s * .75)} {f(-s * .9)}'
         f'C{f(-s * .6)} {f(-s * 1.3)} {f(-s * .1)} {f(-s * 1.25)} 0 {f(-s * 1.05)}'
         f'C{f(s * .1)} {f(-s * 1.25)} {f(s * .6)} {f(-s * 1.3)} {f(s * .75)} {f(-s * .9)}'
         f'C{f(s * .9)} {f(-s * .35)} {f(s * .2)} {f(-s * .3)} 0 0Z')
    return (f'<g transform="translate({f(x)} {f(y)}) rotate({f(ang)})"><path d="{d}" fill="{color}"/>'
            f'<path d="M0 -.1V{f(-s * .95)}" fill="none" stroke-width=".22"/></g>')


def flower(x, y, r, color, petals=5, rot=0):
    ps = ''.join(f'<ellipse cx="0" cy="{f(-r * .62)}" rx="{f(r * .42)}" ry="{f(r * .6)}" transform="rotate({a})"/>'
                 for a in range(0, 360, 360 // petals))
    return (f'<g transform="translate({f(x)} {f(y)}) rotate({f(rot)})" fill="{color}">{ps}'
            f'<circle r="{f(r * .32)}" fill="#fff3a0"/></g>')


def wrap(inner, sw=.38):
    return (f'<g stroke="{LINE}" stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round">'
            f'{inner}</g>')


# ----------------------------------------------------------------------------
# Pots. Base centre at (0, 0); they grow upwards (negative y).

def pot(rng, w, h, color, face):
    kind = rng.choice(['flowerpot', 'bowl', 'tin'])
    if kind == 'flowerpot':
        rim = h * .26
        body = (f'M{f(-w * .4)} {f(-h + rim)}L{f(-w * .3)} 0H{f(w * .3)}L{f(w * .4)} {f(-h + rim)}Z')
        shade = f'M{f(w * .14)} {f(-h + rim)}L{f(w * .12)} 0H{f(w * .3)}L{f(w * .4)} {f(-h + rim)}Z'
        rims = f'<rect x="{f(-w / 2)}" y="{f(-h)}" width="{f(w)}" height="{f(rim)}" rx="{f(rim * .3)}" fill="{color}"/>'
        top = -h
    elif kind == 'bowl':
        body = f'M{f(-w / 2)} {f(-h)}H{f(w / 2)}C{f(w / 2)} {f(-h * .2)} {f(w * .25)} 0 0 0C{f(-w * .25)} 0 {f(-w / 2)} {f(-h * .2)} {f(-w / 2)} {f(-h)}Z'
        shade = f'M{f(w * .18)} {f(-h)}H{f(w / 2)}C{f(w / 2)} {f(-h * .2)} {f(w * .25)} 0 {f(w * .1)} {f(-h * .02)}Z'
        rims = f'<ellipse cx="0" cy="{f(-h)}" rx="{f(w / 2)}" ry="{f(h * .1)}" fill="{color}"/>'
        top = -h
    else:
        body = f'M{f(-w * .38)} {f(-h)}V{f(-h * .08)}Q{f(-w * .38)} 0 {f(-w * .3)} 0H{f(w * .3)}Q{f(w * .38)} 0 {f(w * .38)} {f(-h * .08)}V{f(-h)}Z'
        shade = f'M{f(w * .16)} {f(-h)}V0H{f(w * .3)}Q{f(w * .38)} 0 {f(w * .38)} {f(-h * .08)}V{f(-h)}Z'
        rims = f'<ellipse cx="0" cy="{f(-h)}" rx="{f(w * .38)}" ry="{f(h * .09)}" fill="{color}"/>'
        top = -h
    out = (f'<ellipse cx="0" cy=".3" rx="{f(w * .45)}" ry="{f(h * .07 + .3)}" fill="url(#tone-ink)" stroke="none" opacity=".3"/>'
           f'<path d="{body}" fill="{color}"/><path d="{shade}" fill="url(#tone-ink)" stroke="none" opacity=".18"/>{rims}')
    if face:
        fy = -h * .45
        out += (f'<g transform="translate(0 {f(fy)}) scale({f(w / 22)})" stroke="none"><use href="#face-{rng.choice(["happy", "cat", "smile"])}"/></g>')
    return out, top


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
        stems.append(f'<path d="M{f(rng.uniform(-w * .1, w * .1))} {f(top + 1)}Q{f(cx)} {f(top - L * .6)} {f(ex)} {f(ey)}" fill="none" stroke-width=".35"/>')
        col = rng.choice(GREENS)
        s = rng.uniform(.17, .24) * h
        stems.append(heart_leaf(ex, ey, a * 1.2, s * .62, col) if heart else leaf(ex, ey + s * .1, a * 1.15, s, s * .42, col))
    return wrap(''.join(stems) + p)


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
        blades.append(f'<g transform="translate({f(x)} {f(top + 1)}) rotate({f(a)})">'
                      f'<path d="M{f(-bw)} 0C{f(-bw * 1.4)} {f(-L * .5)} {f(-bw * .4)} {f(-L * .9)} 0 {f(-L)}C{f(bw * .4)} {f(-L * .9)} {f(bw * 1.4)} {f(-L * .5)} {f(bw)} 0Z" fill="{col}"/>'
                      + ''.join(f'<path d="M{f(-bw * .8)} {f(-L * t)}q{f(bw * .8)} {f(-bw * .5)} {f(bw * 1.6)} 0" fill="none" stroke="#e9ffe9" stroke-width=".3"/>'
                                for t in (.25, .45, .65)) + '</g>')
    return wrap(''.join(blades) + p)


def cactus(rng, h):
    w = h * .4
    ph = h * .32
    p, top = pot(rng, w, ph, rng.choice(POTS), rng.random() < .5)
    bh = h - ph
    bw = w * .36
    col = rng.choice(GREENS)
    body = (f'M{f(-bw / 2)} {f(top + 1)}V{f(top - bh + bw / 2)}A{f(bw / 2)} {f(bw / 2)} 0 0 1 {f(bw / 2)} {f(top - bh + bw / 2)}V{f(top + 1)}Z')
    arms = ''
    for side in (-1, 1):
        if rng.random() < .8:
            ay = top - bh * rng.uniform(.35, .55)
            ah = bh * rng.uniform(.25, .4)
            aw = bw * .62
            ax = side * (bw / 2 + aw * .9)
            arms += (f'<path d="M{f(side * bw * .4)} {f(ay)}H{f(ax)}V{f(ay - ah)}" fill="none" stroke="{LINE}" stroke-width="{f(aw + .76)}"/>'
                     f'<path d="M{f(side * bw * .4)} {f(ay)}H{f(ax)}V{f(ay - ah)}" fill="none" stroke="{col}" stroke-width="{f(aw)}"/>')
    spines = ''.join(f'<path d="M{f(rng.uniform(-bw * .35, bw * .35))} {f(top - rng.uniform(1, bh - 1))}l.5 -.4" fill="none" stroke-width=".22"/>'
                     for _ in range(10))
    flw = flower(0, top - bh, bw * .45, rng.choice(FLOWERS))
    return wrap(arms + f'<path d="{body}" fill="{col}"/>'
                f'<path d="M0 {f(top)}V{f(top - bh + 1.5)}" fill="none" stroke-width=".25" opacity=".6"/>' + spines + flw + p)


def succulent(rng, h):
    w = h * .9
    ph = h * .4
    p, top = pot(rng, w * .8, ph, rng.choice(POTS), rng.random() < .6)
    out = []
    for layer, (n, L) in enumerate(((9, h * .55), (7, h * .42), (5, h * .3))):
        col = GREENS[(layer + 1) % len(GREENS)] if layer else rng.choice(DEEP_GREENS)
        for i in range(n):
            a = -80 + 160 * i / (n - 1)
            out.append(leaf(0, top + 1, a * (1 - layer * .2), L, L * .32, col, rib=False))
    if rng.random() < .5:
        out.append(f'<path d="M0 {f(top - h * .25)}Q{f(h * .15)} {f(top - h * .55)} {f(h * .2)} {f(top - h * .75)}" fill="none" stroke-width=".3"/>'
                   + flower(h * .2, top - h * .75, h * .07, rng.choice(FLOWERS)))
    return wrap(''.join(out) + p)


def tulips(rng, h):
    w = h * .42
    ph = h * .3
    p, top = pot(rng, w, ph, rng.choice(POTS), rng.random() < .5)
    out = []
    col = rng.choice(FLOWERS)
    n = rng.randint(3, 4)
    for i in range(n):
        x = (i - (n - 1) / 2) * w * .22
        L = (h - ph) * rng.uniform(.7, .95)
        tx = x * 1.8
        ty = top - L
        out.append(f'<path d="M{f(x)} {f(top + 1)}Q{f(x)} {f(top - L * .5)} {f(tx)} {f(ty)}" fill="none" stroke="{DEEP_GREENS[0]}" stroke-width=".9"/>'
                   f'<path d="M{f(x)} {f(top + 1)}Q{f(x)} {f(top - L * .5)} {f(tx)} {f(ty)}" fill="none" stroke-width=".25"/>')
        out.append(leaf(x, top + .5, (i - (n - 1) / 2) * 25, L * .45, L * .1, rng.choice(GREENS)))
        s = h * .09
        out.append(f'<path transform="translate({f(tx)} {f(ty)})" d="M{f(-s)} {f(-s * 1.6)}L{f(-s * .5)} {f(-s * .9)} 0 {f(-s * 1.7)} {f(s * .5)} {f(-s * .9)} {f(s)} {f(-s * 1.6)}C{f(s * 1.1)} {f(-s * .3)} {f(s * .5)} 0 0 0C{f(-s * .5)} 0 {f(-s * 1.1)} {f(-s * .3)} {f(-s)} {f(-s * 1.6)}Z" fill="{col}"/>')
    return wrap(''.join(out) + p)


def mug(rng, h):
    w = h * .8
    col = rng.choice(POTS)
    body = f'M{f(-w * .4)} {f(-h * .62)}V{f(-h * .08)}Q{f(-w * .4)} 0 {f(-w * .3)} 0H{f(w * .2)}Q{f(w * .3)} 0 {f(w * .3)} {f(-h * .08)}V{f(-h * .62)}Z'
    handle = f'<path d="M{f(w * .3)} {f(-h * .5)}c{f(w * .25)} 0 {f(w * .25)} {f(h * .32)} 0 {f(h * .32)}" fill="none" stroke-width="{f(h * .1)}"/>' \
             f'<path d="M{f(w * .3)} {f(-h * .5)}c{f(w * .25)} 0 {f(w * .25)} {f(h * .32)} 0 {f(h * .32)}" fill="none" stroke="{col}" stroke-width="{f(h * .06)}"/>'
    steam = ''.join(f'<path d="M{f(x)} {f(-h * .7)}c{f(-h * .1)} {f(-h * .1)} {f(h * .1)} {f(-h * .18)} 0 {f(-h * .3)}" fill="none" stroke-width=".3" opacity=".7"/>'
                    for x in (-w * .15, w * .05))
    heart = f'<use href="#heart-d" transform="translate({f(-w * .05)} {f(-h * .3)}) scale({f(h * .022)})" fill="#ff9cc2"/>'
    return wrap(f'<ellipse cx="0" cy=".3" rx="{f(w * .45)}" ry=".6" fill="url(#tone-ink)" stroke="none" opacity=".3"/>'
                + handle + f'<path d="{body}" fill="{col}"/>'
                f'<ellipse cx="{f(-w * .05)}" cy="{f(-h * .62)}" rx="{f(w * .35)}" ry="{f(h * .06)}" fill="#c99a7a"/>' + heart + steam)


def books(rng, h):
    out, y = [], 0
    n = rng.randint(2, 4)
    bh = h / n
    for i in range(n):
        bw = h * rng.uniform(1.1, 1.5)
        x = rng.uniform(-1.2, 1.2)
        col = rng.choice(POTS)
        out.append(f'<rect x="{f(x - bw / 2)}" y="{f(y - bh)}" width="{f(bw)}" height="{f(bh)}" rx=".5" fill="{col}"/>'
                   f'<path d="M{f(x - bw / 2 + 1.2)} {f(y - bh)}v{f(bh)}M{f(x + bw / 2 - 1.2)} {f(y - bh)}v{f(bh)}" fill="none" stroke-width=".25"/>'
                   f'<rect x="{f(x + bw / 2 - .9)}" y="{f(y - bh + .4)}" width=".7" height="{f(bh - .8)}" fill="#fff" stroke="none" opacity=".7"/>')
        y -= bh
    out.append(f'<use href="#heart-d" transform="translate({f(rng.uniform(-2, 2))} {f(y - 1.2)}) scale(.16)" fill="#ff9cc2"/>')
    return wrap(''.join(out))


def cat(rng, h):
    """A curled-up sleeping cat, about 2h wide."""
    s = h / 10
    col = rng.choice(['#fff', '#ffe9d6', '#e9e3f2'])
    patch = rng.choice(['#ffc9a3', '#cdbfe6', '#b9b0c4'])
    return wrap(f'<g transform="scale({f(s)})">'
                f'<ellipse cx="0" cy=".2" rx="10" ry="1" fill="url(#tone-ink)" stroke="none" opacity=".35"/>'
                f'<path d="M-9 0C-10 -6 -5 -9.5 1 -9 6 -8.5 9 -5 8.5 0Z" fill="{col}"/>'
                f'<path d="M-2 -8.8C1 -9.6 5 -8 6.5 -5 4 -6.5 0 -6.5 -2 -8.8Z" fill="{patch}" stroke="none"/>'
                f'<path d="M8.5 0C11 -.5 11.5 -3 9.5 -3.6" fill="none" stroke-width="1.6"/>'
                f'<path d="M8.5 0C11 -.5 11.5 -3 9.5 -3.6" fill="none" stroke="{col}" stroke-width="1"/>'
                f'<path d="M-10.5 0C-11.5 -1.5 -11.4 -4.5 -10.5 -5.5L-10.2 -8.2 -8.3 -6.3C-7 -6.8 -5.6 -6.8 -4.3 -6.3L-2.6 -8 -2.3 -5.3C-1.3 -4 -1.5 -1 -2.5 0Z" fill="{col}"/>'
                f'<path d="M-9.9 -6.8l.2 -.9.8 .7zM-3.2 -6.7l.4 -.8.3 .9z" fill="#ffc2da" stroke="none"/>'
                f'<path d="M-9 -3.2q.7 .6 1.4 0M-5.6 -3.2q.7 .6 1.4 0" fill="none" stroke-width=".32"/>'
                f'<path d="M-6.9 -2.1l-.3 .3h.6z" fill="#ff9cc2" stroke-width=".2"/>'
                f'<ellipse cx="-9.4" cy="-1.6" rx=".8" ry=".4" fill="#ff9cc2" stroke="none" opacity=".7"/>'
                f'<ellipse cx="-3.8" cy="-1.6" rx=".8" ry=".4" fill="#ff9cc2" stroke="none" opacity=".7"/>'
                f'<text x="-1" y="-11" font-family="Pop" font-size="2.6" fill="{LINE}" stroke="none">z</text>'
                f'<text x="1.4" y="-13" font-family="Pop" font-size="3.4" fill="{LINE}" stroke="none">z</text>'
                '</g>')


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
    out = []
    n = max(1, int(w / 4.2))
    for i in range(n):
        cx = x + (i + .5) * w / n + rng.uniform(-.5, .5)
        hgt = rng.uniform(2.2, 3.4)
        col = rng.choice(GREENS)
        blades = ''.join(leaf(cx + dx, y + .1, a + rng.uniform(-6, 6), hgt * k, .62, col, rib=False)
                         for dx, a, k in ((-.5, -30, .72), (0, 0, 1), (.5, 30, .78)))
        out.append(f'<g stroke="{GRASS_LINE}" stroke-width=".2" stroke-linejoin="round">{blades}</g>')
    if w > 6 and rng.random() < .7:
        for _ in range(rng.randint(1, 2)):
            fx = x + rng.uniform(1, w - 1)
            fh = rng.uniform(3.5, 5.5)
            out.append(f'<path d="M{f(fx)} {f(y)}Q{f(fx + .4)} {f(y - fh / 2)} {f(fx)} {f(y - fh)}" fill="none" stroke="{GRASS_LINE}" stroke-width=".35"/>'
                       + wrap(flower(fx, y - fh, rng.uniform(.9, 1.3), rng.choice(FLOWERS)), .25))
    return ''.join(out)


# ----------------------------------------------------------------------------
# Vines: a stem along a guide path with alternating leaves, buds and curls

def vine(rng, pts, leaf_gap=3.2, size=1.0):
    d = smooth_d(pts)
    out = [f'<path d="{d}" fill="none" stroke="{LINE}" stroke-width="{f(.9 * size)}"/>',
           f'<path d="{d}" fill="none" stroke="{DEEP_GREENS[1]}" stroke-width="{f(.45 * size)}"/>']
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
            out.append(wrap(flower(x1, y1, 1.5 * size, rng.choice(FLOWERS), rot=rng.uniform(0, 72)), .3))
        elif r < .2:
            sx, sy = x1, y1
            a0 = math.radians(ang + side * 70)
            curl = [(sx + math.sin(a0 + side * t * .9) * (2.4 - t * .35) * size * .8,
                     sy - math.cos(a0 + side * t * .9) * (2.4 - t * .35) * size * .8) for t in range(0, 7)]
            out.append(f'<path d="{smooth_d([(sx, sy)] + curl)}" fill="none" stroke="{LINE}" stroke-width=".25"/>')
        else:
            L = rng.uniform(2.6, 3.8) * size
            out.append(wrap(leaf(x1, y1, ang + side * rng.uniform(45, 75), L, L * .42, rng.choice(GREENS)), .3))
    return ''.join(out)


def garland_pts(x0, x1, y, sag):
    n = max(8, int((x1 - x0) / 1.5))
    return [(x0 + (x1 - x0) * t / n, y + sag * 4 * (t / n) * (1 - t / n)) for t in range(n + 1)]


def bow(x, y, color):
    return wrap(f'<g transform="translate({f(x)} {f(y)})">'
                f'<path d="M0 0C-2.5 -2 -4 -.5 -3.5 1 -3 2.3 -1.2 1.4 0 0Z" fill="{color}"/>'
                f'<path d="M0 0C2.5 -2 4 -.5 3.5 1 3 2.3 1.2 1.4 0 0Z" fill="{color}"/>'
                f'<path d="M0 0L-1.4 3.4M0 0L1.4 3.4" fill="none" stroke-width=".6"/>'
                f'<circle r=".8" fill="{color}"/></g>', .3)


def charm(rng, x, y, length):
    """A dangling string with a heart, star or tiny hanging planter."""
    kind = rng.choice(['heart-d', 'star', 'planter', 'sparkle'])
    out = f'<path d="M{f(x)} {f(y)}v{f(length)}" fill="none" stroke="{LINE}" stroke-width=".25" stroke-dasharray=".6 .4"/>'
    ey = y + length
    if kind == 'planter':
        col = rng.choice(POTS)
        leaves = ''.join(leaf(x + dx, ey - .2, a, 2.8, 1.2, rng.choice(GREENS)) for dx, a in ((-1, -40), (0, 0), (1, 40)))
        trail = vine(rng, [(x + 1.6, ey + .5), (x + 2.4, ey + 3), (x + 1.8, ey + 6), (x + 2.6, ey + 9)], leaf_gap=2.2, size=.7)
        out += trail + wrap(leaves + f'<path d="M{f(x - 2.4)} {f(ey)}H{f(x + 2.4)}Q{f(x + 2.4)} {f(ey + 3.2)} {f(x)} {f(ey + 3.2)}Q{f(x - 2.4)} {f(ey + 3.2)} {f(x - 2.4)} {f(ey)}Z" fill="{col}"/>'
                                    f'<path d="M{f(x - 2.4)} {f(ey)}L{f(x)} {f(y + length * .4)}L{f(x + 2.4)} {f(ey)}" fill="none" stroke-width=".22"/>', .3)
    else:
        s = 3.2 if kind != 'sparkle' else 4
        out += f'<use href="#{kind}" transform="translate({f(x)} {f(ey + s * .5)}) scale({f(s / 10)})" fill="{rng.choice(FLOWERS)}" stroke="{LINE}"/>'
    return out


# ----------------------------------------------------------------------------
# Loose cables

def plug(rng, x, y, ang, color):
    kind = rng.choice(['dupont', 'dupont', 'alligator', 'stripped', 'banana'])
    g = f'<g transform="translate({f(x)} {f(y)}) rotate({f(ang)})" stroke="{LINE}" stroke-width=".3" stroke-linejoin="round">'
    if kind == 'dupont':
        body = (f'<rect x="-.4" y="-1.4" width="6" height="2.8" rx=".4" fill="#6c5a7c"/>'
                f'<rect x=".6" y="-.9" width="4" height=".5" fill="{color}" stroke="none" opacity=".9"/>'
                f'<rect x="5.6" y="-.32" width="2.6" height=".64" fill="#f3e6b8"/>')
    elif kind == 'alligator':
        body = (f'<path d="M-.4 -1.5H3.6L5 -1V1L3.6 1.5H-.4Z" fill="{color}"/>'
                f'<path d="M5 -.9L10 -1.8 10.2 -.6 5 -.2Z" fill="#e3e0ea"/><path d="M5 .9L10 1.8 10.2 .6 5 .2Z" fill="#e3e0ea"/>'
                f'<path d="M6 -.9l.5 .4.5 -.55.5 .5.5 -.6.5 .5.5 -.65.5 .5M6 .9l.5 -.4.5 .55.5 -.5.5 .6.5 -.5.5 .65.5 -.5" fill="none" stroke-width=".18"/>')
    elif kind == 'banana':
        body = (f'<path d="M-.4 -1.3H4.5Q5.5 -1.3 5.5 0Q5.5 1.3 4.5 1.3H-.4Z" fill="{color}"/>'
                f'<path d="M5.4 -.35H8Q8.8 -.7 9.4 -.35Q9.8 0 9.4 .35Q8.8 .7 8 .35H5.4Z" fill="#e3e0ea"/>')
    else:
        strands = ''.join(f'<path d="M1.2 {f(o * .25)}l{f(rng.uniform(2, 3))} {f(o * rng.uniform(.3, .7))}" fill="none" stroke="#e7a36b" stroke-width=".22"/>'
                          for o in (-2, -1, 0, 1, 2))
        body = f'{strands}<rect x="-.4" y="-.6" width="1.8" height="1.2" rx=".3" fill="{color}"/>'
    return g + body + '</g>'


def cable(rng, pts, color):
    d = smooth_d(pts)
    out = (f'<path d="{d}" fill="none" stroke="{LINE}" stroke-width="1.45" stroke-linecap="round" stroke-linejoin="round"/>'
           f'<path d="{d}" fill="none" stroke="{color}" stroke-width=".9" stroke-linecap="round" stroke-linejoin="round"/>'
           f'<path d="{d}" fill="none" stroke="#fff" stroke-width=".22" stroke-linecap="round" opacity=".75" transform="translate(-.18 -.18)"/>')
    (x0, y0), (x1, y1) = pts[-2], pts[-1]
    ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
    return out + plug(rng, x1, y1, ang, color)


# ----------------------------------------------------------------------------
# Little parts lying around, centred at (0, 0), about 14 mm long

def resistor(rng):
    bands = rng.sample(['#a0522d', '#ff6b6b', '#ffa94d', '#ffe066', '#69db7c', '#74c0fc', '#b197fc'], 3)
    b = ''.join(f'<rect x="{f(-2.2 + i * 1.5)}" y="-1.4" width=".7" height="2.8" fill="{c}" stroke="none"/>' for i, c in enumerate(bands))
    return wrap('<path d="M-7 1.5Q-6 0 -3.4 0M3.4 0Q6 0 7 -1.5" fill="none" stroke="#bdb5c9" stroke-width=".55"/>'
                '<path d="M-3.6 -1.3Q-3.6 -1.7 -3 -1.7H3Q3.6 -1.7 3.6 -1.3V1.3Q3.6 1.7 3 1.7H-3Q-3.6 1.7 -3.6 1.3Z" fill="#ffe3c2"/>'
                + b + '<rect x="1.9" y="-1.4" width=".7" height="2.8" fill="#d4af37" stroke="none"/>', .3)


def led(rng):
    c = rng.choice(['#ff9fb5', '#9fcbff', '#a9e3b5', '#ffd77a'])
    return wrap(f'<path d="M-1 1.6V7.5M1 1.6V5.5Q1 6.5 2 7" fill="none" stroke="#bdb5c9" stroke-width=".5"/>'
                f'<path d="M-2.2 1.6V-1.5A2.2 2.2 0 0 1 2.2 -1.5V1.6Z" fill="{c}" fill-opacity=".85"/>'
                f'<rect x="-2.7" y="1.2" width="5.4" height=".9" rx=".3" fill="{c}"/>'
                '<path d="M-1.1 -1.8Q-1 -2.9 0 -3.1" fill="none" stroke="#fff" stroke-width=".4"/>'
                f'<use href="#sparkle" transform="translate(3.6 -3.6) scale(.18)" fill="#fff6a8"/>', .3)


def electrolytic(rng):
    c = rng.choice(['#c9d8ff', '#d8c8ff', '#bfeee6'])
    return wrap(f'<path d="M-1 4.8V8.5M1 4.8V7.5" fill="none" stroke="#bdb5c9" stroke-width=".5"/>'
                f'<rect x="-2.8" y="-4.6" width="5.6" height="9.4" rx="1.2" fill="{c}"/>'
                '<rect x="1.3" y="-4.5" width="1.3" height="9.2" fill="#fff" stroke="none" opacity=".75"/>'
                '<path d="M1.95 -3.4v.9M1.95 -1.4v.9M1.95 .6v.9" fill="none" stroke-width=".3"/>'
                '<g transform="translate(-.6 .6) scale(.3)" stroke="none"><use href="#face-happy"/></g>', .3)


def chip(rng):
    c = rng.choice(['#6c5a7c', '#7d6b8f'])
    legs = ''.join(f'<path d="M{f(-3.75 + i * 2.5)} -2.6v-1.4M{f(-3.75 + i * 2.5)} 2.6v1.4" fill="none" stroke="#bdb5c9" stroke-width=".7"/>' for i in range(4))
    return wrap(legs + f'<rect x="-5" y="-2.7" width="10" height="5.4" rx=".5" fill="{c}"/>'
                '<circle cx="-3.9" cy="-1.6" r=".45" fill="#9b8aad" stroke="none"/>'
                '<g transform="translate(.4 .3) scale(.32)" stroke="none"><use href="#face-sparkle"/></g>', .3)


def ceramic(rng):
    return wrap('<path d="M-.9 1.8V6.5M.9 1.8V5.5" fill="none" stroke="#bdb5c9" stroke-width=".45"/>'
                '<ellipse cx="0" cy="0" rx="2.4" ry="2.1" fill="#ffd27f"/><text x="0" y=".7" font-family="MPR" font-weight="800" font-size="1.6" '
                f'text-anchor="middle" fill="{LINE}" stroke="none">104</text>', .3)


PARTS = [resistor, led, electrolytic, chip, ceramic, resistor, led]


def cloud(w):
    h = w * .45
    d = (f'M{f(-w * .45)} 0C{f(-w * .6)} 0 {f(-w * .6)} {f(-h * .55)} {f(-w * .38)} {f(-h * .5)}'
         f'C{f(-w * .38)} {f(-h * 1.05)} {f(-w * .05)} {f(-h * 1.1)} {f(w * .02)} {f(-h * .75)}'
         f'C{f(w * .12)} {f(-h * 1.2)} {f(w * .45)} {f(-h * 1)} {f(w * .38)} {f(-h * .5)}'
         f'C{f(w * .6)} {f(-h * .5)} {f(w * .6)} 0 {f(w * .45)} 0Z')
    return wrap(f'<path d="{d}" fill="#fff"/><path d="{d}" fill="url(#tone-pink)" stroke="none" opacity=".45" transform="translate(.6 .6)"/>', .32)


def shelf(x0, y, w):
    """A little wall shelf; y is the top of the plank."""
    br = ''.join(f'<path d="M{f(bx - 1.6)} {f(y + 1.8)}H{f(bx + 1.6)}L{f(bx)} {f(y + 6)}Z" fill="#e9c9a6"/>'
                 for bx in (x0 + 7, x0 + w - 7))
    return wrap(f'<rect x="{f(x0 + .9)}" y="{f(y + .9)}" width="{f(w)}" height="1.8" rx=".5" fill="url(#tone-ink)" stroke="none" opacity=".35"/>'
                + br + f'<rect x="{f(x0)}" y="{f(y)}" width="{f(w)}" height="1.8" rx=".5" fill="#f6dcbc"/>'
                f'<path d="M{f(x0 + 2)} {f(y + .7)}h{f(w * .3)}M{f(x0 + w * .55)} {f(y + 1.1)}h{f(w * .25)}" fill="none" stroke-width=".2" opacity=".6"/>')


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
        d = ''.join(ds)
        return (f'<path d="{d}" fill="none" stroke="{LINE}" stroke-width=".95" stroke-linecap="round"/>'
                f'<path d="{d}" fill="none" stroke="{light}" stroke-width=".5" stroke-linecap="round"/>')

    behind = stem(behind_d, DEEP_GREENS[2])
    out = []
    if lead_in:
        out.append(vine(rng, lead_in + [pts[0]], leaf_gap=2.6))
    out.append(stem(front_d, DEEP_GREENS[1]))
    side = 1
    for i in range(6, len(pts), 5):
        if not front[i]:
            continue
        x, y = pts[i]
        side = -side
        r = rng.random()
        if r < .1:
            out.append(wrap(flower(x + side * 1.2, y, 1.4, rng.choice(FLOWERS), rot=rng.uniform(0, 72)), .3))
        else:
            L = rng.uniform(2.6, 3.8)
            out.append(wrap(leaf(x, y, side * rng.uniform(55, 100) + (0 if dirn > 0 else 180) * 0, L, L * .42, rng.choice(GREENS)), .3))
    # a curl at the growing tip
    x, y = pts[-1]
    out.append(f'<path d="{smooth_d([(x, y), (x + 1.2, y + dirn * 1), (x + .6, y + dirn * 2), (x - .2, y + dirn * 1.4), (x + .2, y + dirn * 1)])}" '
               f'fill="none" stroke="{LINE}" stroke-width=".28"/>')
    return behind, ''.join(out)


# ----------------------------------------------------------------------------
# Cables that obey gravity

def cable_clip(x, y):
    return wrap(f'<rect x="{f(x - 1.3)}" y="{f(y - 1.6)}" width="2.6" height="3.2" rx=".8" fill="#fff6c8"/>'
                f'<circle cx="{f(x)}" cy="{f(y - .6)}" r=".35" fill="#ffb3cf" stroke="none"/>', .3)


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
        return f'<g transform="scale({f(k)}) translate(0 {f(-foot)})">{fn(rng)}</g>'
    draw.__name__ = 'part_' + fn.__name__
    return draw


PART_ITEMS = [
    (standing(resistor, 1.5, 3.2), 3.4, 4.2, 14 / 3.2),
    (standing(led, 7.5, 11.1), 7, 10, 6.5 / 11.1),
    (standing(electrolytic, 8.5, 13.1), 8, 11, 5.8 / 13.1),
    (standing(chip, 4, 8), 5, 7, 10.5 / 8),
    (standing(ceramic, 6.5, 8.6), 6, 8, 5 / 8.6),
]
