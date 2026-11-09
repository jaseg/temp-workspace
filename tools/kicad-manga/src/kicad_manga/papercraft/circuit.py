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

from ..circuit import Circuit, character_kind, poly_d, ref_prefix, shape_points, unit_graphics
from ..kicad import at, fill, font, hidden, justify, quarter_turned, rotation, stroke, xy
from ..palette import NetColors
from ..svg import Markup, group, num as f2, path, tag
from ..text import plain, text_el, text_extent
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
            rng = random.Random(f'net{root}')
            pieces = [self.tape_piece(rng, a, b, TAPE_W) for _, a, b in items]
            parts = P.soft_shadow(''.join(pieces), .45, .9) + [path(q, cls='tape', fill=col) for q in pieces]
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
                    parts.append(path(f'M{f2(a[0])} {f2(a[1])}L{f2(b[0])} {f2(b[1])}', fill='none', stroke=scol,
                                      stroke_width=TAPE_W * .4, stroke_opacity=.8))
            self.add('wires', group(parts, cls='net', data_net=name))
        self.render_buses()

    @staticmethod
    def tape_piece(rng, a, b, width):
        """A piece of tape laid by hand from a to b: running on a little past both ends (so pieces overlap at
        corners), torn off slightly askew, its edges not quite straight."""
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1e-6:
            return ''
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        e0, e1 = width * rng.uniform(.3, .55), width * rng.uniform(.3, .55)
        pts = [(a[0] - ux * e0, a[1] - uy * e0), (b[0] + ux * e1, b[1] + uy * e1)]
        return P.cut_strip(rng, pts, width, amp=.07, step=1.6)

    def render_buses(self):
        buses = [[xy(p) for p in b.points] for b in self.sch.buses]
        rng = random.Random('buses')
        for p in buses:
            pieces = ''.join(self.tape_piece(rng, a, b, BUS_W) for a, b in zip(p, p[1:]))
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
            self.add('wires', group(P.soft_shadow(pieces, .6, .9) + [path(pieces, cls='tape', fill='#c9b3f2'),
                                                                   path(stripes, cls='tape-bus')], data_kind='bus'))
            for a, c in zip(p, p[1:]):
                self.mark(a[0], a[1], c[0], c[1], pad=1.4, fine_pad=1.2)
        rng = random.Random('bus entries')
        for be in self.sch.bus_entries:
            (x, y), (sx, sy) = at(be), xy(be.size)
            col = P.shade(self.color_at((x + sx, y + sy)), -.06)
            d = self.tape_piece(rng, (x, y), (x + sx, y + sy), TAPE_W * .8)
            self.add('wires', group(P.soft_shadow(d, .45, .9) + [path(d, cls='tape', fill=col)],
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

    def directive_label(self, lab):
        """Netclass flags: a short strip of paper with a punched paper dot (or a little square or diamond) on
        the end, and the class name handwritten next to it."""
        x, y = at(lab)
        length = float(lab.length or 2.54)
        shape = str(lab.shape or 'round')
        props = lab.properties
        prop = props[0] if props else None
        px, py = at(prop) if prop else (x, y - length)
        dx, dy = px - x, py - y
        if abs(dx) > abs(dy):
            ux, uy = (1 if dx > 0 else -1), 0
        else:
            ux, uy = 0, (1 if dy > 0 else -1)
        ex, ey = x + ux * length, y + uy * length
        col = self.colors(prop.value) if prop and prop.value else '#f0b8c8'
        rng = random.Random(f'flag{x}{y}')
        if shape == 'diamond':
            head = [(ex, ey - .9), (ex + .9, ey), (ex, ey + .9), (ex - .9, ey)]
        elif shape == 'rectangle':
            head = P.rect_pts(ex - .8, ey - .8, ex + .8, ey + .8)
        else:
            head = P.sample_circle(ex, ey, .8, .3)
        stem = P.cut_strip(rng, [(x, y), (ex - ux * .5, ey - uy * .5)], .26, amp=.12, step=.5)
        dot = P.cut_outline(rng, head, amp=.04, step=.3)
        parts = P.soft_shadow(stem + dot, .6) + [path(stem, cls='pc-pin'), path(dot, fill=col)]
        for p in props:
            if not hidden(p) and p.value:
                qx, qy = at(p)
                hj, vj = justify(p)
                size = font(p)[0]
                parts.append(ptext(qx, qy, p.value, size, rotation(p), hj, vj, 'pc-hand'))
                self.mark_text(qx, qy, p.value, size, rotation(p), hj, vj, cls='pc-hand')
        self.add('labels', group(parts, data_kind='netclass_flag'))
        self.mark(x, y, ex, ey, pad=1.0, fine_pad=1.0)

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
        tilt = rng.uniform(-1.2, 1.2)
        out = P.cut_piece(rng, pts, col, depth=.6, amp=.05)
        if hole:     # punched through: the card below shows, and the hole's far rim catches a little shadow
            r = min(.22, hh * .16)
            out.append(tag('circle', cx=hx, cy=ym, r=r, fill=P.CARD))
            out.append(path(f'M{f2(hx - r)} {f2(ym)}a{f2(r)} {f2(r)} 0 0 1 {f2(2 * r)} 0', fill='none',
                            stroke=P.SHADOW, stroke_width=.07, stroke_opacity=.3))
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
        fillc = col if kind == 'global_label' else P.shade(col, .04)
        return group(P.cut_piece(random.Random(f'{x}{w}{shape}'), top + right + bottom, fillc, depth=.7, amp=.05))

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
        """A strip of printed washi tape behind a heading, torn off at both ends; the heading is outlined in
        white so it reads on the print."""
        cx, cy = x + w / 2, y + h * .52
        width = h * 1.3
        pattern = ('dots', 'stripes', 'grid', 'stitch')[int(rng.random() * 4)]
        return P.tape_strip(rng, cx, cy, w + width * 1.6, width, rng.uniform(-1.5, 1.5), colour, pattern,
                            alpha=.86, sh=(.3, .4))

    @staticmethod
    def note_paper(x, y, w, h, rng):
        """A torn-off scrap of lined notepaper behind a long note, with a strip of tape at the top."""
        p = 1.0
        x0, y0, x1, y1 = x - p, y - p * .8, x + w + p, y + h + p * .8
        d = P.torn_rect(rng, x0, y0, x1, y1, step=.8, amp=.22, sides='b')
        lines = ''.join(f'M{f2(x0 + .3)} {f2(yy)}H{f2(x1 - .3)}' for yy in P.frange(y0 + 1.2, y1 - .5, 1.25))
        out = P.soft_shadow(d, 1.1) + [path(d, fill='#fffdf3')]
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

        bodies, strips, texts = [], [], []     # (points, colour); (points, width, colour, closed)
        xs, ys, rects = [], [], []
        rng = random.Random(f'{ref}{lib_id}{sym.at.x}{sym.at.y}')

        def Pt(px, py):
            X, Y = xf(px, py)
            xs.append(X)
            ys.append(Y)
            return X, Y

        for sub in subs:
            for kind, g in unit_graphics(sub):
                ftype, fcolor = fill(g)
                sw, dkind, scol = stroke(g)
                pts, closed = None, False
                if char and kind != 'text':
                    for q in (shape_points(kind, g) if kind == 'polyline' else []):
                        Pt(*q)
                    continue
                if kind == 'polyline':
                    pts = [Pt(*q) for q in shape_points(kind, g)]
                    if len(pts) > 2 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 1e-3:
                        pts = pts[:-1]
                    closed = len(pts) > 2 and (ftype != 'none' or power)
                elif kind == 'rectangle':
                    (sx, sy), (ex, ey) = xy(g.start), xy(g.end)
                    (ax, ay), (bx, by) = Pt(sx, sy), Pt(ex, ey)
                    pts = [(ax, ay), (bx, ay), (bx, by), (ax, by)]
                    closed = True
                    rects.append((sx, sy, ex, ey, ftype))
                    if ftype == 'none':
                        ftype = 'pale'
                elif kind == 'circle':
                    cx, cy = Pt(*xy(g.center))
                    r = float(g.radius or 1)
                    xs.extend((cx - r, cx + r))
                    ys.extend((cy - r, cy + r))
                    pts = P.sample_circle(cx, cy, r)
                    closed = True
                    if ftype == 'none' and r > 1:
                        ftype = 'pale'
                elif kind == 'arc':
                    pts = P.sample_arc(Pt(*xy(g.start)), Pt(*xy(g.mid)), Pt(*xy(g.end)))
                elif kind == 'bezier':
                    q = [Pt(*q) for q in shape_points(kind, g)]
                    if len(q) >= 4:
                        pts = P.sample_bezier(q)
                elif kind == 'text':
                    if hidden(g):
                        continue
                    tx, ty = Pt(*at(g))
                    size, bold, italic, tcol = font(g)
                    h, v = justify(g)
                    ang = rotation(g)
                    ang = ang / 10 if ang > 360 else ang
                    swap = quarter_turned(sym)
                    texts.append(text_el(tx, ty, g.text, size, 90 if (round(ang) % 180 == 90) != swap else 0, h, v,
                                         'symtxt', style=text_style(bold, italic, tcol)))
                    continue
                if not pts or len(pts) < 2:
                    continue
                if power and closed:
                    bodies.append((pts, rail_col))
                    continue
                if ftype in ('background', 'color', 'pale') and closed:
                    colour = fcolor if ftype == 'color' and fcolor else body_col
                    if ftype == 'pale':
                        colour = P.shade(colour, .03)
                    bodies.append((pts, colour))
                    if kind == 'rectangle' or ftype == 'pale':
                        continue
                    strips.append((pts, .2, P.shade(colour, -.3, -.15), True))   # a folded rim on small shapes
                elif ftype == 'outline' and closed:
                    bodies.append((pts, P.INK))
                else:
                    strips.append((pts, max(STRIP, sw), scol or P.INK, closed))

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
                pins_d.append(P.cut_strip(rng, [a, line_end], PIN_W, amp=.12, step=.6))
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

        # assemble: one soft shadow for all of the symbol's paper, then the cut pieces, strips and pins
        dx, dy = rng.uniform(-.06, .06), rng.uniform(-.06, .06)     # bodies are pasted on a bit off
        body_d = [(P.cut_outline(rng, [(x + dx, y + dy) for x, y in pts], amp=.06), c) for pts, c in bodies]
        strip_d = [(P.cut_strip(rng, pts, w, closed=cl), c) for pts, w, c, cl in strips]
        everything = ''.join(d for d, _ in body_d + strip_d) + ''.join(pins_d)
        parts = P.soft_shadow(everything) if everything else []
        parts += [path(d, fill=c) for d, c in body_d]
        big = [d for (d, _), (pts, _) in zip(body_d, bodies) if P.area(pts) > 20]
        if big:     # the paper grain shows on the larger pieces
            parts.append(path(''.join(big), fill='url(#pc-grain)'))
        parts += [path(d, fill=c) for d, c in strip_d]
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
            rng = random.Random(entry['ref'])
            ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
            place = lambda pts: [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts]  # noqa: E731
            ds = []
            for pts, colour, how in art:
                if how == 'piece':
                    ds.append((P.cut_outline(rng, place(pts), amp=.05, step=.4), colour))
                else:
                    ds.append((P.cut_strip(rng, place(pts), how[1], amp=.12, step=.35), colour))
            shapes = P.soft_shadow(''.join(d for d, _ in ds), .9) + [path(d, fill=c) for d, c in ds]
            entry['parts'].append(group(shapes, cls='pc-passive', data_character=kind))

    # Each passive is built along the x axis around 0 as [(points, colour, kind)], kind 'piece' (a cut shape) or
    # ('strip', width) (a strip of paper along the points); render_characters turns it into place, so that the
    # shadows all fall the same way.

    @staticmethod
    def paper_resistor(L, value):
        """A paper bar with narrow strips of coloured paper glued round it for its colour code."""
        hl = max(1.0, L / 2 - .05)
        hw = .78
        out = [(P.rect_pts(-hl, -hw, hl, hw, .5), '#ecd9b4', 'piece')]
        bands = colour_code(value)
        if bands:
            n = len(bands)
            bw = min(.36, hl * .22)
            span = hl * 1.1
            xs = [-span / 2 + span * i / max(1, n - 1) if n > 1 else 0 for i in range(n)] + [hl * .7]
            for bx, c in zip(xs, bands + [GOLD]):
                out.append(([(bx, -hw - .08), (bx, hw + .08)], c, ('strip', bw)))
        return out

    @staticmethod
    def paper_capacitor(L, plus=None):
        """Two plates of card across the axis, with paper leads; a polarised one has a coral + plate with a
        little + cut from paper next to it."""
        gap = max(.35, min(.75, L * .25))
        th, hh = .55, 1.45
        out = [([(-L / 2, 0), (-gap / 2 - th * .5, 0)], '#7d6a8c', ('strip', PIN_W)),
               ([(gap / 2 + th * .5, 0), (L / 2, 0)], '#7d6a8c', ('strip', PIN_W))]
        for sgn in (-1, 1):
            x0 = gap / 2 if sgn > 0 else -gap / 2 - th
            colour = '#f0a5a0' if plus == sgn else '#a9d6c8'
            out.append((P.rect_pts(x0, -hh, x0 + th, hh, .15), colour, 'piece'))
            if plus == sgn:
                px = x0 + th / 2 + sgn * 1.0
                out.append(([(px - .4, -hh - .1), (px + .4, -hh - .1)], '#d9707e', ('strip', .26)))
                out.append(([(px, -hh - .5), (px, -hh + .3)], '#d9707e', ('strip', .26)))
        return out

    @staticmethod
    def quilled_inductor(L, bead=False):
        """Coils of rolled paper strip (quilling) along the axis; ferrite beads are a grey paper bead."""
        hl = max(1.0, L / 2)
        if bead:
            return [(P.rect_pts(-hl * .7, -.9, hl * .7, .9, .5), '#bdb6c6', 'piece')]
        n = max(2, min(4, round(L / 1.6)))
        r = min(.95, L / n / 2)
        out = []
        for i in range(n):
            cx = -hl + r + (2 * hl - 2 * r) * i / max(1, n - 1)
            out.append((P.sample_circle(cx, 0, r, .3), '#f6d2bd', 'piece'))
            pts = []
            turns, steps = 2.4, 26
            for k in range(int(turns * steps) + 1):
                t = k / (turns * steps)
                ang = i + t * turns * 2 * math.pi
                rr = r * .9 * (.12 + .88 * t)
                pts.append((cx + math.cos(ang) * rr, math.sin(ang) * rr))
            out.append((pts, '#d98e6c', ('strip', .13)))
        return out
