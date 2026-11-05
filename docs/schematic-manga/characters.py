"""Passive components as little characters.

Each function draws over the symbol it replaces. The symbol's own marks (the
plates, the box, the core lines) are kept on top, so the schematic still reads
correctly, and the pin ends stay visible so you can see where the wires attach.
Faces are always drawn upright.
"""

import math
import re

INK = '#4b3a5a'
FUR = [('#ffffff', '#ffd0a8'), ('#fff1dc', '#ffb98a'), ('#e9e3f2', '#b9adc9'), ('#ffd9b3', '#f7a86b'),
       ('#f2f0f5', '#4b3a5a'), ('#fde7ef', '#d9b8c9')]
BODY = ['#ffe3c2', '#ffd6e5', '#d9f2e6', '#dfe8ff', '#fff0b8', '#eadcff']


def f(v):
    return f'{v:.3f}'.rstrip('0').rstrip('.')


def parse_si(s):
    """'4u7/10V' -> 4.7e-6, '3k3' -> 3300, '100n' -> 1e-7. None if unknown."""
    m = re.match(r'^\s*(\d+)(?:([pnumkKMR.])(\d*))?', s)
    if not m:
        return None
    mult = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3, 'k': 1e3, 'K': 1e3, 'M': 1e6, 'R': 1, '.': 1, None: 1}
    whole, unit, frac = m.groups()
    v = float(f'{whole}.{frac or 0}')
    return v * mult[unit]


# ----------------------------------------------------------------------------
# Capacitor cats

def cat_capacitor(rng, cx, cy, vertical, value, plates):
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
    pw = max(.42, b - .45)
    parts = [
        f'<path d="{tail}" fill="none" stroke="{INK}" stroke-width=".62" stroke-linecap="round"/>',
        f'<path d="{tail}" fill="none" stroke="{fur}" stroke-width=".34" stroke-linecap="round"/>',
        f'<path d="{body}" fill="{fur}"/>',
        f'<ellipse cx="0" cy="{f(1.05 + .1 * chub)}" rx="{f(.25 + b * .45)}" ry="{f(.3 + .3 * chub)}" fill="#fff" stroke="none" opacity=".75"/>',
        f'<ellipse cx="{f(b * .45)}" cy=".95" rx="{f(b * .3)}" ry=".4" fill="{patch}" stroke="none" opacity=".5"/>',
        f'<ellipse cx="{f(-pw)}" cy="{f(yb - .05)}" rx=".36" ry=".22" fill="{fur}"/><ellipse cx="{f(pw)}" cy="{f(yb - .05)}" rx=".36" ry=".22" fill="{fur}"/>',
        f'<path d="M{f(-hr * .92)} {f(-.85 - hy * .3)}L{f(-hr * .8)} {f(-.85 - hy * .55 - ear * .75)}L{f(-hr * .18)} {f(-.85 - hy * .82)}Z" fill="{fur}"/>',
        f'<path d="M{f(hr * .92)} {f(-.85 - hy * .3)}L{f(hr * .8)} {f(-.85 - hy * .55 - ear * .75)}L{f(hr * .18)} {f(-.85 - hy * .82)}Z" fill="{fur}"/>',
        f'<path d="M{f(-hr * .72)} {f(-.85 - hy * .5)}L{f(-hr * .72)} {f(-.85 - hy * .55 - ear * .55)}L{f(-hr * .38)} {f(-.85 - hy * .72)}Z" fill="#ffb3cf" stroke="none"/>',
        f'<path d="M{f(hr * .72)} {f(-.85 - hy * .5)}L{f(hr * .72)} {f(-.85 - hy * .55 - ear * .55)}L{f(hr * .38)} {f(-.85 - hy * .72)}Z" fill="#ffb3cf" stroke="none"/>',
        f'<ellipse cx="0" cy="-.85" rx="{f(hr)}" ry="{f(hy)}" fill="{fur}"/>',
    ]
    bw = b
    if rng.random() < .45:
        parts.append(f'<path d="M{f(hr * .1)} {f(-.85 - hy * .92)}C{f(hr * .7)} {f(-.85 - hy * .85)} {f(hr * .95)} -.9 {f(hr * .9)} -.6'
                     f'C{f(hr * .5)} -.7 {f(hr * .2)} -1.2 {f(hr * .1)} {f(-.85 - hy * .92)}Z" fill="{patch}" stroke="none" opacity=".7"/>')
    eyes = rng.choice(['dot', 'happy', 'sleepy'])
    ex, ey = hr * .4, -1.02
    if eyes == 'dot':
        parts.append(f'<circle cx="{f(-ex)}" cy="{f(ey)}" r=".15" fill="{INK}" stroke="none"/><circle cx="{f(ex)}" cy="{f(ey)}" r=".15" fill="{INK}" stroke="none"/>'
                     f'<circle cx="{f(-ex + .05)}" cy="{f(ey - .05)}" r=".05" fill="#fff" stroke="none"/><circle cx="{f(ex + .05)}" cy="{f(ey - .05)}" r=".05" fill="#fff" stroke="none"/>')
    elif eyes == 'happy':
        parts.append(f'<path d="M{f(-ex - .17)} {f(ey + .05)}q.17 -.22 .34 0M{f(ex - .17)} {f(ey + .05)}q.17 -.22 .34 0" fill="none" stroke-width=".11"/>')
    else:
        parts.append(f'<path d="M{f(-ex - .17)} {f(ey)}q.17 .16 .34 0M{f(ex - .17)} {f(ey)}q.17 .16 .34 0" fill="none" stroke-width=".11"/>')
    parts.append(
        f'<ellipse cx="{f(-hr * .62)}" cy="-.72" rx=".2" ry=".11" fill="#ff9cc2" stroke="none" opacity=".8"/>'
        f'<ellipse cx="{f(hr * .62)}" cy="-.72" rx=".2" ry=".11" fill="#ff9cc2" stroke="none" opacity=".8"/>'
        f'<path d="M-.17 -.74q.085 .1 .17 0q.085 .1 .17 0" fill="none" stroke-width=".09"/>'
        f'<path d="M-.03 -.86h.06l-.03 .05z" fill="#ff8fab" stroke-width=".05"/>'
        f'<path d="M{f(-hr * .5)} -.8l{f(-hr * .55)} -.06M{f(-hr * .5)} -.7l{f(-hr * .55)} .05'
        f'M{f(hr * .5)} -.8l{f(hr * .55)} -.06M{f(hr * .5)} -.7l{f(hr * .55)} .05" fill="none" stroke-width=".06" opacity=".7"/>')
    if c is None:
        parts.append(f'<text x="{f(max(bw, hr) + .2)}" y="-1.4" font-family="Pop" font-size="1.2" fill="#ff7fb2" stroke="none">?</text>')
    # the bell on the collar (the upper plate)
    parts.append('<circle cx="0" cy="-.25" r=".22" fill="#ffd95e" stroke-width=".07"/>')
    cat = (f'<g transform="translate({f(cx)} {f(cy)}) rotate({rot}) scale(1.12)" stroke="{INK}" stroke-width=".14" '
           f'stroke-linejoin="round">{"".join(parts)}</g>')
    pl = ''.join(f'<path d="M{f(a[0])} {f(a[1])}L{f(b[0])} {f(b[1])}"/>' for a, b in plates)
    return cat + f'<g stroke="{INK}" stroke-width=".34" stroke-linecap="round">{pl}</g>'


# ----------------------------------------------------------------------------
# Resistors: grumpy little boxes that throw things

def brick(x, y, ang, k=1.5):
    return (f'<g transform="translate({f(x)} {f(y)}) rotate({f(ang)}) scale({f(k)})" stroke="{INK}" stroke-width=".12" stroke-linejoin="round">'
            '<rect x="-.95" y="-.55" width="1.9" height="1.1" rx=".2" fill="#ff9f9f"/>'
            '<path d="M-.95 0H.95M-.3 -.55V0M.4 0V.55" fill="none" stroke="#fff" stroke-width=".1"/>'
            '<circle cx="-.5" cy=".25" r=".07" fill="' + INK + '" stroke="none"/><circle cx="-.1" cy=".25" r=".07" fill="' + INK + '" stroke="none"/>'
            '<ellipse cx="-.62" cy=".4" rx=".12" ry=".06" fill="#ffd0dc" stroke="none"/></g>')


def molotov(x, y, ang, k=1.35):
    return (f'<g transform="translate({f(x)} {f(y)}) rotate({f(ang)}) scale({f(k)})" stroke="{INK}" stroke-width=".12" stroke-linejoin="round">'
            '<path d="M-.45 1.1V.1Q-.45 -.3 -.18 -.45V-.85H.18V-.45Q.45 -.3 .45 .1V1.1Q.45 1.25 .3 1.25H-.3Q-.45 1.25 -.45 1.1Z" fill="#bfeee6"/>'
            '<path d="M-.42 .45H.42V1.1Q.42 1.22 .3 1.22H-.3Q-.42 1.22 -.42 1.1Z" fill="#ffb3cf" stroke="none"/>'
            '<path d="M-.1 .75l.1 .1.1 -.1" fill="none" stroke="#fff" stroke-width=".09"/>'
            '<path d="M-.1 -.85Q-.25 -1.15 0 -1.3" fill="none" stroke="#fff3c4" stroke-width=".18"/>'
            '<path d="M0 -1.25C-.55 -1.45 -.4 -1.95 -.1 -2.35-.05 -2.05.15 -2 .2 -2.25.55 -1.85.45 -1.4 0 -1.25Z" fill="#ffb86b"/>'
            '<path d="M0 -1.35C-.22 -1.5 -.15 -1.75 0 -1.9.05 -1.75.2 -1.6 0 -1.35Z" fill="#fff1a0" stroke="none"/>'
            '<circle cx="-.13" cy=".15" r=".06" fill="' + INK + '" stroke="none"/><circle cx=".13" cy=".15" r=".06" fill="' + INK + '" stroke="none"/></g>')


def resistor_guy(rng, cx, cy, vertical, half_len, mood, throw):
    """Draw the resistor box itself (a bit chubbier) with a face and arms.

    `throw` is None or (dx, dy, kind): where the projectile flies, relative to the centre."""
    hw = 1.25
    if vertical:
        x0, y0, x1, y1 = cx - hw, cy - half_len, cx + hw, cy + half_len
    else:
        x0, y0, x1, y1 = cx - half_len, cy - hw, cx + half_len, cy + hw
    col = rng.choice(BODY)
    out = []
    arm = 'fill="none" stroke="' + INK + '" stroke-width=".26" stroke-linecap="round" stroke-linejoin="round"'
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
        out.append(f'<path d="M{f(hx)} {f(hy)}Q{f(hx + ux * .3)} {f(hy - .8)} {f(tx)} {f(ty)}" {arm}/>')
        px, py = cx + dx, cy + dy
        mx, my = (tx + px) / 2 - uy * .9 * 0 , min(ty, py) - 1.1
        out.append(f'<path d="M{f(tx)} {f(ty)}Q{f(mx)} {f(my)} {f(px)} {f(py)}" fill="none" stroke="#c9a0c2" stroke-width=".13" stroke-dasharray=".25 .25"/>')
        ang = rng.uniform(-35, 35)
        out.append(brick(px, py, ang) if kind == 'brick' else molotov(px, py, ang * .6))
        for i in (-1, 1):
            out.append(f'<path d="M{f(px - ux * 1.4 + i * uy * .4)} {f(py - uy * 1.4 - i * ux * .4)}l{f(-ux * .5)} {f(-uy * .5)}" fill="none" stroke="#c9a0c2" stroke-width=".12" stroke-linecap="round"/>')
        # the other arm on its hip
        ox, oy = (x0, cy + .3) if vertical and ux > 0 else (x1, cy + .3) if vertical else (cx - ux * .6, y0 if uy > 0 else y1)
        sgn = -1 if (vertical and ux > 0) else 1
        if vertical:
            out.append(f'<path d="M{f(ox)} {f(oy - .5)}l{f(sgn * .55)} .35l{f(-sgn * .45)} .4" {arm}/>')
    else:
        for sx in (-1, 1):
            if vertical:
                ex = x1 if sx > 0 else x0
                out.append(f'<path d="M{f(ex)} {f(cy)}q{f(sx * .5)} -.2 {f(sx * .55)} -.9" {arm}/>')
    out.append(f'<rect x="{f(x0)}" y="{f(y0)}" width="{f(x1 - x0)}" height="{f(y1 - y0)}" rx=".45" fill="{col}" stroke="{INK}" stroke-width=".3"/>')
    out.append(f'<rect x="{f(x0)}" y="{f(y0)}" width="{f(x1 - x0)}" height="{f(y1 - y0)}" rx=".45" fill="url(#tone-w)" stroke="none"/>')
    out.append(f'<use href="#rface-{mood}" transform="translate({f(cx)} {f(cy - (.25 if vertical else 0))}) scale(.3)"/>')
    return ''.join(out)


def resistor_face_defs():
    st = f'fill="none" stroke="{INK}" stroke-width=".55" stroke-linecap="round" stroke-linejoin="round"'
    blush = '<ellipse cx="-2.5" cy="1.1" rx=".9" ry=".5" fill="#ff9cc2" opacity=".8"/><ellipse cx="2.5" cy="1.1" rx=".9" ry=".5" fill="#ff9cc2" opacity=".8"/>'
    eyes = f'<circle cx="-1.4" cy="0" r=".62" fill="{INK}"/><circle cx="1.4" cy="0" r=".62" fill="{INK}"/><circle cx="-1.2" cy="-.2" r=".22" fill="#fff"/><circle cx="1.6" cy="-.2" r=".22" fill="#fff"/>'
    return f'''
<g id="rface-grumpy">{eyes}<path d="M-2.3 -1.5L-.6 -.9M2.3 -1.5L.6 -.9" {st}/>{blush}<path d="M-.6 1.6Q0 1.1 .6 1.6" {st}/></g>
<g id="rface-yell"><path d="M-2 -.6L-.9 0-2 .6M2 -.6L.9 0 2 .6" {st}/>{blush}<path d="M-.6 1Q0 2.3.6 1Z" fill="#ff7f9e" stroke="{INK}" stroke-width=".4"/></g>
<g id="rface-smug">{eyes}<path d="M-2.2 -1.3L-.7 -1.1M2.2 -1.5L.7 -1" {st}/>{blush}<path d="M-.7 1.2Q.2 1.9.9 .9" {st}/></g>
<g id="rface-pout"><path d="M-2 -.1q.6 .5 1.2 0M.8 -.1q.6 .5 1.2 0" {st}/><path d="M-2.3 -1.2L-.8 -.8M2.3 -1.2L.8 -.8" {st}/>{blush}<circle cx="0" cy="1.4" r=".45" {st}/></g>'''


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
    out = []
    for i in reversed(range(n)):
        t = (i + .5) / n
        px, py = ax + ux * L * t, ay + uy * L * t
        r = .62 if i else .78
        out.append(f'<circle cx="{f(px)}" cy="{f(py)}" r="{f(r)}" fill="{col if i else "#d9f5c4"}" stroke="{INK}" stroke-width=".14"/>')
        if i:
            for s in (-1, 1):
                out.append(f'<path d="M{f(px + nx * s * .55)} {f(py + ny * s * .55)}l{f(nx * s * .3)} {f(ny * s * .3)}" stroke="{INK}" stroke-width=".14" stroke-linecap="round"/>')
    hx, hy = ax + ux * L * .5 / n, ay + uy * L * .5 / n
    for s in (-1, 1):
        tx, ty = hx - ux * .9 + nx * s * .55, hy - uy * .9 + ny * s * .55
        out.append(f'<path d="M{f(hx - ux * .5 + nx * s * .25)} {f(hy - uy * .5 + ny * s * .25)}L{f(tx)} {f(ty)}" stroke="{INK}" stroke-width=".12"/>'
                   f'<circle cx="{f(tx)}" cy="{f(ty)}" r=".16" fill="#ffb3cf" stroke="{INK}" stroke-width=".08"/>')
    out.append(f'<use href="#face-happy" transform="translate({f(hx)} {f(hy)}) scale(.19)"/>')
    lines = ''.join(f'<path d="M{f(p[0])} {f(p[1])}L{f(q[0])} {f(q[1])}"/>' for p, q in core_lines)
    return ''.join(out) + f'<g stroke="{INK}" stroke-width=".3" stroke-linecap="round">{lines}</g>'


# ----------------------------------------------------------------------------
# Dancing crystal

def dancing_crystal(rng, cx, cy, body, free=lambda x, y: True):
    """`body` = the crystal's box (x0, y0, x1, y1) in sheet coordinates."""
    x0, y0, x1, y1 = body
    arm = f'fill="none" stroke="{INK}" stroke-width=".24" stroke-linecap="round"'
    out = [f'<path d="M{f(x0)} {f(cy - .2)}q-.7 -.3 -.9 -1.3M{f(x1)} {f(cy - .2)}q.6 -.6 1.3 -.5" {arm}/>',
           f'<circle cx="{f(x0 - .9)}" cy="{f(cy - 1.5)}" r=".2" fill="#fff" stroke="{INK}" stroke-width=".12"/>',
           f'<circle cx="{f(x1 + 1.35)}" cy="{f(cy - .7)}" r=".2" fill="#fff" stroke="{INK}" stroke-width=".12"/>',
           f'<g transform="rotate(-8 {f(cx)} {f(cy)})"><rect x="{f(x0)}" y="{f(y0)}" width="{f(x1 - x0)}" height="{f(y1 - y0)}" rx=".35" fill="#e6f7ff" stroke="{INK}" stroke-width=".26"/>'
           f'<path d="M{f(x0 + .3)} {f(y0 + .3)}l.5 .5" stroke="#fff" stroke-width=".25" stroke-linecap="round"/>'
           f'<use href="#face-happy" transform="translate({f(cx)} {f(cy - .2)}) scale(.17)"/></g>']
    spots = [(-3.2, -3.6, 1.6, '♪'), (2.8, -3.9, 1.9, '♫'), (4.3, -2.2, 1.3, '♪'), (-4.4, -2.0, 1.2, '♬'),
             (-3.4, 3.2, 1.5, '♫'), (3.6, 3.0, 1.5, '♪'), (-5.5, .6, 1.3, '♪'), (5.6, .4, 1.3, '♬'),
             (-7.5, -1.8, 1.7, '♫'), (-9.2, .8, 1.4, '♪'), (-7, 3.4, 1.3, '♬'), (-10.5, -2.6, 1.2, '♪')]
    for i, (dx, dy, s, ch) in enumerate(spots):
        if not free(cx + dx + s * .3, cy + dy - s * .4):
            continue
        col = ['#ff8fbf', '#8fc3ff', '#b79cff', '#7fd8c0'][i % 4]
        out.append(f'<text x="{f(cx + dx)}" y="{f(cy + dy)}" font-size="{f(s * 1.5)}" font-family="DejaVu Sans, sans-serif" fill="{col}" '
                   f'stroke="{INK}" stroke-width=".12" paint-order="stroke" transform="rotate({rng.uniform(-20, 20):.0f} {f(cx + dx)} {f(cy + dy)})">{ch}</text>')
    for s in (-1, 1):
        out.append(f'<path d="M{f(cx + s * 2.4)} {f(cy - 2.6)}q{f(s * .6)} .5 {f(s * .5)} 1.2M{f(cx + s * 2.9)} {f(cy - 2.1)}q{f(s * .45)} .4 {f(s * .35)} .9" '
                   f'fill="none" stroke="#c9a0c2" stroke-width=".13" stroke-linecap="round"/>')
    return ''.join(out)



def legend(rng):
    """The cast of characters, as (svg, width, height) with the origin at the top left."""
    w, h = 150, 54
    t = lambda x, y, txt, size, fam='Pop', col=INK, anchor='start', extra='': (
        f'<text x="{f(x)}" y="{f(y)}" font-family="{fam}" font-size="{f(size)}" fill="{col}" '
        f'text-anchor="{anchor}"{extra}>{txt}</text>')
    out = [f'<rect x="1.5" y="1.5" width="{w}" height="{h}" rx="6" fill="url(#tone-ink)" opacity=".5"/>',
           f'<rect width="{w}" height="{h}" rx="6" fill="#fff" stroke="{INK}" stroke-width=".8"/>',
           f'<rect x="2" y="2" width="{w - 4}" height="{h - 4}" rx="4.5" fill="none" stroke="#ffb8d0" stroke-width=".45" stroke-dasharray="1.6 1"/>',
           t(w / 2, 9, '♡ cast of characters ♡', 5, anchor='middle', col='#ff7fb2',
             extra=f' stroke="#fff" stroke-width=".8" paint-order="stroke"')]
    # capacitors: a row of cats from slim to chonky
    for i, v in enumerate(['10p', '1n', '100n', '1u', '4u7', '22u']):
        cx = 12 + i * 13.5
        out.append(f'<g transform="translate({f(cx)} 21) scale(2.2) translate({f(-cx)} -21)">'
                   f'{cat_capacitor(rng, cx, 21, True, v, [])}</g>')
        out.append(t(cx, 30.5, v.replace('u', 'µ') + 'F', 2.6, 'MPR', '#2f8f86', 'middle', ' font-weight="800"'))
    out.append(t(92, 18.5, 'capacitors', 4))
    out.append(t(92, 23.5, 'more capacitance, more chonk', 2.7, 'Zen', '#7b5b94', extra=' font-weight="700"'))
    out.append(t(92, 27.5, '(the wires go in one end and out the other)', 2.2, 'Zen', '#a08cb0', extra=' font-weight="700"'))
    # resistor, ferrite, crystal
    out.append(f'<g transform="translate(10 44) scale(1.9)">{resistor_guy(rng, 0, 0, True, 1.778, "grumpy", (3.6, -.6, "brick"))}</g>')
    out.append(t(22, 42, 'resistor', 3.6) + t(22, 46.5, 'grumpy, throws bricks', 2.5, 'Zen', '#7b5b94', extra=' font-weight="700"')
               + t(22, 50, '(and the odd molotov)', 2.2, 'Zen', '#a08cb0', extra=' font-weight="700"'))
    out.append(f'<g transform="translate(66 45) scale(1.9)">{caterpillar(rng, (-2.6, 0), (2.6, 0), [])}</g>')
    out.append(t(75, 42, 'ferrite bead', 3.6) + t(75, 46.5, 'a very hungry inductor', 2.5, 'Zen', '#7b5b94', extra=' font-weight="700"'))
    out.append(f'<g transform="translate(116 45) scale(1.7)">'
               f'{dancing_crystal(rng, 0, 0, (-.762, -1.524, .762, 1.524), lambda x, y: y < -1 and abs(x) < 5)}</g>')
    out.append(t(126, 42, 'crystal', 3.6) + t(126, 46.5, 'dances at its', 2.5, 'Zen', '#7b5b94', extra=' font-weight="700"')
               + t(126, 50, 'own frequency ♪', 2.5, 'Zen', '#7b5b94', extra=' font-weight="700"'))
    return ''.join(out), w, h
