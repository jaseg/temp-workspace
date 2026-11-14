"""KiCoil layout with flat corners ("cornerflat").

Same as `kicoil.geometry`, but polygon shapes use `CornerFlatSkeletonator`, whose spiral arms run at constant depth
around the polygon's corners and change depth only in ramps in the middle of the edges (see
`kicoil.skeletonator_alt_cornerflat`). The depth of an arm is linear in a *warped* angle, so the arm start, fold and end
angles of `PlanarInductor` are defined in warped angles and mapped back to position angles.
"""

from dataclasses import dataclass
from math import pi

from . import geometry
from .geometry import *  # noqa: F401,F403  re-export helpers
from .geometry import CircleShape, Shape  # noqa: F401
from .skeletonator_alt_cornerflat import CornerFlatSkeletonator


class OffsetShape(geometry.OffsetShape):
    def __post_init__(self):
        self.sk = CornerFlatSkeletonator(self.polygon)
        if self.annular_width >= self.sk.max_depth:
            raise ValueError(f'Annular width ({self.annular_width:.2f}) is too large. Must be less than {self.sk.max_depth:.2f}')
        if self.annular_width <= 0:
            raise ValueError(f'Annular width must be positive')
        self.sk.set_angle_reference(self.annular_width)
        self.max_via_offset = self.sk.max_depth - self.annular_width
        self.outer_radius = self.sk.radius
        self.inner_radius = self.sk.radius - self.annular_width

    def unwarp_angle(self, a):
        """ Position angle (radians) for a warped angle (radians) """
        return self.sk.unwarp(a / (2*pi)) * 2*pi


@dataclass
class PolygonShape(OffsetShape):
    polygon: list
    annular_width: float
    arc_tolerance: float = 0.05

    @property
    def slug(self):
        return f'polygon_{len(self.polygon)}pt'

    @property
    def desc(self):
        return f'{len(self.polygon)} point polygonal'


@dataclass
class PlanarInductor(geometry.PlanarInductor):

    def arm_angles(self, i):
        start_angle = i*self.sector_angle
        fold_angle = start_angle + self.sweeping_angle
        end_angle = fold_angle + self.sweeping_angle
        unwarp = getattr(self.shape, 'unwarp_angle', None)
        if unwarp is None:
            return start_angle, fold_angle, end_angle
        return unwarp(start_angle), unwarp(fold_angle), unwarp(end_angle)
