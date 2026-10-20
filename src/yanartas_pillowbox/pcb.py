"""PCB layout of the box as a flex PCB: a security mesh on both sides of the foil, whose
traces leave through the FPC cable to the plug's contacts.

Each copper layer carries its own mesh (``mesh``): ``mesh_traces`` loops over the box's faces,
kept ``mesh_edge_clearance`` off the cut edges, the slits and the cable. The front (F.Cu)
mesh's exit cell sits against the junction, where the cable leaves the inner flap, so its
loops' ends run straight on into the cable, on the plug's pin 1 side. The back (B.Cu) mesh's
grid is offset by half a cell in x and y, so that the strips the two layers' whole cells
leave bare along the edges differ: its exit cell sits half a cell into the flap, beside the
front one's, and its loops' ends run straight on across the gap. Along the cable they keep
the mesh's pitch, each on its own layer. Just before the plug they fan out to their
contacts' places, and the back mesh's traces change to the contact side (F.Cu) through two
staggered rows of vias.

The plug's pins carry, from pin 1: GND, mesh ends 1-4, GND, 5-8, GND, 9-12, GND, 13-16, GND
(the front mesh's ends 1-8, the back mesh's 9-16, each loop's two ends mirrored about the
middle of its eight); the rest stay unconnected. GND is a ground plane on both layers of the
cable: a KiCad zone, filled in KiCad (not in the Gerber and SVG output here); vias stitch the
two layers together, and connect the GND contacts to the back layer.

Coordinates are the pattern's (mm, y down), as in KiCad.
"""

from __future__ import annotations

import functools
import itertools
import math
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from shapely.geometry import LineString, Polygon

from yanartas_pillowbox import kimesh, progress, sfc
from yanartas_pillowbox import mesh as meshgen
from yanartas_pillowbox.config import Config
from yanartas_pillowbox.geometry import (
    Arc,
    Cable,
    Pattern,
    Segment,
    _segment_key,
    build_pattern,
)

Point = tuple[float, float]

VIA_SIZE, VIA_DRILL = 0.45, 0.2
SLIT_WIDTH = 0.1  # the slits' cut, as a slot (a closed board edge)
TOLERANCE = 0.005  # arcs as polylines (chord error)
FOLD_CLEARANCE = 1.0  # vias keep this far from the cable's folds
STITCH_PITCH = 6.0  # GND stitching vias along the cable
GROUPS = 4  # mesh ends between GND pins on the plug

FRONT, BACK = "F.Cu", "B.Cu"


class PcbError(ValueError):
    """The layout cannot be made for this configuration."""


@dataclass
class Track:
    points: tuple[Point, ...]
    layer: str
    net: str
    width: float
    # the track as lines and arcs (``points``: these drawn as a polyline), if fitted
    arcs: tuple[meshgen.Piece, ...] | None = None


@dataclass
class Via:
    at: Point
    net: str


@dataclass
class Pad:
    number: int
    at: Point
    size: tuple[float, float]
    net: str | None


@dataclass
class Layout:
    """The finished layout, in plain geometry (``export`` turns it into files)."""

    board: Polygon  # the foil: the outline with the slits and scraps cut out
    folds: tuple[Segment, ...]
    tracks: list[Track] = field(default_factory=list)
    vias: list[Via] = field(default_factory=list)
    pads: list[Pad] = field(default_factory=list)
    ground: Polygon | None = None  # the cable: GND zone on both layers
    meshes: dict[str, meshgen.Mesh] = field(default_factory=dict)
    area: Polygon | None = None  # what the meshes cover
    clearance: float = 0.15
    width: float = 0.15
    _cache: dict = field(default_factory=dict, repr=False)

    def net_lengths(self) -> dict[str, float]:
        """Each net's copper length (mm): all its tracks, from contact to contact for a mesh
        net (the loop and its runs along the cable)."""
        out: dict[str, float] = {}
        for t in self.tracks:
            length = sum(math.dist(a, b) for a, b in itertools.pairwise(t.points))
            out[t.net] = out.get(t.net, 0.0) + length
        return out

    def longest_trace(self) -> tuple[str, float]:
        """The longest mesh net and its length (mm)."""
        lengths = {n: v for n, v in self.net_lengths().items() if n.startswith("MESH_")}
        net = max(lengths, key=lengths.__getitem__)
        return net, lengths[net]

    def spacing(self) -> dict[str, meshgen.Spacing]:
        """Each mesh's spacing profile (its traces' space against the nominal one), by
        layer. (Measured on first use.)"""
        if "spacing" not in self._cache:
            self._cache["spacing"] = {
                layer: meshgen.spacing(m.traces, self.width, self.clearance)
                for layer, m in self.meshes.items()
            }
        return self._cache["spacing"]

    def density(self) -> dict[str, meshgen.Density]:
        """Each mesh's coverage of its area (how evenly), by layer. (Measured on first
        use.)"""
        if "density" not in self._cache:
            self._cache["density"] = {
                layer: meshgen.density(m.traces, self.area, self.width, self.clearance)
                for layer, m in self.meshes.items()
                if self.area is not None
            }
        return self._cache["density"]

    def skew(self) -> dict[str, list[tuple[str, str, float, float]]]:
        """Each mesh's neighbouring traces (net 1 and 2, 2 and 3, ...) taken as differential
        pairs, by layer: the nets, the difference in their lengths and the largest local
        difference (mm), over the mesh (the cable's runs left out)."""
        if "skew" not in self._cache:
            out: dict[str, list[tuple[str, str, float, float]]] = {}
            for layer, m in self.meshes.items():
                side = "F" if layer == FRONT else "B"
                out[layer] = [
                    (f"MESH_{side}{i + 1}", f"MESH_{side}{i + 2}", *meshgen.skew(a, b))
                    for i, (a, b) in enumerate(itertools.pairwise(m.traces))
                ]
            self._cache["skew"] = out
        return self._cache["skew"]


def pinout(pins: int, traces: int) -> list[str | None]:
    """Each pin's signal, from pin 1: "GND" or "M<i>" (mesh end i, from 1), None if free."""
    ends = 4 * traces  # two ends per loop, two sides
    out: list[str | None] = ["GND"]
    for i in range(ends):
        out.append(f"M{i + 1}")
        if (i + 1) % GROUPS == 0:
            out.append("GND")
    if len(out) > pins:
        raise PcbError(f"the plug needs at least {len(out)} pins for the mesh's ends")
    return out + [None] * (pins - len(out))


# ----------------------------------------------------------------------------- geometry
def sample(segments: Iterable[Segment], tol: float = TOLERANCE) -> list[Point]:
    """The chain of segments as a polyline (arcs within ``tol``), without the closing
    repeat of its first point."""
    out: list[Point] = []
    for seg in segments:
        if isinstance(seg, Arc):
            step = 2 * math.acos(max(-1.0, 1 - tol / seg.radius))
            n = max(1, math.ceil(abs(seg.sweep) / step))
        else:
            n = 1
        pts = [seg.point_at(i / n) for i in range(n + 1)]
        pts[0], pts[-1] = seg.start, seg.end
        out.extend(pts if not out else pts[1:])
    if len(out) > 1 and math.dist(out[0], out[-1]) < 1e-9:
        out.pop()
    return out


def _unit(a: Point, b: Point) -> Point:
    k = math.dist(a, b)
    return ((b[0] - a[0]) / k, (b[1] - a[1]) / k)


def _left(d: Point) -> Point:
    """Left-hand normal of a run going ``d`` (as ``fpc._side``)."""
    return (d[1], -d[0])


def offset_path(path: Sequence[Point], k: float) -> list[Point]:
    """The polyline ``path`` (square corners) offset ``k`` to its left (as ``fpc.outline``)."""
    dirs = [_unit(a, b) for a, b in itertools.pairwise(path)]
    n0 = _left(dirs[0])
    out = [(path[0][0] + k * n0[0], path[0][1] + k * n0[1])]
    for p, d0, d1 in zip(path[1:-1], dirs, dirs[1:], strict=False):
        a, b = _left(d0), _left(d1)
        out.append((p[0] + k * (a[0] + b[0]), p[1] + k * (a[1] + b[1])))
    n1 = _left(dirs[-1])
    out.append((path[-1][0] + k * n1[0], path[-1][1] + k * n1[1]))
    return out


# ----------------------------------------------------------------------------- fan-out
def fan(starts: Sequence[float], ends: Sequence[float], pitch: float) -> list[list[Point]]:
    """Traces moving sideways from offsets ``starts`` to ``ends`` (both in the same order),
    each by one 45 degree jog, staggered so that neighbours stay ``pitch`` apart (centre to
    centre). In local coordinates (u along, from 0, v across): each trace's points from
    ``(0, start)`` to ``(length, end)``, all ending at the same ``length``."""
    n = len(starts)
    delay = [0.0] * n

    def trace(i: int, length: float | None = None) -> list[Point]:
        a, b, u = starts[i], ends[i], delay[i]
        pts = [(0.0, a), (u, a), (u + abs(b - a), b)]
        if length is not None:
            pts.append((length, b))
        return pts

    for _ in range(64 * n):
        moved = False
        for i in range(n - 1):
            ta, tb = LineString(trace(i, 1e3)), LineString(trace(i + 1, 1e3))
            if ta.distance(tb) >= pitch - 1e-9:
                continue
            # Whoever moves towards the other waits for the other to get out of the way.
            gap_start, gap_end = abs(starts[i] - starts[i + 1]), abs(ends[i] - ends[i + 1])
            towards_a = (ends[i + 1] - starts[i + 1]) * (starts[i] - starts[i + 1]) > 0
            j = i + 1 if towards_a or gap_end < gap_start else i
            delay[j] += 0.02
            moved = True
        if not moved:
            break
    else:  # pragma: no cover - the fan always settles for ordered offsets
        raise PcbError("could not fan the traces out")
    length = max(delay[i] + abs(ends[i] - starts[i]) for i in range(n)) + pitch
    return [_dedupe(trace(i, length)) for i in range(n)]


def _dedupe(pts: list[Point]) -> list[Point]:
    out: list[Point] = []
    for p in pts:
        if not out or math.dist(out[-1], p) > 1e-9:
            out.append(p)
    return out


# ----------------------------------------------------------------------------- layout
def layout(cfg: Config, pattern: Pattern | None = None) -> Layout:
    """The PCB layout for the configuration. Raises ``PcbError``."""
    pattern = pattern or build_pattern(cfg)
    cable = pattern.cable
    if cable is None:
        raise PcbError("the PCB layout needs the FPC cable (its traces leave through it)")
    n = int(cfg.mesh_traces)
    w, space = cfg.mesh_trace_width, cfg.mesh_trace_space
    pitch = w + space
    pins = pinout(int(cfg.fpc_pins), n)
    ec = cfg.mesh_edge_clearance

    # The foil: the outline, less the slits (as narrow slots) and the scraps.
    outline = Polygon(sample(pattern.outline.segments))
    cuts = [LineString(sample(chain)) for chain in pattern.slits]
    board = outline.difference(shapely.union_all([c.buffer(SLIT_WIDTH / 2) for c in cuts]))
    board = board.difference(shapely.union_all([Polygon(sample(s)) for s in pattern.scraps]))
    if not isinstance(board, Polygon):  # pragma: no cover - the foil is one piece
        raise PcbError("the foil falls apart")

    # The cable: its cut (the outline that bounds no face), closed across the junction.
    faces = {_segment_key(s) for f in pattern.faces for s in f.boundary}
    cable_cut = [s for s in pattern.outline.segments if _segment_key(s) not in faces]
    cable_poly = Polygon(sample(cable_cut)).buffer(0)
    (jl, yj), (jr, _) = cable.junction
    xc = (jl + jr) / 2
    out_dir = _unit(cable.path[0], cable.path[1])  # from the flap into the cable
    up = out_dir[1] < 0  # (the cable leaves the top end upward)
    r = 2 * cfg.fpc_corner_radius + 1
    beyond = shapely.box(jl - r, yj - r if up else yj, jr + r, yj if up else yj + r)
    # (its cut closes across the fillets' ends, a little into the flap: cut off level)
    x0, y0, x1, y1 = cable_poly.bounds
    side = (
        shapely.box(x0 - 1, y0 - 1, x1 + 1, yj) if up else shapely.box(x0 - 1, yj, x1 + 1, y1 + 1)
    )
    cable_poly = cable_poly.intersection(side)
    mask = board.buffer(-ec).difference(cable_poly).difference(beyond)

    # Pins: across the plug, pin 1 on the cable's left (walking from the flap to the tip).
    pin_pitch = cfg.fpc_pitch
    npins = int(cfg.fpc_pins)

    def k_pin(j: int) -> float:
        return ((npins + 1) / 2 - j) * pin_pitch

    left0 = _left(out_dir)
    mesh_pins = {s: j + 1 for j, s in enumerate(pins) if s and s.startswith("M")}
    per_side = 2 * n
    sides = {
        FRONT: [mesh_pins[f"M{i + 1}"] for i in range(per_side)],
        BACK: [mesh_pins[f"M{per_side + i + 1}"] for i in range(per_side)],
    }

    result = Layout(board, (*(f.segment for f in pattern.folds), *(f.segment for f in cable.folds)))
    result.area = mask
    result.clearance, result.width = space, w
    cell = 2 * n * pitch
    half = cable.width / 2
    tracks: dict[str, list[tuple[float, str, Point]]] = {}  # layer -> ends (k, net, point)
    grid = None  # the front mesh's exit corner
    corners = {}
    for layer, side_pins in sides.items():
        centre = sum(k_pin(j) for j in side_pins) / len(side_pins)
        x0 = xc + centre * left0[0] - cell / 2  # (the exit cell centred on its pins)
        if grid is None:
            corner = (x0, yj if up else yj - cell)
            grid = corner
        else:
            # The back mesh's grid is offset by half a cell both ways, so that the strips
            # each layer's whole cells leave bare along the edges differ: its exit cell sits
            # half a cell into the flap (its traces run straight on across the gap) and on
            # the nearest column of its grid.
            # (and optionally by a trace width more, so its traces lie over the front's gaps)
            shift = cell / 2 + (w if cfg.mesh_back_offset == "cell_trace" else 0.0)
            x0 = grid[0] + shift + round((x0 - grid[0] - shift) / cell) * cell
            corner = (x0, yj + shift if up else yj - cell - shift)
        if abs((x0 + cell / 2 - xc) * left0[0]) + cell / 2 > half - ec:
            raise PcbError("no room for the mesh's exit at the cable's junction")
        corners[layer] = corner

    def mesh(i: int, corner: Point) -> meshgen.Mesh:
        # (its own copy of the mask: preparing a shared geometry from two threads crashes)
        area = shapely.from_wkb(shapely.to_wkb(mask))
        side = meshgen.UP if up else meshgen.DOWN
        seed = int(cfg.mesh_seed) * 2 + i
        if cfg.mesh_algorithm == "sfc":
            # (the panels as zones: the curve crosses the folds as seldom as can be)
            zones = [Polygon(sample(f.boundary)) for f in pattern.faces]
            return sfc.generate(
                area, corner, side, n, pitch, seed=seed, zones=zones,
                arcs=cfg.mesh_shape == "arcs",
            )  # fmt: skip
        return kimesh.generate(area, corner, side, n, pitch, seed=seed)

    # The two sides are independent: laid out at once.
    try:
        meshes = progress.side_by_side(
            [(layer, functools.partial(mesh, i, c)) for i, (layer, c) in enumerate(corners.items())]
        )
    except meshgen.MeshError as e:
        raise PcbError(str(e)) from e
    for layer, m in zip(corners, meshes, strict=True):
        result.meshes[layer] = m
        side = "F" if layer == FRONT else "B"
        for net, trace in enumerate(m.traces):
            arcs = m.arcs[net] if m.arcs else None
            result.tracks.append(Track(trace, layer, f"MESH_{side}{net + 1}", w, arcs))
        # The loops' ends, across the cable from pin 1's side: they run on into the cable.
        tracks[layer] = sorted(
            (
                ((p[0] - xc) * left0[0], f"MESH_{side}{net + 1}", p)
                for net, t in enumerate(m.traces)
                for p in (t[0], t[-1])
            ),
            reverse=True,
        )

    _route_cable(cfg, cable, result, sides, tracks, k_pin, pins)
    result.ground = cable_poly
    problems = verify(result)  # (a fail-safe: no layout leaves here open or shorted)
    if problems:
        raise PcbError("the layout failed its check: " + "; ".join(problems[:5]))
    return result


def _route_cable(
    cfg: Config,
    cable: Cable,
    result: Layout,
    sides: dict[str, list[int]],
    ends: dict[str, list[tuple[float, str, Point]]],
    k_pin: Callable[[int], float],
    pins: list[str | None],
) -> None:
    """The traces along the cable, their fan-out and vias before the plug, the plug's pads
    and the GND stitching vias."""
    w, pitch = result.width, result.width + result.clearance
    path = list(cable.path)
    tip, before = path[-1], path[-2]
    u = _unit(before, tip)  # along the last row, towards the tip
    nl = _left(u)
    plug = cfg.fpc_plug_length

    def at(s: float, k: float) -> Point:
        """s back from the tip along the last row, k to its left."""
        return (tip[0] - s * u[0] + k * nl[0], tip[1] - s * u[1] + k * nl[1])

    # Rows before the plug: GND vias behind the GND contacts, then the back mesh's vias in
    # two staggered rows, then the fan-out.
    row_gnd = plug + 0.2 + VIA_SIZE / 2
    rows = (row_gnd + VIA_SIZE + result.clearance, row_gnd + 2 * (VIA_SIZE + result.clearance))
    fans = {
        layer: fan([k for k, _, _ in ends[layer]], [k_pin(j) for j in side_pins], pitch)
        for layer, side_pins in sides.items()
    }
    fan_start = rows[1] + VIA_SIZE / 2 + result.clearance + max(f[0][-1][0] for f in fans.values())
    straight = math.dist(before, tip) - (cable.width / 2 if len(path) > 3 else 0.0)
    if fan_start > straight:
        raise PcbError(
            f"the cable's last row is too short for its traces to reach the plug: it needs "
            f"{fan_start:.1f} mm of straight run before the tip"
        )

    folds = shapely.union_all([LineString([f.segment.start, f.segment.end]) for f in cable.folds])

    def clear_of_folds(p: Point) -> bool:
        return shapely.Point(p).distance(folds) >= FOLD_CLEARANCE

    for layer, side_pins in sides.items():
        for idx, ((k, net, start), j, local) in enumerate(
            zip(ends[layer], side_pins, fans[layer], strict=True)
        ):
            # From the mesh's end (straight on to the junction if its exit cell lies further
            # in), along the cable at k, up to the fan, then fanned out to the pin's place.
            along = [start, *offset_path(path, k)[:-1], at(fan_start, k)]
            fanned = [at(fan_start - du, dv) for du, dv in local[1:]]
            if layer == FRONT:
                pts = [*along, *fanned, at(plug, k_pin(j))]
                result.tracks.append(Track(_clean(pts), FRONT, net, w))
            else:
                via = at(rows[idx % 2], k_pin(j))
                result.tracks.append(Track(_clean([*along, *fanned, via]), BACK, net, w))
                result.tracks.append(Track(_clean([via, at(plug, k_pin(j))]), FRONT, net, w))
                if not clear_of_folds(via):
                    raise PcbError("the back mesh's vias would sit on a fold of the cable")
                result.vias.append(Via(via, net))
            result.pads.append(_pad(j, at, plug, k_pin, u, net))

    for j, signal in enumerate(pins, start=1):
        if signal == "GND":
            result.pads.append(_pad(j, at, plug, k_pin, u, "GND"))
            via = at(row_gnd, k_pin(j))
            result.tracks.append(Track((at(plug, k_pin(j)), via), FRONT, "GND", w))
            result.vias.append(Via(via, "GND"))
        elif signal is None:
            result.pads.append(_pad(j, at, plug, k_pin, u, None))

    # Stitching vias along both edges of the cable and between the two meshes' traces.
    edge = cable.width / 2 - result.clearance - VIA_SIZE / 2 - cfg.mesh_edge_clearance / 2
    lanes = [edge, -edge]
    bundles = sorted(k for layer in ends for k, _, _ in ends[layer])
    gaps = [
        (a + b) / 2
        for a, b in itertools.pairwise(bundles)
        if b - a >= VIA_SIZE + 2 * result.clearance + w
    ]
    lanes += gaps
    keep_out = shapely.union_all(
        [shapely.Point(v.at).buffer(VIA_SIZE + result.clearance) for v in result.vias]
    )
    for k in lanes:
        line = LineString(offset_path(path, k))
        length = line.length - fan_start - VIA_SIZE
        s = STITCH_PITCH / 2
        while s < length:
            q = line.interpolate(s)
            p = (q.x, q.y)
            if clear_of_folds(p) and not keep_out.contains(q) and _clear_of_turns(p, cable):
                result.vias.append(Via(p, "GND"))
            s += STITCH_PITCH


def _clear_of_turns(p: Point, cable: Cable) -> bool:
    """Off the cable's corner squares (folded flat, they stack the cable's layers)."""
    h = cable.width / 2 + FOLD_CLEARANCE
    return all(max(abs(p[0] - c[0]), abs(p[1] - c[1])) > h for c in cable.path[1:-1])


def _pad(
    j: int,
    at: Callable[[float, float], Point],
    plug: float,
    k_pin: Callable[[int], float],
    u: Point,
    net: str | None,
) -> Pad:
    """Contact j: from 0.2 mm short of the tip to the end of the plug."""
    centre = at((plug + 0.2) / 2, k_pin(j))
    length, width = plug - 0.2, 0.6 * (k_pin(1) - k_pin(2))
    size = (length, width) if abs(u[0]) > abs(u[1]) else (width, length)
    return Pad(j, centre, size, net)


def _clean(pts: Sequence[Point]) -> tuple[Point, ...]:
    return tuple(meshgen.straighten(_dedupe(list(pts))))


# ----------------------------------------------------------------------------- export
def verify(result: Layout) -> list[str]:
    """The layout's electrical check, as a list of problems (none: it passes):

    - every mesh net one connected piece of copper (tracks, vias, pads) from its contact
      pad to its other contact pad, with no other pad on it (no opens);
    - no copper of one net touching copper of another on the same layer (no shorts).

    The ground zone is left out (it is poured around the traces, at their clearance)."""
    problems: list[str] = []

    def key(p: Point) -> tuple[int, int]:
        return (round(p[0] * 1e4), round(p[1] * 1e4))

    # Connectivity: the tracks' points (by layer), joined along each track and through vias.
    parent: dict[tuple, tuple] = {}

    def find(a: tuple) -> tuple:
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def join(a: tuple, b: tuple) -> None:
        parent[find(a)] = find(b)

    for t in result.tracks:
        first = (t.net, t.layer, key(t.points[0]))
        for p in t.points[1:]:
            join(first, (t.net, t.layer, key(p)))
    for v in result.vias:
        join((v.net, FRONT, key(v.at)), (v.net, BACK, key(v.at)))
    ends: dict[str, list[tuple]] = defaultdict(list)  # (track ends on a net's pads)
    for t in result.tracks:
        if not t.net.startswith("MESH_") or t.layer != FRONT:
            continue
        for p in (t.points[0], t.points[-1]):
            for pad in result.pads:
                (x, y), (sx, sy) = pad.at, pad.size
                if abs(p[0] - x) <= sx / 2 + 1e-6 and abs(p[1] - y) <= sy / 2 + 1e-6:
                    if pad.net != t.net:
                        problems.append(f"{t.net} ends on pad {pad.number} ({pad.net})")
                    ends[t.net].append((pad.number, find((t.net, FRONT, key(p)))))
    nets = sorted({t.net for t in result.tracks if t.net.startswith("MESH_")})
    for net in nets:
        pads = {num for num, _ in ends[net]}
        if len(pads) != 2:
            problems.append(f"{net} reaches {len(pads)} contact pads, not 2")
        roots = {find(n) for n in parent if n[0] == net}
        if len(roots) != 1:
            problems.append(f"{net} is open: {len(roots)} separate pieces of copper")

    # Shorts: copper of different nets overlapping, layer by layer.
    for layer in (FRONT, BACK):
        geoms, nets_, radius = [], [], []
        for t in result.tracks:
            if t.layer == layer:
                pts = np.asarray(t.points, float)
                geoms += list(shapely.linestrings(np.stack([pts[:-1], pts[1:]], 1)))
                nets_ += [t.net] * (len(pts) - 1)
                radius += [t.width / 2] * (len(pts) - 1)
        for v in result.vias:
            geoms.append(shapely.Point(v.at))
            nets_.append(v.net)
            radius.append(VIA_SIZE / 2)
        if layer == FRONT:
            for pad in result.pads:
                (x, y), (sx, sy) = pad.at, pad.size
                geoms.append(shapely.box(x - sx / 2, y - sy / 2, x + sx / 2, y + sy / 2))
                nets_.append(pad.net or f"(pad {pad.number})")
                radius.append(0.0)
        if not geoms:
            continue
        g = np.array(geoms, dtype=object)
        net_arr = np.array(nets_, dtype=object)
        rad = np.array(radius)
        i, j = shapely.STRtree(g).query(g, predicate="dwithin", distance=2 * float(rad.max()))
        keep = (i < j) & (net_arr[i] != net_arr[j])
        i, j = i[keep], j[keep]
        if len(i):
            d = shapely.distance(g[i], g[j])
            short = d < rad[i] + rad[j] - 1e-9
            for a, b in list(zip(i[short], j[short], strict=True))[:5]:
                c = shapely.centroid(g[a])
                problems.append(
                    f"short between {net_arr[a]} and {net_arr[b]} on {layer} "
                    f"near ({c.x:.2f}, {c.y:.2f})"
                )
    return problems


def to_kicad(result: Layout, name: str = "pillowbox") -> Any:
    """The layout as a gerbonara KiCad board: the foil's outline on Edge.Cuts, the folds on
    Dwgs.User, the tracks, vias and the plug's contacts (footprint J1), and the cable's GND
    zone on both copper layers (left unfilled: KiCad fills it)."""
    from gerbonara.cad.kicad import footprints as kfp
    from gerbonara.cad.kicad import graphical_primitives as kgr
    from gerbonara.cad.kicad import pcb as kpcb
    from gerbonara.cad.kicad import primitives as kpr
    from gerbonara.cad.kicad.base_types import AtPos, Net, Stroke, XYCoord
    from gerbonara.cad.kicad.sexp import Atom

    board = kpcb.Board.empty_board()
    board.legacy_footprints = None  # (gerbonara cannot write an empty legacy list)
    board.nets[0] = ""
    nets = sorted({t.net for t in result.tracks} | {"GND"})
    for net in nets:
        board.net_id(net)

    def xy(p: Point) -> XYCoord:
        return XYCoord(round(p[0], 6), round(p[1], 6))

    def stroke(width: float) -> Stroke:
        return Stroke(width=width, type=Atom.solid)

    for ring in (result.board.exterior, *result.board.interiors):
        pts = list(ring.coords)
        for a, b in itertools.pairwise(pts):
            board.add(kgr.Line(start=xy(a), end=xy(b), layer="Edge.Cuts", stroke=stroke(0.05)))
    for seg in result.folds:
        if isinstance(seg, Arc):
            board.add(
                kgr.Arc(
                    start=xy(seg.start),
                    mid=xy(seg.point_at(0.5)),
                    end=xy(seg.end),
                    layer="Dwgs.User",
                    stroke=stroke(0.1),
                )
            )
        else:
            board.add(
                kgr.Line(
                    start=xy(seg.start), end=xy(seg.end), layer="Dwgs.User", stroke=stroke(0.1)
                )
            )

    for track in result.tracks:
        net = board.net_id(track.net)
        if track.arcs:
            for a, m, b in track.arcs:
                board.add(
                    kpcb.TrackSegment(
                        start=xy(a), end=xy(b), width=track.width, layer=track.layer, net=net
                    )
                    if m is None
                    else kpcb.TrackArc(
                        start=xy(a),
                        mid=xy(m),
                        end=xy(b),
                        width=track.width,
                        layer=track.layer,
                        net=net,
                    )
                )
            continue
        for a, b in itertools.pairwise(track.points):
            board.add(
                kpcb.TrackSegment(
                    start=xy(a), end=xy(b), width=track.width, layer=track.layer, net=net
                )
            )
    for via in result.vias:
        board.add(
            kpcb.Via(
                at=xy(via.at),
                size=VIA_SIZE,
                drill=VIA_DRILL,
                layers=[FRONT, BACK],
                net=board.net_id(via.net),
            )
        )

    plug = kfp.Footprint(name="pillowbox:FPC_plug", layer=FRONT, at=AtPos(0, 0, 0))
    plug.reference, plug.value = "J1", "FPC plug"
    for pad in result.pads:
        net = Net(board.net_id(pad.net), pad.net) if pad.net else None
        plug.pads.append(
            kfp.Pad(
                number=str(pad.number),
                type=Atom.smd,
                shape=Atom.rect,
                at=AtPos(round(pad.at[0], 6), round(pad.at[1], 6), 0),
                size=XYCoord(*pad.size),
                layers=[FRONT, "F.Mask"],
                net=net,
            )
        )
    board.add(plug)

    if result.ground is not None:
        zone = kpr.Zone(net=board.net_id("GND"), net_name="GND", layers=[FRONT, BACK], name="GND")
        zone.connect_pads.clearance = result.clearance
        zone.min_thickness = result.width
        polys = getattr(result.ground, "geoms", [result.ground])
        ring = max(polys, key=lambda g: g.area).exterior
        zone.polygon = kpr.ZonePolygon(pts=[xy(p) for p in list(ring.coords)[:-1]])
        board.add(zone)
    return board


def kicad_project(result: Layout, name: str) -> dict:
    """A minimal KiCad project: the design rules the layout keeps (mesh trace and space,
    vias), as the default net class."""
    w, c = result.width, result.clearance
    return {
        "board": {
            "design_settings": {
                "rules": {
                    "min_clearance": c,
                    "min_track_width": w,
                    "min_via_diameter": VIA_SIZE,
                    "min_through_hole_diameter": VIA_DRILL,
                    "min_via_annular_width": (VIA_SIZE - VIA_DRILL) / 2,
                    "min_copper_edge_clearance": min(c, 0.1),
                }
            }
        },
        "meta": {"filename": f"{name}.kicad_pro", "version": 1},
        "net_settings": {
            "classes": [
                {
                    "name": "Default",
                    "clearance": c,
                    "track_width": w,
                    "via_diameter": VIA_SIZE,
                    "via_drill": VIA_DRILL,
                }
            ],
            "meta": {"version": 3},
        },
    }


def render_stack(board: Any) -> Any:
    """The board's copper, mask, outline, drawing and drill layers as a gerbonara layer
    stack (zones unfilled: left out)."""
    from gerbonara.cad.kicad.base_types import LAYER_MAP_K2G
    from gerbonara.layers import LayerStack

    stack = LayerStack()
    layers = {k: g for k, g in LAYER_MAP_K2G.items() if g in stack}
    for obj in (*board.graphic_objects(), *board.track_segments, *board.track_arcs):
        if layer := layers.get(obj.layer):
            stack[layer].objects.extend(obj.render())
    for via in board.vias:
        for name in via.layers:
            if layer := layers.get(name):
                stack[layer].objects.extend(via.render())
        stack.drill_pth.objects.extend(via.render_drill())
    for fp in board.footprints:
        fp.render(stack, layers)
    return stack


def export(result: Layout, directory: str | Path, name: str = "pillowbox") -> list[Path]:
    """Write the layout into ``directory``: ``<name>.kicad_pcb`` (with ``<name>.kicad_pro``),
    the Gerber and drill files in ``<name>-gerbers/``, and ``<name>-top.svg`` and
    ``<name>-bottom.svg``. Returns the paths written."""
    import json

    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    board = to_kicad(result, name)
    pcb_file, pro_file = out / f"{name}.kicad_pcb", out / f"{name}.kicad_pro"
    pcb_file.write_text(board.serialize())
    pro_file.write_text(json.dumps(kicad_project(result, name), indent=2))
    stack = render_stack(board)
    gerbers = out / f"{name}-gerbers"
    stack.save_to_directory(gerbers, board_name=name)
    svgs = []
    for side in ("top", "bottom"):
        svg = out / f"{name}-{side}.svg"
        svg.write_text(str(stack.to_pretty_svg(side=side)))
        svgs.append(svg)
    return [pcb_file, pro_file, gerbers, *svgs]


def preview_json(result: Layout, offset: Point = (0.0, 0.0)) -> dict:
    """The layout for the UI's previews, compact: each copper layer's tracks as flat
    [x, y, x, y, ...] lists (mm, pattern coordinates, rounded to µm), the vias, the plug's
    pads, the foil's bounds (``bbox``) and the sheet ``offset`` of the 2D view."""

    def flat(points: Iterable[Point]) -> list[float]:
        return [round(c, 3) for p in points for c in p]

    lengths = result.net_lengths()
    longest = result.longest_trace()
    spacing, skew, density = result.spacing(), result.skew(), result.density()
    layers: dict[str, list[list[float]]] = {"front": [], "back": []}
    for track in result.tracks:
        layers["front" if track.layer == FRONT else "back"].append(flat(track.points))
    return {
        "layers": layers,
        "width": result.width,
        "vias": flat(v.at for v in result.vias),
        "via_size": VIA_SIZE,
        "pads": [round(c, 3) for p in result.pads for c in (*p.at, *p.size)],
        "bbox": [round(c, 3) for c in result.board.bounds],
        "offset": list(offset),
        "meshes": {
            ("front" if layer == FRONT else "back"): {
                "cells": m.cells,
                "unreached": m.unreached,
                "cell": m.cell,
                "longest": round(
                    max(v for n, v in lengths.items() if n.startswith(f"MESH_{layer[0]}")), 3
                ),
                "algorithm": m.algorithm,
                "spacing": spacing[layer].to_dict(),
                "density": density[layer].to_dict() if layer in density else None,
                "skew": [
                    {"nets": [a, b], "total": round(total, 3), "local": round(local, 3)}
                    for a, b, total, local in skew[layer]
                ],
            }
            for layer, m in result.meshes.items()
        },
        "space": result.clearance,
        "longest_trace": {"net": longest[0], "length": round(longest[1], 3)},
    }


def export_zip(result: Layout, name: str = "pillowbox") -> bytes:
    """``export``'s files as a zip archive (the Gerbers in their own folder)."""
    import io
    import tempfile
    import zipfile

    buf = io.BytesIO()
    with tempfile.TemporaryDirectory() as tmp:
        export(result, tmp, name)
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(Path(tmp).rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(tmp).as_posix())
    return buf.getvalue()
