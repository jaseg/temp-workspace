
# Copyright 2025 Jan Sebastian Götte <code@jaseg.de>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import warnings
import logging
from dataclasses import dataclass, field
import sys
from math import *

from gerbonara.cad.kicad.footprints import Footprint
from gerbonara.cad.kicad.primitives import Zone, Hatch, ZoneKeepout, ZonePolygon, XYCoord

from . import kicad, skeletonator


mu_0 = 1.25663706127e-06 # from scipy.constants


def point_line_distance(p, l1, l2):
    x0, y0 = p
    x1, y1 = l1
    x2, y2 = l2
    # https://en.wikipedia.org/wiki/Distance_from_a_point_to_a_line
    return ((x2-x1)*(y1-y0) - (x1-x0)*(y2-y1)) / sqrt((x2-x1)**2 + (y2-y1)**2)


# https://en.wikipedia.org/wiki/Farey_sequence#Next_term
def farey_sequence(n: int, descending: bool = False) -> None:
    """Print the n'th Farey sequence. Allow for either ascending or descending."""
    a, b, c, d = 0, 1, 1, n
    if descending:
        a, c = 1, n - 1
    yield a, b

    while c <= n and not descending or a > 0 and descending:
        k = (n + b) // d
        a, b, c, d = c, d, k * c - a, k * d - b
        yield a, b


def divisors(n, max_b=10):
    for a, b in farey_sequence(n):
        if a != 0 and a == n and b < max_b:
            yield b
        if b != 1 and b == n and a < max_b:
            yield a


def arc_approximate(points, trace_width, layer, tolerance=0.02, level=0):
    """ Approximate spiral arm using circular arcs. This results in a smoother output using less segments than if we
    approximate the arc using straight line segments.

    The input to this function is a list of points of a straight line segment approximation, and it returns a list of
    gerbonara arc objects approximating the input. """ 
    indent = '    ' * level
    if len(points) < 3:
        raise ValueError('Need at least three points to approximate')

    i_mid = len(points)//2

    x0, y0 = points[0]
    x1, y1 = points[i_mid]
    x2, y2 = points[-1]

    if len(points) < 5:
        yield kicad.make_arc(x0, y0, x2, y2, x1, y1, trace_width, layer)

    # https://stackoverflow.com/questions/56224824/how-do-i-find-the-circumcenter-of-the-triangle-using-python-without-external-lib
    d = 2 * (x0 * (y2 - y1) + x2 * (y1 - y0) + x1 * (y0 - y2))
    cx = ((x0 * x0 + y0 * y0) * (y2 - y1) + (x2 * x2 + y2 * y2) * (y1 - y0) + (x1 * x1 + y1 * y1) * (y0 - y2)) / d
    cy = ((x0 * x0 + y0 * y0) * (x1 - x2) + (x2 * x2 + y2 * y2) * (x0 - x1) + (x1 * x1 + y1 * y1) * (x2 - x0)) / d
    r = dist((cx, cy), (x1, y1))
    if any(abs(dist((px, py), (cx, cy)) - r) > tolerance for px, py in points):
        yield from arc_approximate(points[:i_mid+1], trace_width, layer, tolerance, level+1)
        yield from arc_approximate(points[i_mid:], trace_width, layer, tolerance, level+1)

    else:
        if point_line_distance((x1, y1), (x0, y0), (x2, y2)) > 0:
            yield kicad.make_arc(x0, y0, x2, y2, x1, y1, trace_width, layer)
        else:
            yield kicad.make_arc(x2, y2, x0, y0, x1, y1, trace_width, layer)


class Shape:
    pass


@dataclass
class CircleShape(Shape):
    outer_diameter: float
    inner_diameter: float


    def __post_init__(self):
        self.outer_radius = self.outer_diameter / 2
        self.inner_radius = self.inner_diameter / 2


    @property
    def slug(self):
        return 'circle_{self.outer_diameter:.2f}x{self.inner_diameter:.2f}'


    @property
    def desc(self):
        return f'{self.outer_diameter:.2f} mm OD, {self.inner_diameter:.2f} mm ID circular'


    def compute_spiral(self, a1, a2, fn=64):
        r1, r2 = self.outer_radius, self.inner_radius
        fn = ceil(fn * abs(a2-a1)/(2*pi))
        x0, y0 = cos(a1)*r1, sin(a1)*r1
        dr = 3 if r2 < r1 else -3

        xn, yn = x0, y0
        points = [(x0, y0)]
        dists = []
        for i in range(fn):
            xp, yp = xn, yn
            r = r1 + (i+1)*(r2-r1)/fn
            a = a1 + (i+1)*(a2-a1)/fn
            xn, yn = cos(a)*r, sin(a)*r
            points.append((xn, yn))
            dists.append(dist((xp, yp), (xn, yn)))

        return points, sum(dists), [None]*len(points)


    def project_point(self, r, a, r_ref=None):
        return cos(a) * r, sin(a) * r


    def offset_exterior(self, margin):
        r = self.outer_radius + margin
        tol = 0.05 # mm
        n = ceil(pi / acos(1 - tol/r))
        return [(r*cos(a*2*pi/n), r*sin(a*2*pi/n)) for a in range(n)]


class OffsetShape(Shape):
    def __post_init__(self):
        self.sk = skeletonator.Skeletonator(self.polygon)
        self.outer_radius = self.sk.radius
        self.inner_radius = self.sk.radius - self.annular_width

    @property
    def slug(self):
        return 'polygonal_{len(self.polygon)}pt_r{self.radius:.2f}mm'


    @property
    def desc(self):
        return f'polygonal (n={len(self.polygon)} point, r={self.radius:.2f} mm radius)'


    def compute_spiral(self, a1, a2, fn=None):
        # Skeletonator uses a t coordinate from 0 - 1 per revolution instead of a radian angle.
        points = []
        angle_refs = []
        for point, angle_ref in self.sk.do_spiral(a1/(2*pi), a2/(2*pi), self.outer_radius, self.inner_radius):
            points.append(point)
            angle_refs.append(angle_ref)
        if a2 < a1:
            points = points[::-1]
            angle_refs = angle_refs[::-1]
        arm_length = sum(dist(p1, p2) for p1, p2 in zip(points, points[1:]))
        return points, arm_length, angle_refs


    def project_point(self, r, a, r_ref=None):
        # Skeletonator uses a t coordinate from 0 - 1 per revolution instead of a radian angle.
        return self.sk.project_point(a/(2*pi) % 1, r, r_ref=r_ref)


    def offset_exterior(self, margin):
        return self.sk.do_spiral(0, 1, self.outer_radius + margin, self.outer_radius + margin)


@dataclass
class TrapezoidShape(OffsetShape):
    width: float
    height: float
    offset: float
    annular_width: float
    arc_tolerance: float = 0.05 # mm
    polygon: list = field(init=False)

    def __post_init__(self):
        w, h, d = self.width, self.height, self.offset
        self.polygon = [(w/2-d, -h/2), (w/2, h/2), (-w/2, h/2), (-w/2+d, -h/2)]
        super().__post_init__()
    
    @property
    def slug(self):
        return f'trapezoid_{self.width:.2f}-2*{self.offset:.2f}x{self.height:.2f}'
    
    @property
    def desc(self):
        return f'{self.width:.2f} x {self.height:.2f} mm, {self.offset:.2f} mm offset isosceles trapezoidal'


@dataclass
class RectangleShape(OffsetShape):
    width: float
    height: float
    annular_width: float
    arc_tolerance: float = 0.05 # mm
    polygon: list = field(init=False)

    def __post_init__(self):
        w, h = self.width, self.height
        self.polygon = [(w/2, -h/2), (w/2, h/2), (-w/2, h/2), (-w/2, -h/2)]
        super().__post_init__()
    
    @property
    def slug(self):
        return f'rectangle_{self.width:.2f}x{self.height:.2f}'
    
    @property
    def desc(self):
        return f'{self.width:.2f} x {self.height:.2f} mm rectangle'

@dataclass
class SectorShape(OffsetShape):
    inner_diameter: float
    outer_diameter: float
    angle: float
    annular_width: float
    arc_tolerance: float = 0.05 # mm
    polygon: list = field(init=False)

    def __post_init__(self):
        # Careful: The inner/outer radius properties are relative to the polygon center and are very different from these!
        r1, r2 = self.inner_diameter / 2, self.outer_diameter/2
        n1 = ceil(pi / acos(1 - self.arc_tolerance/self.inner_diameter) * self.angle / (2*pi))
        n2 = ceil(pi / acos(1 - self.arc_tolerance/self.outer_diameter) * self.angle / (2*pi))
        # center on y axis
        pt = lambda r, a: (r*sin(a), r*cos(a))
        self.polygon  = [pt(r2, self.angle/2 - i/n1 * self.angle) for i in range(n1+1)]
        self.polygon += [pt(r1, i/n1 * self.angle - self.angle/2) for i in range(n1+1)]
        super().__post_init__()
    
    @property
    def slug(self):
        return f'sector_{self.outer_diameter:.2f}x{self.inner_diameter:.2f}_{degrees(self.angle):.0f}deg'
    
    @property
    def desc(self):
        return f'{self.outer_diameter:.2f} x {self.inner_diameter:.2f} mm {degrees(self.angle):.0f} deg sector'


@dataclass
class StarShape(OffsetShape):
    inner_diameter: float
    outer_diameter: float
    annular_width: float
    points: int = 5
    arc_tolerance: float = 0.05 # mm
    polygon: list = field(init=False)

    def __post_init__(self):
        # center on y axis
        pt = lambda r, a: (-r*sin(a), r*cos(a))
        circle = lambda r, n, phase: [pt(r, (i + phase)*2*pi/n) for i in range(n)]
        self.polygon  = [x for pair in zip(circle(self.outer_diameter/2, self.points, 0), circle(self.inner_diameter/2, self.points, 0.5)) for x in pair]
        super().__post_init__()
    
    @property
    def slug(self):
        return f'star_{self.outer_diameter:.2f}x{self.inner_diameter:.2f}'
    
    @property
    def desc(self):
        purpose = ', for demonic purposes' if self.points == 5 else ''
        return f'{self.outer_diameter:.2f} x {self.inner_diameter:.2f} mm star shape{purpose}'


@dataclass
class RegularPolygonShape(OffsetShape):
    diameter: float
    annular_width: float
    corners: int = 8
    arc_tolerance: float = 0.05 # mm
    polygon: list = field(init=False)

    def __post_init__(self):
        # center on y axis
        pt = lambda r, a: (-r*sin(a), r*cos(a))
        circle = lambda r, n, phase: [pt(r, (i + phase)*2*pi/n) for i in range(n)]
        self.polygon  = list(circle(self.diameter/2, self.corners, 0))
        print(self.polygon)
        super().__post_init__()
    
    @property
    def slug(self):
        return f'regular_{self.corners}gon_{self.diameter:.2f}'
    
    @property
    def desc(self):
        return f'{self.diameter:.2f} mm diameter {self.corners} corner regular polygon'


@dataclass
class SVGShape(OffsetShape):
    filename: str
    annular_width: float
    arc_tolerance: float = 0.05 # mm
    polygon: list = field(init=False)

    def __post_init__(self):
        # center on y axis
        from bs4 import BeautifulSoup
        with open(self.filename) as f:
            soup = BeautifulSoup(f.read(), features='xml')
            path = soup.find('path', recursive=True)
            d = path.attrs['d']
            d = d.strip('MmZ ').replace(',', 'L')
            coord_pairs = d.split('L')
            coords = list(reversed([tuple(map(float, pair.split())) for pair in coord_pairs]))
            # Calculate bounding box
            min_x = min(x for x, _y in coords)
            min_y = max(x for x, _y in coords)
            max_x = min(y for _x, y in coords)
            max_y = max(y for _x, y in coords)
            if max_x < 0 or max_y < 0 or min_x > 0 or min_y > 0:
                # (0, 0) is not within the polygon's axis-aligned bounding box, recenter.
                ox, oy = skeletonator.polygon_center_of_mass(coords)
                warnings.warn(f'Polygon looks not centered, bounds are ({min_x:.2f}, {min_y:.2f}), ({max_x:.2f}, {max_y:.2f}). Aligning (0, 0) with polygon centroid at ({ox:.2f}, {oy:.2f})')
                coords = [(x-ox, y-oy) for x, y in coords]
        self.polygon  = coords
        super().__post_init__()
    
    @property
    def slug(self):
        return f'svg_{len(self.polygon)}n'
    
    @property
    def desc(self):
        return f'{len(self.polygon)} node imported SVG shape'

@dataclass
class PlanarInductor():
    shape: Shape
    turns: int
    twists: int
    trace_width: float = None
    clearance: float = None
    layers: int = 2
    via_diameter: float = 0.6
    via_drill: float = None
    via_offset: float = None
    stagger_inner_vias: bool = False
    stagger_outer_vias: bool = False
    keepout_zone: bool = True
    keepout_margin: float = 0.0
    copper_thickness: float = 0.035
    layer_pair: str = 'F.Cu,B.Cu'
    clockwise: bool = False
    approximate_arcs: bool = True

    def __post_init__(self):
        self.logger = logging.getLogger('kicoil')
        self.turns_per_layer = self.turns/self.layers
        self.sector_angle = 2*pi / self.twists

        if self.clockwise:
            self.sector_angle *= -1
            
        self.sweeping_angle = self.sector_angle * self.turns_per_layer
        self.spiral_pitch = (self.shape.outer_radius-self.shape.inner_radius) / self.turns_per_layer
        self.R = None # will be calculated during render

        c1 = self.shape.inner_radius
        c2 = self.shape.inner_radius + self.spiral_pitch
        alpha1 = atan((self.shape.outer_radius - self.shape.inner_radius) / self.sweeping_angle / c1)
        alpha2 = atan((self.shape.outer_radius - self.shape.inner_radius) / self.sweeping_angle / c2)
        alpha = (alpha1+alpha2)/2
        self.projected_spiral_pitch = self.spiral_pitch*cos(alpha)

        if self.layers == 1 and self.twists > 1:
            warnings.warn('Warning: Twists set to a value other than 1, but single-layer mode is enabled. The twists value will be ignored.')
            self.twists = 1

        if self.turns < 1:
            raise ValueError(f'Error: PlanarInductor.turns must be 1 or more')

        if self.twists < 0:
            raise ValueError(f'Error: PlanarInductor.turns must be 0 or more')

        if gcd(self.twists, self.turns) != 1:
            raise ValueError(f'For the geometry to work out, the twists parameter must be co-prime to turns, i.e. the two must have 1 as their greatest common divisor. You can print valid values for twists by running the kicoil CLI with --show-twists [turns number].\n\n'
                                       f'Right now, both are divisible by {gcd(self.twists, self.turns)}.\n'
                                       f'Valid twist counts for n={self.turns} turns are: {list(divisors(self.turns, max(self.turns, 25)))}\n'
                                       f'Valid turn counts for k={self.twists} twists are: {list(divisors(self.twists, max(self.twists, 25)))}')

        if (self.stagger_inner_vias or self.stagger_outer_vias) and self.twists%2 != 0:
            raise ValueError('For via staggering to work, twists must be even and turns must be odd.')

        if self.trace_width is None and self.clearance is None:
            self.clearance = 0.15
            warnings.warn(f'Warning: Neither trace width nor clearance given. Defaulting to {self.clearance:.2f} mm clearance.')

        if self.trace_width is None:
            if round(self.clearance, 3) > round(self.projected_spiral_pitch, 3):
                warnings.warn(f'Error: Given clearance of {clearance:.2f} mm is larger than the projected spiral pitch of {projected_spiral_pitch:.2f} mm. Reduce clearance or increase the size of the coil.')
            self.trace_width = self.projected_spiral_pitch - self.clearance
            self.logger.info(f'Calculated trace width for {self.clearance:.2f} mm clearance is {self.trace_width:.2f} mm.')

        elif self.clearance is None:
            if round(self.trace_width, 2) > round(self.projected_spiral_pitch, 2):
                warnings.warn(f'Error: Given trace width of {self.trace_width:.2f} mm is larger than the projected spiral pitch of {self.projected_spiral_pitch:.2f} mm. Reduce clearance or increase the size of the coil.')
            self.clearance = self.projected_spiral_pitch - self.trace_width
            self.logger.info(f'Calculated clearance for {self.trace_width:.2f} mm trace width is {self.clearance:.2f} mm.')

        else:
            if round(self.trace_width, 2) > round(self.projected_spiral_pitch, 2):
                raise click.ClickException(f'Error: Given trace width of {self.trace_width:.2f} mm is larger than the projected spiral pitch of {self.projected_spiral_pitch:.2f} mm. Reduce clearance or increase the size of the coil.')
            clearance_actual = self.projected_spiral_pitch - self.trace_width
            if round(clearance_actual, 3) < round(self.clearance, 3):
                raise click.ClickException(f'Error: Actual clearance for {self.trace_width:.2f} mm trace is {clearance_actual:.2f} mm, which is lower than the given clearance of {self.clearance:.2f} mm.')

        if round(self.via_diameter, 2) < round(self.trace_width, 2):
            self.logger.warning(f'Clipping via diameter from {self.via_diameter:.2f} mm to trace width of {self.trace_width:.2f} mm.')
            self.via_diameter = self.trace_width

        if self.via_drill is None:
            self.via_drill = max(self.via_diameter / 2, self.via_diameter - 1.2)
            self.logger.warning(f'No via drill given, defaulting to {self.via_drill:.2f} mm based on via diameter.')

        if self.via_offset is None:
            self.via_offset = max(0, (self.via_diameter - self.trace_width)/2)
            self.logger.info(f'Autocalculated via offset {self.via_offset:.2f} mm')

        if isclose(self.via_offset, 0, abs_tol=1e-6):
            self.via_offset = 0

        self.inner_via_ring_radius = self.shape.inner_radius - self.via_offset
        inner_via_angle = 2*asin((self.via_diameter + self.clearance)/2 / self.inner_via_ring_radius)

        self.outer_via_ring_radius = self.shape.outer_radius + self.via_offset
        outer_via_angle = 2*asin((self.via_diameter + self.clearance)/2 / self.outer_via_ring_radius)

        self.logger.info(f'Inner via ring @r={self.inner_via_ring_radius:.2f} mm (from {self.shape.inner_radius:.2f} mm)')
        self.logger.info(f'    {degrees(inner_via_angle):.1f} deg / via')
        self.logger.info(f'Outer via ring @r={self.outer_via_ring_radius:.2f} mm (from {self.shape.outer_radius:.2f} mm)')
        self.logger.info(f'    {degrees(outer_via_angle):.1f} deg / via')

        # Check if the vias of the inner ring are so large that they would overlap
        if inner_via_angle*self.twists > (4*pi if self.stagger_inner_vias else 2*pi):
            min_dia = 2*((self.via_diameter + self.clearance) / (2*sin(pi / self.twists * (2 if self.stagger_inner_vias else 1))) + self.via_offset)
            warnings.warn(f'Overlapping vias in inner via ring. Calculated minimum inner diameter is {min_dia:.2f} mm.')

        t, _, b = self.layer_pair.partition(',')
        self.layer_pair = (t.strip(), b.strip())

        # For fill factor & inductance formulas, See https://coil32.net/pcb-coil.html for details
        d_avg = (2*self.shape.outer_radius + self.shape.inner_radius)/2
        phi = (2*self.shape.outer_radius - 2*self.shape.inner_radius) / (2*self.shape.outer_radius + 2*self.shape.inner_radius)
        c1, c2, c3, c4 = 1.00, 2.46, 0.00, 0.20 # FIXME for other shapes
        self.L = mu_0 * self.turns**2 * d_avg*1e3 * c1 / 2 * (log(c2/phi) + c3*phi + c4*phi**2)
        self.logger.info(f'Outer diameter: {2*self.shape.outer_radius:g} mm')
        self.logger.info(f'Average diameter: {d_avg:g} mm')
        self.logger.info(f'Inner diameter: {2*self.shape.inner_radius:g} mm')
        self.logger.info(f'Fill factor: {phi:g}')
        self.logger.info(f'Approximate inductance: {self.L:g} µH')

        _points, arm_length, _angle_refs = self.shape.compute_spiral(a1=0, a2=self.sector_angle)

        self.track_length = arm_length*self.twists*self.layers
        self.logger.info(f'Approximate track length: {self.track_length:.2f} mm')

        A = self.copper_thickness/1e3 * self.trace_width/1e3 # trace cross-section area
        rho = 1.68e-8 # specific resistivity of copper
        self.R = self.track_length/1e3 * rho / A
        self.logger.info(f'Approximate resistance: {self.R:g} Ω')

    @property
    def default_footprint_name(self):
        return f'planar-coil-{self.shape.slug}-n{self.turns}-k{self.twists}'

    def render_footprint(self, name=None, arc_tolerance=0.02, circle_segments=64):
        if name is None:
            name = self.default_footprint_name

        from . import __version__
        footprint = Footprint(
                name=name,
                generator=kicad.Atom('kicoil'),
                generator_version=__version__,
                layer='F.Cu',
                descr=f"{self.turns} turn {self.shape.desc} twisted coil footprint, inductance approximately {self.L:.6f} µH. Generated by kicoil, version {__version__}.",
                clearance=self.clearance,
                zone_connect=0)

        total_angle = self.twists*2*self.sweeping_angle*self.layers

        inverse = {}
        for i in range(self.twists):
            inverse[i*self.turns%self.twists] = i

        arms_layers = [[], []]
        # Array where we collect all gerbonara kicad line and arc objects
        for i in range(self.twists):
            start_angle = i*self.sector_angle
            fold_angle = start_angle + self.sweeping_angle
            end_angle = fold_angle + self.sweeping_angle

            # Handle the spiral arm
            points_layer0, arm_length, angle_refs_layer0 = self.shape.compute_spiral(a1=start_angle, a2=fold_angle, fn=circle_segments)
            x0, y0 = points_layer0[0]
            xn, yn = points_layer0[-1]
            if angle_refs_layer0:
                ref_0, ref_n = angle_refs_layer0[0], angle_refs_layer0[-1]
            else:
                ref_0, ref_n = None, None

            if self.approximate_arcs and isinstance(self.shape, CircleShape):
                footprint.arcs.extend(arc_approximate(points_layer0, self.trace_width, self.layer_pair[0], arc_tolerance))
            else:
                footprint.lines.extend(kicad.make_line(*p1, *p2, self.trace_width, self.layer_pair[0]) for p1, p2 in zip(points_layer0, points_layer0[1:]))

            if self.layers > 1:
                # Handle the returning arm on the bottom layer
                points_layer1, _, angle_refs_layer1 = self.shape.compute_spiral(a1=end_angle, a2=fold_angle, fn=circle_segments)
                points_layer1 = points_layer1[::-1]
                if self.approximate_arcs and isinstance(self.shape, CircleShape):
                    footprint.arcs.extend(arc_approximate(points_layer1, self.trace_width, self.layer_pair[1], arc_tolerance))
                else:
                    footprint.lines.extend(kicad.make_line(*p1, *p2, self.trace_width, self.layer_pair[1]) for p1, p2 in zip(points_layer1, points_layer1[1:]))

            else:
                # Add a straight connecting segment connecting the inner point to the outside of the spiral.
                ref = angle_refs_layer0[-1]
                xq, yq = self.shape.project_point(self.shape.outer_radius, fold_angle, r_ref=ref)
                angle_refs_layer1 = [ref, ref]
                points_layer1 = [(xn, yn), (xq, yq)]
                footprint.lines.append(kicad.make_line(xn, yn, xq, yq, self.trace_width, self.layer_pair[1]))
            
            arms_layers[0].append((points_layer0, angle_refs_layer0))
            arms_layers[1].append((points_layer1, angle_refs_layer1))

        for i in range(self.twists):
            start_angle = i*self.sector_angle
            fold_angle = start_angle + self.sweeping_angle
            end_angle = fold_angle + self.sweeping_angle
            
            # Handle inner via ring and process staggering if enabled
            r = self.inner_via_ring_radius
            if self.stagger_inner_vias:
                if i%2 != 0:
                    r -= 2*self.via_offset

            points_layer0, refs_layer0 = arms_layers[0][i]
            points_layer1, refs_layer1 = arms_layers[1][i]

            xv, yv = self.shape.project_point(r, fold_angle, r_ref=refs_layer0[-1])

            footprint.lines.append(kicad.make_line(*points_layer0[-1], xv, yv, self.trace_width, self.layer_pair[0]))
            footprint.lines.append(kicad.make_line(xv, yv, *points_layer1[0], self.trace_width, self.layer_pair[1]))

            footprint.pads.append(kicad.make_via(xv, yv,
                                                 self.via_diameter, self.via_drill, self.clearance,
                                                 self.layer_pair))

            # Handle outer via ring and process staggering if enabled unless we are at the start of the coil, where we will
            # place pads below.
            r = self.outer_via_ring_radius

            if self.stagger_outer_vias:
                if i%2 != 0:
                    r += 2*self.via_offset

            points_layer0, refs_layer0 = arms_layers[0][i]
            points_layer1, refs_layer1 = arms_layers[1][(i - self.turns) % self.twists]
            
            xv, yv = self.shape.project_point(r, start_angle, r_ref=refs_layer0[0])

            footprint.lines.append(kicad.make_line(*points_layer0[0], xv, yv, self.trace_width, self.layer_pair[0]))
            footprint.lines.append(kicad.make_line(*points_layer1[-1], xv, yv, self.trace_width, self.layer_pair[1]))

            if i > 0:
                footprint.pads.append(kicad.make_via(xv, yv,
                                                     self.via_diameter, self.via_drill, self.clearance,
                                                     self.layer_pair))
            
            else:
                # Place the pads on the outer radius
                px, py = self.shape.project_point(self.shape.outer_radius, 0)
                footprint.pads.extend([
                        kicad.make_pad(1, [self.layer_pair[0]], px, py, self.trace_width, self.clearance),
                        kicad.make_pad(2, [self.layer_pair[1]], px, py, self.trace_width, self.clearance)])

        if self.keepout_zone:
            pts = self.shape.offset_exterior(self.keepout_margin)
            footprint.zones.append(Zone(layers=['*.Cu'],
                hatch=Hatch(),
                filled_areas_thickness=False,
                keepout=ZoneKeepout(copperpour_allowed=False),
                polygon=ZonePolygon(pts=[XYCoord(x=x, y=y) for x, y in pts])))

        return footprint

