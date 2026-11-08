"""Around the circuit: the sampler's floral border, its title panel and the floss key.

All of it is charted on the same cloth as the schematic. The border runs in the margin outside KiCad's drawing
frame. The title panel goes where KiCad's title block would be, the bottom right corner, and moves along the
bottom or up the right side when the schematic is in the way."""

import itertools
import math
import re
from pathlib import Path

from gerbonara.cad.kicad.base_types import kicad_text_svg, kicad_text_width

from ..kicad import paper_name
from . import motifs as mo
from . import threads as th
from .chart import Stitch
from .geometry import flatten

EDGE = 2                 # bare cloth outside the border, in cells
class Page:
    def __init__(self, chart, sch, path, cfg, title):
        self.c, self.sch, self.path, self.cfg, self.title = chart, sch, path, cfg, title
        self.b = chart.hole
        W, H = sch.page_settings.size
        self.W, self.H = W, H
        self.cols, self.rows = math.floor(W / self.b), math.floor(H / self.b)
        self.notes = []

    def build(self, threads):
        self.border(self.c.occupied(pad=0))
        self.panel(self.c.occupied(pad=3), threads)

    def report(self):
        return self.notes

    # -- text --------------------------------------------------------------------------------
    def backstitch_text(self, text, x, y, size, color, h='left', v='bottom', bold=False):
        pen = size / (5 if bold else 9)
        tags = kicad_text_svg(text, x, y, size, h_align=h, v_align=v, stroke_width=pen, stroke='t', fill='none')
        for p in flatten(tags):
            if p.kind == 'line' and len(p.pts) > 1:
                self.c.stitches.append(Stitch(p.pts, color, 'text', 0, p.width))

    def frame(self, i0, j0, i1, j1, color, double=True):
        """A backstitched frame along the holes of cells i0..i1, j0..j1 (exclusive)."""
        b = self.b
        for k in ((0, 1) if double else (0,)):
            pts = [((i0 + k) * b, (j0 + k) * b), ((i1 - k) * b, (j0 + k) * b), ((i1 - k) * b, (j1 - k) * b),
                   ((i0 + k) * b, (j1 - k) * b), ((i0 + k) * b, (j0 + k) * b)]
            self.c.stitches.append(Stitch(pts, color, 'wire', b))

    # -- the border ------------------------------------------------------------------------------
    def border(self, busy):
        n = mo.BAND_ROWS
        i0, j0 = EDGE, EDGE
        i1, j1 = self.cols - EDGE, self.rows - EDGE        # exclusive
        clash = sum(1 for (i, j) in busy if (i0 <= i < i1 and j0 <= j < j1) and
                    not (i0 + n + 4 <= i < i1 - n - 4 and j0 + n + 4 <= j < j1 - n - 4))
        if clash:
            self.notes.append(f'cross-stitch: the schematic reaches into the border in {clash} cells')
        self.frame(i0, j0, i1, j1, th.INK)
        self.frame(i0 + n + 4, j0 + n + 4, i1 - n - 4, j1 - n - 4, th.INK, double=False)
        a, z = i0 + 2, i1 - 2 - n                       # corner squares' top-left cells
        top, bottom = j0 + 2, j1 - 2 - n
        for ci, cj in ((a, top), (z, top), (a, bottom), (z, bottom)):
            self.c.motif(mo.CORNER, ci, cj, mo.KEY)
        span = (z - a - n)                               # cells between the corners along the top
        self.band(mo.VINE, a + n, top, span, horizontal=True)
        self.band(mo.flip(mo.VINE), a + n, bottom, span, horizontal=True)
        vspan = bottom - top - n
        right = mo.rotate(mo.VINE)
        left = mo.rotate(mo.rotate(right))
        self.band(left, a, top + n, vspan, horizontal=False)
        self.band(right, z, top + n, vspan, horizontal=False)

    def band(self, unit, i, j, span, horizontal):
        """Repeat a motif along `span` cells, centred, starting at cell (i, j)."""
        size = len(unit[0]) if horizontal else len(unit)
        reps = max(0, span // size)
        off = (span - reps * size) // 2
        stem = mo.STEM if horizontal else mo.rotate(mo.STEM)
        for k in range(-1, span // size + 2):      # the stem runs all the way, under the gaps too
            for r, row in enumerate(stem):
                for cc, v in enumerate(row):
                    di, dj = (k * size + cc, r) if horizontal else (cc, k * size + r)
                    if v != '.' and 0 <= (di if horizontal else dj) < span:
                        self.c.crosses.setdefault((i + di, j + dj), mo.KEY[v])
        for k in range(reps):
            if horizontal:
                self.c.motif(unit, i + off + k * size, j, mo.KEY)
            else:
                self.c.motif(unit, i, j + off + k * size, mo.KEY)

    # -- the title panel ------------------------------------------------------------------------
    def panel(self, busy, threads):
        """The title panel, as near the bottom right corner as it fits, then the floss key next to it."""
        n = EDGE + mo.BAND_ROWS + 6                      # inside the border's inner frame
        area = (n, n, self.cols - n, self.rows - n)
        self.sat = self.summed(busy)
        title = self.title['title'].upper()
        corner = (area[2], area[3])
        found = None
        for scale in (1, .5):
            for lines in wraps(title):
                L = self.title_layout(lines, scale)
                spot = self.find_spot(*L['size'], area, corner)
                if spot:
                    found = (L, spot)
                    break
            if found:
                break
        if found is None:
            L = self.title_layout(wraps(title)[-1], .5)
            w, h = L['size']
            found = (L, (area[2] - w, area[3] - h))
            self.notes.append('cross-stitch: no free spot for the title panel; it overlaps the schematic')
        L, (pi, pj) = found
        self.draw_title(L, pi, pj)
        w, h = L['size']
        busy |= {(i, j) for i in range(pi - 2, pi + w + 2) for j in range(pj - 2, pj + h + 2)}
        self.sat = self.summed(busy)

        key = self.floss_key(threads)
        if not key:
            return
        near = (pi + w // 2, pj + h // 2)
        for ncols in (1, 2, 3, 4, 5, 6):
            K = self.key_layout(key, ncols)
            spot = self.find_spot(*K['size'], area, near, centre=True)
            if spot:
                self.draw_key(K, *spot)
                return
        self.notes.append('cross-stitch: no free spot for the floss key; left it out')

    def summed(self, busy):
        cols, rows = self.cols + 1, self.rows + 1
        S = [[0] * (cols + 1) for _ in range(rows + 1)]          # summed-area table of the busy cells
        for j in range(rows):
            acc = 0
            for i in range(cols):
                acc += (i, j) in busy
                S[j + 1][i + 1] = S[j][i + 1] + acc
        return S

    def find_spot(self, w, h, area, target, centre=False):
        """The free w x h cells in `area` nearest to `target` (their bottom right corner, or centre)."""
        S = self.sat
        i0, j0, i1, j1 = area
        best = None
        for cj in range(j0, j1 - h + 1):
            row0, row1 = S[cj], S[cj + h]
            for ci in range(i0, i1 - w + 1):
                if row1[ci + w] - row0[ci + w] - row1[ci] + row0[ci]:
                    continue
                if centre:
                    d = abs(ci + w / 2 - target[0]) + abs(cj + h / 2 - target[1])
                else:
                    d = abs(ci + w - target[0]) + 1.5 * abs(cj + h - target[1])
                if best is None or d < best[0]:
                    best = (d, (ci, cj))
        return best[1] if best else None

    def floss_key(self, threads):
        out = []
        for col, (name, what) in sorted(threads.used.items(), key=lambda kv: kv[1][0]):
            what = sorted(what)
            desc = ', '.join(what[:4]) + (f' +{len(what) - 4}' if len(what) > 4 else '')
            out.append((col, name, desc))
        return out

    def title_layout(self, lines, scale):
        pad = 3
        title_w = math.ceil(max(mo.text_width(line) for line in lines) * scale)
        title_h = math.ceil((len(lines) * 9 - 2) * scale)
        footer_w = math.ceil(kicad_text_width(self.title['footer'], 1.6) / self.b)
        sub_w = math.ceil(kicad_text_width(self.title.get('subtitle') or '', 2.2) / self.b)
        width = max(title_w, footer_w, sub_w, 44)
        info_h = 6
        w = width + 2 * pad
        h = pad + 6 + 2 + title_h + 2 + info_h + pad
        return {'lines': lines, 'scale': scale, 'size': (w, h), 'pad': pad, 'title_h': title_h}

    def key_layout(self, key, ncols):
        col_w = max(math.ceil(kicad_text_width(f'{name} · {desc}', 1.27) / self.b) + 3 for _, name, desc in key)
        nrows = math.ceil(len(key) / ncols)
        pad = 3
        w = ncols * col_w + (ncols - 1) * 2 + 2 * pad
        h = pad + 3 + nrows * 2 + pad - 1
        return {'key': key, 'size': (w, h), 'pad': pad, 'col_w': col_w, 'nrows': nrows}

    def draw_title(self, L, pi, pj):
        b, c = self.b, self.c
        w, h = L['size']
        pad = L['pad']
        self.frame(pi, pj, pi + w, pj + h, th.INK)
        for ci, cj in ((pi + 2, pj + 2), (pi + w - 5, pj + 2), (pi + 2, pj + h - 5), (pi + w - 5, pj + h - 5)):
            c.motif(mo.SMALL_HEART, ci, cj, mo.KEY)
        # a row of motifs along the top
        row_j = pj + pad
        unit = [(mo.STRAWBERRY, 5), (mo.BIRD, 8), (mo.TULIP, 5), (mo.mirror(mo.BIRD), 8)]
        items, x, k = [], 0, 0
        while True:
            m, mw = unit[k % len(unit)]
            if x + mw > w - 2 * pad - 6:
                break
            items.append((m, x))
            x += mw + 3
            k += 1
        x0 = pi + (w - (x - 3)) // 2
        for m, dx in items:
            c.motif(m, x0 + dx, row_j + (6 - len(m)), mo.KEY)
        # the title, centred
        s = L['scale']
        y = row_j + 8
        for line in L['lines']:
            cells, lw = mo.text_cells(line)
            if s == 1:
                x0 = pi + (w - lw) // 2
                for cx, cy in cells:
                    c.crosses[(x0 + cx, y + cy)] = th.INK
            else:
                x0 = pi + (w - lw * s) / 2
                for cx, cy in cells:
                    c.petite.append(((x0 + cx * s) * b, (y + cy * s) * b, s * b, th.INK))
            y += 9 * s
        y = pj + pad + 8 + L['title_h'] + 2
        t = self.title
        if t.get('subtitle'):
            self.backstitch_text(t['subtitle'], (pi + w / 2) * b, (y + 2) * b, 2.2, th.VALUE, h='center')
        self.backstitch_text(t['footer'], (pi + w / 2) * b, (y + 4.6) * b, 1.6, th.NOTE, h='center')

    def draw_key(self, K, pi, pj):
        b, c = self.b, self.c
        w, h = K['size']
        pad = K['pad']
        self.frame(pi, pj, pi + w, pj + h, th.INK, double=False)
        self.backstitch_text('FLOSS KEY', (pi + pad) * b, (pj + pad + 1) * b, 1.8, th.INK, bold=True)
        y = pj + pad + 3
        for n, (col, name, desc) in enumerate(K['key']):
            ci = pi + pad + (n // K['nrows']) * (K['col_w'] + 2)
            cj = y + (n % K['nrows']) * 2
            c.crosses[(ci, cj)] = col
            self.backstitch_text(f'{name} · {desc}', (ci + 1.7) * b, (cj + .5) * b, 1.27, th.NOTE, v='middle')


def wraps(title):
    """Ways to break the title into lines at spaces, dashes and underscores: one line, two, three."""
    words = [w for w in re.split(r'(?<=[-_ ])', title) if w]
    out = [[title]]
    for n in (2, 3):
        if len(words) < n:
            break
        best = None
        # split into n lines as evenly as possible
        for cuts in itertools.combinations(range(1, len(words)), n - 1):
            parts = [''.join(words[a:b2]).strip() for a, b2 in zip((0, *cuts), (*cuts, len(words)))]
            score = max(mo.text_width(p) for p in parts)
            if best is None or score < best[0]:
                best = (score, parts)
        out.append(best[1])
    return out


def title_info(sch, path, overrides):
    from ..kicad import title_comment
    tb = sch.title_block
    stem = re.sub(r'^[0-9a-f]{8}-', '', Path(path).stem)
    pages = [p.page for p in sch.sheet_instances]
    rev, date, company = (tb.rev, tb.date, tb.company) if tb is not None else ('', '', '')
    footer = [f'sheet {pages[0]}' if pages and pages[0] else '', company, f'rev {rev}' if rev else '', date,
              f'paper {paper_name(sch)}', 'stitched with love']
    return {
        'title': overrides.get('title') or (tb.title if tb is not None else '') or stem,
        'subtitle': overrides.get('subtitle') or title_comment(tb, 1),
        'footer': ' · '.join(x for x in footer if x),
    }
