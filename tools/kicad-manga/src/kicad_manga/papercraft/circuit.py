"""The schematic, cut from paper.

The manga style's Circuit does the bookkeeping (nets and their colours, the occupancy grids, sheets, tables,
images); this subclass draws the parts the paper craft way:

- symbol bodies are pastel cardstock with a soft cast shadow, and their lines thin strips of plum paper;
- wires are washi tape in the net's colour, printed with dots (signals), stitches (supplies) or pinstripes
  (grounds); buses are wide striped tape;
- junctions are brass paper fasteners, no-connects little crosses of tape;
- net labels are paper tags with a punched hole, big text is a paper banner taped down, long notes are torn
  notepaper;
- resistors are paper bars with their colour code, capacitors two plates of card, inductors quilled coils.
"""

import math
import random
import re

from ..circuit import Circuit, arc_path, bezier_d, circle_d, poly_d, prop_value, ref_prefix, rounded_poly, \
    rounded_rect, shape_points, unit_graphics, character_kind
from ..kicad import at, fill, font, hidden, justify, quarter_turned, rotation, stroke, xy
from ..palette import NetColors
from ..svg import Markup, group, num as f2, path, tag
from ..text import plain, text_extent
from ..util import parse_si
from . import paper as P
from .text import ptext

TAPE_W = .95        # washi tape width for wires, mm
BUS_W = 1.9
STRIP = .3          # symbol lines as paper strips
PIN_W = .24


def text_style(bold, italic, col):
    style = []
    if bold:
        style.append('font-weight:800')
    if italic:
        style.append('font-style:italic')
    if col:
        style.append(f'fill:{col}')
    return ';'.join(style)


def tape_pattern(name):
    """Which print a net's tape gets."""
    if not name:
        return 'plain'
    if name.upper().startswith(('GND', 'VSS', 'AGND', 'DGND', 'PGND')):
        return 'pinstripe'
    if NetColors.is_supply(name):
        return 'stitch'
    return 'dots'


# Resistor colour code, in paper colours
BANDS = ['#4b3a5a', '#a0714f', '#e8606a', '#f39a4c', '#f5d34f', '#73c08a', '#6aa6e0', '#b08be0', '#a9a3b0',
         '#fffdf8']
GOLD = '#d9b04a'


def colour_code(value):
    """Band colours for a resistor value: two digits and a multiplier, or one black band for 0 ohm."""
    v = parse_si(value or '')
    if v is None:
        return []
    if v < .01:
        return [BANDS[0]]
    e = math.floor(math.log10(v)) - 1
    digits = round(v / 10 ** e)
    if digits >= 100:
        digits, e = digits // 10, e + 1
    a, b = divmod(digits, 10)
    mult = BANDS[e] if 0 <= e <= 9 else GOLD
    return [BANDS[a], BANDS[b], mult]


class PaperCircuit(Circuit):
    def __init__(self, sch, characters=True, seed=7):
        super().__init__(sch, characters=characters, seed=seed)
        self.prng = random.Random(seed + 101)

    # -- wires: washi tape ---------------------------------------------------
    def render_wires(self):
        by_net = {}
        for w, (a, b), root in zip(self.wire_items, self.wires, self.net_of):
            by_net.setdefault(root, []).append((w, a, b))
            self.mark(a[0], a[1], b[0], b[1], pad=0.8, fine_pad=0.6)
        hw = TAPE_W / 2
        for root, items in by_net.items():
            name = self.net_name.get(root, '')
            col = P.shade(self.net_color(root), -.06, .05)
            d = ''.join(f'M{f2(a[0])} {f2(a[1])}L{f2(b[0])} {f2(b[1])}' for _, a, b in items)
            kind = tape_pattern(name)
            parts = [P.shadow_stroke(d, TAPE_W, .22, .3, .2, cap='square'),
                     path(d, cls='tape', stroke=col, stroke_width=TAPE_W)]
            if kind == 'dots':
                parts.append(path(d, cls='tape-dots', stroke_width=hw * .6, stroke_dasharray=f'0 {f2(hw * 1.7)}'))
            elif kind == 'stitch':
                parts.append(path(d, cls='tape-stitch', stroke_width=hw * .3,
                                  stroke_dasharray=f'{f2(hw * .9)} {f2(hw * .7)}'))
            elif kind == 'pinstripe':
                o = hw * .55
                dd = ''
                for _, a, b in items:
                    L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1
                    nx, ny = -(b[1] - a[1]) / L * o, (b[0] - a[0]) / L * o
                    for s in (-1, 1):
                        dd += f'M{f2(a[0] + s * nx)} {f2(a[1] + s * ny)}L{f2(b[0] + s * nx)} {f2(b[1] + s * ny)}'
                parts.append(path(dd, cls='tape-stripe', stroke_width=hw * .16))
            for w, a, b in items:          # dashed wires keep their dashes, as gaps in the tape print
                _, dkind, scol = stroke(w)
                if scol:
                    parts.append(path(f'M{f2(a[0])} {f2(a[1])}L{f2(b[0])} {f2(b[1])}', cls='tape', stroke=scol,
                                      stroke_width=TAPE_W * .5))
            self.add('wires', group(parts, cls='net', data_net=name))
        self.render_buses()

    def render_buses(self):
        buses = [[xy(p) for p in b.points] for b in self.sch.buses]
        segs = [(a, b) for p in buses for a, b in zip(p, p[1:])]
        for p in buses:
            d = poly_d(p)
            hw = BUS_W / 2
            stripes = ''
            for a, b in zip(p, p[1:]):
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                if L < .1:
                    continue
                ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
                nx, ny = -uy, ux
                t = hw
                while t < L - hw:
                    cx, cy = a[0] + ux * t, a[1] + uy * t
                    stripes += (f'M{f2(cx - nx * hw * .85 - ux * hw * .45)} {f2(cy - ny * hw * .85 - uy * hw * .45)}'
                                f'l{f2(nx * hw * 1.7 + ux * hw * .9)} {f2(ny * hw * 1.7 + uy * hw * .9)}')
                    t += hw * 1.25
            self.add('wires', group([P.shadow_stroke(d, BUS_W, .3, .4, .2, cap='square'),
                                     path(d, cls='tape', stroke='#c9b3f2', stroke_width=BUS_W),
                                     path(stripes, cls='tape-bus')], data_kind='bus'))
            for a, c in zip(p, p[1:]):
                self.mark(a[0], a[1], c[0], c[1], pad=1.4, fine_pad=1.2)
        for be in self.sch.bus_entries:
            (x, y), (sx, sy) = at(be), xy(be.size)
            col = P.shade(self.color_at((x + sx, y + sy)), -.06)
            d = f'M{f2(x)} {f2(y)}l{f2(sx)} {f2(sy)}'
            self.add('wires', group([P.shadow_stroke(d, TAPE_W * .8, .22, .3, .2),
                                     path(d, cls='tape', stroke=col, stroke_width=TAPE_W * .8)],
                                    data_kind='bus_entry'))
            self.mark(x, y, x + sx, y + sy, pad=1)

    def render_junctions(self):
        for j in self.sch.junctions:
            x, y = at(j)
            r = max(.45, min(.7, (j.diameter / 2) if j.diameter else .55))
            self.add('junctions', group(P.brad(x, y, r), data_kind='junction'))
        for n in self.sch.no_connects:
            x, y = at(n)
            parts = []
            for ang in (45, -45):
                a = math.radians(ang)
                ux, uy = math.cos(a) * .8, math.sin(a) * .8
                d = f'M{f2(x - ux)} {f2(y - uy)}L{f2(x + ux)} {f2(y + uy)}'
                parts += [P.shadow_stroke(d, .5, .15, .2, .25, cap='butt'),
                          path(d, stroke='#f48aa6', stroke_width=.5, fill='none', stroke_opacity=.9)]
            self.add('junctions', group(parts, data_kind='no_connect'))
            self.mark(x - 1, y - 1, x + 1, y + 1)

    # -- labels: paper tags ------------------------------------------------------
    def net_label(self, lab, kind):
        x, y = at(lab)
        ang = round(rotation(lab)) % 360
        h, _ = justify(lab)
        size, bold, italic, tcol = font(lab)
        name = lab.text
        col = self.color_at((x, y), name)
        vertical = ang in (90, 270)
        sign = 1 if h != 'right' else -1
        if h == 'center':
            sign = 1 if ang in (0, 90) else -1
            h = 'left' if sign > 0 else 'right'
        style = text_style(bold, italic, tcol)
        ext_w, ext_h = text_extent(name, size, 'pc-lbl')
        rng = random.Random(f'{name}{x}{y}')
        if kind == 'label':
            off = .8
            tx, ty = (x - off, y) if vertical else (x, y - off)
            bg = lambda bx, by, bw, bh: self.tag_shape(bx, by, bw, bh, sign, col, rng, hole=True)
            parts = [ptext(tx, ty, name, size, 90 if vertical else 0, h, 'bottom', 'pc-lbl', bg=bg, style=style)]
            dx, dy = (0, -sign * ext_w) if vertical else (sign * ext_w, 0)
            self.mark(x, y, x + dx - (ext_h + off if vertical else 0), y + dy - (0 if vertical else ext_h + off),
                      pad=0.6)
        else:
            shape = str(lab.shape or 'passive')
            off = size * 1.15
            dirx, diry = (0, -sign) if vertical else (sign, 0)
            tx, ty = x + dirx * off, y + diry * off
            bg = lambda bx, by, bw, bh: self.flag_shape(bx, by, bw, bh, sign, off, shape, col, kind)
            parts = [ptext(tx, ty, name, size, 90 if vertical else 0, h, 'center', 'pc-lbl', bg=bg, style=style)]
            L = off + ext_w + 1.5
            if vertical:
                self.mark(x - ext_h, y, x + ext_h, y - sign * L, pad=0.6)
            else:
                self.mark(x, y - ext_h, x + sign * L, y + ext_h, pad=0.6)
            for prop in lab.properties:
                if not hidden(prop) and prop.value:
                    px, py = at(prop)
                    hj, vj = justify(prop)
                    parts.append(ptext(px, py, prop.value.replace('${INTERSHEET_REFS}', '[…]'), font(prop)[0],
                                       rotation(prop), hj, vj, 'pc-hand'))
        self.add('labels', group(parts, data_kind=kind, data_net=name))

    @staticmethod
    def tag_shape(x, y, w, h, sign, col, rng, hole=True):
        """A paper luggage tag behind a label's text box, its clipped end (with the punched hole) at the end
        the label connects to."""
        hh = h * .82
        y0, y1 = y + h * .12 - .12, y + h * .12 + hh + .12
        ym = (y0 + y1) / 2
        cut = (y1 - y0) * .42
        if sign > 0:
            xa, xb = x - .5 - cut * .9, x + w + .5
            pts = [(xa, ym - cut * .55), (xa + cut, y0), (xb, y0), (xb, y1), (xa + cut, y1), (xa, ym + cut * .55)]
            hx = xa + cut * .62
        else:
            xa, xb = x + w + .5 + cut * .9, x - .5
            pts = [(xa, ym - cut * .55), (xa - cut, y0), (xb, y0), (xb, y1), (xa - cut, y1), (xa, ym + cut * .55)]
            hx = xa - cut * .62
        d = rounded_poly(pts, .25)
        tilt = rng.uniform(-1.2, 1.2)
        out = P.piece(d, col, edge=P.shade(col, -.2, -.1), sh=(.2, .26), edge_w=.08)
        if hole:
            out.append(tag('circle', cx=hx, cy=ym, r=min(.22, hh * .16), fill=P.CARD, stroke=P.shade(col, -.25),
                           stroke_width=.06))
        return group(out, transform=f'rotate({f2(tilt)} {f2(x)} {f2(ym)})')

    @staticmethod
    def flag_shape(x, y, w, h, sign, off, shape, col, kind):
        """A paper pennant for global and hierarchical labels: pointed where the signal flows."""
        y0, y1 = y + h * .08 - .3, y + h * .92 + .3
        ym, dd = (y0 + y1) / 2, (y1 - y0) / 2
        xa = -sign * off
        far = (x + w if sign > 0 else x) + sign * .6
        pa = shape in ('input', 'bidirectional', 'tri_state')
        pf = shape in ('output', 'bidirectional', 'tri_state')
        if pf:
            far += sign * dd
        top = [(xa, ym), (xa + sign * dd, y0)] if pa else [(xa, y1), (xa, y0)]
        right = [(far - sign * dd, y0), (far, ym), (far - sign * dd, y1)] if pf else \
            [(far, y0), (far - sign * dd * .6, ym), (far, y1)]
        bottom = [(xa + sign * dd, y1)] if pa else []
        d = rounded_poly(top + right + bottom, .3)
        fillc = col if kind == 'global_label' else P.shade(col, .04)
        return group(P.piece(d, fillc, edge=P.shade(col, -.22, -.1), sh=(.22, .3), edge_w=.1))

    # -- free text ---------------------------------------------------------------
    def render_texts(self):
        for t in self.sch.texts:
            s = t.text
            x, y = at(t)
            ang = rotation(t)
            size, bold, italic, col = font(t)
            h, v = justify(t)
            rng = random.Random(f'{s}{x}{y}')
            bg = None
            if size >= 2.4:
                cls = 'pc-title'
                colour = P.PAPERS[sum(map(ord, s)) % len(P.PAPERS)]
                bg = lambda bx, by, bw, bh, c=colour, r=rng: self.banner(bx, by, bw, bh, c, r)
            elif size >= 1.8:
                cls = 'pc-caption'
            elif len(plain(s)) >= 14:
                cls = 'pc-hand'
                bg = lambda bx, by, bw, bh, r=rng: self.note_paper(bx, by, bw, bh, r)
            else:
                cls = 'pc-hand'
            style = text_style(False, italic, col if cls != 'pc-title' else None)
            self.add('text', group([ptext(x, y, s, size, ang, h, v, cls, bg=bg, style=style)], data_kind='text'))
            self.mark_text(x, y, s, size * (1.3 if cls == 'pc-title' else 1), ang, h, v, pad=2.5, cls=cls)

    @staticmethod
    def banner(x, y, w, h, colour, rng):
        """A strip of paper with notched ends behind a heading, taped down at both ends."""
        px, py, n = 2.6, .8, 1.3
        x0, x1 = x - px, x + w + px
        y0, y1 = y + h * .1 - py, y + h * .9 + py
        ym = (y0 + y1) / 2
        d = (f'M{f2(x0 - n)} {f2(y0)}H{f2(x1 + n)}L{f2(x1)} {f2(ym)}L{f2(x1 + n)} {f2(y1)}H{f2(x0 - n)}'
             f'L{f2(x0)} {f2(ym)}Z')
        tw = (y1 - y0) * .55
        out = P.piece(d, colour, sh=(.45, .55))
        out.append(path(f'M{f2(x0 + .6)} {f2(y0 + .45)}H{f2(x1 - .6)}M{f2(x0 + .6)} {f2(y1 - .45)}H{f2(x1 - .6)}',
                        fill='none', stroke=P.WHITE, stroke_width=.18, stroke_dasharray='.7 .5', stroke_opacity=.9))
        tc = P.PAPERS[(P.PAPERS.index(colour) + 3) % len(P.PAPERS)]
        for ex, a in ((x0 + .3, -50 + rng.uniform(-10, 10)), (x1 - .3, 50 + rng.uniform(-10, 10))):
            out.append(P.tape_strip(rng, ex, y0 + .2, tw * 2.2, tw, a, P.shade(tc, -.05), 'stripes'))
        return group(out)

    @staticmethod
    def note_paper(x, y, w, h, rng):
        """A torn-off scrap of lined notepaper behind a long note, with a strip of tape at the top."""
        p = 1.0
        x0, y0, x1, y1 = x - p, y - p * .8, x + w + p, y + h + p * .8
        d = P.torn_rect(rng, x0, y0, x1, y1, step=.8, amp=.22, sides='b')
        lines = ''.join(f'M{f2(x0 + .3)} {f2(yy)}H{f2(x1 - .3)}' for yy in P.frange(y0 + 1.2, y1 - .5, 1.25))
        out = P.piece(d, '#fffdf3', sh=(.35, .45))
        out.append(path(lines, fill='none', stroke='#bcd7f0', stroke_width=.08))
        out.append(path(f'M{f2(x0 + 1)} {f2(y0)}V{f2(y1)}', fill='none', stroke='#f3a6b8', stroke_width=.1))
        out.append(P.tape_strip(rng, (x0 + x1) / 2, y0 + .1, min(6, (x1 - x0) * .4), 1.3, rng.uniform(-6, 6),
                                '#f7c6d4', 'dots'))
        return group(out)

    # -- symbols: cut paper --------------------------------------------------------
    def render_symbol(self, sym):
        lib_id = sym.lib_id
        lib = self.lib(sym)
        if lib is None:
            return
        unit = int(sym.unit or 1)
        style = int(sym.body_style or sym.convert or 1)
        dnp = bool(sym.dnp)
        xf = sym.transform_point
        power = lib.is_power
        props = {p.key: p for p in sym.properties}
        ref = props['Reference'].value if 'Reference' in props else '?'
        value = props['Value'].value if 'Value' in props else ''
        body_col = self.lib_colors(lib_id)
        rail_col = (self.colors(value) or '#ffd0e0') if power else None

        pn = lib.pin_names
        name_off = float(pn.offset) if pn is not None and pn.offset is not None else 0.508
        names_hidden = pn is not None and bool(pn.hide)
        nums_hidden = lib.pin_numbers is not None and bool(lib.pin_numbers.hide)

        units = {u.unit_index for u in lib.units}
        subs = [u for u in lib.units if u.unit_index in (0, unit) and u.demorgan_style in (0, style)]
        all_pins = [p for u in subs for p in u.pins]
        char = character_kind(ref, lib_id, len(all_pins)) if self.characters and not power else None
        if char == 'xtal':
            char = None

        bodies, strips, texts = [], [], []     # (d, colour); (d, width, colour)
        xs, ys, rects = [], [], []

        def Pt(px, py):
            X, Y = xf(px, py)
            xs.append(X)
            ys.append(Y)
            return X, Y

        for sub in subs:
            for kind, g in unit_graphics(sub):
                ftype, fcolor = fill(g)
                sw, dkind, scol = stroke(g)
                d, closed = None, False
                if char and kind != 'text':
                    for q in (shape_points(kind, g) if kind == 'polyline' else []):
                        Pt(*q)
                    continue
                if kind == 'polyline':
                    p = [Pt(*q) for q in shape_points(kind, g)]
                    if not p:
                        continue
                    d = poly_d(p)
                    closed = len(p) > 2 and (ftype != 'none' or power)
                    if closed and ftype in ('background', 'color'):
                        d = rounded_poly(p, .5)
                    elif closed:
                        d += 'Z'
                elif kind == 'rectangle':
                    (sx, sy), (ex, ey) = xy(g.start), xy(g.end)
                    a, b = Pt(sx, sy), Pt(ex, ey)
                    rr = min(.7, .1 * min(abs(a[0] - b[0]), abs(a[1] - b[1])))
                    d = rounded_rect(a[0], a[1], b[0], b[1], rr)
                    closed = True
                    rects.append((sx, sy, ex, ey, ftype))
                    if ftype == 'none':
                        ftype = 'pale'
                elif kind == 'circle':
                    cx, cy = Pt(*xy(g.center))
                    r = float(g.radius or 1)
                    xs.extend((cx - r, cx + r))
                    ys.extend((cy - r, cy + r))
                    d = circle_d(cx, cy, r)
                    closed = True
                    if ftype == 'none' and r > 1:
                        ftype = 'pale'
                elif kind == 'arc':
                    d = arc_path(Pt(*xy(g.start)), Pt(*xy(g.mid)), Pt(*xy(g.end)))
                elif kind == 'bezier':
                    p = [Pt(*q) for q in shape_points(kind, g)]
                    if len(p) >= 4:
                        d = bezier_d(p)
                elif kind == 'text':
                    if hidden(g):
                        continue
                    tx, ty = Pt(*at(g))
                    size, bold, italic, tcol = font(g)
                    h, v = justify(g)
                    ang = rotation(g)
                    ang = ang / 10 if ang > 360 else ang
                    swap = quarter_turned(sym)
                    from ..text import text_el
                    texts.append(text_el(tx, ty, g.text, size, 90 if (round(ang) % 180 == 90) != swap else 0, h, v,
                                         'symtxt', style=text_style(bold, italic, tcol)))
                    continue
                if d is None:
                    continue
                if power and closed:
                    bodies.append((d, rail_col))
                    strips.append((d, .18, P.shade(rail_col, -.3, -.2)))
                    continue
                if ftype in ('background', 'color', 'pale') and closed:
                    colour = fcolor if ftype == 'color' and fcolor else body_col
                    if ftype == 'pale':
                        colour = P.shade(colour, .03)
                    bodies.append((d, colour))
                    strips.append((d, .16, P.shade(colour, -.22, -.15)))
                elif ftype == 'outline' and closed:
                    bodies.append((d, P.INK))
                else:
                    strips.append((d, max(STRIP, sw), scol or P.INK))

        # pins: thin strips of paper, with their decorations
        pins_d, deco, pin_info = [], [], []
        for pin in all_pins:
            if pin.hide:
                continue
            px, py, pa = float(pin.at.x), float(pin.at.y), float(pin.at.rotation or 0)
            L = float(pin.length if pin.length is not None else 2.54)
            ux, uy = round(math.cos(math.radians(pa))), round(math.sin(math.radians(pa)))
            a = Pt(px, py)
            b = Pt(px + ux * L, py + uy * L)
            pin_info.append((a, b, L, pin))
            sdx, sdy = b[0] - a[0], b[1] - a[1]
            nrm = math.hypot(sdx, sdy) or 1
            sdx, sdy = sdx / nrm, sdy / nrm
            ptype, pshape = str(pin.etype), str(pin.style)
            line_end = b
            if pshape in ('inverted', 'inverted_clock') and L > 1.3:
                r = .5
                line_end = (b[0] - sdx * 2 * r, b[1] - sdy * 2 * r)
                deco.append(tag('circle', cx=b[0] - sdx * r, cy=b[1] - sdy * r, r=r, cls='pc-bubble'))
            if L > 0:
                pins_d.append(f'M{f2(a[0])} {f2(a[1])}L{f2(line_end[0])} {f2(line_end[1])}')
            nx, ny = -sdy, sdx
            if pshape in ('clock', 'inverted_clock', 'clock_low', 'edge_clock_high'):
                deco.append(path(f'M{f2(b[0] + nx * .55)} {f2(b[1] + ny * .55)}L{f2(b[0] + sdx * .9)} '
                                 f'{f2(b[1] + sdy * .9)}L{f2(b[0] - nx * .55)} {f2(b[1] - ny * .55)}', cls='pc-pin-deco'))
            if pshape in ('input_low', 'clock_low'):
                deco.append(path(f'M{f2(b[0])} {f2(b[1])}L{f2(b[0] - sdx * 1.27 - nx * .9)} '
                                 f'{f2(b[1] - sdy * 1.27 - ny * .9)}L{f2(b[0] - sdx * 1.27)} {f2(b[1] - sdy * 1.27)}',
                                 cls='pc-pin-deco'))
            if pshape == 'output_low':
                deco.append(path(f'M{f2(b[0] - nx * .9)} {f2(b[1] - ny * .9)}L{f2(b[0] - sdx * 1.27)} '
                                 f'{f2(b[1] - sdy * 1.27)}', cls='pc-pin-deco'))
            if pshape == 'non_logic' or ptype == 'no_connect':
                deco.append(path(f'M{f2(a[0] - .45)} {f2(a[1] - .45)}l.9 .9M{f2(a[0] + .45)} {f2(a[1] - .45)}l-.9 .9',
                                 cls='pc-pin-deco'))
            if char:
                continue
            vertical = abs(sdy) > 0.5
            name = pin.name.value or '' if pin.name is not None else ''
            num = pin.number.value or '' if pin.number is not None else ''
            nsize = font(pin.name)[0] if pin.name is not None else 1.27
            msize = font(pin.number)[0] if pin.number is not None else 1.27
            show_name = not names_hidden and name not in ('', '~') and nsize > 0 and not power and not hidden(pin.name)
            show_num = not nums_hidden and num != '' and msize > 0 and not power and not hidden(pin.number)
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            from ..text import text_el
            if show_name:
                if name_off > 0:
                    tx, ty = b[0] + sdx * name_off, b[1] + sdy * name_off
                    h = ('left' if sdy < 0 else 'right') if vertical else ('left' if sdx > 0 else 'right')
                    texts.append(text_el(tx, ty, name, nsize, 90 if vertical else 0, h, 'center', 'pinname'))
                elif vertical:
                    texts.append(text_el(mx - 0.4, my, name, nsize, 90, 'center', 'bottom', 'pinname'))
                else:
                    texts.append(text_el(mx, my - 0.4, name, nsize, 0, 'center', 'bottom', 'pinname'))
            if show_num:
                above = name_off > 0 or not show_name
                if vertical:
                    texts.append(text_el(mx - 0.4 if above else mx + 0.4, my, num, msize, 90, 'center',
                                         'bottom' if above else 'top', 'pinnum'))
                else:
                    texts.append(text_el(mx, my - 0.4 if above else my + 0.4, num, msize, 0, 'center',
                                         'bottom' if above else 'top', 'pinnum'))

        # fields
        from ..text import text_el
        nunits = len(units - {0})
        for pname, prop in props.items():
            if hidden(prop) or not prop.value:
                continue
            s = prop.value
            if pname == 'Reference':
                if s.startswith('#'):
                    continue
                if nunits > 1:
                    s += chr(ord('A') + unit - 1)
            if prop.show_name:
                s = f'{pname}: {s}'
            fx, fy = at(prop)
            fang = rotation(prop)
            h, v = justify(prop)
            size, bold, italic, tcol = font(prop)
            swap = quarter_turned(sym)
            vertical = (round(fang) % 180 == 90) != swap
            dvec = {'left': 1, 'right': -1, 'center': 0}[h]
            if dvec:
                rd = (math.cos(math.radians(fang)), -math.sin(math.radians(fang)))
                tx_, ty_ = sym.transform_vector(rd[0] * dvec, -rd[1] * dvec)
                if vertical and abs(ty_) > 0.5:
                    h = 'left' if ty_ < 0 else 'right'
                elif not vertical and abs(tx_) > 0.5:
                    h = 'left' if tx_ > 0 else 'right'
            cls = {'Reference': 'ref', 'Value': 'pwr' if power else 'value'}.get(pname, 'field')
            texts.append(text_el(fx, fy, s, size, 90 if vertical else 0, h, v, cls,
                                 style=text_style(bold, italic, tcol)))
            self.mark_text(fx, fy, s, size, 90 if vertical else 0, h, v, pad=0.8, cls=cls)

        # assemble: shadow, paper bodies with their rims, strips, pins, decorations
        parts = []
        sh = []
        if bodies:
            sh.append(path(''.join(d for d, _ in bodies)))
        thick = [(d, w) for d, w, _ in strips if w > .2]
        if pins_d:
            thick.append((''.join(pins_d), PIN_W))
        sx, sy = P.SH
        if sh:
            parts.append(P.shadow(sh, sx, sy))
        for d, w in thick:
            parts.append(P.shadow_stroke(d, w, sx * .7, sy * .7))
        parts += [path(d, fill=c) for d, c in bodies]
        for d, w, c in strips:
            parts.append(path(d, cls='pc-strip', stroke=c, stroke_width=w))
        if pins_d:
            parts.append(path(''.join(pins_d), cls='pc-pin'))
        parts += deco

        sid = self.uid(ref)
        entry = {'id': sid, 'ref': ref, 'lib_id': lib_id, 'parts': parts}
        if xs:
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            self.grid.mark_rect(x0, y0, x1, y1, pad=2.0)
            self.fine.mark_rect(x0, y0, x1, y1, pad=0.3)
            if not power and not dnp and not char:
                face = self.face_for(xf, rects, all_pins, name_off, names_hidden, subs)
                if face:
                    parts.append(Markup(re.sub(r'#face-(\w+)', lambda m: f'#pc-face-{hash(sid) % 3}', str(face))))
        entry['texts'] = texts
        if char:
            self.passives.append({'entry': entry, 'kind': char, 'xf': xf, 'subs': subs, 'value': value,
                                  'lib_id': lib_id, 'pins': pin_info})
        if dnp and xs:
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            r = max(1.8, min(4, max(x1 - x0, y1 - y0) / 2))
            entry['dnp'] = group([P.tape_strip(self.prng, mx, my, r * 2.4, .9, a, '#f27b96', 'stitch', alpha=.85)
                                  for a in (40, -40)], cls='pc-dnp')
        self.symbols.append(entry)

    # -- passives -------------------------------------------------------------
    def cast(self):
        return {}

    def render_characters(self):
        for p in self.passives:
            entry, kind, pins = p['entry'], p['kind'], p['pins']
            if len(pins) < 2:
                continue
            a_, b_ = max(((u, v) for i, u in enumerate(pins) for v in pins[i + 1:]),
                         key=lambda uv: math.hypot(uv[0][0][0] - uv[1][0][0], uv[0][0][1] - uv[1][0][1]))
            (pa, pa_in, _, pin_a), (pb, pb_in, _, pin_b) = a_, b_
            cx, cy = (pa_in[0] + pb_in[0]) / 2, (pa_in[1] + pb_in[1]) / 2
            L = math.hypot(pa_in[0] - pb_in[0], pa_in[1] - pb_in[1])
            ang = math.degrees(math.atan2(pb_in[1] - pa_in[1], pb_in[0] - pa_in[0]))
            if kind == 'res':
                art = self.paper_resistor(L, p['value'])
            elif kind == 'cap':
                plus = None
                lid = p['lib_id'].lower()
                if 'polar' in lid or p['lib_id'].split(':')[-1].upper().startswith('CP'):
                    num_a = pin_a.number.value if pin_a.number is not None else ''
                    plus = -1 if num_a == '1' else 1
                art = self.paper_capacitor(L, plus)
            else:
                bead = ref_prefix(entry['ref']) == 'FB' or 'bead' in p['lib_id'].lower()
                art = self.quilled_inductor(L, bead)
            entry['parts'].append(group([art], cls='pc-passive', data_character=kind,
                                        transform=f'translate({f2(cx)} {f2(cy)}) rotate({f2(ang)})'))

    @staticmethod
    def paper_resistor(L, value):
        """A paper bar along x, centred on 0, with its colour code bands."""
        hl = max(1.0, L / 2 - .05)
        hw = .78
        d = rounded_rect(-hl, -hw, hl, hw, .55)
        out = P.piece(d, '#f5dcaa', edge='#d6b67c', sh=(.3, .4), edge_w=.1)
        bands = colour_code(value)
        if bands:
            n = len(bands)
            bw = min(.38, hl * .22)
            span = hl * 1.1
            for i, c in enumerate(bands):
                bx = -span / 2 + span * i / max(1, n - 1) if n > 1 else 0
                out.append(tag('rect', x=bx - bw / 2, y=-hw, width=bw, height=2 * hw, fill=c))
            out.append(tag('rect', x=hl * .7 - bw / 2, y=-hw, width=bw, height=2 * hw, fill=GOLD))
        out.append(path(f'M{f2(-hl + .4)} {f2(-hw + .3)}H{f2(hl - .4)}', fill='none', stroke=P.WHITE,
                        stroke_width=.16, stroke_linecap='round', stroke_opacity=.7))
        return group(out)

    @staticmethod
    def paper_capacitor(L, plus=None):
        """Two plates of card across the axis; a polarised one has a coral + plate with a tiny + on it."""
        gap = max(.35, min(.75, L * .25))
        th, hh = .55, 1.45
        out = []
        for s in (-1, 1):
            x0 = s * gap / 2 if s > 0 else -gap / 2 - th
            colour = '#f59b9b' if plus == s else '#9ed9c8'
            d = rounded_rect(x0, -hh, x0 + th, hh, .2)
            out += P.piece(d, colour, edge=P.shade(colour, -.22, -.15), sh=(.3, .4), edge_w=.08)
            if plus == s:
                px = x0 + th / 2 + s * 1.0
                out.append(path(f'M{f2(px - .4)} {f2(-hh - .1)}h.8M{f2(px)} {f2(-hh - .5)}v.8', fill='none',
                                stroke='#e0607a', stroke_width=.25, stroke_linecap='round'))
        # the leads meet the plates
        out.append(path(f'M{f2(-L / 2)} 0H{f2(-gap / 2 - th)}M{f2(gap / 2 + th)} 0H{f2(L / 2)}', cls='pc-pin'))
        return group(out)

    @staticmethod
    def quilled_inductor(L, bead=False):
        """Coils of rolled paper strip (quilling) along the axis; ferrite beads get a grey band instead."""
        hl = max(1.0, L / 2)
        if bead:
            d = rounded_rect(-hl * .7, -.9, hl * .7, .9, .3)
            out = P.piece(d, '#bdb6c6', edge='#8f879b', sh=(.3, .4), edge_w=.1)
            out.append(path(f'M{f2(-hl * .7 + .3)} -.5H{f2(hl * .7 - .3)}', fill='none', stroke=P.WHITE,
                            stroke_width=.15, stroke_opacity=.6))
            return group(out)
        n = max(2, min(4, round(L / 1.6)))
        r = min(.95, L / n / 2)
        out = []
        for i in range(n):
            cx = -hl + r + (2 * hl - 2 * r) * i / max(1, n - 1)
            out += P.piece(circle_d(cx, 0, r), '#ffd0b5', sh=(.25, .32))
            out.append(path(P.spiral_d(cx, 0, r * .92, 2.4, rot=i), fill='none', stroke='#e8875f', stroke_width=.13,
                            stroke_linecap='round'))
        return group(out)
