"""Text: KiCad-style text elements, and their size, measured with HarfBuzz in the fonts the page uses.

Text is positioned on explicit baselines (no `dominant-baseline`, which renderers treat differently), so what
is measured here is what every renderer draws, and backgrounds (label pills, banners, ...) can be built right
away."""

import re
import shutil
import subprocess
from functools import cache

from .svg import FONT_MPR, FONT_POP, FONT_ZEN, Markup, escape, num, tag

FS = 1.36     # SVG font-size per KiCad text height
CHAR_W = 0.6  # rough average advance (em), for collision estimates and when no fonts are available
LINE = 1.55   # line spacing, in KiCad text heights

# The font of each text class, as in the stylesheet (styles.py): (family, weight, italic)
CLASSES = {
    '': (FONT_MPR, 500, False), 'pinname': (FONT_MPR, 500, False), 'pinnum': (FONT_MPR, 500, False),
    'ref': (FONT_MPR, 800, False), 'value': (FONT_MPR, 800, False), 'pwr': (FONT_POP, 400, False),
    'symtxt': (FONT_MPR, 500, False), 'lbl': (FONT_MPR, 800, False), 'title': (FONT_POP, 400, False),
    'caption': (FONT_ZEN, 700, False), 'note': (FONT_ZEN, 700, False), 'remark': (FONT_ZEN, 700, False),
    'boxtext': (FONT_ZEN, 700, False), 'sheetname': (FONT_POP, 400, False), 'sheetfile': (FONT_ZEN, 700, True),
    'field': (FONT_MPR, 500, False),
}


# ----------------------------------------------------------------------------
# Measuring

class Metrics:
    """Advances and vertical metrics of the page's fonts (fonts.Font), via HarfBuzz. Characters a font lacks
    are measured in the font fontconfig falls back to, as renderers do."""

    def __init__(self, fonts=()):
        import uharfbuzz as hb
        self.hb = hb
        self.faces = {}
        for f in fonts:
            blob = hb.Blob(f.ttf.read_bytes())
            self.faces[f.family, f.weight] = self.font(blob)
        self.fallback = None
        if (path := fallback_font()) is not None:
            self.fallback = self.font(hb.Blob(open(path, 'rb').read()))

    def font(self, blob):
        face = self.hb.Face(blob)
        font = self.hb.Font(face)
        ext = font.get_font_extents('ltr')
        return font, face.upem, ext.ascender / face.upem, -ext.descender / face.upem

    def pick(self, family, weight):
        cands = [(abs(w - weight), w) for f, w in self.faces if f == family]
        if not cands:
            return None
        return self.faces[family, min(cands)[1]]

    def advance(self, s, family, weight):
        """Width of `s` in em."""
        f = self.pick(family, weight)
        if f is None:
            return len(s) * CHAR_W
        font, upem = f[0], f[1]
        buf = self.hb.Buffer()
        buf.add_str(s)
        buf.guess_segment_properties()
        self.hb.shape(font, buf, {})
        w = 0
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            if info.codepoint == 0:          # not in this font: as wide as in the fallback font
                ch = s[info.cluster]
                w += self.fallback_advance(ch)
            else:
                w += pos.x_advance / upem
        return w

    def fallback_advance(self, ch):
        if self.fallback is None:
            return 1.0
        font, upem = self.fallback[0], self.fallback[1]
        gid = font.get_nominal_glyph(ord(ch))
        return font.get_glyph_h_advance(gid) / upem if gid else 1.0

    def vertical(self, family, weight):
        """(ascent, descent) in em, both positive."""
        f = self.pick(family, weight)
        return (f[2], f[3]) if f else (0.9, 0.25)


@cache
def fallback_font():
    """The file fontconfig uses for symbols such as ♡ and ♪, if fontconfig is around."""
    if not shutil.which('fc-match'):
        return None
    try:
        out = subprocess.run(['fc-match', '-f', '%{file}', 'sans-serif:charset=2661'], capture_output=True,
                             text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out if out.endswith(('.ttf', '.otf')) else None


_metrics = None


def use_fonts(fonts):
    """Measure text in these fonts (fonts.Font) from now on."""
    global _metrics
    _metrics = Metrics(fonts)


def metrics():
    global _metrics
    if _metrics is None:
        _metrics = Metrics()
    return _metrics


# ----------------------------------------------------------------------------
# KiCad's ~{overbar} _{sub} ^{super} markup

MARKUP = re.compile(r'([~_^])\{((?:[^{}]|\{[^{}]*\})*)\}')


def runs(s):
    """[(text, kind)] with kind '', '~', '_' or '^'."""
    out, pos = [], 0
    for m in MARKUP.finditer(s):
        if m.start() > pos:
            out.append((s[pos:m.start()], ''))
        out.append((m.group(2), m.group(1)))
        pos = m.end()
    if pos < len(s):
        out.append((s[pos:], ''))
    return out


def plain(s):
    return MARKUP.sub(lambda m: m.group(2), s)


def markup_tspans(s):
    out = []
    for text, kind in runs(s):
        if kind == '~':
            out.append(tag('tspan', [escape(text)], cls='ovl'))
        elif kind:
            out.append(tag('tspan', [escape(text)], baseline_shift='sub' if kind == '_' else 'super', font_size='75%'))
        else:
            out.append(escape(text))
    return Markup(''.join(out))


def font_of(cls, style=''):
    family, weight, italic = CLASSES.get(cls.split()[0] if cls else '', CLASSES[''])
    if 'font-weight:800' in style:
        weight = 800
    return family, weight, italic


def line_width(line, size, family, weight):
    """Width of one line of (marked up) text at KiCad text height `size`, in mm."""
    m = metrics()
    return sum(m.advance(text, family, weight) * (.75 if kind in ('_', '^') else 1)
               for text, kind in runs(line)) * size * FS


def text_extent(s, size, cls=''):
    """(width, height) of a (multi-line) text, in mm."""
    family, weight, _ = font_of(cls)
    lines = s.split('\n')
    return max(line_width(line, size, family, weight) for line in lines), len(lines) * 1.5 * size


# ----------------------------------------------------------------------------
# Text elements

def layout(s, size, h, v, cls, style=''):
    """Lines as [(x, baseline y, text)] relative to the anchor, the text-anchor, and the bounding box
    (x, y, w, h) as a browser would report it (advance widths, font ascent to descent)."""
    family, weight, _ = font_of(cls, style)
    asc, desc = metrics().vertical(family, weight)
    fs = size * FS
    lines = s.split('\n')
    lh = LINE * size
    if v == 'center':
        y0, shift = -(len(lines) - 1) * lh / 2, (asc - desc) / 2 * fs     # the "central" baseline
    elif v == 'bottom':
        y0, shift = -(len(lines) - 1) * lh, 0
    else:
        y0, shift = 0, .8 * asc * fs                                   # the "hanging" baseline
    anchor = {'left': 'start', 'right': 'end', 'center': 'middle'}[h]
    out, xs0, xs1 = [], [], []
    for i, line in enumerate(lines):
        w = line_width(line, size, family, weight)
        x0 = {'start': 0, 'middle': -w / 2, 'end': -w}[anchor]
        xs0.append(x0)
        xs1.append(x0 + w)
        out.append((0, y0 + i * lh + shift, line))
    top = out[0][1] - asc * fs
    bottom = out[-1][1] + desc * fs
    return out, anchor, (min(xs0), top, max(xs1) - min(xs0), bottom - top)


def text_el(x, y, s, size, ang, h, v, cls, bg=None, style='', **attrs):
    """KiCad-style text anchored at (x, y); ang is 0 or 90 (reads bottom-to-top).

    Wrapped in its own <g> holding the position. With `bg` (a backgrounds.build() description) the background
    shape is drawn behind the text, fitted to its measured size."""
    from . import backgrounds
    lines, anchor, box = layout(s, size, h, v, cls, style)
    spans = [tag('tspan', [markup_tspans(t)], x=lx, y=ly) for lx, ly, t in lines]
    t = tag('text', spans, cls=cls, font_size=size * FS, text_anchor=anchor, style=style or None, **attrs)
    rot = ' rotate(-90)' if round(ang) % 180 == 90 else ''
    children = [backgrounds.build(bg, box) if bg else None, t]
    return tag('g', children, transform=f'translate({num(x)} {num(y)}){rot}')
