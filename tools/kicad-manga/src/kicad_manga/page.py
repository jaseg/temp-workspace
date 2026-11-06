"""The page around the circuit: frame, title panel, legend and decorations.

Decorations are designed for an A1-ish sheet. They are drawn in a "design space"
whose short side is always 594 units and then scaled to the real page, so on an A4
sheet everything shrinks together. The circuit keeps its true size unless it would
collide with the frame, the title panel or the decoration bands; then it is scaled
down and moved to make room.
"""

import math
import random

from markupsafe import Markup

from . import characters as C
from . import drawings as D
from .circuit import Grid
from .palette import PAPER
from .sexp import f2
from .svg import group, render, tag

DESIGN_SHORT = 594.0
FM = 8            # frame line inset (design units)
TW, TH = 176, 58  # title panel


def est_width(s, size):
    return len(s) * .62 * size


def fit(s, size, width):
    return min(size, width / max(1, est_width(s, 1)))


class Page:
    def __init__(self, circuit, title, cfg):
        self.c = circuit
        self.title = title
        self.cfg = cfg
        self.W, self.H = circuit.W, circuit.H
        self.k = max(.3, min(1.6, min(self.W, self.H) / DESIGN_SHORT))
        self.DW, self.DH = self.W / self.k, self.H / self.k
        self.layers = {name: [] for name in ('bg', 'deco', 'edgeback', 'frame', 'edgefront', 'titlepanel')}
        self.grid = Grid(self.DW, self.DH, 1.0)
        self.layout()

    def add(self, layer, svg):
        self.layers[layer].append(Markup(svg))

    # -- where the circuit goes -------------------------------------------------
    def title_rect(self):
        x1, y1 = self.DW - FM - 8, self.DH - FM - 8
        return x1 - TW - 32, y1 - TH - 40, x1, y1

    def layout(self):
        k, DW, DH = self.k, self.DW, self.DH
        inner = (FM + 9, FM + 20, DW - FM - 9, DH - FM - 30)   # garland band on top, plants at the bottom
        R = self.title_rect()
        B = self.c.grid.bbox()
        self.sc, self.T = 1.0, (0.0, 0.0)
        if B is not None:
            bd = [v / k for v in B]
            fits = inner[0] <= bd[0] and inner[1] <= bd[1] and bd[2] <= inner[2] and bd[3] <= inner[3]
            if not fits or overlaps(bd, R):
                bw, bh = (B[2] - B[0]) / k, (B[3] - B[1]) / k
                iw, ih = inner[2] - inner[0], inner[3] - inner[1]
                s0 = min(1, iw / bw, ih / bh)
                if not overlaps((inner[0], inner[1], inner[0] + bw * s0, inner[1] + bh * s0), R):
                    s, ox, oy = s0, inner[0] + (iw - bw * s0) / 2, inner[1] + (ih - bh * s0) / 2
                    if overlaps((ox, oy, ox + bw * s, oy + bh * s), R):
                        ox, oy = inner[0], inner[1]
                else:   # beside or above the title panel, whichever leaves it bigger
                    s1 = min(s0, (R[0] - 4 - inner[0]) / bw)
                    s2 = min(s0, (R[1] - 4 - inner[1]) / bh)
                    if s1 >= s2:
                        s, ox, oy = s1, inner[0], inner[1] + (ih - bh * s1) / 2
                    else:
                        s, ox, oy = s2, inner[0] + (iw - bw * s2) / 2, inner[1]
                self.sc = s
                self.T = (k * ox - s * B[0], k * oy - s * B[1])
        # what the circuit occupies, in design units
        for x0, y0, x1, y1 in self.c.grid.runs():
            self.grid.mark_rect(*self.to_design(x0, y0), *self.to_design(x1, y1))

    def to_design(self, x, y):
        return (self.sc * x + self.T[0]) / self.k, (self.sc * y + self.T[1]) / self.k

    # -- frame and title --------------------------------------------------------
    def frame_and_title(self):
        W, H, m = self.DW, self.DH, FM
        t = self.title
        self.add('bg', tag('rect', width=W, height=H, fill=PAPER))
        self.add('bg', tag('rect', width=W, height=H, fill='url(#tone-bg)', mask='url(#vignette)', opacity=.7))
        rx0, ry0, rx1, ry1 = self.title_rect()
        rng = random.Random(3)
        lines = []
        ox, oy = rx1 - TW / 2, ry1 - TH / 2
        for _ in range(80):     # speed lines radiating from the title panel
            a = rng.uniform(0, 2 * math.pi)
            r0 = rng.uniform(95, 140)
            r1 = r0 + rng.uniform(40, 160)
            w = rng.uniform(0.15, 0.9)
            x0, y0 = ox + math.cos(a) * r0, oy + math.sin(a) * r0 * 0.55
            x1, y1 = ox + math.cos(a) * r1, oy + math.sin(a) * r1 * 0.55
            nx, ny = -math.sin(a) * w, math.cos(a) * w
            lines.append(f'M{f2(x0)} {f2(y0)}L{f2(x1 + nx)} {f2(y1 + ny)}L{f2(x1 - nx)} {f2(y1 - ny)}Z')
        self.add('bg', tag('path', d=''.join(lines), fill='#f6e2ee', opacity=.4))
        ncol, nrow = (8, 6) if W >= H else (6, 8)
        self.add('frame', render(
            'page/frame.svg.j2', W=W, H=H, m=m,
            corners=[(m + 2, m + 2), (W - m - 2, m + 2), (m + 2, H - m - 2), (W - m - 2, H - m - 2)],
            cols=[(m + (W - 2 * m) * (i + 0.5) / ncol, i + 1) for i in range(ncol)],
            rows=[(m + (H - 2 * m) * (i + 0.5) / nrow, chr(ord('A') + i)) for i in range(nrow)]))
        tx, ty = rx1 - TW, ry1 - TH
        self.grid.mark_rect(rx0, ry0, rx1 + 4, ry1 + 4)
        kicker = f'✦ {t["kicker"]} ✦' if t['kicker'] else ''
        bub = split_two(t['bubble'])
        bw = max(40, max(est_width(line, 4.6) for line in bub) + 10)
        self.add('titlepanel', render(
            'page/title.svg.j2', tx=tx, ty=ty, TW=TW, TH=TH,
            kicker=kicker, kicker_size=fit(kicker, 7.5, TW - 20),
            title=t['title'], title_size=fit(t['title'], 8.6, TW - 16),
            subtitle=f"~ {t['subtitle']} ~" if t['subtitle'] else '', subtitle_size=fit(t['subtitle'], 5, TW - 16),
            footer_left=t['footer_left'], footer_right=t['footer_right'],
            bw=bw, bubble=[(8.6 + 7 * i if len(bub) > 1 else 12.2, line) for i, line in enumerate(bub)]))

    def legend(self):
        svg, w, h = C.legend(random.Random(5), self.c.cast())
        W, H, m = self.DW, self.DH, FM + 8
        for s in (1, .8, .62):
            sw, sh = w * s, h * s
            for x, y in ((m, 30), (W - m - sw, 30), (m, H - 70 - sh), (m, (H - sh) / 2), (W - m - sw, (H - sh) / 2),
                         ((W - sw) / 2, 30), ((W - sw) / 2, H - 70 - sh)):
                if self.grid.free(x - 3, y - 3, x + sw + 3, y + sh + 3):
                    self.add('titlepanel', group([svg], id='legend', transform=f'translate({f2(x)} {f2(y)}) scale({f2(s)})'))
                    self.grid.mark_rect(x, y, x + sw, y + sh, pad=4)
                    return True
        return False

    # -- decorations --------------------------------------------------------------
    def decorate(self, seed=42, sound_effects=True):
        rng = random.Random(seed)
        W, H = self.DW, self.DH
        G = self.grid
        fm = FM
        m = 14
        add = self.add
        top, base = fm + 0.8, H - fm - 0.8   # inner edges of the frame line

        def try_place(wd, ht, tries, pad=1.0):
            for _ in range(tries):
                x = rng.uniform(m + wd / 2, W - m - wd / 2)
                y = rng.uniform(m + ht / 2, H - m - ht / 2)
                if G.free(x - wd / 2 - pad, y - ht / 2 - pad, x + wd / 2 + pad, y + ht / 2 + pad):
                    G.mark_rect(x - wd / 2, y - ht / 2, x + wd / 2, y + ht / 2, pad=pad)
                    return x, y
            return None

        # 1. leafy garlands hanging from the top of the frame, with charms
        x = fm + 5
        joints = []
        while x < W - fm - 25:
            span, sag = rng.uniform(40, 75), rng.uniform(6, 12)
            x1 = min(x + span, W - fm - 5)
            if G.free(x, top + 1.5, x1, top + sag + 4):
                add('edgefront', D.vine(rng, D.garland_pts(x, x1, top + .4, sag), leaf_gap=2.4))
                G.mark_rect(x, top, x1, top + sag + 4, pad=1)
                joints += [x, x1]
                mid = (x + x1) / 2 + rng.uniform(-6, 6)
                L = rng.uniform(5, 13)
                ymid = top + .4 + sag * (1 - ((mid - (x + x1) / 2) / ((x1 - x) / 2)) ** 2) - .3
                if rng.random() < .55 and G.free(mid - 4, ymid + 1, mid + 4, ymid + L + 12):
                    add('edgefront', D.charm(rng, mid, ymid, L))
                    G.mark_rect(mid - 4, ymid, mid + 4, ymid + L + 10, pad=1)
                x = x1
            else:
                x += 5
        for jx in sorted(set(round(v, 1) for v in joints)):
            add('edgefront', D.bow(jx, top + .6, rng.choice(D.FLOWERS)))

        # 2. vines wound around the side frame lines: hanging from the garlands at the
        #    top corners, and growing up out of a pot in the bottom corners
        def strip_free(ex, side, y0, y1, reach=5.5):
            x0, x1 = (ex - 2, ex + reach) if side < 0 else (ex - reach, ex + 2)
            return G.free(x0, min(y0, y1), x1, max(y0, y1))

        for side in (-1, 1):
            ex = fm if side < 0 else W - fm
            y, y_stop = top + 1, top + rng.uniform(90, 200)
            while y < y_stop and strip_free(ex, side, y, y + 1, 3 if y < top + 20 else 5.5):
                y += 1
            if y - top > 25:
                back, front = D.twining_vine(rng, ex, top + .6, y - 2)
                add('edgeback', back)
                add('edgefront', front)
                G.mark_rect(ex - 4, top, ex + 4, y, pad=1)
            pcx = ex - side * 7
            if G.free(pcx - 5, base - 9, pcx + 5, base - 1.2):
                pot_svg, _ = D.pot(rng, 8, 6.5, rng.choice(D.POTS), True)
                start = base - 6.5 - 1
                y, y_stop = start - 6, start - rng.uniform(80, 190)
                while y > y_stop and strip_free(ex, side, y - 1, y):
                    y -= 1
                if start - y > 25:
                    lead = [(pcx, base - 6.5), (pcx + side * 1.5, base - 9), (ex - side * 1.2, base - 12.5)]
                    back, front = D.twining_vine(rng, ex, base - 13, y + 2, lead_in=lead)
                    add('edgeback', back)
                    add('edgefront', front)
                    add('edgefront', group([D.wrap(pot_svg)], transform=f'translate({f2(pcx)} {f2(base)})'))
                    G.mark_rect(pcx - 5, base - 9, pcx + 5, base, pad=1)
                    G.mark_rect(ex - 4, y, ex + 4, base, pad=1)

        # 3. things standing on the bottom of the frame: plants, a mug, books, a cat
        limits = {'cat': 1, 'mug': 2, 'books': 2, 'floor_cable': 3}
        ground = D.GROUND_ITEMS * 3 + D.PART_ITEMS + [(None, 3, 3, 0)] * 2
        x = fm + 6
        while x < W - fm - 8:
            draw, lo, hi, ar = rng.choice(ground)
            name = draw.__name__ if draw else 'floor_cable'
            if name == 'floor_cable' and limits['floor_cable'] > 0:
                cw = rng.uniform(40, 52)
                if x + cw < W - fm - 6 and G.free(x, base - 6, x + cw, base - 1.2):
                    add('edgefront', D.floor_cable(rng, x, base, cw, rng.choice(D.CABLES)))
                    G.mark_rect(x, base - 5, x + cw, base, pad=1)
                    limits['floor_cable'] -= 1
                    x += cw + rng.uniform(2, 5)
                continue
            if limits.get(name, 99) <= 0:
                continue
            placed = False
            for h in (rng.uniform(lo, hi), lo, lo * .75):
                w = h * ar
                need = h * (1.6 if name == 'cat' else 1.08)
                if x + w < W - fm - 6 and G.free(x, base - need - 1, x + w, base - 1.2):
                    add('edgefront', group([draw(rng, h)], transform=f'translate({f2(x + w / 2)} {f2(base)})'))
                    G.mark_rect(x, base - need, x + w, base, pad=1.5)
                    limits[name] = limits.get(name, 99) - 1
                    x += w + rng.uniform(1, 4)
                    placed = True
                    break
            if not placed:
                x += 2.5
                continue
            gw = rng.uniform(5, 16)
            if rng.random() < .7 and G.free(x, base - 7, x + gw, base - 1.2):
                add('edgefront', D.grass(rng, x, base, gw))
                G.mark_rect(x, base - 6, x + gw, base, pad=.5)
                x += gw + rng.uniform(0, 3)

        # 4. cables clipped to the side frame lines, hanging straight down
        cables, tries = 0, 0
        while cables < 8 and tries < 200:
            tries += 1
            side = rng.choice((-1, 1))
            ex = fm if side < 0 else W - fm
            ay = rng.uniform(top + 15, base - 60)
            drop = rng.uniform(22, 55)
            x0, x1 = sorted((ex - side * 5, ex - side * 14))
            if not G.free(x0, ay - 2, x1, ay + drop + 12):
                continue
            add('edgefront', D.hanging_cable(rng, ex, ay, -side, drop, rng.choice(D.CABLES)))
            G.mark_rect(x0, ay - 3, x1, ay + drop + 12, pad=4)
            cables += 1

        # 5. wall shelves with plants and clutter in the big empty areas
        shelf_items = [it for it in D.GROUND_ITEMS if it[0].__name__ != 'cat'] * 3 + D.PART_ITEMS
        for _ in range(5):
            sw, sh = rng.uniform(42, 72), rng.uniform(26, 40)
            pos = try_place(sw, sh + 7, 500, pad=5)
            if not pos:
                continue
            x0 = pos[0] - sw / 2
            plank = pos[1] + (sh + 7) / 2 - 7
            items = [D.shelf(x0, plank, sw)]
            x, fails, once = x0 + 3, 0, set()
            while x < x0 + sw - 4 and fails < 12:
                draw, lo, hi, ar = rng.choice(shelf_items)
                if draw.__name__ in once:
                    fails += 1
                    continue
                if draw.__name__ in ('mug', 'books'):
                    once.add(draw.__name__)
                h = rng.uniform(lo, min(hi, sh - 2)) if lo < sh - 2 else 0
                if not h or x + h * ar > x0 + sw - 2:
                    fails += 1
                    continue
                items.append(group([draw(rng, h)], transform=f'translate({f2(x + h * ar / 2)} {f2(plank)})'))
                x += h * ar + rng.uniform(1.5, 4)
            if rng.random() < .75:
                side = rng.choice((-1, 1))
                edge = x0 + sw if side > 0 else x0
                drop = rng.uniform(14, 30)
                gx0, gx1 = sorted((edge - side * 2, edge + side * 6))
                if G.free(gx0, plank + 13, gx1, plank + drop + 12):
                    items.append(D.draped_cable(rng, edge, plank, side, drop, rng.choice(D.CABLES)))
                    G.mark_rect(gx0, plank, gx1, plank + drop + 12, pad=2)
            add('deco', group(items, cls='shelf'))

        # 6. a few clouds
        for _ in range(6):
            w = rng.uniform(16, 28)
            pos = try_place(w * 1.2, w * .55, 300, pad=3)
            if pos:
                add('deco', group([D.cloud(w)], transform=f'translate({f2(pos[0])} {f2(pos[1] + w * .25)})'))

        # 7. just a few faint sound effects
        cols = ['#ffb3d1', '#a6e3d3', '#b3d4ff', '#ffd98f', '#cdb8ff', '#ffbfa3']
        if sound_effects:
            sfx = [('キラキラ', 'kira kira'), ('ふわふわ', 'fuwa fuwa'), ('ドキドキ', 'doki doki')]
            for i, (jp, ro) in enumerate(sfx):
                size = rng.uniform(7, 9)
                pos = try_place(len(jp) * size * 1.05, size * 1.6, 600, pad=6)
                if pos:
                    add('deco', render('page/sound-effect.svg.j2', x=pos[0], y=pos[1], angle=rng.uniform(-12, 12),
                                       size=size, colour=cols[i], jp=jp, ro=ro))

        # 8. a light sprinkle of sparkles and confetti
        kinds = [('sparkle', 4, 7), ('heart-d', 3, 5), ('star', 3.5, 6), ('blossom-d', 3.5, 6), ('sparkle', 2.5, 3.5)]
        for _ in range(170):
            k, lo, hi = rng.choice(kinds)
            sz = rng.uniform(lo, hi)
            pos = try_place(sz, sz, 3, pad=6)
            if pos:
                rot = rng.uniform(-25, 25)
                add('deco', tag('use', href=f'#{k}', transform=f'translate({f2(pos[0])} {f2(pos[1])}) rotate({f2(rot)}) '
                                f'scale({f2(sz / 10)})', fill=rng.choice(cols), opacity=.38))
        for _ in range(260):
            sz = rng.uniform(.8, 1.6)
            pos = try_place(sz, sz, 2, pad=4)
            if pos:
                add('deco', tag('circle', cx=pos[0], cy=pos[1], r=sz / 2, fill=rng.choice(cols), opacity=.28))

    # -- the whole thing ----------------------------------------------------------
    def svg(self, defs, decorations=True, legend=True, seed=42, sound_effects=True):
        self.frame_and_title()
        if legend and self.c.passives:
            self.legend()
        if decorations:
            self.decorate(seed, sound_effects)
        L = self.layers
        return str(render(
            'page/document.svg.j2', W=self.W, H=self.H, k=self.k, defs=Markup(defs), T=self.T, sc=self.sc,
            circuit=Markup(self.c.svg()),
            layers=[('background', 'Background', L['bg']),
                    ('decorations-back', 'Decorations (back)', L['deco'] + L['edgeback']),
                    ('frame', 'Frame', L['frame']),
                    ('decorations-front', 'Decorations (front)', L['edgefront']),
                    ('title', 'Title & legend', L['titlepanel'])])) + '\n'


def overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def split_two(s):
    """Split a speech-bubble line in two at the space nearest its middle."""
    if len(s) < 18 or ' ' not in s:
        return [s]
    mid = len(s) / 2
    i = min((i for i, ch in enumerate(s) if ch == ' '), key=lambda i: abs(i - mid))
    return [s[:i], s[i + 1:]]
