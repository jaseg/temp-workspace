"""The scrapbook page around the circuit: cream cardstock inside a scalloped, polka-dotted mat with a stitched
edge, a bunting along the top, a title card with cut-paper letters and a paper crane, and stickers and paper
confetti in the free space.

Like the manga page, everything is drawn in design units (the short side is 594 units, so an A1 sheet is drawn
1:1 in mm) and the circuit is shrunk and moved out of the way when it would collide with the title card."""

import math
import random

from ..page import FM, TH, TW, Page, fit, split_two, text_width
from ..svg import Markup, escape, group, num as f2, path, render, tag
from ..text import FS, metrics
from . import paper as P
from . import stickers as S
from .text import BUBBLE, MALI

MAT = '#f6c3cf'
MAT_DOT = '#fde6ec'
STITCH = '#d9879f'
MAT_IN = FM + 3       # inner edge of the mat (the scallops bulge in from here)


def hand_width(s, size):
    return metrics().advance(s, MALI, 500) * size


def bubble_width(s, size):
    return metrics().advance(s, BUBBLE, 800) * size


class PaperPage(Page):
    # -- frame -------------------------------------------------------------------
    def frame_and_title(self):
        W, H = self.DW, self.DH
        rng = random.Random(4)
        add = self.add
        add('bg', tag('rect', width=W, height=H, fill='rgb(246,238,225)'))   # the texture's mean colour (not muted), for any seams between tiles
        add('bg', tag('rect', width=W, height=H, fill='url(#pc-card)'))

        # the mat: an evenodd shape, the outer rectangle minus the scalloped inside
        m = MAT_IN
        mat = f'M0 0H{f2(W)}V{f2(H)}H0Z' + P.scallops(m, m, W - m, H - m, 2.6)
        add('frame', path(mat, fill=P.SHADOW, fill_opacity=.2, fill_rule='evenodd', transform='translate(.9 1.2)'))
        add('frame', path(mat, fill=MAT, fill_rule='evenodd'))
        add('frame', path(mat, fill='url(#pc-mat-dots)', fill_rule='evenodd'))
        add('frame', tag('rect', x=3.2, y=3.2, width=W - 6.4, height=H - 6.4, rx=1.5, fill='none', stroke=STITCH,
                         stroke_width=.55, stroke_dasharray='2.2 1.6', stroke_linecap='round'))
        add('frame', tag('rect', x=m + 4.5, y=m + 4.5, width=W - 2 * m - 9, height=H - 2 * m - 9, rx=2, fill='none',
                         stroke='#e7b9c6', stroke_width=.45, stroke_dasharray='1.8 1.4', stroke_linecap='round'))
        # grid references on little paper discs along the mat
        ncol, nrow = (8, 6) if W >= H else (6, 8)
        discs = []
        for i in range(ncol):
            x = m + (W - 2 * m) * (i + .5) / ncol
            discs += [(x, 5.4, str(i + 1)), (x, H - 5.4, str(i + 1))]
        for i in range(nrow):
            y = m + (H - 2 * m) * (i + .5) / nrow
            discs += [(5.4, y, chr(ord('A') + i)), (W - 5.4, y, chr(ord('A') + i))]
        for x, y, s in discs:
            add('frame', group(P.cut_piece(rng, P.sample_circle(x, y, 3.1, .6), P.WHITE, depth=1.4, amp=.12)
                               + [tag('text', [escape(s)], x=x, y=y + 1.45, cls='pc-coord', text_anchor='middle')]))
        # paper flowers on the corners
        for x, y in ((m, m), (W - m, m), (m, H - m), (W - m, H - m)):
            add('frame', paper_flower(rng, x, y, 9))
        for x0, y0, x1, y1 in ((0, 0, W, m), (0, H - m - 2, W, H), (0, 0, m + 2, H), (W - m - 2, 0, W, H)):
            self.grid.mark_rect(x0, y0, x1, y1)
        self.title_card()

    # -- title ------------------------------------------------------------------
    def title_card(self):
        t = self.title
        rx0, ry0, rx1, ry1 = self.title_rect()
        tx, ty = rx1 - TW, ry1 - TH
        rng = random.Random(9)
        out = []
        # the backing card (scalloped, pink) and the front card (cream, lined)
        back = P.cut_piece(rng, P.rect_pts(tx - 5, ty - 5, tx + TW + 5, ty + TH + 5), '#bfe3d6', depth=2.6, amp=.25)
        out.append(group(back, transform=f'rotate(-1.2 {f2(tx + TW / 2)} {f2(ty + TH / 2)})'))
        front = P.cut_piece(rng, P.rect_pts(tx, ty, tx + TW, ty + TH), '#fffaf0', depth=2, amp=.2)
        out += front + [path(front[-1].split(' d="')[1].split('"')[0], fill='url(#pc-grain)')]
        lines = ''.join(f'M{f2(tx + 4)} {f2(y)}H{f2(tx + TW - 4)}' for y in P.frange(ty + 9, ty + TH - 3, 6.5))
        out.append(path(lines, fill='none', stroke='#cfe2f2', stroke_width=.3))
        out.append(path(f'M{f2(tx + 12)} {f2(ty)}V{f2(ty + TH)}', fill='none', stroke='#f6b3c3', stroke_width=.35))
        # washi tape on the top corners
        out.append(P.tape_strip(rng, tx + 4, ty + 1, 26, 8, -38, '#ffd59e', 'stripes', sh=(.6, .8)))
        out.append(P.tape_strip(rng, tx + TW - 4, ty + 1, 26, 8, 38, '#b8dcf5', 'dots', sh=(.6, .8)))

        cx = tx + TW / 2 + 4
        kicker = t['kicker']
        y = ty + 9.5
        if kicker:
            out.append(tag('text', [escape(kicker)], x=cx, y=y, cls='pc-kicker', text_anchor='middle'))
            y += 3
        # the title, one cut-paper square per letter
        out.append(cut_letters(rng, t['title'], cx, y + 12.5, TW - 30, 15))
        y += 26
        if t['subtitle']:
            size = min(6.5, (TW - 30) / max(1e-6, hand_width(t['subtitle'], 1)))
            out.append(tag('text', [escape(t['subtitle'])], x=cx, y=y + 1.5, cls='pc-sub', font_size=size,
                           text_anchor='middle'))
        fy = ty + TH - 4
        if t['footer_left']:
            out.append(tag('text', [escape(t['footer_left'].replace('♡', '·'))], x=tx + 15, y=fy, cls='pc-foot'))
        if t['footer_right']:
            fr = t['footer_right'].replace('drawn with love ♪', 'cut & pasted with love ♡')
            size = min(4.4, (TW - 60) / max(1e-6, hand_width(fr, 1)))
            out.append(tag('text', [escape(fr)], x=tx + TW - 5, y=fy, cls='pc-foot', font_size=size, text_anchor='end'))
        self.add('titlepanel', group(out, id='title-card'))
        # a chip sticker says hello from above the card
        self.add('titlepanel', S.use('chip', tx - 12, ty - 22, 26, -12))
        bub = split_two(t['bubble'])
        bw = max(40, max(hand_width(line, 5.2) for line in bub) + 12)
        bx, by = tx + 14, ty - 34
        bh = 8 + 6 * len(bub)
        bubble = _rounded_bubble(bx, by, bw, bh)
        items = P.soft_shadow(bubble, 2) + [path(bubble, fill=P.WHITE)]
        for i, line in enumerate(bub):
            items.append(tag('text', [escape(line)], x=bx + bw / 2, y=by + 9 + 6 * i - (0 if len(bub) > 1 else -1),
                             cls='pc-bubble-t', text_anchor='middle'))
        self.add('titlepanel', group(items))
        self.grid.mark_rect(rx0 - 6, ry0 - 6, rx1 + 6, ry1 + 6)

    # -- legend -----------------------------------------------------------------
    def legend(self):
        return False

    # -- decorations --------------------------------------------------------------
    def decorate(self, seed=42, sound_effects=True):
        rng = random.Random(seed)
        W, H = self.DW, self.DH
        G = self.grid
        add = self.add
        m = MAT_IN + 6

        def try_place(wd, ht, tries, pad=1.0):
            for _ in range(tries):
                x = rng.uniform(m + wd / 2, W - m - wd / 2)
                y = rng.uniform(m + ht / 2, H - m - ht / 2)
                if G.free(x - wd / 2 - pad, y - ht / 2 - pad, x + wd / 2 + pad, y + ht / 2 + pad):
                    G.mark_rect(x - wd / 2, y - ht / 2, x + wd / 2, y + ht / 2, pad=pad)
                    return x, y
            return None

        # 1. bunting across the top, in spans that are free
        top = MAT_IN + 2
        x = MAT_IN + 8
        while x < W - MAT_IN - 30:
            span, sag = rng.uniform(55, 90), rng.uniform(5, 9)
            x1 = min(x + span, W - MAT_IN - 8)
            if x1 - x > 25 and G.free(x, top + 2, x1, top + sag + 10):
                add('edgefront', bunting(rng, x, x1, top + 1, sag))
                G.mark_rect(x, top, x1, top + sag + 10, pad=1)
                x = x1 + rng.uniform(4, 10)
            else:
                x += 6

        # 2. stickers
        names = list(S.STICKERS)
        rng.shuffle(names)
        placed = 0
        for i in range(40):
            size = rng.uniform(13, 20)
            pos = try_place(size + 4, size + 4, 250, pad=3)
            if pos:
                add('deco', S.use(names[i % len(names)], pos[0], pos[1], size, rng.uniform(-18, 18)))
                placed += 1

        # 4. paper confetti
        conf = []
        for _ in range(420):
            sz = rng.uniform(1.4, 2.8)
            pos = try_place(sz, sz, 2, pad=3)
            if pos:
                conf.append((pos, sz, rng.choice(P.PAPERS), rng.choice(('circle', 'tri', 'heart', 'circle')),
                             rng.uniform(0, 360)))
        sh, pieces = [], []
        for (x, y), sz, c, kind, rot in conf:
            d = confetti_d(kind, x, y, sz, rot)
            sh.append(d)
            pieces.append(path(d, fill=c))
        add('deco', group(P.soft_shadow(''.join(sh), 1.2)))
        add('deco', group(pieces))

    # -- the whole thing ----------------------------------------------------------
    def svg(self, defs, decorations=True, legend=True, seed=42, sound_effects=True):
        self.frame_and_title()
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
                    ('title', 'Title', L['titlepanel'])])) + '\n'


def _circle(x, y, r):
    return f'M{f2(x - r)} {f2(y)}a{f2(r)} {f2(r)} 0 1 0 {f2(2 * r)} 0a{f2(r)} {f2(r)} 0 1 0 {f2(-2 * r)} 0Z'


def _rounded_bubble(x, y, w, h, r=3.5):
    return (f'M{f2(x + r)} {f2(y)}H{f2(x + w - r)}Q{f2(x + w)} {f2(y)} {f2(x + w)} {f2(y + r)}V{f2(y + h - r)}'
            f'Q{f2(x + w)} {f2(y + h)} {f2(x + w - r)} {f2(y + h)}H{f2(x + 16)}L{f2(x + 5)} {f2(y + h + 7)}'
            f'L{f2(x + 9)} {f2(y + h)}H{f2(x + r)}Q{f2(x)} {f2(y + h)} {f2(x)} {f2(y + h - r)}V{f2(y + r)}'
            f'Q{f2(x)} {f2(y)} {f2(x + r)} {f2(y)}Z')


def confetti_d(kind, x, y, s, rot):
    if kind == 'circle':
        return _circle(x, y, s / 2)
    if kind == 'tri':
        pts = [(x + math.cos(math.radians(rot + a)) * s * .6, y + math.sin(math.radians(rot + a)) * s * .6)
               for a in (0, 120, 240)]
        return P.pts_d(pts)
    k = s / 16
    return (f'M{f2(x)} {f2(y + 5 * k)}C{f2(x - 9 * k)} {f2(y - 1 * k)} {f2(x - 6 * k)} {f2(y - 9 * k)} {f2(x)} '
            f'{f2(y - 4 * k)}C{f2(x + 6 * k)} {f2(y - 9 * k)} {f2(x + 9 * k)} {f2(y - 1 * k)} {f2(x)} {f2(y + 5 * k)}Z')


def paper_flower(rng, x, y, r):
    """A layered paper flower: two rings of petals and a button in the middle."""
    out = []
    c1, c2 = rng.sample(['#f7b6c8', '#ffd59e', '#d4c4f5', '#b8dcf5', '#bfe8c6'], 2)
    for layer, (rr, col, n) in enumerate(((r, c1, 6), (r * .68, c2, 5))):
        rot = rng.uniform(0, 60)
        petals = []
        for i in range(n):
            a = math.radians(rot + i * 360 / n)
            px, py = x + math.cos(a) * rr * .52, y + math.sin(a) * rr * .52
            petals.append(tag('ellipse', cx=px, cy=py, rx=rr * .5, ry=rr * .32,
                               transform=f'rotate({f2(math.degrees(a))} {f2(px)} {f2(py)})'))
        out.append(group(petals, fill=P.SHADOW, fill_opacity=.18, transform='translate(.6 .8)'))
        out.append(group(petals, fill=col, stroke=P.shade(col, -.15), stroke_width=.25))
    out.append(tag('circle', cx=x + .3, cy=y + .4, r=r * .26, fill=P.SHADOW, fill_opacity=.2))
    out.append(tag('circle', cx=x, cy=y, r=r * .26, fill='#fff3c4', stroke='#e2c27a', stroke_width=.3))
    for dx in (-.32, .32):
        out.append(tag('circle', cx=x + dx * r * .26 * 1.2, cy=y, r=r * .05, fill='#b48f4a'))
    return group(out, cls='pc-flower')


def bunting(rng, x0, x1, y, sag):
    """A string of paper pennants hanging from (x0, y) to (x1, y)."""
    def at(t):
        return x0 + (x1 - x0) * t, y + sag * 4 * t * (1 - t)
    n = max(3, int((x1 - x0) / 8.5))
    string = 'M' + 'L'.join(f'{f2(px)} {f2(py)}' for px, py in (at(i / 30) for i in range(31)))
    out = [path(string, fill='none', stroke='#b49a86', stroke_width=.4)]
    sh, flags = [], []
    start = rng.randrange(len(P.PAPERS))
    for i in range(n):
        ta, tb = (i + .12) / n, (i + .88) / n
        (ax, ay), (bx, by) = at(ta), at(tb)
        mx, my = at((ta + tb) / 2)
        L = 7.2
        tip = (mx + (ay - by) * .1, my + L)
        d = P.cut_outline(rng, [(ax, ay), (bx, by), tip], amp=.12, step=.9)
        sh.append(d)
        col = P.PAPERS[(start + i * 3) % len(P.PAPERS)]
        flags.append(path(d, fill=col))
        flags.append(path(P.pts_d([(ax + (tip[0] - ax) * .2, ay + (tip[1] - ay) * .2),
                                   (bx + (tip[0] - bx) * .2, by + (tip[1] - by) * .2)], close=False),
                          fill='none', stroke=P.WHITE, stroke_width=.3, stroke_dasharray='.8 .6'))
    out[:0] = P.soft_shadow(''.join(sh), 2)
    return group(out + flags, cls='pc-bunting')


def cut_letters(rng, s, cx, cy, width, size):
    """`s` spelled in letters on little squares of coloured paper, each a bit askew, centred on (cx, cy)."""
    if not s:
        return ''
    fs = size
    gap = .12
    def widths(fs):
        return [max(fs * .62, bubble_width(ch, fs) + fs * .32) if ch != ' ' else fs * .45 for ch in s]
    ws = widths(fs)
    total = sum(ws) + gap * fs * (len(s) - 1)
    if total > width:
        fs *= width / total
        ws = widths(fs)
        total = sum(ws) + gap * fs * (len(s) - 1)
    x = cx - total / 2
    sh, tiles, letters = [], [], []
    for i, (ch, w) in enumerate(zip(s, ws)):
        if ch != ' ':
            col = P.PAPERS[(i * 3 + rng.randrange(2)) % len(P.PAPERS)]
            rot = rng.uniform(-7, 7)
            dy = rng.uniform(-.06, .06) * fs
            h = fs * 1.18
            x0, y0 = x, cy - h / 2 + dy
            tr = f'rotate({f2(rot)} {f2(x + w / 2)} {f2(cy + dy)})'
            d = P.torn_rect(rng, x0, y0, x0 + w, y0 + h, step=fs * .18, amp=fs * .025)
            sh.append(path(d, transform=tr))
            tiles.append(group([path(d, fill=col),
                                tag('text', [escape(ch)], x=x + w / 2, y=cy + dy + fs * .36, font_size=fs,
                                    cls='pc-cut-letter', text_anchor='middle')], transform=tr))
        x += w + gap * fs
    return group([group(sh, fill=P.SHADOW, fill_opacity=.2, transform=f'translate({f2(fs * .05)} {f2(fs * .07)})')]
                 + tiles, cls='pc-title-letters')
