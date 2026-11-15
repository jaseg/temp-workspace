"""Outline import from SVG files (geometry.SVGShape).

`read_outline(filename, tolerance)` returns the outline of an SVG drawing as a list of (x, y) points in mm, in the
file's own coordinate directions (SVG and KiCad both have y pointing down) and in the order the file gives them.

What is read:

* Shapes: <path> (all commands: M L H V Z C S Q T A, absolute and relative, implicit repeated commands, numbers with
  exponents and without separators, "-" and "." starting a new number, arc flags without separators), <polygon>,
  <polyline>, <rect> (also with rounded corners), <circle> and <ellipse>, also when reached through <use> (of a shape,
  a group or a <symbol>, with the symbol's viewBox fitted to the width and height of the <use> or the symbol). <line>,
  text, and the contents of <defs>, <symbol>, <clipPath>, <mask>, <marker> and <pattern> are not part of the outline.
* Hidden elements are not part of it either: display:none (e.g. hidden Inkscape layers) and visibility:hidden or
  collapse, given as attributes, in style attributes, or in <style> sheets with type, .class, #id or * selectors and
  their combinations (other selectors that hide something are a ValueError; rules inside @media and other at-rules
  are ignored). Other CSS (e.g. transforms in style) is not read.
* Transforms: the transform attribute (matrix, translate, scale, rotate, skewX, skewY) of the shape and of all its
  ancestors, nested <svg> viewports and the x/y of <use>.
* Curves and arcs are flattened to polylines that stay within `tolerance` (mm, after all transforms; default
  DEFAULT_TOLERANCE = 0.01 mm) of the curve: Bezier curves with Wang's bound, as one segment if all control points are
  within the tolerance of the chord; arcs by the sagitta of the transformed ellipse. Straight segments keep their
  vertices as given.
* Units: if the root <svg> has a width or height with an absolute unit (mm, cm, in, pt, pc, Q, or px at 96 px per
  inch), the viewBox is scaled to that size (only the scale: the origin of the user coordinate system stays the
  origin, so a drawing centered on (0, 0) stays centered). When width and height agree with the viewBox size up to the
  precision they are written with and to 1e-4 relative (EXACT_UNIT_REL), as exporters write them (width="100.24mm"
  viewBox="0 0 100.2394 54.4735"), one user unit is exactly one unit of width and height. Without a viewBox, user
  units are CSS px (SVG specification), with a warning. Without an absolute unit (no width and height, unitless ones,
  or percentages) one user unit is 1 mm, as kicoil always read SVG files; unitless width and height that differ from
  the viewBox size only give a warning (by the specification they would be px and scale the viewBox). Adobe
  Illustrator writes its points (1/72 in) as px or without a unit, so its files come out at 3/4 size or 72/25.4 times
  too large; export them with mm units.
* Several shapes and subpaths: each subpath is a contour. A subpath is closed by Z, or when it ends where it started
  (within JOIN_TOLERANCE = 0.01 mm). Open subpaths whose end points meet within JOIN_TOLERANCE (as in KiCad and FreeCAD
  exports, where every line and arc of a board outline is a path of its own) are joined into closed contours. The
  outline is the contour with the largest area. It has to be closed and must not touch or cross itself, otherwise this
  is a ValueError. All other contours (holes inside it, shapes next to it, open paths) are ignored with a warning: the
  coil covers the whole outline. A frame or page border drawn around the outline (e.g. a KiCad plot with the
  worksheet) is the largest contour and is taken as the outline, with that warning; delete it from the file.
"""

import math
import re
import warnings

from lxml import etree


# mm: end points closer than this are the same point (subpath closing, joining open subpaths). Well above the rounding
# of exporters (3 decimals of mm: 0.5 um per coordinate, so separately computed ends of a line and an arc can miss by
# 1.4 um), well below any clearance.
JOIN_TOLERANCE = 0.01
# mm: default flattening tolerance of curves and arcs. 1/15 of a 0.15 mm clearance and below PCB etching tolerances.
# The flattened outline is the outline of the coil (all turns are offsets of it), so the deviation from the true curve
# only shifts the coil as a whole, by at most this much; the straight skeleton's cost grows about quadratically with
# the vertex count of curved, non-convex outlines (60 cubic lobes of 40 mm radius: 460 vertices, 15 s; at 0.002 mm:
# 996 vertices, 67 s).
DEFAULT_TOLERANCE = 0.01
# Relative agreement of width/height with the viewBox size below which one user unit is exactly one unit of them
EXACT_UNIT_REL = 1e-4
MAX_CURVE_SEGMENTS = 10000 # per curve segment, against absurd inputs

UNIT_MM = {'mm': 1.0, 'cm': 10.0, 'in': 25.4, 'pt': 25.4/72, 'pc': 25.4/6, 'q': 0.25, 'px': 25.4/96}
# Lengths with a unit inside the drawing (e.g. <rect width="10mm">) in user units, which are CSS px there
UNIT_PX = {'': 1.0, 'px': 1.0, 'mm': 96/25.4, 'cm': 960/25.4, 'in': 96.0, 'pt': 96/72, 'pc': 16.0, 'q': 96/25.4/4}

SKIP_ELEMENTS = {'defs', 'symbol', 'clipPath', 'mask', 'marker', 'pattern', 'metadata', 'title', 'desc', 'style',
                 'script', 'linearGradient', 'radialGradient', 'filter', 'foreignObject', 'text', 'namedview',
                 'image', 'font', 'font-face', 'cursor', 'view'}

IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

_NUMBER = r'[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?'
_NUMBER_RE = re.compile(_NUMBER)
_SEP_RE = re.compile(r'[\s,]*')
_LENGTH_RE = re.compile(r'\s*(' + _NUMBER + r')\s*([a-zA-Z%]*)\s*$')


def _localname(el):
    tag = el.tag
    if not isinstance(tag, str): # comments, processing instructions
        return None
    return etree.QName(tag).localname


def _mul(m1, m2):
    """ Affine matrix product m1 * m2 (m2 applied first), matrices as SVG (a, b, c, d, e, f) """
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (a1*a2 + c1*b2, b1*a2 + d1*b2,
            a1*c2 + c1*d2, b1*c2 + d1*d2,
            a1*e2 + c1*f2 + e1, b1*e2 + d1*f2 + f1)


def _apply(m, p):
    a, b, c, d, e, f = m
    x, y = p
    return (a*x + c*y + e, b*x + d*y + f)


def parse_transform(text):
    """ Matrix of an SVG transform attribute (list of matrix/translate/scale/rotate/skewX/skewY) """
    m = IDENTITY
    if not text:
        return m
    pos = 0
    item_re = re.compile(r'[\s,]*([a-zA-Z]+)\s*\(([^)]*)\)[\s,]*')
    while pos < len(text):
        mo = item_re.match(text, pos)
        if not mo:
            if not text[pos:].strip(' \t\r\n,'):
                break
            raise ValueError(f'SVG: cannot parse transform "{text}"')
        name, args = mo.group(1), mo.group(2)
        pos = mo.end()
        vals = [float(v) for v in _NUMBER_RE.findall(args)]
        if _NUMBER_RE.sub('', args).strip(' \t\r\n,'):
            raise ValueError(f'SVG: cannot parse transform "{text}"')
        n = len(vals)
        if name == 'matrix' and n == 6:
            t = tuple(vals)
        elif name == 'translate' and n in (1, 2):
            t = (1.0, 0.0, 0.0, 1.0, vals[0], vals[1] if n == 2 else 0.0)
        elif name == 'scale' and n in (1, 2):
            t = (vals[0], 0.0, 0.0, vals[1] if n == 2 else vals[0], 0.0, 0.0)
        elif name == 'rotate' and n in (1, 3):
            a = math.radians(vals[0])
            ca, sa = math.cos(a), math.sin(a)
            t = (ca, sa, -sa, ca, 0.0, 0.0)
            if n == 3:
                cx, cy = vals[1], vals[2]
                t = _mul(_mul((1.0, 0.0, 0.0, 1.0, cx, cy), t), (1.0, 0.0, 0.0, 1.0, -cx, -cy))
        elif name == 'skewX' and n == 1:
            t = (1.0, 0.0, math.tan(math.radians(vals[0])), 1.0, 0.0, 0.0)
        elif name == 'skewY' and n == 1:
            t = (1.0, math.tan(math.radians(vals[0])), 0.0, 1.0, 0.0, 0.0)
        else:
            raise ValueError(f'SVG: unsupported transform "{name}({args})"')
        m = _mul(m, t)
    return m


def _parse_length(text, what='length'):
    """ (value, unit) of an SVG length, unit lower case ('' for none) """
    mo = _LENGTH_RE.match(text)
    if not mo:
        raise ValueError(f'SVG: cannot parse {what} "{text}"')
    return float(mo.group(1)), mo.group(2).lower()


def _user_length(el, name, default=0.0):
    """ A length attribute of a shape element in user units """
    text = el.get(name)
    if text is None or not text.strip():
        return default
    val, unit = _parse_length(text, f'{name} of <{_localname(el)}>')
    if unit not in UNIT_PX:
        raise ValueError(f'SVG: unsupported unit in {name}="{text}" of <{_localname(el)}> (percentages and font '
                         f'relative units are not supported)')
    return val * UNIT_PX[unit]


def _parse_viewbox(text):
    if text is None or not text.strip():
        return None
    vals = [float(v) for v in _NUMBER_RE.findall(text)]
    if len(vals) != 4:
        raise ValueError(f'SVG: cannot parse viewBox "{text}"')
    if vals[2] <= 0 or vals[3] <= 0:
        raise ValueError(f'SVG: viewBox "{text}" has a non-positive size')
    return vals


def _parse_aspect(text):
    """ (align, slice) of preserveAspectRatio; align is None for "none" """
    words = (text or '').split()
    if words and words[0] == 'defer':
        words = words[1:]
    align = words[0] if words else 'xMidYMid'
    if align == 'none':
        return None, False
    return align, (len(words) > 1 and words[1] == 'slice')


def _viewbox_scale(vb, width, height, aspect):
    """ Scale (sx, sy) that maps the viewBox onto a viewport of the given size (either may be None) """
    _, _, vw, vh = vb
    if width is None and height is None:
        return 1.0, 1.0
    if width is None:
        width = height * vw / vh
    if height is None:
        height = width * vh / vw
    sx, sy = width / vw, height / vh
    align, slice_ = _parse_aspect(aspect)
    if align is None:
        return sx, sy
    s = max(sx, sy) if slice_ else min(sx, sy)
    return s, s


def _decimals(text):
    """ Number of decimal places a number is written with """
    mant = text.strip().lower().split('e')[0]
    return len(mant.split('.')[1]) if '.' in mant else 0


def root_scale(root):
    """ (sx, sy) in mm per user unit of the root <svg> element. See the module docstring. """
    vb = _parse_viewbox(root.get('viewBox'))
    size = {}
    for name in ('width', 'height'):
        text = root.get(name)
        if text is None or not text.strip():
            continue
        val, unit = _parse_length(text, f'{name} of <svg>')
        if unit in UNIT_MM:
            size[name] = (val, unit, _decimals(_LENGTH_RE.match(text).group(1)))
        elif unit == '':
            size[name] = (val, 'mm', None) # unitless: taken as mm
        elif unit != '%':
            raise ValueError(f'SVG: unsupported unit in {name}="{text}" of <svg>')
    physical = any(d is not None for _v, _u, d in size.values())
    if not physical:
        # No physical unit: one user unit is 1 mm, whatever unitless width and height say (as kicoil always read them)
        if vb is not None and any(abs(val - vb[2 if name == 'width' else 3]) > EXACT_UNIT_REL * vb[2 if name == 'width'
                                  else 3] for name, (val, _u, _d) in size.items()):
            warnings.warn(f'SVG width/height ({root.get("width")}, {root.get("height")}) have no unit and differ from '
                          f'the viewBox size ({vb[2]:g} x {vb[3]:g}). One user unit is taken as 1 mm, the drawing is '
                          f'not scaled to width/height. Give width and height a unit (e.g. mm) to scale it.')
        return 1.0, 1.0
    if vb is None:
        dims = ' '.join(f'{size[k][0]:g}' for k in ('width', 'height') if k in size)
        warnings.warn(f'SVG has a width/height with a unit but no viewBox: by the SVG specification its coordinates '
                      f'are CSS px (1 px = 1/96 in = 0.2646 mm). If they are meant in the unit of width and height, add '
                      f'viewBox="0 0 {dims}" to the <svg> element.')
        return UNIT_MM['px'], UNIT_MM['px']
    # Exporters write width and height with fewer digits than the viewBox. When both agree with the viewBox size up
    # to the precision they are written with, and to EXACT_UNIT_REL, one user unit is one unit of width and height,
    # exactly. (Otherwise the scale is width/viewBox width, which differs from that by less than EXACT_UNIT_REL.)
    units = {u for _v, u, _d in size.values()}
    if len(units) == 1 and all(d is not None for _v, _u, d in size.values()):
        unit = units.pop()
        if all(abs(val - vbd) <= 0.5 * 10.0**-dec * (1 + 1e-9) and abs(val - vbd) <= EXACT_UNIT_REL * vbd
               for name, (val, _u, dec) in size.items() for vbd in [vb[2 if name == 'width' else 3]]):
            return UNIT_MM[unit], UNIT_MM[unit]
    w, h = (size[k][0] * UNIT_MM[size[k][1]] if k in size else None for k in ('width', 'height'))
    return _viewbox_scale(vb, w, h, root.get('preserveAspectRatio'))


def _fit_viewbox(vb, w, h, aspect):
    """ Transform that maps a viewBox onto a viewport of size w x h at (0, 0), with preserveAspectRatio aspect """
    sx, sy = _viewbox_scale(vb, w, h, aspect)
    align, _ = _parse_aspect(aspect)
    tx = ty = 0.0
    if align is not None:
        fx = {'xMin': 0.0, 'xMid': 0.5, 'xMax': 1.0}[align[:4]]
        fy = {'YMin': 0.0, 'YMid': 0.5, 'YMax': 1.0}[align[4:]]
        tx, ty = (w - vb[2]*sx) * fx, (h - vb[3]*sy) * fy
    return (sx, 0.0, 0.0, sy, tx - vb[0]*sx, ty - vb[1]*sy)


def _viewport_size(els, what):
    """ (width, height) in user units of a viewport element, each from the first of els that has it """
    size = []
    for k in ('width', 'height'):
        el = next((e for e in els if e.get(k, '').strip()), None)
        if el is None or el.get(k).strip().endswith('%'):
            raise ValueError(f'SVG: {what} with a viewBox needs a width and height (not a percentage)')
        size.append(_user_length(el, k))
    return size


def _viewport_transform(el):
    """ Transform of a nested <svg> element: its x/y and its viewBox (scaled and aligned onto its width/height) """
    x, y = _user_length(el, 'x'), _user_length(el, 'y')
    m = (1.0, 0.0, 0.0, 1.0, x, y)
    vb = _parse_viewbox(el.get('viewBox'))
    if vb is None:
        return m
    w, h = _viewport_size([el], 'nested <svg>')
    return _mul(m, _fit_viewbox(vb, w, h, el.get('preserveAspectRatio')))


_STYLE_PROPS = ('display', 'visibility')
_HIDING = {('display', 'none'), ('visibility', 'hidden'), ('visibility', 'collapse')}
_SIMPLE_SELECTOR = re.compile(r'(\*|[A-Za-z][\w-]*)?((?:[.#][\w-]+)*)$')


def _declarations(text):
    """ {property: value} of the display and visibility declarations of a CSS declaration block """
    out = {}
    for decl in text.split(';'):
        name, sep, value = decl.partition(':')
        name = name.strip().lower()
        if sep and name in _STYLE_PROPS:
            out[name] = value.replace('!important', '').strip().lower()
    return out


def _strip_at_rules(text):
    """ CSS without its at-rules (@media and @supports blocks, @import ...): their rules apply only conditionally """
    out, i = [], 0
    while (j := text.find('@', i)) >= 0:
        out.append(text[i:j])
        k = j
        while k < len(text) and text[k] not in '{;':
            k += 1
        if k < len(text) and text[k] == '{':
            depth = 0
            while k < len(text):
                depth += {'{': 1, '}': -1}.get(text[k], 0)
                k += 1
                if depth == 0:
                    break
        else:
            k += 1
        i = k
    out.append(text[i:])
    return ''.join(out)


class _Styles:
    """ The display and visibility of elements, from presentation attributes, style attributes and the document's
    <style> sheets. Selectors in style sheets: type, .class, #id and their combinations (path.cut, #a.b) and *.
    A sheet that hides elements (display:none, visibility:hidden or collapse) with another selector is a ValueError. """

    def __init__(self, root):
        sheets = [''.join(el.itertext()) for el in root.iter() if _localname(el) == 'style'
                  and el.get('type', 'text/css').strip().lower() in ('', 'text/css')]
        text = _strip_at_rules(re.sub(r'/\*.*?\*/', ' ', ' '.join(sheets), flags=re.S))
        self.rules = []
        for order, (selectors, block) in enumerate(re.findall(r'([^{}]*)\{([^{}]*)\}', text)):
            props = _declarations(block)
            if not props:
                continue
            for sel in selectors.split(','):
                sel = sel.strip()
                mo = _SIMPLE_SELECTOR.match(sel)
                if not sel or not mo:
                    hides = [f'{k}:{v}' for k, v in props.items() if (k, v) in _HIDING]
                    if hides:
                        raise ValueError(f'SVG: the style sheet hides elements with "{sel} {{{"; ".join(hides)}}}", '
                                         f'a selector kicoil does not evaluate (only type, .class and #id). Delete the '
                                         f'hidden elements or the rule.')
                    continue
                tag = mo.group(1) if mo.group(1) not in (None, '*') else None
                parts = re.findall(r'([.#])([\w-]+)', mo.group(2))
                ids = {n for k, n in parts if k == '#'}
                classes = {n for k, n in parts if k == '.'}
                self.rules.append(((len(ids), len(classes), tag is not None), order, tag, ids, classes, props))

    def value(self, el, prop):
        """ Specified value of prop on el (not inherited), or None """
        inline = _declarations(el.get('style', ''))
        if prop in inline:
            return inline[prop]
        best = None
        if self.rules:
            name, eid, classes = _localname(el), el.get('id'), set(el.get('class', '').split())
            for spec, order, tag, ids, cls, props in self.rules:
                if prop in props and (tag is None or tag == name) and ids <= {eid} and cls <= classes \
                        and (best is None or (spec, order) >= best[0]):
                    best = ((spec, order), props[prop])
        if best is not None:
            return best[1]
        v = el.get(prop)
        return v.strip().lower() if v is not None else None


class _Scanner:
    """ Tokenizer for SVG path data """

    def __init__(self, text, what):
        self.text, self.pos, self.what = text, 0, what

    def skip(self):
        self.pos = _SEP_RE.match(self.text, self.pos).end()

    def at_end(self):
        self.pos = len(self.text) - len(self.text[self.pos:].lstrip())
        return self.pos >= len(self.text)

    def command(self):
        """ Next command letter, or None if the next token is a number (implicit repetition) """
        self.at_end()
        c = self.text[self.pos]
        if c.isalpha() and c not in 'eE':
            self.pos += 1
            return c
        return None

    def number_follows(self):
        self.skip()
        return self.pos < len(self.text) and _NUMBER_RE.match(self.text, self.pos) is not None

    def number(self):
        self.skip()
        mo = _NUMBER_RE.match(self.text, self.pos)
        if not mo:
            self.error('expected a number')
        self.pos = mo.end()
        return float(mo.group(0))

    def flag(self):
        self.skip()
        if self.pos < len(self.text) and self.text[self.pos] in '01':
            self.pos += 1
            return self.text[self.pos-1] == '1'
        self.error('expected an arc flag (0 or 1)')

    def error(self, msg):
        ctx = self.text[max(0, self.pos-20):self.pos+20]
        raise ValueError(f'SVG: invalid path data in {self.what} at character {self.pos} ({msg}): ...{ctx}...')


def parse_path(d, what='<path>'):
    """ Subpaths of SVG path data as a list of (start, segments, closed). Segments are ('L', p), ('C', c1, c2, p),
    ('Q', c, p) or ('A', rx, ry, phi, large_arc, sweep, p), each starting where the previous one ends. """
    sc = _Scanner(d, what)
    subpaths = []
    cur = (0.0, 0.0)
    start = None
    segs = None
    last_cmd = None
    last_ctrl = None # second control point of the last C/S, or control point of the last Q/T

    def begin(p):
        nonlocal segs, start
        segs = []
        start = p
        subpaths.append([start, segs, False])

    if sc.at_end():
        return []
    cmd = sc.command()
    if cmd not in ('M', 'm'):
        sc.error('path data has to start with a moveto (M or m)')
    while True:
        if cmd is None:
            break
        rel = cmd.islower()
        C = cmd.upper()

        def pt():
            x = sc.number()
            y = sc.number()
            return (cur[0] + x, cur[1] + y) if rel else (x, y)

        first = True
        while True:
            if C == 'Z':
                if segs is not None:
                    subpaths[-1][2] = True
                    cur = start
                    segs = None # a drawing command after Z starts a new subpath at the same start point
                last_ctrl, last_cmd = None, 'Z'
                break
            if not first and not sc.number_follows():
                break
            if C == 'M':
                p = pt()
                if first:
                    begin(p)
                    cur = p
                    last_ctrl, last_cmd = None, 'M'
                    C = 'L' # further coordinate pairs are implicit linetos
                    first = False
                    continue
            if segs is None:
                begin(cur)
            if C == 'L':
                p = pt()
                segs.append(('L', p))
            elif C == 'H':
                x = sc.number()
                p = (cur[0] + x if rel else x, cur[1])
                segs.append(('L', p))
            elif C == 'V':
                y = sc.number()
                p = (cur[0], cur[1] + y if rel else y)
                segs.append(('L', p))
            elif C in 'CS':
                if C == 'C':
                    c1 = pt()
                else:
                    c1 = (2*cur[0] - last_ctrl[0], 2*cur[1] - last_ctrl[1]) if last_cmd in ('C', 'S') else cur
                c2 = pt()
                p = pt()
                segs.append(('C', c1, c2, p))
                last_ctrl = c2
            elif C in 'QT':
                if C == 'Q':
                    c = pt()
                else:
                    c = (2*cur[0] - last_ctrl[0], 2*cur[1] - last_ctrl[1]) if last_cmd in ('Q', 'T') else cur
                p = pt()
                segs.append(('Q', c, p))
                last_ctrl = c
            elif C == 'A':
                rx, ry, phi = sc.number(), sc.number(), sc.number()
                large, sweep = sc.flag(), sc.flag()
                p = pt()
                segs.append(('A', rx, ry, phi, large, sweep, p))
            else:
                sc.error(f'unknown command "{cmd}"')
            cur = p
            last_cmd = C
            first = False
        if sc.at_end():
            break
        cmd = sc.command()
        if cmd is None:
            sc.error('expected a command')
    return [tuple(s) for s in subpaths]


def _wang_segments(ctrl, tol):
    """ Number of uniform parameter steps that keep a Bezier curve within tol of its polyline (Wang's formula) """
    n = len(ctrl) - 1
    dd = max(math.hypot(ctrl[i][0] - 2*ctrl[i+1][0] + ctrl[i+2][0], ctrl[i][1] - 2*ctrl[i+1][1] + ctrl[i+2][1])
             for i in range(n - 1))
    k = math.ceil(math.sqrt(n*(n-1)/8 * dd / tol)) if dd > 0 else 1
    return max(1, min(k, MAX_CURVE_SEGMENTS))


def _arc_points(p0, seg, m, tol):
    """ Points (transformed by m) of an SVG elliptical arc from p0, without p0. Implementation notes of the SVG
    specification (endpoint to center parameterization), sampled in angle so that the chords stay within tol of the
    transformed ellipse. """
    _, rx, ry, phi, large, sweep, p1 = seg
    x1, y1 = p0
    x2, y2 = p1
    if (x1, y1) == (x2, y2):
        return []
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [_apply(m, p1)]
    ph = math.radians(phi % 360)
    cp, sp = math.cos(ph), math.sin(ph)
    dx, dy = (x1 - x2)/2, (y1 - y2)/2
    x1p, y1p = cp*dx + sp*dy, -sp*dx + cp*dy
    lam = (x1p/rx)**2 + (y1p/ry)**2
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx*s, ry*s
    num = rx*rx*ry*ry - rx*rx*y1p*y1p - ry*ry*x1p*x1p
    den = rx*rx*y1p*y1p + ry*ry*x1p*x1p
    coef = math.sqrt(max(0.0, num/den)) if den > 0 else 0.0
    if large == sweep:
        coef = -coef
    cxp, cyp = coef*rx*y1p/ry, -coef*ry*x1p/rx
    cx, cy = cp*cxp - sp*cyp + (x1 + x2)/2, sp*cxp + cp*cyp + (y1 + y2)/2

    def ang(ux, uy, vx, vy):
        return math.atan2(ux*vy - uy*vx, ux*vx + uy*vy)
    th1 = ang(1, 0, (x1p - cxp)/rx, (y1p - cyp)/ry)
    dth = ang((x1p - cxp)/rx, (y1p - cyp)/ry, (-x1p - cxp)/rx, (-y1p - cyp)/ry)
    if not sweep and dth > 0:
        dth -= 2*math.pi
    elif sweep and dth < 0:
        dth += 2*math.pi
    # Largest semi-axis of the transformed ellipse: largest singular value of M * R(phi) * diag(rx, ry)
    a, b, c, d = m[:4]
    u = (rx*(a*cp + c*sp), rx*(b*cp + d*sp))
    v = (ry*(-a*sp + c*cp), ry*(-b*sp + d*cp))
    t1, t2, t3 = u[0]**2 + u[1]**2, v[0]**2 + v[1]**2, u[0]*v[0] + u[1]*v[1]
    rmax = math.sqrt((t1 + t2)/2 + math.sqrt(((t1 - t2)/2)**2 + t3**2))
    step = 2*math.acos(1 - tol/rmax) if tol < rmax else math.pi/2
    n = max(1, min(MAX_CURVE_SEGMENTS, math.ceil(abs(dth) / min(step, math.pi/2))))
    out = []
    for i in range(1, n):
        t = th1 + dth*i/n
        ex, ey = rx*math.cos(t), ry*math.sin(t)
        out.append(_apply(m, (cp*ex - sp*ey + cx, sp*ex + cp*ey + cy)))
    out.append(_apply(m, p1))
    return out


def _segment_distance(p, a, b):
    """ Distance of point p from the segment ab """
    dx, dy = b[0] - a[0], b[1] - a[1]
    ll = dx*dx + dy*dy
    t = 0.0 if ll == 0 else min(1.0, max(0.0, ((p[0] - a[0])*dx + (p[1] - a[1])*dy) / ll))
    return math.hypot(p[0] - a[0] - t*dx, p[1] - a[1] - t*dy)


def flatten(start, segs, m, tol):
    """ Polyline (transformed by m) of a subpath, within tol of its curves """
    pts = [_apply(m, start)]
    cur = start
    for seg in segs:
        kind = seg[0]
        if kind == 'L':
            pts.append(_apply(m, seg[1]))
        elif kind in ('C', 'Q'):
            ctrl = [_apply(m, p) for p in (cur,) + seg[1:]]
            if all(_segment_distance(c, ctrl[0], ctrl[-1]) <= tol for c in ctrl[1:-1]):
                # (Nearly) straight: the curve lies in the convex hull of its control points, so within tol of its
                # chord. Wang's bound would also count the uneven speed along the line (e.g. a line written as
                # "C x0 y0 x3 y3 x3 y3") and give it many collinear vertices.
                pts.append(ctrl[-1])
                cur = seg[-1]
                continue
            n = _wang_segments(ctrl, tol)
            if len(ctrl) == 4:
                (x0, y0), (x1, y1), (x2, y2), (x3, y3) = ctrl
                for i in range(1, n):
                    t = i/n
                    s = 1 - t
                    pts.append((s*s*s*x0 + 3*s*s*t*x1 + 3*s*t*t*x2 + t*t*t*x3,
                                s*s*s*y0 + 3*s*s*t*y1 + 3*s*t*t*y2 + t*t*t*y3))
            else:
                (x0, y0), (x1, y1), (x2, y2) = ctrl
                for i in range(1, n):
                    t = i/n
                    s = 1 - t
                    pts.append((s*s*x0 + 2*s*t*x1 + t*t*x2, s*s*y0 + 2*s*t*y1 + t*t*y2))
            pts.append(ctrl[-1])
        elif kind == 'A':
            pts += _arc_points(cur, seg, m, tol)
        cur = seg[-1]
    return pts


def _points_attr(el):
    vals = [float(v) for v in _NUMBER_RE.findall(el.get('points', ''))]
    if _NUMBER_RE.sub('', el.get('points', '')).strip(' \t\r\n,'):
        raise ValueError(f'SVG: cannot parse points of <{_localname(el)}>')
    if len(vals) % 2:
        vals = vals[:-1] # SVG: an odd number of coordinates is an error, render up to the last pair
    return [(vals[i], vals[i+1]) for i in range(0, len(vals), 2)]


def _ellipse_subpath(cx, cy, rx, ry):
    """ An ellipse as a closed subpath of two arcs """
    return ((cx + rx, cy), [('A', rx, ry, 0.0, False, True, (cx - rx, cy)),
                            ('A', rx, ry, 0.0, False, True, (cx + rx, cy))], True)


def element_subpaths(el):
    """ Subpaths (as parse_path) of a shape element, in its own user units """
    name = _localname(el)
    what = f'<{name}' + (f' id="{el.get("id")}"' if el.get('id') else '') + '>'
    if name == 'path':
        return parse_path(el.get('d', ''), what)
    if name in ('polygon', 'polyline'):
        pts = _points_attr(el)
        if len(pts) < 2:
            return []
        return [(pts[0], [('L', p) for p in pts[1:]], name == 'polygon')]
    if name == 'rect':
        x, y = _user_length(el, 'x'), _user_length(el, 'y')
        w, h = _user_length(el, 'width'), _user_length(el, 'height')
        if w <= 0 or h <= 0:
            return []
        rx = _user_length(el, 'rx', None) if el.get('rx', 'auto').strip() != 'auto' else None
        ry = _user_length(el, 'ry', None) if el.get('ry', 'auto').strip() != 'auto' else None
        if rx is None:
            rx = ry
        if ry is None:
            ry = rx
        rx, ry = min(max(rx or 0.0, 0.0), w/2), min(max(ry or 0.0, 0.0), h/2)
        if rx == 0 or ry == 0:
            return [((x, y), [('L', (x+w, y)), ('L', (x+w, y+h)), ('L', (x, y+h))], True)]
        arc = lambda p: ('A', rx, ry, 0.0, False, True, p)
        segs = [('L', (x+w-rx, y)), arc((x+w, y+ry)), ('L', (x+w, y+h-ry)), arc((x+w-rx, y+h)),
                ('L', (x+rx, y+h)), arc((x, y+h-ry)), ('L', (x, y+ry)), arc((x+rx, y))]
        return [((x+rx, y), segs, True)]
    if name == 'circle':
        r = _user_length(el, 'r')
        if r <= 0:
            return []
        return [_ellipse_subpath(_user_length(el, 'cx'), _user_length(el, 'cy'), r, r)]
    if name == 'ellipse':
        rx, ry = _user_length(el, 'rx', None), _user_length(el, 'ry', None)
        rx = ry if rx is None else rx
        ry = rx if ry is None else ry
        if not rx or not ry or rx <= 0 or ry <= 0:
            return []
        return [_ellipse_subpath(_user_length(el, 'cx'), _user_length(el, 'cy'), rx, ry)]
    return []


def _href(el):
    return el.get('href') or el.get('{http://www.w3.org/1999/xlink}href')


def collect_contours(root, m_root, tol):
    """ All subpaths of all shapes of the document as (points in mm, closed, description) """
    ids = {el.get('id'): el for el in root.iter() if isinstance(el.tag, str) and el.get('id')}
    styles = _Styles(root)
    out = []

    def walk(el, m, stack, visible=True):
        name = _localname(el)
        if name is None or name in SKIP_ELEMENTS or styles.value(el, 'display') == 'none':
            return
        vis = styles.value(el, 'visibility')
        if vis in ('visible', 'hidden', 'collapse'): # inherited, children can make themselves visible again
            visible = vis == 'visible'
        m = _mul(m, parse_transform(el.get('transform')))
        if name == 'svg' and el is not root:
            m = _mul(m, _viewport_transform(el))
        if name == 'use':
            ref = _href(el)
            target = ids.get(ref[1:]) if ref and ref.startswith('#') else None
            if target is None or target in stack:
                return
            m = _mul(m, (1.0, 0.0, 0.0, 1.0, _user_length(el, 'x'), _user_length(el, 'y')))
            if _localname(target) == 'symbol':
                if styles.value(target, 'display') == 'none':
                    return
                vis = styles.value(target, 'visibility')
                if vis in ('visible', 'hidden', 'collapse'):
                    visible = vis == 'visible'
                vb = _parse_viewbox(target.get('viewBox'))
                if vb is not None:
                    what = f'<use> of <symbol id="{target.get("id")}">'
                    w, h = _viewport_size([el, target], what)
                    m = _mul(m, _fit_viewbox(vb, w, h, target.get('preserveAspectRatio')))
                for child in target:
                    walk(child, m, stack + (target,), visible)
            else:
                walk(target, m, stack + (target,), visible)
            return
        if name in ('path', 'polygon', 'polyline', 'rect', 'circle', 'ellipse'):
            if not visible:
                return
            what = f'<{name}' + (f' id="{el.get("id")}"' if el.get('id') else '') + '>'
            subs = element_subpaths(el)
            for i, (start, segs, closed) in enumerate(subs):
                pts = flatten(start, segs, m, tol)
                out.append((pts, closed, what + (f' (subpath {i+1} of {len(subs)})' if len(subs) > 1 else '')))
            return
        for child in el:
            walk(child, m, stack, visible)

    walk(root, m_root, ())
    return out


def _dist(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _close(pts, closed, tol):
    """ Closed point list (without a repeated start point) of a contour, or None if it is open """
    if len(pts) > 1 and _dist(pts[-1], pts[0]) <= tol:
        return pts[:-1]
    return pts if closed else None


def join_open_contours(open_contours, tol):
    """ Join open polylines whose end points meet (within tol) into longer ones, and close chains that return to their
    start. Returns (closed contours, remaining open contours), each as (points, description). End points where more
    than two polylines meet are not joined. """
    items = [list(p) for p, _w in open_contours]
    whats = [w for _p, w in open_contours]
    ends = [(i, e) for i in range(len(items)) for e in (0, 1)]

    def endpoint(i, e):
        return items[i][0] if e == 0 else items[i][-1]
    # Group end points that coincide (within tol), on a grid of cell size tol
    cells = {}
    for i, e in ends:
        x, y = endpoint(i, e)
        cells.setdefault((math.floor(x/tol), math.floor(y/tol)), []).append((i, e))

    def partners(i, e):
        x, y = endpoint(i, e)
        gx, gy = math.floor(x/tol), math.floor(y/tol)
        out = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j, f in cells.get((gx+dx, gy+dy), ()):
                    if (j, f) != (i, e) and _dist(endpoint(j, f), (x, y)) <= tol:
                        out.append((j, f))
        return out
    link = {}
    for i, e in ends:
        ps = partners(i, e)
        if len(ps) == 1 and len(partners(*ps[0])) == 1:
            link[(i, e)] = ps[0]
    used = [False]*len(items)
    closed, still_open = [], []
    for i in range(len(items)):
        if used[i]:
            continue
        # Walk back to the start of the chain (or around a loop)
        j, e = i, 0
        while (j, e) in link:
            k, f = link[(j, e)]
            j, e = k, 1 - f
            if j == i:
                break
        is_loop = (j == i and (i, 0) in link)
        start = (i, 0) if is_loop else (j, e)
        chain, names = [], []
        j, e = start
        while True:
            used[j] = True
            seq = items[j] if e == 0 else items[j][::-1]
            chain += seq if not chain else seq[1:]
            names.append(whats[j])
            nxt = link.get((j, 1 - e))
            if nxt is None or used[nxt[0]]:
                break
            j, e = nxt[0], nxt[1]
        what = names[0] if len(names) == 1 else f'{len(names)} joined paths ({names[0]}, ...)'
        if is_loop:
            closed.append((chain[:-1], what))
        else:
            still_open.append((chain, what))
    return closed, still_open


def _bbox_area(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def signed_area(pts):
    n = len(pts)
    if n < 3:
        return 0.0
    x0, y0 = pts[0]
    a = 0.0
    for i in range(1, n - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i+1]
        a += (x1 - x0)*(y2 - y0) - (x2 - x0)*(y1 - y0)
    return a / 2


def _point_in_polygon(p, poly):
    x, y = p
    inside = False
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i+1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1)*(x2 - x1)/(y2 - y1):
            inside = not inside
    return inside


def _orient(p, q, r):
    return (q[0]-p[0])*(r[1]-p[1]) - (q[1]-p[1])*(r[0]-p[0])


def _on_segment(p, q, r):
    """ r (collinear with pq) lies on segment pq """
    return min(p[0], q[0]) <= r[0] <= max(p[0], q[0]) and min(p[1], q[1]) <= r[1] <= max(p[1], q[1])


def _segments_meet(a, b, c, d):
    o1, o2, o3, o4 = _orient(a, b, c), _orient(a, b, d), _orient(c, d, a), _orient(c, d, b)
    if ((o1 > 0 and o2 < 0) or (o1 < 0 and o2 > 0)) and ((o3 > 0 and o4 < 0) or (o3 < 0 and o4 > 0)):
        return True
    return ((o1 == 0 and _on_segment(a, b, c)) or (o2 == 0 and _on_segment(a, b, d)) or
            (o3 == 0 and _on_segment(c, d, a)) or (o4 == 0 and _on_segment(c, d, b)))


def find_self_intersection(pts):
    """ A point where the closed polygon touches or crosses itself, or None. Consecutive duplicate points are ignored.
    Segments are bucketed on a grid, so this is about linear for outlines without long edges next to many short ones. """
    p = [q for i, q in enumerate(pts) if q != pts[i-1]]
    n = len(p)
    if n < 3:
        return None
    xs, ys = [q[0] for q in p], [q[1] for q in p]
    size = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    cell = size / max(1.0, math.sqrt(n))
    x0, y0 = min(xs), min(ys)
    grid = {}
    for i in range(n):
        a, b = p[i], p[(i+1) % n]
        for gx in range(math.floor((min(a[0], b[0]) - x0)/cell), math.floor((max(a[0], b[0]) - x0)/cell) + 1):
            for gy in range(math.floor((min(a[1], b[1]) - y0)/cell), math.floor((max(a[1], b[1]) - y0)/cell) + 1):
                grid.setdefault((gx, gy), []).append(i)
    checked = set()
    for segs in grid.values():
        for k, i in enumerate(segs):
            for j in segs[k+1:]:
                i1, j1 = min(i, j), max(i, j)
                if (i1, j1) in checked:
                    continue
                checked.add((i1, j1))
                a, b, c, d = p[i1], p[(i1+1) % n], p[j1], p[(j1+1) % n]
                if j1 == i1 + 1 or (i1 == 0 and j1 == n - 1):
                    # Neighbors share a vertex; they only meet elsewhere if they fold back onto each other
                    s, t, u = (a, b, d) if j1 == i1 + 1 else (c, a, b) # the shared vertex is t
                    if _orient(s, t, u) == 0 and ((t[0]-s[0])*(u[0]-t[0]) + (t[1]-s[1])*(u[1]-t[1])) < 0:
                        return t
                    continue
                if _segments_meet(a, b, c, d):
                    return _intersection_point(a, b, c, d)
    return None


def _intersection_point(a, b, c, d):
    den = (b[0]-a[0])*(d[1]-c[1]) - (b[1]-a[1])*(d[0]-c[0])
    if den == 0:
        for q in (c, d, a, b):
            if _orient(a, b, q) == 0 and _on_segment(a, b, q) and _on_segment(c, d, q):
                return q
        return a
    t = ((c[0]-a[0])*(d[1]-c[1]) - (c[1]-a[1])*(d[0]-c[0])) / den
    return (a[0] + t*(b[0]-a[0]), a[1] + t*(b[1]-a[1]))


def read_outline(filename, tolerance=DEFAULT_TOLERANCE):
    """ The outline of an SVG file as a list of (x, y) points in mm. See the module docstring. """
    parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_comments=True, huge_tree=False)
    try:
        tree = etree.parse(str(filename), parser)
    except etree.XMLSyntaxError as e:
        raise ValueError(f'SVG: {filename} is not a valid XML file: {e}') from e
    root = tree.getroot()
    if _localname(root) != 'svg':
        raise ValueError(f'SVG: the root element of {filename} is <{_localname(root)}>, not <svg>')
    if not tolerance > 0:
        raise ValueError('SVG: the curve tolerance has to be positive')
    sx, sy = root_scale(root)
    contours = collect_contours(root, (sx, 0.0, 0.0, sy, 0.0, 0.0), tolerance)

    closed, open_ = [], []
    for pts, is_closed, what in contours:
        c = _close(pts, is_closed, JOIN_TOLERANCE)
        if c is not None:
            closed.append((c, what))
        elif len(pts) > 1:
            open_.append((pts, what))
    joined, open_ = join_open_contours(open_, JOIN_TOLERANCE)
    closed += joined
    # By area; contours without (e.g. a figure eight with lobes of equal area) by their bounding box after all others,
    # so that a file whose only contour is like that is rejected below as self-intersecting
    candidates = [(abs(signed_area(c)), c, w) for c, w in closed if len(set(c)) >= 3]
    open_cand = [(abs(signed_area(c)), c, w) for c, w in open_ if len(c) >= 3]
    if not candidates:
        if open_cand:
            area, pts, what = max(open_cand, key=lambda t: t[0])
            raise ValueError(f'SVG: {filename} has no closed outline. {what} is open: it ends at '
                             f'({pts[-1][0]:.3f}, {pts[-1][1]:.3f}), {_dist(pts[0], pts[-1]):.3f} mm from its start at '
                             f'({pts[0][0]:.3f}, {pts[0][1]:.3f}). Close it (Z).')
        raise ValueError(f'SVG: {filename} contains no outline (no closed path, polygon, rect, circle or ellipse)')
    area, outline, what = max(candidates, key=lambda t: (t[0], _bbox_area(t[1])))
    if open_cand and max(open_cand, key=lambda t: t[0])[0] > area:
        _a, pts, owhat = max(open_cand, key=lambda t: t[0])
        raise ValueError(f'SVG: the largest contour of {filename}, {owhat}, is open: it ends at '
                         f'({pts[-1][0]:.3f}, {pts[-1][1]:.3f}), {_dist(pts[0], pts[-1]):.3f} mm from its start. '
                         f'Close it (Z) or remove it.')
    x = find_self_intersection(outline)
    if x is not None:
        raise ValueError(f'SVG: the outline of {filename} ({what}) touches or crosses itself at '
                         f'({x[0]:.3f}, {x[1]:.3f}) mm. It has to be a simple polygon.')
    others = [c for c in closed if c[0] is not outline]
    if others or open_:
        holes = sum(1 for c, _w in others if c and _point_in_polygon(c[0], outline))
        outside = len(others) - holes
        parts = [f'{holes} hole(s) inside it'] * bool(holes) + [f'{outside} other closed contour(s)'] * bool(outside) + \
                [f'{len(open_)} open path(s)'] * bool(open_)
        bounds = f'({min(p[0] for p in outline):.2f}, {min(p[1] for p in outline):.2f}) to ' \
                 f'({max(p[0] for p in outline):.2f}, {max(p[1] for p in outline):.2f}) mm'
        warnings.warn(f'SVG: using {what} as the outline ({len(outline)} points, {area:.2f} mm², {bounds}), ignoring '
                      + ', '.join(parts) + '. The coil covers the whole outline.'
                      + (' If this contour is a frame or page border around the intended outline, delete it from the '
                         'file.' if holes else ''))
    return outline
