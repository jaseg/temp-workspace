"""Work out what should be drawn for a set of poles - no KiCad involved.

The output is a list of item specs in schematic coordinates (nanometres), each with a
stable ``key`` (what it is) and a ``sig`` (what it looks like).  :mod:`kicad_io` stores
both on the generated KiCad items so the next run can tell what is already up to date.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field

from . import geometry, network
from .config import Settings
from .network import Pole, Wire
from .textures import TexturePack, kicad_image_scale

Color = tuple[float, float, float, float]
PointNm = tuple[int, int]


def _sig(*parts: object) -> str:
    return hashlib.sha1(repr(parts).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class ImageSpec:
    key: str
    position: PointNm
    scale: float
    png: bytes = field(repr=False)
    digest: str

    @property
    def sig(self) -> str:
        # Position is deliberately left out: a moved pole only needs its image moved.
        return _sig("image", self.digest, round(self.scale, 9))


@dataclass(frozen=True)
class PolylineSpec:
    key: str
    points: tuple[PointNm, ...]
    width: int
    color: Color
    dashed: bool = False

    @property
    def sig(self) -> str:
        return _sig("polyline", self.points, self.width, self.color, self.dashed)


@dataclass(frozen=True)
class CircleSpec:
    key: str
    center: PointNm
    radius: int
    width: int
    color: Color
    dashed: bool = True

    @property
    def sig(self) -> str:
        return _sig("circle", self.center, self.radius, self.width, self.color, self.dashed)


Spec = ImageSpec | PolylineSpec | CircleSpec


@dataclass
class Plan:
    items: list[Spec]
    wires: list[Wire]
    frames: dict[str, int]
    islands: dict[str, list[list[Pole]]]
    warnings: list[str]

    def stranded(self) -> list[Pole]:
        """Poles cut off from the biggest island of their net."""
        return [p for groups in self.islands.values() for g in groups[1:] for p in g]


#: Eeschema's internal unit is 100 nm; anything finer is rounded away on the round trip.
IU_NM = 100


def _nm(settings: Settings, p: tuple[float, float]) -> PointNm:
    return (
        round(p[0] * settings.tile_nm / IU_NM) * IU_NM,
        round(p[1] * settings.tile_nm / IU_NM) * IU_NM,
    )


def make_plan(poles: Sequence[Pole], settings: Settings, pack: TexturePack | None) -> Plan:
    wires = network.connect(poles, settings.connection_mode, settings.max_connections)
    frames = network.orientations(poles, wires)
    isl = network.islands(poles, wires)
    items: list[Spec] = []
    warnings: list[str] = []
    width = round(settings.wire_width_mm * 1e6)

    # Pole sprites
    if pack is not None:
        for p in sorted(poles, key=lambda p: p.id):
            try:
                sprite = pack.sprite(
                    p.type, frames[p.id], settings.shadows, settings.shadow_angle, settings.shadow_opacity
                )
            except Exception as e:  # noqa: BLE001 - one bad texture must not stop the rest
                warnings.append(f"{p.type.name}: {e}")
                continue
            center = (p.position[0] + sprite.center[0], p.position[1] + sprite.center[1])
            items.append(
                ImageSpec(
                    key=f"pole:{p.id}",
                    position=_nm(settings, center),
                    scale=kicad_image_scale(sprite.tiles_per_pixel, settings.tile_mm),
                    png=sprite.png,
                    digest=sprite.digest,
                )
            )

    # Wires (and their shadows)
    for w in wires:
        cp_a = w.a.type.connection_points[frames[w.a.id]]
        cp_b = w.b.type.connection_points[frames[w.b.id]]
        span = w.a.distance(w.b)
        n = geometry.samples_for_span(span)
        pts = geometry.wire_polyline(
            w.a.position, cp_a.wire.copper, w.b.position, cp_b.wire.copper, settings.wire_slack, n
        )
        if settings.shadows:
            # Cast the wire's shadow the same way as the poles' (see geometry.shadow_matrix).
            sh_a = geometry.apply(
                geometry.shadow_matrix(cp_a.wire.copper, cp_a.shadow.copper, settings.shadow_angle), cp_a.shadow.copper
            )
            sh_b = geometry.apply(
                geometry.shadow_matrix(cp_b.wire.copper, cp_b.shadow.copper, settings.shadow_angle), cp_b.shadow.copper
            )
            spts = geometry.shadow_polyline(
                w.a.position, cp_a.wire.copper, sh_a,
                w.b.position, cp_b.wire.copper, sh_b,
                settings.wire_slack, n,
            )  # fmt: skip
            items.append(
                PolylineSpec(
                    key=f"wire-shadow:{w.a.id}:{w.b.id}",
                    points=tuple(_nm(settings, q) for q in spts),
                    width=width,
                    color=(0.0, 0.0, 0.0, settings.shadow_opacity),
                )
            )
        items.append(
            PolylineSpec(
                key=f"wire:{w.a.id}:{w.b.id}",
                points=tuple(_nm(settings, q) for q in pts),
                width=width,
                color=settings.wire_color,
            )
        )

    # Point out poles that can't reach the rest of their net.
    plan = Plan(items, wires, frames, isl, warnings)
    stranded = plan.stranded()
    for net, groups in isl.items():
        if len(groups) > 1:
            sizes = ", ".join(str(len(g)) for g in groups)
            warnings.append(f"net {net!r} is split into {len(groups)} separate pole networks (sizes {sizes})")
    if settings.mark_islands:
        for p in stranded:
            items.append(
                CircleSpec(
                    key=f"reach:{p.id}",
                    center=_nm(settings, p.position),
                    radius=round(p.type.maximum_wire_distance * settings.tile_nm / IU_NM) * IU_NM,
                    width=round(0.15e6),
                    color=settings.island_color,
                )
            )
    return plan
