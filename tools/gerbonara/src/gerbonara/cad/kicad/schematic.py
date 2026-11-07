"""
Library for handling KiCad's schematic files (`*.kicad_sch`).
"""

import math
import string
from pathlib import Path
from dataclasses import field, KW_ONLY
from itertools import chain
import re
import fnmatch
import os.path
import warnings

from .sexp import *
from .base_types import *
from .primitives import *
from .symbols import Symbol, _lookup_symbol, lib_to_sheet_vector
from . import graphical_primitives as gr

from .. import primitives as cad_pr
from ... import __version__

from ... import graphic_primitives as gp
from ... import graphic_objects as go
from ... import apertures as ap
from ...layers import LayerStack
from ...newstroke import Newstroke
from ...utils import MM, rotate_point, Tag, setup_svg
from .schematic_colors import *


@sexp_type('path')
class SheetPath:
    path: str = '/'
    page: Named(str) = '1'


@sexp_type('junction')
class Junction:
    at: Rename(XYCoord) = field(default_factory=XYCoord)
    diameter: Named(float) = 0
    color: Color = field(default_factory=lambda: Color(0, 0, 0, 0))
    uuid: UUID = field(default_factory=UUID)
    locked: Named(YesNoAtom()) = None
    custom_properties: List(CustomProperty) = field(default_factory=list)

    def bounding_box(self, default=None):
        r = (self.diameter/2 or 0.5)
        return (self.at.x - r, self.at.y - r), (self.at.x + r, self.at.y + r)
    
    def to_svg(self, colorscheme=Colorscheme.KiCad):
        yield Tag('circle', cx=f'{self.at.x:.3f}', cy=f'{self.at.y:.3f}', r=(self.diameter/2 or 0.5),
                   fill=self.color.svg(colorscheme.wire))


@sexp_type('no_connect')
class NoConnect:
    at: Rename(XYCoord) = field(default_factory=XYCoord)
    uuid: UUID = field(default_factory=UUID)
    locked: Named(YesNoAtom()) = None
    custom_properties: List(CustomProperty) = field(default_factory=list)

    def bounding_box(self, default=None):
        r = 0.635
        return (self.at.x - r, self.at.y - r), (self.at.x + r, self.at.y + r)

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        r = 0.635
        x, y = self.at.x, self.at.y
        yield Tag('path', d=f'M {x-r:.3f} {y-r:.3f} L {x+r:.3f} {y+r:.3f} M {x-r:.3f} {y+r:.3f} L {x+r:.3f} {y-r:.3f}',
                   fill='none', stroke_width='0.254', stroke=colorscheme.no_connect)


@sexp_type('bus_alias')
class BusAlias:
    name: str = ''
    members: Named(Array(str)) = field(default_factory=list)


@sexp_type('bus_entry')
class BusEntry:
    at: AtPos = field(default_factory=AtPos)
    size: Rename(XYCoord) = field(default_factory=lambda: XYCoord(2.54, 2.54))
    stroke: Stroke = field(default_factory=Stroke)
    uuid: UUID = field(default_factory=UUID)
    start_shape: LineStart = None
    end_shape: LineEnd = None
    locked: Named(YesNoAtom()) = None
    custom_properties: List(CustomProperty) = field(default_factory=list)

    def bounding_box(self, default=None):
        x1, y1 = self.at.x, self.at.y
        x2, y2 = x1 + self.size.x, y1 + self.size.y
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)

        r = (self.stroke.width or 0.254) / 2
        return (x1-r, y1-r), (x2+r, y2+r)

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        yield Tag('path', d=f'M {self.at.x:.3f} {self.at.y:.3f} l {self.size.x:.3f} {self.size.y:.3f}',
                  fill='none', stroke=self.stroke.svg_color(colorscheme.bus), stroke_width=self.stroke.width or 0.254,
                  stroke_linecap='round')


def _polyline_svg(self, default_color):
    da = Dasher(self)
    if len(self.points) < 2:
        warnings.warn(f'Schematic {type(self)} with less than two points')
        return Tag('path', d='')

    p0, *rest = self.points
    da.move(p0.x, p0.y)
    for pn in rest:
        da.line(pn.x, pn.y)

    return da.svg(stroke=self.stroke.svg_color(default_color))


def _fill_svg(fill, colorscheme):
    if fill is None or fill.type == Atom.none:
        return 'none'
    elif fill.type == Atom.outline:
        return colorscheme.lines
    elif fill.type == Atom.color and fill.color:
        return fill.color.svg(colorscheme.fill)
    return colorscheme.fill


def _ellipse_d(e, segments=64):
    """ An ellipse or elliptical arc as a polyline. Angles run counter-clockwise on the sheet, like KiCad's. """
    a, b = e.major_radius, e.minor_radius
    rot = math.radians(e.rotation_angle or 0)
    t0, t1 = (math.radians(e.start_angle), math.radians(e.end_angle)) if hasattr(e, 'start_angle') else (0, 2*math.pi)
    if t1 <= t0:
        t1 += 2*math.pi
    pts = []
    for i in range(segments + 1):
        t = t0 + (t1 - t0) * i / segments
        x, y = a*math.cos(t), b*math.sin(t)
        x, y = x*math.cos(rot) - y*math.sin(rot), x*math.sin(rot) + y*math.cos(rot)
        pts.append((e.center.x + x, e.center.y - y))
    d = 'M ' + ' L '.join(f'{x:.3f} {y:.3f}' for x, y in pts)
    return d if hasattr(e, 'start_angle') else d + ' Z'


def _shape_svg(self, colorscheme, name='path', **attrs):
    return Tag(name, **attrs, fill=_fill_svg(self.fill, colorscheme), **self.stroke.svg_attrs(colorscheme.lines))


def _polyline_bounds(self):
    x1 = min(pt.x for pt in self.points)
    y1 = min(pt.y for pt in self.points)
    x2 = max(pt.x for pt in self.points)
    y2 = max(pt.y for pt in self.points)

    r = (self.stroke.width or 0.254) / 2
    return (x1-r, y1-r), (x2+r, y2+r)


@sexp_type('wire')
class Wire:
    points: PointList = field(default_factory=list)
    stroke: Stroke = field(default_factory=Stroke)
    uuid: UUID = field(default_factory=UUID)
    start_shape: LineStart = None
    end_shape: LineEnd = None
    locked: Named(YesNoAtom()) = None
    custom_properties: List(CustomProperty) = field(default_factory=list)

    def bounding_box(self, default=None):
        return _polyline_bounds(self)

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        yield _polyline_svg(self, colorscheme.wire)


@sexp_type('bus')
class Bus:
    points: PointList = field(default_factory=list)
    stroke: Stroke = field(default_factory=Stroke)
    uuid: UUID = field(default_factory=UUID)
    custom_properties: List(CustomProperty) = field(default_factory=list)

    def bounding_box(self, default=None):
        return _polyline_bounds(self)

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        yield _polyline_svg(self, colorscheme.bus)


@sexp_type('polyline')
class Polyline:
    points: PointList = field(default_factory=list)
    stroke: Stroke = field(default_factory=Stroke)
    fill: OmitDefault(Fill) = None
    uuid: UUID = field(default_factory=UUID)
    start_shape: LineStart = None
    end_shape: LineEnd = None
    locked: Named(YesNoAtom()) = None
    custom_properties: List(CustomProperty) = field(default_factory=list)

    def bounding_box(self, default=None):
        return _polyline_bounds(self)

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        yield _polyline_svg(self, colorscheme.lines)


@sexp_type('circle')
class Circle:
    center: Rename(XYCoord) = field(default_factory=XYCoord)
    radius: Named(float) = 0.0
    stroke: Stroke = field(default_factory=Stroke)
    fill: OmitDefault(Fill) = None
    uuid: UUID = field(default_factory=UUID)
    locked: Named(YesNoAtom()) = None
    custom_properties: List(CustomProperty) = field(default_factory=list)

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        yield _shape_svg(self, colorscheme, 'circle', cx=f'{self.center.x:.3f}', cy=f'{self.center.y:.3f}',
                         r=f'{self.radius:.3f}')


@sexp_type('rectangle')
class Rectangle:
    start: Rename(XYCoord) = field(default_factory=XYCoord)
    end: Rename(XYCoord) = field(default_factory=XYCoord)
    stroke: Stroke = field(default_factory=Stroke)
    fill: OmitDefault(Fill) = None
    uuid: UUID = field(default_factory=UUID)
    locked: Named(YesNoAtom()) = None
    custom_properties: List(CustomProperty) = field(default_factory=list)

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        x1, y1, x2, y2 = self.start.x, self.start.y, self.end.x, self.end.y
        yield _shape_svg(self, colorscheme, d=f'M {x1:.3f} {y1:.3f} H {x2:.3f} V {y2:.3f} H {x1:.3f} Z')


@sexp_type('arc')
class Arc:
    start: Rename(XYCoord) = field(default_factory=XYCoord)
    mid: Rename(XYCoord) = field(default_factory=XYCoord)
    end: Rename(XYCoord) = field(default_factory=XYCoord)
    stroke: Stroke = field(default_factory=Stroke)
    fill: OmitDefault(Fill) = None
    uuid: UUID = field(default_factory=UUID)
    start_shape: LineStart = None
    end_shape: LineEnd = None
    locked: Named(YesNoAtom()) = None
    custom_properties: List(CustomProperty) = field(default_factory=list)

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        try:
            _c, r, sweep, large = kicad_arc_svg_flags(self.start, self.mid, self.end)
            to = f'A {r:.3f} {r:.3f} 0 {int(large)} {int(sweep)}'
        except ValueError: # start, mid and end on one line
            to = 'L'
        yield _shape_svg(self, colorscheme, d=f'M {self.start.x:.3f} {self.start.y:.3f} {to} {self.end.x:.3f} {self.end.y:.3f}')


@sexp_type('ellipse')
class Ellipse:
    """ KiCad 10.99 ellipse. Angles are in degrees. """
    center: Rename(XYCoord) = field(default_factory=XYCoord)
    major_radius: Named(float) = 0.0
    minor_radius: Named(float) = 0.0
    rotation_angle: Named(float) = 0.0
    stroke: Stroke = field(default_factory=Stroke)
    fill: OmitDefault(Fill) = None
    uuid: UUID = field(default_factory=UUID)
    locked: Named(YesNoAtom()) = None
    custom_properties: List(CustomProperty) = field(default_factory=list)

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        yield _shape_svg(self, colorscheme, d=_ellipse_d(self))


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
    fill: OmitDefault(Fill) = None
    uuid: UUID = field(default_factory=UUID)
    locked: Named(YesNoAtom()) = None
    custom_properties: List(CustomProperty) = field(default_factory=list)

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        yield _shape_svg(self, colorscheme, d=_ellipse_d(self))


@sexp_type('bezier')
class Bezier:
    points: PointList = field(default_factory=list)
    stroke: Stroke = field(default_factory=Stroke)
    fill: OmitDefault(Fill) = None
    uuid: UUID = field(default_factory=UUID)
    start_shape: LineStart = None
    end_shape: LineEnd = None
    locked: Named(YesNoAtom()) = None
    custom_properties: List(CustomProperty) = field(default_factory=list)

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        if len(self.points) != 4:
            return
        p0, *rest = self.points
        yield _shape_svg(self, colorscheme, d=f'M {p0.x:.3f} {p0.y:.3f} C ' + ' '.join(f'{p.x:.3f} {p.y:.3f}' for p in rest))


def _justify(item, default_h='center', default_v='middle'):
    j = item.effects.justify if item.effects is not None else None
    h = str(j.h) if j is not None and j.h is not None else default_h
    v = str(j.v) if j is not None and j.v is not None else default_v
    return h, ('middle' if v == 'center' else v)


def _text_size(item):
    f = item.effects.font if item.effects is not None else None
    return (f.size.y or 1.27) if f is not None and f.size is not None else 1.27


def _pen_width(item):
    """ KiCad's pen width for a text item: its thickness, else a fifth of its size for bold and an eighth otherwise. """
    f = item.effects.font if item.effects is not None else None
    size = _text_size(item)
    if f is not None and f.thickness:
        return f.thickness
    return size / 5 if f is not None and f.bold else size / 8


def _is_vertical(item):
    return round(item.at.rotation or 0) % 180 == 90


def _wrap_text(text, size, width):
    """ Word-wrap text to `width`, like KiCad does in text boxes and table cells. """
    out = []
    for para in kicad_unescape(text or '').split('\n'):
        line = ''
        for word in para.split(' '):
            candidate = f'{line} {word}' if line else word
            if line and kicad_text_width(candidate, size) > width:
                out.append(line)
                line = word
            else:
                line = candidate
        out.append(line)
    return '\n'.join(out)


def _text_box_svg(box, colorscheme, border=True):
    """ A text box or table cell: its frame (unless border is False, or its stroke width is negative, which KiCad
    uses for no frame), its fill, and its text, wrapped to fit and aligned inside the margins. Text boxes rotated by 90
    degrees are drawn unrotated. """
    x, y = box.at.x, box.at.y
    w, h = (box.size.x, box.size.y) if box.size is not None else (0, 0)
    if w < 0:
        x, w = x + w, -w
    if h < 0:
        y, h = y + h, -h
    fill = _fill_svg(box.fill, colorscheme)
    stroke = getattr(box, 'stroke', None)
    attrs = {}
    if border and stroke is not None and (stroke.width or 0) >= 0:
        attrs = stroke.svg_attrs(colorscheme.lines)
    if attrs or fill != 'none':
        yield Tag('rect', x=f'{x:.3f}', y=f'{y:.3f}', width=f'{w:.3f}', height=f'{h:.3f}', fill=fill, **attrs)

    size = _text_size(box)
    m = box.margins
    ml, mt, mr, mb = (m.left, m.top, m.right, m.bottom) if m is not None else (size*0.75,)*4
    h_align, v_align = _justify(box, default_h='left', default_v='top')
    tx = {'left': x + ml, 'center': x + w/2, 'right': x + w - mr}[h_align]
    ty = {'top': y + mt, 'middle': y + h/2, 'bottom': y + h - mb}[v_align]
    text = _wrap_text(box.text, size, w - ml - mr)
    if text.strip():
        yield kicad_text_svg(text, tx, ty, size, h_align=h_align, v_align=v_align, stroke_width=_pen_width(box),
                             stroke=colorscheme.text)


def label_shape_path_d(shape, w, h):
    """ Outline of a global or hierarchical label of the given shape, height `h` and body width `w`, starting at the
    origin (the connection point) and extending towards +x. Each end is either pointed or square. """
    left, right = {
        Atom.input: '<]',
        Atom.output: '[>',
        Atom.bidirectional: '<>',
        Atom.tri_state: '<>',
        Atom.passive: '[]'}.get(shape, '<]')
    r = h/2

    if left == '[':
        d = f'M {r:.3f} {r:.3f} L 0 {r:.3f} L 0 {-r:.3f} L {r:.3f} {-r:.3f}'
    else:
        d = f'M {r:.3f} {r:.3f} L 0 0 L {r:.3f} {-r:.3f}'

    e = w+r
    d += f' L {e:.3f} {-r:.3f}'

    if right == ']':
        return d + f' L {e+r:.3f} {-r:.3f} L {e+r:.3f} {r:.3f} L {e:.3f} {r:.3f} Z'
    else:
        return d + f' L {e+r:.3f} {0:.3f} L {e:.3f} {r:.3f} Z'


@sexp_type('property')
class DrawnProperty(TextMixin):
    private: Flag() = False
    key: str = None
    value: str = None
    id: Named(int) = None
    at: AtPos = field(default_factory=AtPos)
    show_name: Named(LegacyCompatibleFlag()) = None
    do_not_autoplace: Named(LegacyCompatibleFlag()) = None
    hide: OmitDefault(Named(LegacyCompatibleFlag())) = False
    effects: TextEffect = field(default_factory=TextEffect)
    custom_properties: List(CustomProperty) = field(default_factory=list)
    _: SEXP_END = None
    parent: object = None

    def __after_parse__(self, parent=None):
        self.parent = parent

    # Alias value for text mixin
    @property
    def text(self):
        unit = getattr(self.parent, 'unit', 0)
        if self.key == 'Reference' and unit > 0 and getattr(self.parent, 'unit_count', 1) > 1:
            return f'{self.value}{string.ascii_uppercase[unit-1]}'
        else:
            return self.value

    @text.setter
    def text(self, value):
        self.value = value

    @property
    def default_v_align(self):
        return 'middle'

    @property
    def h_align(self):
        align = self.effects.justify.h_str
        if self.rotation in (90, 270):
            align = {'left': 'right', 'right': 'left'}.get(align, align)
        return align

    @property
    def rotation(self):
        rot = self.at.rotation
        rot += getattr(self.parent.at, 'rotation', 0)
        return rot%360

    @property
    def mirrored(self):
        if hasattr(self.parent, 'mirror'):
            return self.parent.mirror.x, self.parent.mirror.y
        return False, False

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        """ Like KiCad: lay out the text box in the symbol's untransformed frame from the field's justification and
        angle, transform it with the symbol, and draw the text centered on the result, horizontally or vertically.
        Fields of labels and sheets are not transformed. """
        if self.is_hidden or not self.value:
            return
        size = _text_size(self)
        lines = kicad_unescape(self.text).split('\n')
        w, h = kicad_text_width(self.text, size), size * (1 + (len(lines)-1) * KICAD_INTERLINE)
        h_align, v_align = _justify(self)

        sym = self.parent if isinstance(self.parent, SymbolInstance) else None
        if sym is not None:
            ox, oy = sym.at.x, sym.at.y
            # The symbol's transform of sheet-oriented vectors, and its inverse (it is orthogonal)
            (a, b), (c, d) = sym.transform_vector(1, 0), sym.transform_vector(0, -1)
            fwd = lambda x, y: (a*x + c*y, b*x + d*y)
            inv = lambda x, y: (a*x + b*y, c*x + d*y)
            swapped = abs(b) > 0.5
        else:
            ox, oy, fwd, inv, swapped = 0, 0, (lambda x, y: (x, y)), (lambda x, y: (x, y)), False

        px, py = inv(self.at.x - ox, self.at.y - oy)
        x0 = px + {'left': 0, 'center': -w/2, 'right': -w}[h_align]
        y0 = py + {'top': 0, 'middle': -h/2, 'bottom': -h}[v_align]
        corners = [(x0, y0), (x0 + w, y0 + h)]
        angle = round(self.at.rotation or 0) % 360
        for _ in range(angle // 90): # KiCad's RotatePoint() by 90 degrees about the text position
            corners = [(px + (y - py), py - (x - px)) for x, y in corners]
        corners = [fwd(x, y) for x, y in corners]
        cx = ox + (corners[0][0] + corners[1][0]) / 2
        cy = oy + (corners[0][1] + corners[1][1]) / 2
        vertical = (angle % 180 == 90) != swapped
        yield kicad_text_svg(self.text, cx, cy, size, h_align='center', v_align='middle', vertical=vertical,
                             stroke_width=_pen_width(self), stroke=colorscheme.values)


@dataclass
class TextLabel(TextMixin):
    text: str = ''
    shape: Named(AtomChoice(Atom.input, Atom.output, Atom.bidirectional, Atom.tri_state, Atom.passive, Atom.dot, Atom.round, Atom.diamond, Atom.rectangle)) = Atom.passive
    exclude_from_sim: Named(YesNoAtom()) = False
    at: AtPos = field(default_factory=AtPos)
    fields_autoplaced: Named(YesNoAtom()) = False
    effects: TextEffect = field(default_factory=TextEffect)
    uuid: UUID = field(default_factory=UUID)
    properties: List(DrawnProperty) = field(default_factory=list)
    locked: Named(YesNoAtom()) = None
    custom_properties: List(CustomProperty) = field(default_factory=list)


@sexp_type('text')
class Text(TextLabel):
    def to_svg(self, colorscheme=Colorscheme.KiCad):
        """ Like KiCad: horizontal or vertical (reading bottom to top) depending on the angle, aligned by its
        justification. Text at 180 or 270 degrees is stored with the justification that keeps it upright. """
        h_align, v_align = _justify(self)
        # KiCad moves all schematic text up by 0.25 mm "to match KiCad 6" (SCH_TEXT::GetSchematicTextOffset)
        yield kicad_text_svg(self.text, self.at.x, self.at.y - 0.25, _text_size(self), h_align=h_align,
                             v_align=v_align, vertical=_is_vertical(self), stroke_width=_pen_width(self),
                             stroke=colorscheme.text)


@sexp_type('label')
class LocalLabel(TextLabel):
    def to_svg(self, colorscheme=Colorscheme.KiCad):
        """ Like KiCad: the text sits on the wire, raised by KiCad's text offset plus the pen width, horizontal or
        vertical depending on the angle, and extending the way its justification says. """
        h_align, _v = _justify(self, default_h='left')
        vertical = _is_vertical(self)
        size, pen = _text_size(self), _pen_width(self)
        dist = 0.15*size + pen
        x, y = (self.at.x - dist, self.at.y) if vertical else (self.at.x, self.at.y - dist)
        yield kicad_text_svg(self.text, x, y, size, h_align=h_align, v_align='bottom', vertical=vertical,
                             stroke_width=pen, stroke=colorscheme.labels)
        for prop in self.properties:
            yield from prop.to_svg(colorscheme)


def _label_svg(label, colorscheme, text_offset, frame_d):
    """ SVG export shared by global and hierarchical labels. `frame_d` is the label's outline, drawn from the
    connection point towards +x, and the text starts `text_offset` from the connection point in the same direction.
    Like in KiCad, the direction is the label's spin style: horizontal or vertical by its angle, and pointing the
    way its justification says. The text stays upright. """
    x, y = label.at.x, label.at.y
    h_align, _v = _justify(label, default_h='left')
    vertical = _is_vertical(label)
    right = h_align != 'right'
    dx, dy = ((0, -1) if right else (0, 1)) if vertical else ((1, 0) if right else (-1, 0))
    rot = {(1, 0): 0, (0, -1): 90, (-1, 0): 180, (0, 1): 270}[dx, dy]
    text = kicad_text_svg(label.text, x + dx*text_offset, y + dy*text_offset, label.size,
                          h_align='left' if right else 'right', v_align='middle', vertical=vertical,
                          stroke_width=_pen_width(label), stroke=colorscheme.labels)
    frame = Tag('path', fill='none', stroke_width=0.254, stroke=colorscheme.lines, d=frame_d,
                transform=f'translate({x:.3f} {y:.3f}) rotate({-rot})')
    return Tag('g', children=[frame, text, *(t for prop in label.properties for t in prop.to_svg(colorscheme))])


@sexp_type('global_label')
class GlobalLabel(TextLabel):
    def to_svg(self, colorscheme=Colorscheme.KiCad):
        w = kicad_text_width(self.text, self.size)
        yield _label_svg(self, colorscheme, self.size*0.6,
                         label_shape_path_d(self.shape, w + self.size*0.2, self.size*1.2 + 0.254))


@sexp_type('hierarchical_label')
class HierarchicalLabel(TextLabel):
    def to_svg(self, colorscheme=Colorscheme.KiCad):
        yield _label_svg(self, colorscheme, self.size*1.2, label_shape_path_d(self.shape, 0, self.size))


@sexp_type('netclass_flag')
class NetclassFlag(TextLabel):
    length: Named(float) = 2.54

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        """ Like KiCad's SCH_DIRECTIVE_LABEL: a stem of `length` with a dot, circle, diamond or rectangle at its end,
        pointing the way of the label's spin style (up for the usual horizontal, left-justified label), plus the
        label's fields. """
        h_align, _v = _justify(self, default_h='left')
        right = h_align != 'right'
        # KiCad draws the flag downwards and turns it by the spin style
        # (KiCad's RotatePoint() turns (x, y) into (y, -x) for +90 degrees)
        turn = {(False, True): (-1, 0, 0, -1), (False, False): (1, 0, 0, 1),
                (True, True): (0, -1, 1, 0), (True, False): (0, 1, -1, 0)}[_is_vertical(self), right]
        pt = lambda u, v: (self.at.x + turn[0]*u + turn[1]*v, self.at.y + turn[2]*u + turn[3]*v)
        length, sym = self.length or 2.54, 0.508
        style = {'fill': 'none', 'stroke': colorscheme.lines, 'stroke_width': 0.254, 'stroke_linejoin': 'round',
                 'stroke_linecap': 'round'}
        shape = str(self.shape)
        if shape in ('dot', 'round'):
            r = sym * (0.7 if shape == 'dot' else 1)
            (x1, y1), (cx, cy) = pt(0, length - r), pt(0, length)
            yield Tag('path', d=f'M {self.at.x:.3f} {self.at.y:.3f} L {x1:.3f} {y1:.3f}', **style)
            yield Tag('circle', cx=f'{cx:.3f}', cy=f'{cy:.3f}', r=f'{r:.3f}',
                      **{**style, 'fill': colorscheme.lines if shape == 'dot' else 'none'})
        else:
            if shape == 'diamond':
                pts = [(0, 0), (0, length - sym), (-2*sym, length), (0, length + sym), (2*sym, length), (0, length - sym)]
            else: # rectangle
                r = sym * 0.8
                pts = [(0, 0), (0, length - r), (-2*r, length - r), (-2*r, length + r), (2*r, length + r),
                       (2*r, length - r), (0, length - r)]
            d = 'M ' + ' L '.join(f'{x:.3f} {y:.3f}' for x, y in (pt(u, v) for u, v in pts))
            yield Tag('path', d=d, **style)
        for prop in self.properties:
            yield from prop.to_svg(colorscheme)


@sexp_type('directive_label')
class DirectiveLabel(NetclassFlag):
    """ The same as a netclass flag. KiCad still reads this token, which some files use instead of netclass_flag. """


@sexp_type('pin')
class Pin:
    name: str = '1'
    uuid: UUID = field(default_factory=UUID)
    alternate: Named(str) = None
    custom_properties: List(CustomProperty) = field(default_factory=list)


@sexp_type('edit')
class PinMapEdit:
    pin: str = ''
    pad: str = ''


@sexp_type('pin_map_override')
class PinMapOverride:
    """ KiCad 10.99: which of its library symbol's pin maps a placed symbol (or one of its variants) uses. """
    mode: Named(AtomChoice(Atom.library_default, Atom.named_map, Atom.identity, Atom.delegate)) = None
    map: Named(str) = None
    edits: List(PinMapEdit) = field(default_factory=list)


@sexp_type('field')
class VariantField:
    name: Named(str) = ''
    value: Named(str) = ''


@sexp_type('variant')
class Variant:
    """ KiCad 10 assembly variant of a placed symbol or sheet. Attributes that are None are inherited. """
    name: Named(str) = ''
    dnp: Named(YesNoAtom()) = None
    exclude_from_sim: Named(YesNoAtom()) = None
    in_bom: Named(YesNoAtom()) = None
    on_board: Named(YesNoAtom()) = None
    in_pos_files: Named(YesNoAtom()) = None
    fields: List(VariantField) = field(default_factory=list)
    symbol_override: Named(str) = None
    pin_map_override: PinMapOverride = None


# Suddenly, we're doing syntax like this is yaml or something.
@sexp_type('path')
class SymbolCrosslinkSheet:
    path: str = ''
    reference: Named(str) = ''
    unit: Named(int) = 1
    value: OmitDefault(Named(str)) = None
    footprint: OmitDefault(Named(str)) = None
    variants: List(Variant) = field(default_factory=list)


@sexp_type('project')
class SymbolCrosslinkProject:
    project_name: str = ''
    instances: List(SymbolCrosslinkSheet) = field(default_factory=list)


@sexp_type('mirror')
class MirrorFlags:
    x: Flag() = False
    y: Flag() = False


@sexp_type('default_instance')
class DefaultSymbolInstance:
    reference: Named(str) = ''
    unit: Named(int) = 1
    value: Named(str) = ''
    footprint: Named(str) = ''


@sexp_type('symbol')
class SymbolInstance:
    name: str = None
    lib_name: Named(str) = ''
    lib_id: Named(str) = ''
    at: AtPos = field(default_factory=AtPos)
    mirror: OmitDefault(MirrorFlags) = field(default_factory=MirrorFlags)
    unit: Named(int) = 1
    # De Morgan body style. KiCad 9 renamed (convert ...) to (body_style ...).
    convert: Named(int) = None
    body_style: Named(int) = None
    exclude_from_sim: Named(YesNoAtom()) = False
    in_bom: Named(YesNoAtom()) = True
    on_board: Named(YesNoAtom()) = True
    in_pos_files: Named(YesNoAtom()) = None
    dnp: Named(YesNoAtom()) = False
    pin_map_override: PinMapOverride = None
    # KiCad 10.99: whether the symbol's footprint passes through pins to another sheet
    passthrough: Named(AtomChoice(Atom.default, Atom.block, Atom.force)) = None
    fields_autoplaced: Named(YesNoAtom()) = True
    uuid: UUID = field(default_factory=UUID)
    default_instance: DefaultSymbolInstance = None
    properties: List(DrawnProperty) = field(default_factory=list)
    # AFAICT this property is completely redundant.
    pins: List(Pin) = field(default_factory=list)
    # AFAICT this property, too,  is completely redundant. It ultimately just lists paths and references of at most
    # three other uses of the same symbol in this schematic.
    instances: Named(Array(SymbolCrosslinkProject)) = field(default_factory=list)
    locked: Named(YesNoAtom()) = None
    custom_properties: List(CustomProperty) = field(default_factory=list)
    _ : SEXP_END = None
    schematic: object = field(repr=False, default=None)

    def __after_parse__(self, parent):
        self.schematic = parent

    @property
    def reference(self):
        return self['Reference'].value

    @reference.setter
    def reference(self, value):
        self['Reference'].value = value

    @property
    def value(self):
        return self['Value'].value

    @value.setter
    def value(self, value):
        self['Value'].value = value

    @property
    def footprint(self):
        return self['Footprint'].value

    @footprint.setter
    def footprint(self, value):
        self['Footprint'].value = value

    def __getitem__(self, key):
        for prop in self.properties:
            if prop.key == key:
                return prop

    @property
    def rotation(self):
        return self.at.rotation

    def transform_vector(self, dx, dy):
        """ Turn a vector in library symbol coordinates (y pointing up) into sheet coordinates (y pointing down),
        following the symbol's rotation and mirroring. KiCad rotates first, then mirrors. """
        return lib_to_sheet_vector(dx, dy, self.at.rotation, self.mirror.x, self.mirror.y)

    def transform_point(self, x, y):
        """ Position of a point given in library symbol coordinates on the sheet. """
        dx, dy = self.transform_vector(x, y)
        return self.at.x + dx, self.at.y + dy

    @property
    def unit_count(self):
        """ Number of units of this symbol's library symbol, or 1 if it can't be found. """
        try:
            sym = self.schematic.lookup_symbol(self.lib_name, self.lib_id).resolve()
        except (AttributeError, KeyError):
            return 1
        return len({unit.unit_index for unit in sym.units} - {0}) or 1

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        children = []
        rot = self.at.rotation

        sym = self.schematic.lookup_symbol(self.lib_name, self.lib_id)

        units = [unit for unit in sym.units if unit.unit_global or unit.unit_index == self.unit]

        at_xform = xform = f'translate({self.at.x:.3f} {self.at.y:.3f})'
        if self.mirror.y:
            xform += f'scale(-1 -1)'
        elif self.mirror.x:
            xform += f'scale(1 1)'
        else:
            xform += f'scale(1 -1)'
        if rot:
            xform += f'rotate({rot})'

        children = [foo for unit in units for elem in unit.graphical_elements for foo in elem.to_svg(colorscheme)]
        yield Tag('g', children=children, transform=xform, fill=colorscheme.fill, stroke=colorscheme.lines)

        children = [foo for unit in units for pin in unit.pins for foo in pin.to_svg(colorscheme, self.mirror, rot)]
        yield Tag('g', children=children, transform=at_xform, fill=colorscheme.fill, stroke=colorscheme.lines)

        for prop in self.properties:
            yield from prop.to_svg(colorscheme)


@sexp_type('path')
class SubsheetCrosslinkSheet:
    path: str = ''
    page: Named(str) = ''
    variants: List(Variant) = field(default_factory=list)


@sexp_type('project')
class SubsheetCrosslinkProject:
    project_name: str = ''
    instances: List(SubsheetCrosslinkSheet) = field(default_factory=list)


@sexp_type('pin')
class SubsheetPin:
    name: str = '1'
    shape: AtomChoice(Atom.input, Atom.output, Atom.bidirectional, Atom.tri_state, Atom.passive) = Atom.input
    at: AtPos = field(default_factory=AtPos)
    effects: TextEffect = field(default_factory=TextEffect)
    uuid: UUID = field(default_factory=UUID)
    locked: Named(YesNoAtom()) = None
    custom_properties: List(CustomProperty) = field(default_factory=list)
    _ : SEXP_END = None
    subsheet: object = None

    def __after_parse__(self, parent):
        self.subsheet = parent

    def to_svg(self):
        size = self.effects.font.size.y or 1.27
        yield Tag('path', fill='none', d=label_shape_path_d(self.shape, 0, size+0.5),
                  transform=f'translate({self.at.x:.3f} {self.at.y:.3f}) rotate({180-self.at.rotation})')

        # pins sit on the sheet's edge, pointing out of it; the text goes inwards
        rot = round(self.at.rotation or 0) % 360
        dx, dy = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}.get(rot, (-1, 0))
        vertical = rot in (90, 270)
        inward_aligned = (dy < 0) if vertical else (dx > 0)
        yield kicad_text_svg(self.name, self.at.x + dx*(size+1), self.at.y + dy*(size+1), size,
                             h_align='left' if inward_aligned else 'right', v_align='middle', vertical=vertical)

@sexp_type('fill')
class SubsheetFill:
    color: Color = field(default_factory=lambda: Color(0, 0, 0, 0))


@sexp_type('sheet')
class Subsheet:
    at: Rename(XYCoord) = field(default_factory=XYCoord)
    size: Rename(XYCoord) = field(default_factory=lambda: XYCoord(2.54, 2.54))
    exclude_from_sim: Named(YesNoAtom()) = False
    in_bom: Named(YesNoAtom()) = False
    on_board: Named(YesNoAtom()) = False
    dnp: Named(YesNoAtom()) = False
    fields_autoplaced: Named(YesNoAtom()) = True
    stroke: Stroke = field(default_factory=Stroke)
    fill: SubsheetFill = field(default_factory=SubsheetFill)
    uuid: UUID = field(default_factory=UUID)
    _properties: List(DrawnProperty) = field(default_factory=list)
    pins: List(SubsheetPin) = field(default_factory=list)
    # AFAICT this is completely redundant, just like the one in SymbolInstance
    instances: Named(Array(SubsheetCrosslinkProject)) = field(default_factory=list)
    custom_properties: List(CustomProperty) = field(default_factory=list)
    _ : SEXP_END = None
    sheet_name: object = field(default_factory=lambda: DrawnProperty(key='Sheetname', value=''))
    file_name: object = field(default_factory=lambda: DrawnProperty(key='Sheetfile', value=''))
    extra_properties: list = field(default_factory=list)
    schematic: object = field(repr=False, default=None)

    def __after_parse__(self, parent):
        self.sheet_name, self.file_name, *self.extra_properties = self._properties
        self.schematic = parent

    def __before_sexp__(self):
        self._properties = [self.sheet_name, self.file_name, *self.extra_properties]

    @property
    def rotation(self):
        return 0

    def open(self, search_dir=None, safe=True):
        if search_dir is None:
            if not self.schematic.original_filename:
                raise FileNotFoundError('No search path given and path of parent schematic unknown')
            else:
                search_dir = Path(self.schematic.original_filename).parent
        else:
            search_dir = Path(search_dir)

        resolved = search_dir / self.file_name.value
        if safe and os.path.commonprefix((search_dir.parts, resolved.parts)) != search_dir.parts:
                raise ValueError('Subsheet path traversal to parent directory attempted in Subsheet.open(..., safe=True)')

        return Schematic.open(resolved)

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        children = []

        for prop in self._properties:
            yield from prop.to_svg(colorscheme)

        yield Tag('rect', x=f'{self.at.x:.3f}', y=f'{self.at.y:.3f}',
                  width=f'{self.size.x:.3f}', height=f'{self.size.y:.3f}',
                  **self.stroke.svg_attrs(colorscheme.lines), fill=self.fill.color.svg(colorscheme.fill))

        children = []
        for pin in self.pins:
            children += pin.to_svg()

        #xform = f'translate({self.at.x:.3f} {self.at.y:.3f})'
        yield Tag('g', children=children, #transform=xform,
                  fill=self.fill.color.svg(colorscheme.fill),
                  **self.stroke.svg_attrs(colorscheme.lines))


@sexp_type('rule_area')
class RuleArea:
    # KiCad 10 lets rule areas set these attributes of the symbols inside them.
    exclude_from_sim: Named(YesNoAtom()) = None
    in_bom: Named(YesNoAtom()) = None
    on_board: Named(YesNoAtom()) = None
    dnp: Named(YesNoAtom()) = None
    polyline: Polyline = None
    locked: Named(YesNoAtom()) = None
    custom_properties: List(CustomProperty) = field(default_factory=list)

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        if self.polyline is None or len(self.polyline.points) < 3:
            return
        p0, *rest = self.polyline.points
        d = f'M {p0.x:.3f} {p0.y:.3f} ' + ' '.join(f'L {p.x:.3f} {p.y:.3f}' for p in rest) + ' Z'
        yield _shape_svg(self.polyline, colorscheme, d=d)


@sexp_type('text_box')
class TextBox(TextMixin):
    text: str = None
    exclude_from_sim: Named(YesNoAtom()) = False
    at: AtPos = field(default_factory=AtPos)
    size: Rename(XYCoord) = None
    margins: Rename(gr.Margins) = None
    effects: TextEffect = field(default_factory=TextEffect)
    stroke: Stroke = field(default_factory=Stroke)
    fill: OmitDefault(Fill) = None
    effects: TextEffect = field(default_factory=TextEffect)
    uuid: UUID = field(default_factory=UUID)
    locked: Named(YesNoAtom()) = None
    custom_properties: List(CustomProperty) = field(default_factory=list)

    def render(self, variables={}, cache=None):
        yield from gr.TextBox.render(self, variables=variables)

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        yield from _text_box_svg(self, colorscheme)


@sexp_type('border')
class TableBorder:
    external: Named(YesNoAtom()) = True
    header: Named(YesNoAtom()) = True
    stroke: Stroke = field(default_factory=Stroke)


@sexp_type('separators')
class TableSeparators:
    rows: Named(YesNoAtom()) = True
    cols: Named(YesNoAtom()) = True
    stroke: Stroke = field(default_factory=Stroke)


@sexp_type('span')
class TableCellSpan:
    columns: int = 1
    rows: int = 1


@sexp_type('table_cell')
class TableCell:
    text: str = ''
    exclude_from_sim: Named(YesNoAtom()) = False
    at: AtPos = field(default_factory=AtPos)
    size: Rename(XYCoord) = field(default_factory=XYCoord)
    margins: Margins = None
    span: TableCellSpan = field(default_factory=TableCellSpan)
    fill: OmitDefault(Fill) = None
    effects: TextEffect = field(default_factory=TextEffect)
    uuid: UUID = field(default_factory=UUID)
    locked: Named(YesNoAtom()) = None
    custom_properties: List(CustomProperty) = field(default_factory=list)


@sexp_type('table')
class Table:
    """ A table of text cells. Cells are listed row by row, and cells covered by another cell's span are still listed
    (with empty text). """
    column_count: Named(int) = 1
    border: TableBorder = field(default_factory=TableBorder)
    separators: TableSeparators = field(default_factory=TableSeparators)
    column_widths: Named(Array(float)) = field(default_factory=list)
    row_heights: Named(Array(float)) = field(default_factory=list)
    cells: Named(Array(TableCell)) = field(default_factory=list)
    uuid: UUID = None
    custom_properties: List(CustomProperty) = field(default_factory=list)

    @property
    def rows(self):
        n = self.column_count
        return [self.cells[i:i+n] for i in range(0, len(self.cells), n)]

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        """ The cells' fills and text, then the separators and the border. Cells merged by spans still get the
        separators that would run through them. """
        if not self.cells:
            return
        for cell in self.cells:
            yield from _text_box_svg(cell, colorscheme, border=False)

        x0, y0 = self.cells[0].at.x, self.cells[0].at.y
        xs = [x0 + sum(self.column_widths[:i]) for i in range(len(self.column_widths) + 1)]
        ys = [y0 + sum(self.row_heights[:i]) for i in range(len(self.row_heights) + 1)]
        if len(xs) < 2 or len(ys) < 2:
            return
        line = lambda x1, y1, x2, y2, stroke: Tag('path', d=f'M {x1:.3f} {y1:.3f} L {x2:.3f} {y2:.3f}', fill='none',
                                                  **(stroke or Stroke()).svg_attrs(colorscheme.lines))
        sep, border = self.separators, self.border
        if sep is not None and sep.cols:
            for x in xs[1:-1]:
                yield line(x, ys[0], x, ys[-1], sep.stroke)
        if sep is not None and sep.rows:
            for y in ys[2 if border is not None and border.header else 1:-1]:
                yield line(xs[0], y, xs[-1], y, sep.stroke)
        if border is not None and border.header and len(ys) > 2:
            yield line(xs[0], ys[1], xs[-1], ys[1], border.stroke)
        if border is not None and border.external:
            yield Tag('rect', x=f'{xs[0]:.3f}', y=f'{ys[0]:.3f}', width=f'{xs[-1]-xs[0]:.3f}',
                      height=f'{ys[-1]-ys[0]:.3f}', fill='none',
                      **(border.stroke or Stroke()).svg_attrs(colorscheme.lines))


@sexp_type('from')
class NetChainEnd:
    reference: str = ''
    pin: str = ''


@sexp_type('to')
class NetChainStart(NetChainEnd):
    pass


@sexp_type('net_chain')
class NetChain:
    """ KiCad 10.99: a chain of nets from one symbol pin to another. """
    name: str = ''
    start: NetChainEnd = None
    end: NetChainStart = None
    net_class: Named(str) = None
    color: Color = None
    nets: Named(Array(str)) = field(default_factory=list)
    # Some files list member items by uuid here. KiCad skips them, we keep them.
    uuids: List(UUID) = field(default_factory=list)


@sexp_type('group')
class SchematicGroup:
    """ Group of schematic items, given by their uuids. Unlike PCB groups, schematic groups write (locked yes) after
    the name. """
    name: str = ''
    uuid: UUID = field(default_factory=UUID)
    locked: Named(YesNoAtom()) = None
    members: Named(Array(str)) = field(default_factory=list)
    custom_properties: List(CustomProperty) = field(default_factory=list)


@sexp_type('lib_symbols')
class LocalLibrary:
    symbols: List(Symbol) = field(default_factory=list)

    def __getitem__(self, name):
        return _lookup_symbol(self.symbols, name)


SUPPORTED_FILE_FORMAT_VERSIONS = [20230620]
@sexp_type('kicad_sch')
class Schematic:
    _version: Named(int, name='version') = 20230620
    generator: Named(str) = 'gerbonara'
    generator_version: Named(str) = __version__
    legacy_generator: Named(Array(str), name='host') = None
    uuid: UUID = field(default_factory=UUID)
    page_settings: PageSettings = field(default_factory=PageSettings)
    legacy_page: Named(Array(int), name='page') = None
    title_block: TitleBlock = None
    # The doc says this is expected, but eeschema barfs when it's there.
    # path: SheetPath = field(default_factory=SheetPath)
    lib_symbols: LocalLibrary = field(default_factory=LocalLibrary)
    junctions: List(Junction) = field(default_factory=list)
    no_connects: List(NoConnect) = field(default_factory=list)
    rule_areas: List(RuleArea) = field(default_factory=list)
    netclass_flags: List(NetclassFlag) = field(default_factory=list)
    directive_labels: List(DirectiveLabel) = field(default_factory=list)
    bus_aliases: List(BusAlias) = field(default_factory=list)
    bus_entries: List(BusEntry) = field(default_factory=list)
    wires: List(Wire) = field(default_factory=list)
    buses: List(Bus) = field(default_factory=list)
    images: List(gr.Image) = field(default_factory=list)
    polylines: List(Polyline) = field(default_factory=list)
    circles: List(Circle) = field(default_factory=list)
    rectangles: List(Rectangle) = field(default_factory=list)
    arcs: List(Arc) = field(default_factory=list)
    beziers: List(Bezier) = field(default_factory=list)
    ellipses: List(Ellipse) = field(default_factory=list)
    ellipse_arcs: List(EllipseArc) = field(default_factory=list)
    net_chains: List(NetChain) = field(default_factory=list)
    texts: List(Text) = field(default_factory=list)
    text_boxes: List(TextBox) = field(default_factory=list)
    tables: List(Table) = field(default_factory=list)
    local_labels: List(LocalLabel) = field(default_factory=list)
    global_labels: List(GlobalLabel) = field(default_factory=list)
    hierarchical_labels: List(HierarchicalLabel) = field(default_factory=list)
    symbols: List(SymbolInstance) = field(default_factory=list)
    subsheets: List(Subsheet) = field(default_factory=list)
    groups: List(SchematicGroup) = field(default_factory=list)
    sheet_instances: Named(Array(SubsheetCrosslinkSheet)) = field(default_factory=list)
    symbol_instances: Named(Array(SymbolCrosslinkSheet)) = field(default_factory=list)
    embedded_fonts: Named(YesNoAtom()) = False
    embedded_files: EmbeddedFiles = None
    _ : SEXP_END = None
    original_filename: str = None

    @property
    def version(self):
        return self._version

    @version.setter
    def version(self, value):
        if value not in SUPPORTED_FILE_FORMAT_VERSIONS:
            raise FormatError(f'File format version {value} is not supported. Supported versions are {", ".join(map(str, SUPPORTED_FILE_FORMAT_VERSIONS))}.')


    def lookup_symbol(self, lib_name, lib_id):
        key = lib_name or lib_id
        for sym in self.lib_symbols.symbols:
            if sym.name == key or sym.raw_name == key:
                return sym
        raise KeyError(f'Symbol with {lib_name=} {lib_id=} not found')

    def write(self, filename=None):
        with open(filename or self.original_filename, 'w') as f:
            f.write(self.serialize())

    def serialize(self):
        return build_sexp(sexp(type(self), self)[0])

    @classmethod
    def open(kls, pcb_file, *args, **kwargs):
        return kls.load(Path(pcb_file).read_text(), *args, **kwargs, original_filename=pcb_file)

    @classmethod
    def load(kls, data, *args, **kwargs):
        return kls.parse(data, *args, **kwargs)

    @property
    def elements(self):
        yield from self.subsheets
        yield from self.images
        yield from self.rule_areas
        yield from self.polylines
        yield from self.rectangles
        yield from self.circles
        yield from self.arcs
        yield from self.beziers
        yield from self.symbols
        yield from self.junctions
        yield from self.no_connects
        yield from self.bus_entries
        yield from self.wires
        yield from self.buses
        yield from self.ellipses
        yield from self.ellipse_arcs
        yield from self.text_boxes
        yield from self.tables
        yield from self.texts
        yield from self.local_labels
        yield from self.global_labels
        yield from self.hierarchical_labels
        yield from self.netclass_flags
        yield from self.directive_labels

    def to_svg(self, colorscheme=Colorscheme.KiCad):
        children = []
        for elem in self.elements:
            children += elem.to_svg(colorscheme)
        w, h = self.page_settings.size
        return setup_svg(children, ((0, 0), (w, h)), pagecolor=colorscheme.background)


    
# From: https://jakevdp.github.io/blog/2012/10/07/xkcd-style-plots-in-matplotlib/
#def xkcd_line(x, y, xlim=None, ylim=None, mag=1.0, f1=30, f2=0.05, f3=15):
def xkcd_line(x, y, xlim=None, ylim=None, mag=1.0, f1=10, f2=0.05, f3=5):
    """
    Mimic a hand-drawn line from (x, y) data

    Parameters
    ----------
    x, y : array_like
        arrays to be modified
    xlim, ylim : data range
        the assumed plot range for the modification.  If not specified,
        they will be guessed from the  data
    mag : float
        magnitude of distortions
    f1, f2, f3 : int, float, int
        filtering parameters.  f1 gives the size of the window, f2 gives
        the high-frequency cutoff, f3 gives the size of the filter
    
    Returns
    -------
    x, y : ndarrays
        The modified lines
    """
    import numpy as np
    from scipy import interpolate, signal

    x = np.asarray(x)
    y = np.asarray(y)
    
    # get limits for rescaling
    if xlim is None:
        xlim = (x.min(), x.max())
    if ylim is None:
        ylim = (y.min(), y.max())

    if xlim[1] == xlim[0]:
        xlim = ylim
        
    if ylim[1] == ylim[0]:
        ylim = xlim

    # scale the data
    x_scaled = (x - xlim[0]) * 1. / (xlim[1] - xlim[0])
    y_scaled = (y - ylim[0]) * 1. / (ylim[1] - ylim[0])

    # compute the total distance along the path
    dx = x_scaled[1:] - x_scaled[:-1]
    dy = y_scaled[1:] - y_scaled[:-1]
    dist_tot = np.sum(np.sqrt(dx * dx + dy * dy))

    # number of interpolated points is proportional to the distance
    Nu = int(50 * dist_tot)
    u = np.arange(-1, Nu + 1) * 1. / (Nu - 1)

    # interpolate curve at sampled points
    k = min(3, len(x) - 1)
    res = interpolate.splprep([x_scaled, y_scaled], s=0, k=k)
    x_int, y_int = interpolate.splev(u, res[0]) 

    # we'll perturb perpendicular to the drawn line
    dx = x_int[2:] - x_int[:-2]
    dy = y_int[2:] - y_int[:-2]
    dist = np.sqrt(dx * dx + dy * dy)

    # create a filtered perturbation
    coeffs = mag * np.random.normal(0, 0.01, len(x_int) - 2)
    b = signal.firwin(f1, f2 * dist_tot, window=('kaiser', f3))
    response = signal.lfilter(b, 1, coeffs)

    x_int[1:-1] += response * dy / dist
    y_int[1:-1] += response * dx / dist

    # un-scale data
    x_int = x_int[1:-1] * (xlim[1] - xlim[0]) + xlim[0]
    y_int = y_int[1:-1] * (ylim[1] - ylim[0]) + ylim[0]
    
    return x_int, y_int

def wonkify(path):
    out = []
    for segment in path.attrs['d'].split('M')[1:]:
        if 'A' in segment:
            out.append(segment)
            continue

        points = segment.split('L')
        if points[-1].rstrip().endswith('Z'):
            closed = True
            points[-1] = points[-1].rstrip()[:-1].rstrip()
            points.append(points[0])
        else:
            closed = False

        pts = []
        lx, ly = None, None
        for pt in points:
            x, y = pt.strip().split()
            x, y = float(x), float(y)
            if (x, y) == (lx, ly):
                continue

            lx, ly = x, y
            pts.append((x, y))

        if len(pts) == 2:
            segs = [pts]

        else:
            seg = [pts[0]]
            segs = [seg]
            for p0, p1, p2 in zip(pts[0::], pts[1::], pts[2::]):
                dx1, dy1 = p1[0] - p0[0], p1[1] - p0[1]
                dx2, dy2 = p2[0] - p1[0], p2[1] - p1[1]
                l1, l2 = math.hypot(dx1, dy1), math.hypot(dx2, dy2)
                a1, a2 = math.atan2(dy1, dx1), math.atan2(dy2, dx2)
                da = (a2 - a1 + math.pi) % (2*math.pi) - math.pi
                if abs(da) > math.pi/4 and l1+l2 > 3:
                    seg.append(p1)
                    seg = [p1, p2]
                    segs.append(seg)
                seg.append(p1)
            seg.append(p2)

        for seg in segs:
            xs, ys = [x for x, y in seg], [y for x, y in seg]
            xs, ys = xkcd_line(xs, ys)
            d = ' L '.join(f'{x:.3f} {y:.3f}' for x, y in zip(xs, ys))
            if closed:
                d += ' Z'
            out.append(d)

    path.attrs['d'] = ' '.join(f'M {seg}' for seg in out)


def postprocess(tag):
    if tag.name == 'path':
        wonkify(tag)
    else:
        for child in tag.children:
            postprocess(child)
    return tag

if __name__ == '__main__':
    import sys
    from ...layers import LayerStack
    from .tmtheme import *
    sch = Schematic.open(sys.argv[1])
    print('Loaded schematic with', len(sch.wires), 'wires and', len(sch.symbols), 'symbols.')
    for subsh in sch.subsheets:
        subsh = subsh.open()
        print('Loaded sub-sheet with', len(subsh.wires), 'wires and', len(subsh.symbols), 'symbols.')

    sch.write('/tmp/test.kicad_sch')
    for p in Path('/tmp').glob('*.tmTheme'):
        cs = TmThemeSchematic(p.read_text())
        Path(f'/tmp/test-{p.stem}.svg').write_text(str(postprocess(sch.to_svg(cs))))
    for p in Path('/tmp').glob('*.sublime-color-scheme'):
        cs = SublimeSchematic(p.read_text())
        Path(f'/tmp/test-{p.stem}.svg').write_text(str(postprocess(sch.to_svg(cs))))

