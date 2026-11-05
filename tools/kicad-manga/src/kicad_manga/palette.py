"""Pastel colours: net families and per-library body colours."""

import collections
import colorsys
import hashlib
import math
import random
import re

from .sexp import natural_key

INK = '#4b3a5a'          # soft plum "ink" instead of black
INK_SOFT = '#8a7499'
PAPER = '#fffaf2'


def hls_hex(h, l, s):
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, l, s)
    return '#%02x%02x%02x' % (round(r * 255), round(g * 255), round(b * 255))


def jitter(name, n):
    return int(hashlib.md5(name.encode()).hexdigest()[:8], 16) % n


def scattered(n):
    """Positions 0..n-1 visited in an order that puts consecutive items far apart."""
    if n <= 2:
        return list(range(n))
    stride = next(st for st in range(max(1, round(n * .618)), n + 1) if math.gcd(st, n) == 1)
    return [(k * stride) % n for k in range(n)]


class NetColors:
    """Pastel net colours in families: nets whose names start with the same word (FPGA_*,
    SEND_*, LED1..3, ...) share a stretch of the colour wheel; positive supply rails share
    a narrow orange-amber slot and grounds are lilac-grey.

    Each family's stretch is as wide as its share of the sheet's labels, so all hues show
    up in roughly equal measure. Families next to each other on the wheel are picked to
    sit far apart on the sheet, so labels near each other rarely look alike."""

    RAILS = (20, 46)

    def __init__(self, labels):
        """`labels`: (net name, x, y) for every label on the sheet."""
        fams = collections.defaultdict(list)
        for name, x, y in labels:
            if not self.is_supply(name):
                fams[self.prefix(name)].append((name, x, y))
        self.member = {}
        if not fams:
            return
        order = self.arrange(fams)
        gap = 5
        start, span = self.RAILS[1] + gap, 360 - (self.RAILS[1] - self.RAILS[0]) - 2 * gap
        total = sum(len(m) for m in fams.values())
        a = start
        for p in order:
            w = span * len(fams[p]) / total
            bases = sorted({self.base(n) for n, _, _ in fams[p]}, key=natural_key)
            nb = len(bases)
            # members may spread a bit past the family's own arc (its wheel neighbours sit
            # far away on the sheet), and consecutive names are scattered across it
            spread = max(w, 9 * nb ** .5) * 1.4
            for k, (b, pos) in enumerate(zip(bases, scattered(nb))):
                self.member[b] = (a + w / 2 + spread * ((pos + .5) / nb - .5), k)
            a += w

    @staticmethod
    def arrange(fams, near=35.0):
        """Order the families around the wheel so that families with many labels close
        to each other on the sheet end up with hues far apart (swap hill-climbing)."""
        names = sorted(fams)
        n = len(names)
        total = sum(len(fams[p]) for p in names)
        width = [360 * len(fams[p]) / total for p in names]
        prox = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                c = sum(1 for _, ax, ay in fams[names[i]] for _, bx, by in fams[names[j]]
                        if math.hypot(ax - bx, ay - by) < near)
                prox[i][j] = prox[j][i] = c

        def cost(order):
            centre, a = {}, 0
            for i in order:
                centre[i] = a + width[i] / 2
                a += width[i]
            tot = 0
            for i in range(n):
                for j in range(i + 1, n):
                    if prox[i][j]:
                        d = abs(centre[i] - centre[j])
                        d = min(d, 360 - d) - (width[i] + width[j]) / 2
                        tot += prox[i][j] * math.exp(-max(0, d) / 25)
            return tot

        rng = random.Random(1)
        order = sorted(range(n), key=lambda i: -width[i])
        best = cost(order)
        for _ in range(6000 if n > 2 else 0):
            i, j = rng.sample(range(n), 2)
            order[i], order[j] = order[j], order[i]
            c = cost(order)
            if c <= best:
                best = c
            else:
                order[i], order[j] = order[j], order[i]
        return [names[i] for i in order]

    @staticmethod
    def is_supply(name):
        n = name.upper()
        return name.startswith('+') or name.startswith('-') or n.startswith(('GND', 'VCC', 'VDD', 'VSS', 'VEE', 'VBAT'))

    @staticmethod
    def prefix(name):
        name = name.rsplit('/', 1)[-1]           # hierarchical paths: '/sub/CLK' -> 'CLK'
        m = re.match(r'[A-Za-z]+', name.lstrip('+~{'))
        return m.group(0).upper() if m else name

    @staticmethod
    def base(name):
        return re.sub(r'(_?[PN]|[+-])$', '', name)    # a diff pair's two halves match

    def __call__(self, name):
        if not name:
            return None
        j = jitter(name, 1000) / 1000
        if name.upper().startswith(('GND', 'VSS')):
            return hls_hex(262 + 18 * j, .80 + .05 * j, .22)
        if self.is_supply(name):
            lo, hi = self.RAILS
            return hls_hex(lo + (hi - lo) * j, .8 + .06 * j, .95)
        hue, k = self.member.get(self.base(name), (self.RAILS[1] + 5 + jitter(name, 300), 0))
        l, sat = ((.82, .9), (.88, .95), (.85, .68), (.9, .85))[k % 4]   # pastel steps
        return hls_hex(hue, l, sat)

    @staticmethod
    def unnamed(key):
        """A muted grey-teal family for nets without a name."""
        return hls_hex(175 + 30 * jitter(str(key), 1000) / 1000, .8, .28)


class LibColors:
    """Pastel IC body colours: one hue per symbol library, spread evenly round the wheel."""

    def __init__(self, lib_ids):
        libs = sorted({lib_id.split(':')[0] for lib_id in lib_ids}, key=natural_key)
        n = max(1, len(libs))
        self.hue = {lib: 15 + 360 * pos / n for lib, pos in zip(libs, scattered(len(libs)))}

    def __call__(self, lib_id):
        lib = lib_id.split(':')[0]
        hue = self.hue.get(lib, jitter(lib, 360))
        return hls_hex(hue + 10 * (jitter(lib_id, 100) / 100 - .5), .9, .78)
