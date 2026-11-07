"""
Library for processing KiCad's symbol files.
"""

import json
import string
import math
import re
import sys
import itertools
from fnmatch import fnmatch
from collections import defaultdict
from dataclasses import field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .sexp import *
from .sexp_mapper import *
from .base_types import *
from ...utils import rotate_point, Tag, arc_bounds
from ... import __version__
from ...newstroke import Newstroke
from .schematic_colors import *
from .primitives import kicad_mid_to_center_arc, kicad_arc_svg_flags, Margins


PIN_ETYPE = AtomChoice(Atom.input, Atom.output, Atom.bidirectional, Atom.tri_state, Atom.passive, Atom.free,
                       Atom.unspecified, Atom.power_in, Atom.power_out, Atom.open_collector, Atom.open_emitter,
                       Atom.no_connect, Atom.unconnected)


PIN_STYLE = AtomChoice(Atom.line, Atom.inverted, Atom.clock, Atom.inverted_clock, Atom.input_low, Atom.clock_low,
                       Atom.output_low, Atom.edge_clock_high, Atom.non_logic)


@sexp_type('alternate')
class AltFunction:
    name: str = None
    etype: PIN_ETYPE = Atom.unspecified
    shape: PIN_STYLE = Atom.line


@sexp_type('__styled_text')
class StyledText:
    value: str = None
    effects: TextEffect = field(default_factory=TextEffect)


@sexp_type('pin')
class Pin:
    etype: PIN_ETYPE = Atom.unspecified
    style: PIN_STYLE = Atom.line
    at: AtPos = field(default_factory=AtPos)
    length: Named(float) = 2.54
    hide: OmitDefault(Named(LegacyCompatibleFlag())) = False
    name: Rename(StyledText) = field(default_factory=StyledText)
    number: Rename(StyledText) = field(default_factory=StyledText)
    alternates: List(AltFunction) = field(default_factory=list)
    custom_properties: List(CustomProperty) = field(default_factory=list)
    _: SEXP_END = None
    unit: object = None

    def __after_parse__(self, parent=None):
        self.unit = parent

    @property
    def direction(self):
        return {0: 'R', 90: 'U', 180: 'L', 270: 'D'}.get(self.at.rotation, 'R')

    @direction.setter
    def direction(self, value):
        self.at.rotation = {0: 'R', 90: 'U', 180: 'L', 270: 'D'}[value[0].upper()]

    def bounding_box(self, default=None):
        """ The pin's line and its name, which sits beyond the pin's inner end. """
        font = Newstroke.load()
        (_x1, _y1), (w, _y2) = font.bounding_box(self.name.value or '', size=2.54)
        h = 2.54
        l = self.length + 0.2 + w

        x1, y1 = x2, y2 = self.at.x, self.at.y
        if self.at.rotation == 0:
            x2 += l
            y1 -= h/2
            y2 += h/2
        elif self.at.rotation == 90:
            y2 += l
            x1 -= h/2
            x2 += h/2
        elif self.at.rotation == 180:
            x1 -= l
            y1 -= h/2
            y2 += h/2
        elif self.at.rotation == 270:
            y1 -= l
            x1 -= h/2
            x2 += h/2
        else:
            raise ValueError(f'Invalid pin rotation {self.at.rotation}')

        return (x1, y1), (x2, y2)

    def to_svg(self, colorscheme, p_mirror, p_rotation):
        if self.hide:
            return

        psx, psy = (-1 if p_mirror.x else 1), (-1 if p_mirror.y else 1)
        x1, y1 = self.at.x, self.at.y
        x2, y2 = self.at.x+self.length, self.at.y
        if p_mirror.y:
            p_xf = f'scale(-1 -1)'
        elif p_mirror.x:
            p_xf = f'scale(1 1)'
        else:
            p_xf = f'scale(1 -1)'
        p_xf += f'rotate({p_rotation})'
        xform = {'transform': f'{p_xf} translate({self.at.x:.3f} {self.at.y:.3f}) rotate({self.at.rotation})'}
        style = {'stroke_width': 0.254, 'stroke': colorscheme.lines, 'stroke_linecap': 'round'}

        yield Tag('path', **xform, **style, d=f'M 0 0 L {self.length:.3f} 0')

        eps = 1
        for tag in {
                'line': [],
                'inverted': [
                    Tag('circle', **xform, **style, cx=x2-eps/3-0.2, cy=y2, r=eps/3)],
                'clock': [
                    Tag('path', **xform, **style, d=f'M {x2} {y2-eps/2} L {x2+eps/2} {y2} L {x2} {y2+eps/2}')],
                'inverted_clock': [
                    Tag('circle', **xform, **style, cx=x2-eps/3-0.2, cy=y2, r=eps/3),
                    Tag('path', **xform, **style, d=f'M {x2} {y2-eps/2} L {x2+eps/2} {y2} L {x2} {y2+eps/2}')],
                'input_low': [
                    Tag('path', **xform, **style, d=f'M {x2} {y2} L {x2-eps} {y2-eps} L {x2-eps} {y2}')],
                'clock_low': [
                    Tag('path', **xform, **style, d=f'M {x2} {y2} L {x2-eps} {y2-eps} L {x2-eps} {y2}'),
                    Tag('path', **xform, **style, d=f'M {x2} {y2-eps/2} L {x2+eps/2} {y2} L {x2} {y2+eps/2}')],
                'output_low': [
                    Tag('path', **xform, **style, d=f'M {x2} {y2-eps} L {x2-eps} {y2}')],
                'edge_clock_high': [
                    Tag('path', **xform, **style, d=f'M {x2} {y2} L {x2-eps} {y2-eps} L {x2-eps} {y2}'),
                    Tag('path', **xform, **style, d=f'M {x2} {y2-eps/2} L {x2+eps/2} {y2} L {x2} {y2+eps/2}')],
                'non_logic': [
                    Tag('path', **xform, **style, d=f'M {x2-eps/2} {y2-eps/2} L {x2+eps/2} {y2+eps/2}'),
                    Tag('path', **xform, **style, d=f'M {x2-eps/2} {y2+eps/2} L {x2+eps/2} {y2-eps/2}')],
                # FIXME...
        }.get(self.style, []):
            yield tag

        yield from self._text_svg(colorscheme, p_mirror, p_rotation)

    def _text_svg(self, colorscheme, p_mirror, p_rotation):
        """ Pin name and number, placed like KiCad's PIN_LAYOUT_CACHE does it, in coordinates relative to the placed
        symbol's position. Text is never mirrored; vertical pins get vertical text that reads bottom to top. """
        symbol = self.unit.symbol if self.unit is not None else None
        names, numbers = (symbol.pin_names, symbol.pin_numbers) if symbol is not None else (None, None)
        offset = names.offset if names is not None and names.offset is not None else 0.508
        name = self.name.value if self.name is not None else ''
        number = self.number.value if self.number is not None else ''
        show_name = name not in ('', '~') and not (names is not None and names.hide) and not self.name.effects.hide
        show_number = number != '' and not (numbers is not None and numbers.hide) and not self.number.effects.hide

        vec = lambda dx, dy: lib_to_sheet_vector(dx, dy, p_rotation, p_mirror.x, p_mirror.y)
        a = math.radians(self.at.rotation or 0)
        dx, dy = vec(math.cos(a), math.sin(a))  # direction from the connection point into the body
        x0, y0 = vec(self.at.x, self.at.y)
        x1, y1 = x0 + dx*self.length, y0 + dy*self.length
        mx, my = (x0 + x1)/2, (y0 + y1)/2
        vertical = abs(dy) > 0.5
        # "above" the pin: up for horizontal pins, left for vertical ones (above in the frame of vertical text)
        ux, uy = (-1, 0) if vertical else (0, -1)

        if show_name:
            size = self.name.effects.font.size.y or 1.27
            if offset > 0: # inside the body, starting the offset beyond the pin's inner end
                inward = (dy < 0) if vertical else (dx > 0)
                yield kicad_text_svg(name, x1 + dx*offset, y1 + dy*offset, size, h_align='left' if inward else 'right',
                                     v_align='middle', vertical=vertical, stroke=colorscheme.pin_names)
            else: # above the middle of the pin
                d = KICAD_TEXT_OFFSET + size/16
                yield kicad_text_svg(name, mx + ux*d, my + uy*d, size, h_align='center', v_align='bottom',
                                     vertical=vertical, stroke=colorscheme.pin_names)

        if show_number:
            size = self.number.effects.font.size.y or 1.27
            d = 2*KICAD_TEXT_OFFSET + size/8
            if show_name and offset == 0: # name above, number below
                yield kicad_text_svg(number, mx - ux*d, my - uy*d, size, h_align='center', v_align='top',
                                     vertical=vertical, stroke=colorscheme.pin_numbers)
            else:
                yield kicad_text_svg(number, mx + ux*d, my + uy*d, size, h_align='center', v_align='bottom',
                                     vertical=vertical, stroke=colorscheme.pin_numbers)


@sexp_type('fill')
class Fill:
    # hatch, reverse_hatch and cross_hatch are new in KiCad 10.99
    type: Named(AtomChoice(Atom.none, Atom.outline, Atom.background, Atom.color, Atom.hatch, Atom.reverse_hatch,
                           Atom.cross_hatch)) = Atom.none
    color: Color = None

    def svg(self, fg, bg):
        if self.type == 'outline':
            return fg
        elif self.type == 'background':
            return bg
        elif self.type == 'color' and self.color is not None:
            return self.color.svg(bg)
        else:
            return 'none'


@sexp_type('circle')
class Circle:
    center: Rename(XYCoord) = field(default_factory=XYCoord)
    radius: Named(float) = 0.0
    stroke: Stroke = field(default_factory=Stroke)
    fill: Fill = field(default_factory=Fill)
    custom_properties: List(CustomProperty) = field(default_factory=list)

    def bounding_box(self, default=None):
        x, y, r = self.center.x, self.center.y, self.radius
        return (x-r, y-r), (x+r, y+r)

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        yield Tag('circle', cx=f'{self.center.x:.3f}', cy=f'{self.center.y:.3f}', r=f'{self.radius:.3f}',
                  fill=self.fill.svg(colorscheme.lines, colorscheme.fill),
                  **self.stroke.svg_attrs(colorscheme.lines))


@sexp_type('radius')
class ArcRadius:
    at: AtPos = field(default_factory=AtPos)
    length: Named(float) = 0.0
    angles: Rename(XYCoord) = field(default_factory=XYCoord)


@sexp_type('arc')
class Arc:
    start: Rename(XYCoord) = field(default_factory=XYCoord)
    mid: Rename(XYCoord) = field(default_factory=XYCoord)
    end: Rename(XYCoord) = field(default_factory=XYCoord)
    radius: ArcRadius = None
    stroke: Stroke = field(default_factory=Stroke)
    fill: Fill = field(default_factory=Fill)
    start_shape: LineStart = None
    end_shape: LineEnd = None
    custom_properties: List(CustomProperty) = field(default_factory=list)

    @property
    def midpoint(self):
        """ The arc's midpoint. KiCad 6 symbols may give the arc as (radius (at center) (length r) (angles a1 a2))
        instead, running counter-clockwise from angle a1 to a2. """
        if self.mid is not None and self.mid.x is not None:
            return self.mid
        if self.radius is None:
            raise ValueError('Arc has neither a midpoint nor a radius')
        a1, a2 = self.radius.angles.x, self.radius.angles.y
        if a2 < a1:
            a2 += 360
        a = math.radians((a1 + a2) / 2)
        return XYCoord(self.radius.at.x + self.radius.length*math.cos(a), self.radius.at.y + self.radius.length*math.sin(a))

    def _arc(self):
        return kicad_arc_svg_flags(self.start, self.midpoint, self.end)

    def bounding_box(self, default=None):
        try:
            (cx, cy), _r, sweep, _large = self._arc()
        except ValueError: # start, mid and end on one line
            return ((min(self.start.x, self.end.x), min(self.start.y, self.end.y)),
                    (max(self.start.x, self.end.x), max(self.start.y, self.end.y)))
        # Symbol coordinates have the y axis pointing up like arc_bounds expects, so increasing angle means counter-
        # clockwise.
        return arc_bounds(self.start.x, self.start.y, self.end.x, self.end.y, cx, cy, not sweep)

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        try:
            _c, r, sweep, large = self._arc()
            d = f'M {self.start.x:.3f} {self.start.y:.3f} A {r:.3f} {r:.3f} 0 {int(large)} {int(sweep)} {self.end.x:.3f} {self.end.y:.3f}'
        except ValueError: # start, mid and end on one line
            d = f'M {self.start.x:.3f} {self.start.y:.3f} L {self.end.x:.3f} {self.end.y:.3f}'
        yield Tag('path', d=d, fill=self.fill.svg(colorscheme.lines, colorscheme.fill),
                  **self.stroke.svg_attrs(colorscheme.lines))


@sexp_type('bezier')
class Bezier:
    """ Cubic Bézier curve, given by its start point, two control points and end point. """
    points: PointList = field(default_factory=list)
    stroke: Stroke = field(default_factory=Stroke)
    fill: Fill = field(default_factory=Fill)
    start_shape: LineStart = None
    end_shape: LineEnd = None
    custom_properties: List(CustomProperty) = field(default_factory=list)

    def bounding_box(self, default=None):
        # The control polygon contains the curve.
        if not self.points:
            return default
        return (min(p.x for p in self.points), min(p.y for p in self.points)), \
               (max(p.x for p in self.points), max(p.y for p in self.points))

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        if len(self.points) != 4:
            return
        p0, *rest = self.points
        d = f'M {p0.x:.3f} {p0.y:.3f} C ' + ' '.join(f'{p.x:.3f} {p.y:.3f}' for p in rest)
        yield Tag('path', d=d, fill=self.fill.svg(colorscheme.lines, colorscheme.fill), **self.stroke.svg_attrs(colorscheme.lines))


@sexp_type('ellipse')
class Ellipse:
    """ KiCad 10.99 ellipse. Angles are in degrees. """
    center: Rename(XYCoord) = field(default_factory=XYCoord)
    major_radius: Named(float) = 0.0
    minor_radius: Named(float) = 0.0
    rotation_angle: Named(float) = 0.0
    stroke: Stroke = field(default_factory=Stroke)
    fill: Fill = field(default_factory=Fill)
    custom_properties: List(CustomProperty) = field(default_factory=list)


@sexp_type('ellipse_arc')
class EllipseArc:
    """ KiCad 10.99 elliptical arc. Angles are in degrees. """
    center: Rename(XYCoord) = field(default_factory=XYCoord)
    major_radius: Named(float) = 0.0
    minor_radius: Named(float) = 0.0
    rotation_angle: Named(float) = 0.0
    start_angle: Named(float) = 0.0
    end_angle: Named(float) = 0.0
    stroke: Stroke = field(default_factory=Stroke)
    fill: Fill = field(default_factory=Fill)
    custom_properties: List(CustomProperty) = field(default_factory=list)


@sexp_type('polyline')
class Polyline:
    pts: PointList = field(default_factory=list)
    stroke: Stroke = field(default_factory=Stroke)
    fill: Fill = field(default_factory=Fill)
    start_shape: LineStart = None
    end_shape: LineEnd = None
    custom_properties: List(CustomProperty) = field(default_factory=list)

    @property
    def points(self):
        return self.pts

    @points.setter
    def points(self, value):
        self.pts = value

    @property
    def closed(self):
        # if the last and first point are the same, we consider the polyline closed
        # a closed triangle will have 4 points (A-B-C-A) stored in the list of points
        return len(self.points) > 3 and self.points[0].isclose(self.points[-1])

    def bounding_box(self, default=None):
        if not self.points:
            return default

        return (min(p.x for p in self.points), min(p.y for p in self.points)), \
               (max(p.x for p in self.points), max(p.y for p in self.points))

    def as_rectangle(self):
        (maxx, maxy, minx, miny) = self.bbox()
        return Rectangle(minx, maxy, maxx, miny, self.stroke, self.fill)

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        p0, *rest = self.points
        if not rest:
            return

        d = ' '.join([f'M {p0.x:.3f} {p0.y:.3f}', *(f'L {pn.x:.3f} {pn.y:.3f}' for pn in rest)])
        yield Tag('path', d=d, fill=self.fill.svg(colorscheme.lines, colorscheme.fill), **self.stroke.svg_attrs(colorscheme.lines))

    def is_rectangle(self):
        # A rectangle has 5 points and is closed
        if len(self.points) != 5 or not self.is_closed():
            return False
            
        # Check that we have all four corners present
        (x1, y1), (x2, y2) = self.bbox()
        if not all(any(cand.isclose(pt) for cand in self.points[:-1]) for pt in
                   [(x1, y1), (x1, y2), (x2, y2), (x2, y1)]):
            return False

        # Check that we only have horizontal or vertical lines
        if any(x2-x1 and y2-y1 for (x1, y1), (x2,  y2) in zip(self.points[:-1], self.points[1:])):
            return False

        return True


@sexp_type('at')
class TextPos(XYCoord):
    x: float = 0 # in millimeter
    y: float = 0 # in millimeter
    rotation: int = 0  # in degrees

    def __after_parse__(self, parent):
        self.rotation = self.rotation / 10

    def __before_sexp__(self):
        self.rotation = round((self.rotation % 360) * 10)

    @property
    def rotation_rad(self):
        return math.radians(self.rotation)

    @rotation_rad.setter
    def rotation_rad(self, value):
        self.rotation = math.degrees(value)


@sexp_type('text')
class Text(TextMixin):
    text: str = None
    at: TextPos = field(default_factory=TextPos)
    rotation: float = None
    effects: TextEffect = field(default_factory=TextEffect)
    custom_properties: List(CustomProperty) = field(default_factory=list)

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        yield from TextMixin.to_svg(self, colorscheme.text)


@sexp_type('rectangle')
class Rectangle:
    # Some v6 symbols use rectangles, newer ones encode them as polylines.
    # At some point in time we can most likely remove this class since its not used anymore

    start: Rename(XYCoord) = None
    end: Rename(XYCoord) = None
    stroke: Stroke = field(default_factory=Stroke)
    fill: Fill = field(default_factory=Fill)
    custom_properties: List(CustomProperty) = field(default_factory=list)

    def to_polyline(self):
        x1, y1 = self.start.x, self.start.y
        x2, y2 = self.end.x, self.end.y
        return Polyline([XYCoord(x1, y1), XYCoord(x2, y1), XYCoord(x2, y2), XYCoord(x1, y2), XYCoord(x1, y1)],
                        self.stroke, self.fill)

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        return self.to_polyline().to_svg(colorscheme)


@sexp_type('property')
class Property(TextMixin):
    private: Flag() = False
    name: str = None
    value: str = None
    id: Named(int) = None
    at: AtPos = field(default_factory=AtPos)
    # These three are None when absent, so files without them round trip unchanged.
    show_name: Named(LegacyCompatibleFlag()) = None
    do_not_autoplace: Named(LegacyCompatibleFlag()) = None
    hide: Named(LegacyCompatibleFlag()) = None
    effects: TextEffect = field(default_factory=TextEffect)
    custom_properties: List(CustomProperty) = field(default_factory=list)

    # Alias value for text mixin
    @property
    def text(self):
        return self.value

    @text.setter
    def text(self, value):
        self.value = value

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        if not self.is_hidden:
            yield from TextMixin.to_svg(self, colorscheme.text)


@sexp_type('pin_numbers')
class PinNumberSpec:
    hide: Named(LegacyCompatibleFlag()) = False


@sexp_type('pin_names')
class PinNameSpec:
    offset: OmitDefault(Named(float)) = 0.508
    hide: OmitDefault(Named(LegacyCompatibleFlag())) = False

@sexp_type('text_box')
class TextBox:
    text: str = ''
    exclude_from_sim: OmitDefault(Named(YesNoAtom())) = False
    at: AtPos = field(default_factory=AtPos)
    size: Rename(XYCoord) = field(default_factory=XYCoord)
    margins: Margins = None
    stroke: Stroke = field(default_factory=Stroke)
    fill: Fill = field(default_factory=Fill)
    effects: TextEffect = field(default_factory=TextEffect)
    custom_properties: List(CustomProperty) = field(default_factory=list)


@sexp_type('symbol')
class Unit:
    name: str = None
    circles: List(Circle) = field(default_factory=list)
    arcs: List(Arc) = field(default_factory=list)
    polylines: List(Polyline) = field(default_factory=list)
    beziers: List(Bezier) = field(default_factory=list)
    ellipses: List(Ellipse) = field(default_factory=list)
    ellipse_arcs: List(EllipseArc) = field(default_factory=list)
    rectangles: List(Rectangle) = field(default_factory=list)
    texts: List(Text) = field(default_factory=list)
    text_boxes: List(TextBox) = field(default_factory=list)
    pins: List(Pin) = field(default_factory=list)
    unit_name: Named(str) = None
    _ : SEXP_END = None
    unit_global: Flag() = False
    style_global: Flag() = False
    demorgan_style: int = 1
    unit_index: int = 1
    symbol = None

    def __after_parse__(self, parent):
        self.symbol = parent

        if not (m := re.fullmatch(r'(.*)_([0-9]+)_([0-9]+)', self.name)):
            raise FormatError(f'Invalid unit name "{self.name}"')
        sym_name, unit_index, demorgan_style = m.groups()
        if sym_name != self.symbol.raw_name.rpartition(':')[2]:
            raise FormatError(f'Unit name "{self.name}" does not match symbol name "{self.symbol.name}"')
        self.demorgan_style = int(demorgan_style)
        self.unit_index = int(unit_index)
        self.style_global = self.demorgan_style == 0
        self.unit_global = self.unit_index == 0

    @property
    def graphical_elements(self):
        yield from self.rectangles
        yield from self.polylines
        yield from self.circles
        yield from self.arcs
        yield from self.beziers
        yield from self.texts

    def __before_sexp__(self):
        self.name = f'{self.symbol.name}_{self.unit_index}_{self.demorgan_style}'

    def pin_stacks(self):
        stacks = defaultdict(lambda: set())
        for pin in self.all_pins():
            stacks[(pin.at.x, pin.at.y)].add(pin)
        return stacks


def lib_to_sheet_vector(dx, dy, rotation=0, mirror_x=False, mirror_y=False):
    """ Turn a vector in library symbol coordinates (y pointing up) into sheet coordinates (y pointing down) for a
    symbol placed with the given rotation (degrees) and mirroring. KiCad rotates first, then mirrors. """
    a = math.radians(rotation or 0)
    c, s = math.cos(a), math.sin(a)
    c, s = (round(c) if abs(c - round(c)) < 1e-9 else c), (round(s) if abs(s - round(s)) < 1e-9 else s)
    x, y = dx, -dy
    x, y = x*c + y*s, -x*s + y*c
    if mirror_x:
        y = -y
    elif mirror_y:
        x = -x
    return x, y


class JumperPinGroups:
    """ KiCad 9's ``(jumper_pin_groups ("1" "2") ("3" "4"))``: groups of pin numbers that are connected inside the
    part. Maps to a list of lists of pin numbers. """

    def __atoms__(self):
        return [Atom.jumper_pin_groups]

    def __map__(self, obj, parent=None):
        _key, *groups = obj
        return [[str(number) for number in group] for group in groups]

    def __sexp__(self, value):
        if value:
            yield [Atom.jumper_pin_groups, *(list(group) for group in value)]


class BodyStyles:
    """ KiCad 10's ``(body_styles ...)``: either the bare atom ``demorgan`` for a symbol with the classic De Morgan
    alternate body, or the names of the symbol's custom body styles. Maps to a list of these, keeping atoms as atoms. """

    def __atoms__(self):
        return [Atom.body_styles]

    def __map__(self, obj, parent=None):
        _key, *styles = obj
        return styles

    def __sexp__(self, value):
        if value:
            yield [Atom.body_styles, *value]


@sexp_type('footprint')
class AssociatedFootprint:
    lib_id: str = ''
    map: Named(str) = None


@sexp_type('entry')
class PinMapEntry:
    pin: str = ''
    pad: str = ''


@sexp_type('pin_map')
class PinMap:
    """ KiCad 10.99 pin map: which footprint pad each symbol pin goes to. """
    name: str = ''
    entries: List(PinMapEntry) = field(default_factory=list)


@sexp_type('power')
class PowerSpec:
    """ Marks a symbol as a power symbol. KiCad 9 added local power symbols, whose net is local to their sheet. Their
    scope is ``local``, and the scope of global power symbols is ``global``. Files from older KiCad versions only have a
    bare ``(power)``, for which scope is None. """
    scope: AtomChoice(Atom('global'), Atom('local')) = None

    @property
    def is_local(self):
        return self.scope == 'local'


@sexp_type('symbol')
class Symbol:
    raw_name: str = None
    extends: Named(str) = None
    power: PowerSpec = None
    body_styles: BodyStyles() = None
    pin_numbers: OmitDefault(PinNumberSpec) = field(default_factory=PinNumberSpec)
    pin_names: OmitDefault(PinNameSpec) = field(default_factory=PinNameSpec)
    exclude_from_sim: OmitDefault(Named(YesNoAtom())) = False
    exclude_from_sim: Named(YesNoAtom()) = False
    in_bom: Named(YesNoAtom()) = True
    on_board: Named(YesNoAtom()) = True
    in_pos_files: Named(YesNoAtom()) = None
    duplicate_pin_numbers_are_jumpers: Named(YesNoAtom()) = None
    jumper_pin_groups: JumperPinGroups() = None
    properties: List(Property) = field(default_factory=list)
    # KiCad 10.99: footprints that fit the symbol, with the pin map each one uses
    associated_footprints: Named(Array(AssociatedFootprint)) = field(default_factory=list)
    pin_maps: Named(Array(PinMap)) = field(default_factory=list)
    units: List(Unit) = field(default_factory=list)
    embedded_fonts: Named(YesNoAtom()) = False
    embedded_files: EmbeddedFiles = None
    _ : SEXP_END = None
    library = None
    name: str = None
    library_name: str = None

    def __after_parse__(self, parent):
        self.library = parent

        self.library_name, _, self.name = self.raw_name.rpartition(':')

        if self.extends:
            self.in_bom = None
            self.on_board = None

        self.properties = {prop.name: prop for prop in self.properties}
        if (prop := self.properties.get('ki_fp_filters')):
            prop.value = prop.value.split() if prop.value else []

    def __before_sexp__(self):
        if (prop := self.properties.get('ki_fp_filters')):
            if not isinstance(prop.value, str):
                prop.value = ' '.join(prop.value)
        self.properties = list(self.properties.values())

    def default_properties(self):
        for i, (name, value, hide) in enumerate([
            ('Reference',       'U',        False),
            ('Value',           None,       False),
            ('Footprint',       None,       True),
            ('Datasheet',       None,       True),
            ('ki_locked',       None,       True),
            ('ki_keywords',     None,       True),
            ('ki_description',  None,       True),
            ('ki_fp_filters',   None,       False),
            ]):
            self.properties[name] = Property(name=name, value=value, id=i, effects=TextEffect(hide=hide))

    def resolve(self):
        """ The symbol this one is derived from with (extends ...), or this symbol itself. In libraries embedded in
        schematics, names carry a library prefix, which `extends` leaves out; the parent is looked up in the same
        library first. """
        if not self.extends:
            return self
        if self.library_name:
            try:
                return self.library[f'{self.library_name}:{self.extends}']
            except KeyError:
                pass
        return self.library[self.extends]

    def is_graphic_symbol(self):
        return self.extends is None and (
            not self.pins or self.get_property("Reference").value == "#SYM"
        )

    def pins_by_name(self, demorgan_style=None):
        pins = defaultdict(lambda: set())
        for unit in self.units(demorgan_style):
            for pin in unit.all_pins:
                pins[pin.name].add(pin)
        return pins

    def pins_by_number(self, demorgan_style=None):
        pins = defaultdict(lambda: set())
        for unit in self.units(demorgan_style):
            for pin in unit.all_pins:
                pins[pin.number].add(pin)
        return pins

    def filter_pins(self, name=None, direction=None, electrical_type=None):
        for pin in self.all_pins:
            if name and not fnmatch(pin.name, name):
                continue
            if direction and not pin.direction in direction:
                continue
            if electrical_type and not pin.etype in electical_type:
                continue
            yield pin

    def heuristically_small(self):
        """ Heuristically try to determine whether this is a "small" component like a resistor, capacitor, LED, diode,
        or transistor etc. When we have at most two pins, or there is no filled rectangle as symbol outline and we have
        3 or 4 pins, we assume this is a small symbol.
        """
        if len(self.all_pins) <= 2:
            return True
        if len(self.all_pins) > 4:
            return False
        return bool(self.get_center_rectangle(range(self.unit_count)))


def _lookup_symbol(symbols, name):
    """ Find a symbol by its full name (with library prefix, if it has one), else by its name alone. """
    for sym in symbols:
        if sym.raw_name == name:
            return sym
    for sym in symbols:
        if sym.name == name:
            return sym
    raise KeyError(name)


SUPPORTED_FILE_FORMAT_VERSIONS = [20211014, 20220914]
@sexp_type('kicad_symbol_lib')
class Library:
    _version: Named(int, name='version') = 20211014
    generator: Named(str) = Atom.gerbonara
    generator_version: Named(str) = __version__
    symbols: List(Symbol) = field(default_factory=list)
    _ : SEXP_END = None
    original_filename: str = None

    @property
    def version(self):
        return self._version

    @version.setter
    def version(self, value):
        if value not in SUPPORTED_FILE_FORMAT_VERSIONS:
            raise FormatError(f'File format version {value} is not supported. Supported versions are {", ".join(map(str, SUPPORTED_FILE_FORMAT_VERSIONS))}.')

    def __getitem__(self, name):
        return _lookup_symbol(self.symbols, name)

    @classmethod
    def open(cls, filename: str):
        with open(filename) as f:
            return cls.parse(f.read())

    def write(self, filename=None):
        with open(filename or self.original_filename, 'w') as f:
            f.write(build_sexp(sexp(self)))


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        a = Library.open(sys.argv[1])
        print(build_sexp(sexp(a)))
    else:
        print("pass a .kicad_sym file please")
