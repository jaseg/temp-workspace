"""PCB layout of the box as a flex PCB: a security mesh on both sides of the foil, whose
traces leave through the FPC cable to the plug's contacts.

Each copper layer carries its own mesh (``mesh``): its nets (``Config.mesh_nets``: the
space-filling curve's ``mesh_traces`` per partition, KiMesh's ``mesh_traces``) loop over the
box's faces, kept ``mesh_edge_clearance`` off the cut edges, the slits and the cable. The
front (F.Cu) mesh's exit cell sits against the junction, where the cable leaves the front
panel's free edge, so its loops' ends run straight on into the cable, on the plug's pin 1
side. The back (B.Cu) mesh's grid is offset by half a cell in x and y, so that the strips the
two layers' whole cells leave bare along the edges differ: its exit cell sits half a cell
into the panel, beside the front one's, and its loops' ends run straight on across the gap.
Along the cable they keep the mesh's pitch, each on its own layer (where the exit cells do
not fit the cable centred on their pins, they sit side by side across the junction, which
``fpc`` widens for them, and the traces neck down to the plug's pitch in the cable's first
corner). Just before the plug they
fan out to their contacts' places, and the back mesh's traces change to the contact side
(F.Cu) through two staggered rows of vias.

The plug's pins carry, from pin 1: GND, mesh ends 1-4, GND, 5-8, GND, ... (a GND pin after
every four ends; the front mesh's ends first, then the back mesh's, each loop's two ends
mirrored about the middle of its side's ends); the rest stay unconnected. GND is a ground
plane on both layers of the cable: a KiCad zone, filled in KiCad (not in the Gerber and SVG
output here); vias stitch the two layers together, and connect the GND contacts to the back
layer.

Coordinates are the pattern's (mm, y down), as in KiCad.
"""

from __future__ import annotations

import functools
import itertools
import math
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from shapely.geometry import LineString, Polygon

from yanartas_pillowbox import checkpoint, geometry, kimesh, partition, progress, rand, sfc
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
RETRIES = 8  # a layer's curve mesh tried again afresh this often, if it leaves regions out
SLIT_WIDTH = 0.1  # the slits' cut, as a slot (a closed board edge)
TOLERANCE = 0.005  # arcs as polylines (chord error)
# arcs of a larger radius than this (mm) exported as lines, within this share of the
# track's width of them (KiCad releases draw arcs of huge radius in the wrong place)
LARGE_ARC = 100.0
SHALLOW_ARC = 0.05
FOLD_CLEARANCE = 1.0  # vias keep this far from the cable's folds
STITCH_PITCH = 6.0  # GND stitching vias along the cable
GND_VIA_EVERY = 4  # in a run of GND contacts, a via behind every this many (joined along)
PAGE_MARGIN = (25.0, 50.0)  # KiCad page: around the design (x, y; the title block below)
PAGE_MIN = (210.0, 148.0)  # ... and at least this big (A5 landscape)

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
    cable_clearance: float = 0.15  # (the traces' along the cable: necked down, maybe less)
    # the glue tab and the lens-shaped flaps: copies for stiffeners (User.1 in KiCad)
    stiffeners: list[Polygon] = field(default_factory=list)
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

    def average_space(self) -> dict[str, float]:
        """Each mesh's average copper-to-copper space (mm), by layer: the space traces side
        by side would need to cover its area as its copper does (from the density). The set
        space is the least: settled, the traces spread into the room left, so this is more."""
        pitch = self.width + self.clearance
        return {
            layer: pitch / d.mean - self.width for layer, d in self.density().items() if d.mean > 0
        }

    def skew(self) -> dict[str, list[tuple[str, str, float, float]]]:
        """Each mesh's neighbouring traces matched in length together (the curve's: net 1
        and 2, 3 and 4, ..., an odd ribbon's middle three, within each partition, see
        ``mesh.matching``; KiMesh's: 1 and 2, 2 and 3, ...) taken as differential pairs, by
        layer: the nets, the difference in their lengths and the largest local difference
        (mm), over the mesh (the cable's runs left out)."""
        if "skew" not in self._cache:
            out: dict[str, list[tuple[str, str, float, float]]] = {}
            for layer, m in self.meshes.items():
                side = "F" if layer == FRONT else "B"
                out[layer] = [
                    (
                        f"MESH_{side}{i + 1}",
                        f"MESH_{side}{j + 1}",
                        *meshgen.skew(m.traces[i], m.traces[j]),
                    )
                    for i, j in m.pairs
                ]
            self._cache["skew"] = out
        return self._cache["skew"]


def pinout(pins: int, traces: int, group: int | None = None) -> list[str | None]:
    """Each pin's signal, from pin 1: "GND" or "M<i>" (mesh end i, from 1); the pins the
    mesh leaves over GND too; ``traces``: the mesh's nets on each side; ``group``: the
    traces between two GND pins (one partition's, its ends nested: 1s 2s … 2r 1r; default:
    a side's)."""
    ends = 4 * traces  # two ends per loop, two sides
    size = 2 * (group or traces)
    out: list[str | None] = ["GND"]
    for i in range(ends):
        out.append(f"M{i + 1}")
        if (i + 1) % size == 0:
            out.append("GND")
    if len(out) > pins:
        raise PcbError(f"the plug needs at least {len(out)} pins for the mesh's ends")
    return out + ["GND"] * (pins - len(out))


# ----------------------------------------------------------------------------- geometry
def sample(segments: Iterable[Segment], tol: float = TOLERANCE) -> list[Point]:
    """The chain of segments as a polyline (arcs within ``tol``): ``geometry.sample``."""
    return geometry.sample(list(segments), tol)


def _flattened(pieces: Sequence[meshgen.Piece], tol: float) -> tuple[meshgen.Piece, ...]:
    """The pieces, each arc of a radius over ``LARGE_ARC`` as lines along it, as few as keep
    within ``tol`` of it."""
    out: list[meshgen.Piece] = []
    for a, m, b in pieces:
        if m is None:
            out.append((a, m, b))
            continue
        (ax, ay), (mx, my), (bx, by) = a, m, b
        d = 2 * (ax * (my - by) + mx * (by - ay) + bx * (ay - my))
        if abs(d) < 1e-15:  # (straight)
            out.append((a, None, b))
            continue
        sa, sm, sb = ax * ax + ay * ay, mx * mx + my * my, bx * bx + by * by
        cx = (sa * (my - by) + sm * (by - ay) + sb * (ay - my)) / d
        cy = (sa * (bx - mx) + sm * (ax - bx) + sb * (mx - ax)) / d
        r = math.dist((cx, cy), a)
        if r <= LARGE_ARC:
            out.append((a, m, b))
            continue
        # (n chords: each 1/n² as far off as the whole one; the arc's own sagitta at m)
        t0 = math.atan2(ay - cy, ax - cx)
        tm = (math.atan2(my - cy, mx - cx) - t0 + math.pi) % math.tau - math.pi
        sag = r * (1 - math.cos(tm))
        n = max(1, math.ceil(math.sqrt(sag / tol))) if tol > 0 else 1
        pts = (
            [a]
            + [
                (cx + r * math.cos(t0 + 2 * tm * k / n), cy + r * math.sin(t0 + 2 * tm * k / n))
                for k in range(1, n)
            ]
            + [b]
        )
        out += [(p, None, q) for p, q in itertools.pairwise(pts)]
    return tuple(out)


def _unit(a: Point, b: Point) -> Point:
    k = math.dist(a, b)
    return ((b[0] - a[0]) / k, (b[1] - a[1]) / k)


def _left(d: Point) -> Point:
    """Left normal of a run going ``d`` (as ``fpc._side``)."""
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


def stiffeners(
    pattern: Pattern, flap_offset: float = 0.0, tab_offset: float = 0.0
) -> list[Polygon]:
    """The glue tab and the lens-shaped flaps (outer and inner), as polygons: where
    stiffeners may go, each shrunk by its offset (``geometry.stiffener_outlines``)."""
    return [
        Polygon(p) for p in geometry.stiffener_outlines(pattern, flap_offset, tab_offset).values()
    ]


def page(result: Layout) -> tuple[Point, tuple[float, float]]:
    """The KiCad page for the layout: its offset (added to every coordinate: the design in
    the page's middle) and its size, the design's bounds and ``PAGE_MARGIN`` around them,
    at least ``PAGE_MIN``."""
    x0, y0, x1, y1 = result.board.bounds
    w = max(x1 - x0 + 2 * PAGE_MARGIN[0], PAGE_MIN[0])
    h = max(y1 - y0 + 2 * PAGE_MARGIN[1], PAGE_MIN[1])
    w, h = math.ceil(w), math.ceil(h)
    return (round(w / 2 - (x0 + x1) / 2, 3), round(h / 2 - (y0 + y1) / 2, 3)), (w, h)


def mesh_zones(pattern: Pattern) -> list[Polygon]:
    """The pattern's faces as the mesh's zones: those that meet along neither a fold nor a
    slit (e.g. the small pieces of the front panel by its flaps' ends, out past its
    straight fold's line) in one, so that the mesh keeps off only real folds."""
    polys = [Polygon(sample(f.boundary)) for f in pattern.faces]
    folds = [LineString(sample([f.segment])) for f in pattern.folds]
    cuts = shapely.union_all(folds + [LineString(sample(c)) for c in pattern.slits]).buffer(1e-4)
    parent = list(range(len(polys)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    tree = shapely.STRtree(polys)
    for i, j in zip(*tree.query(polys, predicate="intersects"), strict=True):
        if i < j:
            border = polys[i].boundary.intersection(polys[j].buffer(1e-6))
            if border.difference(cuts).length > 1e-3:
                parent[find(i)] = find(j)
    groups: dict[int, list[Polygon]] = defaultdict(list)
    for i, poly in enumerate(polys):
        groups[find(i)].append(poly)
    return [g[0] if len(g) == 1 else shapely.union_all(g) for g in groups.values()]


# ----------------------------------------------------------------------------- layout
@checkpoint.timed_step("layout")
def layout(cfg: Config, pattern: Pattern | None = None) -> Layout:
    """The PCB layout for the configuration. Raises ``PcbError``."""
    pattern = pattern or build_pattern(cfg)
    cable = pattern.cable
    if cable is None:
        raise PcbError("the PCB layout needs the FPC cable (its traces leave through it)")
    n = cfg.mesh_nets
    w, space = cfg.mesh_trace_width, cfg.mesh_trace_space
    pitch = w + space
    # (a GND pin after each partition's ends: the curve's; KiMesh, a side's)
    each = int(cfg.mesh_traces) if cfg.mesh_algorithm == "sfc" else n
    pins = pinout(int(cfg.fpc_pins), n, each)
    ec = cfg.mesh_edge_clearance

    # The foil: the outline, less the slits (as narrow slots) and the scraps.
    outline = Polygon(sample(pattern.outline.segments))
    cuts = [LineString(sample(chain)) for chain in pattern.slits]
    board = outline.difference(shapely.union_all([c.buffer(SLIT_WIDTH / 2) for c in cuts]))
    board = board.difference(shapely.union_all([Polygon(sample(s)) for s in pattern.scraps]))
    if not isinstance(board, Polygon):  # pragma: no cover - the foil is one piece
        raise PcbError("the foil falls apart")

    # The cable: its cut (the outline that bounds no face), closed along the free edge.
    faces = {_segment_key(s) for f in pattern.faces for s in f.boundary}
    cable_cut = [s for s in pattern.outline.segments if _segment_key(s) not in faces]
    cable_poly = Polygon(sample(cable_cut)).buffer(0)
    (xj, ya), (_, yb) = cable.junction
    # (across the cable from its centreline; the junction may be wider, on the side away
    # from the first turn, for the meshes' exits: their traces then neck down in the turn)
    yc, lo, hi = cable.path[0][1], min(ya, yb), max(ya, yb)
    wide = hi - lo > cable.width + 1e-9
    out_dir = _unit(cable.path[0], cable.path[1])  # from the edge into the cable (-x)
    r = 2 * cfg.fpc_corner_radius + 1
    beyond = shapely.box(xj - r, lo - r, xj, hi + r)
    # (its cut closes across the fillets' ends, along the edge: cut off there)
    x0, y0, _, y1 = cable_poly.bounds
    cable_poly = cable_poly.intersection(shapely.box(x0 - 1, y0 - 1, xj, y1 + 1))
    mask = board.buffer(-ec).difference(cable_poly).difference(beyond)

    # Pins: across the plug, pin 1 on the cable's left (walking from the edge to the tip).
    pin_pitch = cfg.fpc_pitch
    npins = int(cfg.fpc_pins)

    def k_pin(j: int) -> float:
        return ((npins + 1) / 2 - j) * pin_pitch

    left0 = _left(out_dir)  # (along the junction, towards pin 1's side)
    mesh_pins = {s: j + 1 for j, s in enumerate(pins) if s and s.startswith("M")}
    per_side = 2 * n
    sides = {
        FRONT: [mesh_pins[f"M{i + 1}"] for i in range(per_side)],
        BACK: [mesh_pins[f"M{per_side + i + 1}"] for i in range(per_side)],
    }

    result = Layout(board, (*(f.segment for f in pattern.folds), *(f.segment for f in cable.folds)))
    result.stiffeners = stiffeners(pattern, cfg.stiffener_flap_offset, cfg.stiffener_tab_offset)
    result.area = mask
    result.clearance, result.width = space, w
    cell = 2 * n * pitch
    half = cable.width / 2
    tracks: dict[str, list[tuple[float, str, Point]]] = {}  # layer -> ends (k, net, point)

    def place(compact: bool) -> dict[str, Point] | None:
        """Each layer's exit corner: each exit cell centred on its pins, in the cable; or
        (``compact``) side by side across the junction, from its end. None: no room."""
        grid = None  # the front mesh's exit corner
        corners = {}
        for layer, side_pins in sides.items():
            centre = sum(k_pin(j) for j in side_pins) / len(side_pins)
            y0 = yc + centre * left0[1] - cell / 2  # (the exit cell centred on its pins)
            end = ec + cfg.fpc_corner_radius  # (off the junction's ends' fillets)
            if compact and grid is None:
                y0 = lo + end + 0.005
            if grid is None:
                corner = (xj, y0)
                grid = corner
            else:
                # The back mesh's grid is offset by half a cell both ways, so that the strips
                # each layer's whole cells leave bare along the edges differ: its exit cell
                # sits half a cell into the panel (its traces run straight on across the gap)
                # and on the nearest row of its grid.
                # (and optionally by a trace width more, so its traces lie over the front's)
                shift = cell / 2 + (w if cfg.mesh_back_offset == "cell_trace" else 0.0)
                if compact:  # (right beside the front one's)
                    y0 = grid[1] + shift
                y0 = grid[1] + shift + round((y0 - grid[1] - shift) / cell) * cell
                corner = (xj + shift, y0)
            inside = (
                lo + end - 1e-6 <= y0 <= hi - end - cell + 1e-6
                if compact
                else abs(y0 + cell / 2 - yc) + cell / 2 <= half - ec
            )
            if not inside:
                return None
            corners[layer] = corner
        return corners

    # (side by side, their traces necked down to the cable's pitch in its first corner,
    # where centred on their pins they do not fit: always, the junction wider than the cable)
    corners = None if wide else place(False)
    neck = corners is None
    corners = corners or place(True)
    if corners is None:
        raise PcbError("no room for the mesh's exit at the cable's junction")

    def copy(g: shapely.Geometry) -> shapely.Geometry:
        # (each job its own: preparing a shared geometry from two threads crashes)
        return shapely.from_wkb(shapely.to_wkb(g))

    side = meshgen.LEFT  # (the cable leaves the edge towards -x)
    jobs: list[tuple[str, Callable[[], meshgen.Mesh]]] = []
    for layer, corner in corners.items():
        seed = rand.derive(cfg.seed, f"layer/{layer}")  # (each layer a key of its own)
        if cfg.mesh_algorithm != "sfc":
            jobs.append((layer, functools.partial(
                kimesh.generate, copy(mask), corner, side, n, pitch, seed=seed
            )))  # fmt: skip
            continue
        # The curve's mesh: the layer's area in partitions of equal area, each its own
        # traces (and its own port: a square a pair of lanes wide, in turn along the
        # junction), all laid out at once.
        count, each = int(cfg.mesh_partitions), int(cfg.mesh_traces)
        port = 2 * each * pitch
        cx, cy = corner
        ports = [
            shapely.box(cx, cy + k * port, cx + port, cy + (k + 1) * port) for k in range(count)
        ]
        area = mask.difference(shapely.box(xj - 1, cy, cx, cy + count * port))  # (the leads)
        zones = mesh_zones(pattern)
        jobs.append((layer, functools.partial(
            _partitioned, cfg, layer, copy(area), [copy(z) for z in zones],
            [copy(q) for q in ports], port,
            [(cx, cy + k * port) for k in range(count)], side, each, pitch,
        )))  # fmt: skip

    # The two sides are independent: laid out at once.
    try:
        done = progress.side_by_side(jobs)
    except meshgen.MeshError as e:
        raise PcbError(str(e)) from e
    meshes = done
    for layer, m in zip(corners, meshes, strict=True):
        result.meshes[layer] = m
        side = "F" if layer == FRONT else "B"
        for net, trace in enumerate(m.traces):
            arcs = _flattened(m.arcs[net], SHALLOW_ARC * w) if m.arcs else None
            result.tracks.append(Track(trace, layer, f"MESH_{side}{net + 1}", w, arcs))
        # The loops' ends, across the cable from pin 1's side: they run on into the cable.
        tracks[layer] = sorted(
            (
                ((p[1] - yc) * left0[1], f"MESH_{side}{net + 1}", p)
                for net, t in enumerate(m.traces)
                for p in (t[0], t[-1])
            ),
            reverse=True,
        )

    _route_cable(cfg, cable, result, sides, tracks, k_pin, pins, neck)
    result.ground = cable_poly
    problems = verify(result)  # (a fail-safe: no layout leaves here open or shorted)
    if problems:
        raise PcbError("the layout failed its check: " + "; ".join(problems[:5]))
    return result


def _partitioned(
    cfg: Config,
    layer: str,
    area: shapely.Geometry,
    zones: list[shapely.Geometry],
    ports: list[shapely.Geometry],
    port: float,
    exits: list[Point],
    side: int,
    each: int,
    pitch: float,
) -> meshgen.Mesh:
    """A layer's curve mesh: its area split into partitions, a curve in each. A split its
    curves leave a region of bare (or none found) is tried again afresh, with the seed
    salted (``mesh_seed`` and "-1", "-2", ...: each layer on its own), up to ``RETRIES``
    times; the last try's is kept as it is (its unreached regions counted)."""
    for salt in range(RETRIES + 1):
        key = cfg.seed if not salt else rand.key_of(f"{cfg.mesh_seed}-{salt}")
        seed = rand.derive(key, f"layer/{layer}")
        last = salt == RETRIES
        if salt:
            progress.report("graph", 0, 1, retry=salt)
        try:
            parts = partition.partition(area, zones, ports, (1.0, 0.0), port, seed)
            return sfc.generate(
                area, exits, side, each, pitch, seed=seed, zones=zones,
                arcs=cfg.mesh_shape == "arcs", partitions=[p.area for p in parts],
                stems=[p.reach for p in parts], strict=not last,
            )  # fmt: skip
        except (partition.Uneven, sfc.Unreached):
            if last:
                raise
    raise AssertionError  # (unreachable: the last try returns or raises)


def _route_cable(
    cfg: Config,
    cable: Cable,
    result: Layout,
    sides: dict[str, list[int]],
    ends: dict[str, list[tuple[float, str, Point]]],
    k_pin: Callable[[int], float],
    pins: list[str | None],
    neck: bool = False,
) -> None:
    """The traces along the cable, their fan-out and vias before the plug, the plug's pads
    and the GND stitching vias. Where the meshes' exits do not fit the cable centred on
    their pins (``neck``: side by side across the junction, wider than the cable maybe),
    each layer's traces neck down in the first corner to the plug's pitch (the mesh's, if
    less), each its block centred on its pins: up the stub at the mesh's pitch, each turns
    where its place up the stub meets its place along the row (the turns nested, none
    crossing)."""
    path = list(cable.path)
    wide = neck
    w = result.width
    pitch = min(w + result.clearance, cfg.fpc_pitch) if wide else w + result.clearance
    space = pitch - w
    result.cable_clearance = space
    # (each end's place along the cable: as at the junction, or necked down)
    along_k: dict[str, list[float]] = {}
    for layer, side_pins in sides.items():
        ks = [k for k, _, _ in ends[layer]]
        if not wide:
            along_k[layer] = ks
            continue
        centre = sum(k_pin(j) for j in side_pins) / len(side_pins)
        m = len(ks)
        # (centred on its pins, but kept off the stitching vias' lanes by the cable's edges,
        # where the cable is wide enough)
        clear = cable.width / 2 - 2 * space - VIA_SIZE - cfg.mesh_edge_clearance / 2 - w / 2
        half = (m - 1) / 2 * pitch
        if half <= clear:
            centre = min(max(centre, -clear + half), clear - half)
        along_k[layer] = [centre + ((m - 1) / 2 - i) * pitch for i in range(m)]
        if max(abs(k) for k in along_k[layer]) + w / 2 + space > cable.width / 2:
            raise PcbError("the cable is too narrow for the mesh's traces at its pitch")
    d0, d1 = _unit(path[0], path[1]), _unit(path[1], path[2])
    a0, a1 = _left(d0), _left(d1)

    def route(k0: float, k: float) -> list[Point]:
        """Along the cable at k from the junction, k0 there (turning at the first corner)."""
        rest = offset_path(path, k)
        if k0 == k:
            return rest
        p0, p1 = path[0], path[1]
        turn = (p1[0] + k0 * a0[0] + k * a1[0], p1[1] + k0 * a0[1] + k * a1[1])
        return [(p0[0] + k0 * a0[0], p0[1] + k0 * a0[1]), turn, *rest[2:]]

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
    rows = (row_gnd + VIA_SIZE + space, row_gnd + 2 * (VIA_SIZE + space))
    fans = {
        layer: fan(along_k[layer], [k_pin(j) for j in side_pins], pitch)
        for layer, side_pins in sides.items()
    }
    fan_start = rows[1] + VIA_SIZE / 2 + space + max(f[0][-1][0] for f in fans.values())
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
        for idx, ((k0, net, start), k, j, local) in enumerate(
            zip(ends[layer], along_k[layer], side_pins, fans[layer], strict=True)
        ):
            # From the mesh's end (straight on to the junction if its exit cell lies further
            # in), along the cable at k, up to the fan, then fanned out to the pin's place.
            along = [start, *route(k0, k)[:-1], at(fan_start, k)]
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

    # GND contacts: each back to the GND vias' row; a run of them (the pins the mesh leaves
    # over) joined along it, a via behind every few (vias at the pin pitch would crowd).
    run = 0
    for j, signal in enumerate(pins, start=1):
        if signal != "GND":
            run = 0
            continue
        result.pads.append(_pad(j, at, plug, k_pin, u, "GND"))
        via = at(row_gnd, k_pin(j))
        result.tracks.append(Track((at(plug, k_pin(j)), via), FRONT, "GND", w))
        if run:
            result.tracks.append(Track((at(row_gnd, k_pin(j - 1)), via), FRONT, "GND", w))
        if run % GND_VIA_EVERY == 0:
            result.vias.append(Via(via, "GND"))
        run += 1

    # Stitching vias along both edges of the cable and between the two meshes' traces.
    edge = cable.width / 2 - space - VIA_SIZE / 2 - cfg.mesh_edge_clearance / 2
    bundles = sorted(k for layer in along_k for k in along_k[layer])
    # (an edge's lane only clear of the traces)
    lanes = [
        k for k in (edge, -edge) if all(abs(k - b) >= VIA_SIZE / 2 + space + w / 2 for b in bundles)
    ]
    gaps = [
        (a + b) / 2 for a, b in itertools.pairwise(bundles) if b - a >= VIA_SIZE + 2 * space + w
    ]
    lanes += gaps
    keep_out = shapely.union_all(
        [shapely.Point(v.at).buffer(VIA_SIZE + space) for v in result.vias]
    )
    # (necking down, the traces cross the lanes in the stub and the first corner: none there)
    first = math.dist(path[0], path[1]) + cable.width / 2 + VIA_SIZE if wide else 0.0
    for k in lanes:
        line = LineString(offset_path(path, k))
        length = line.length - fan_start - VIA_SIZE
        s = max(STITCH_PITCH / 2, first)
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
@checkpoint.timed_step("verify")
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
    # (Only the points other copper meets need be nodes: a track's ends, and any point of
    # it another track's end or a via lands on; a track joins its own.)
    parent: dict[tuple, tuple] = {}

    def find(a: tuple) -> tuple:
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def join(a: tuple, b: tuple) -> None:
        parent[find(a)] = find(b)

    meets: dict[tuple, set] = defaultdict(set)  # (net, layer) -> keys other copper lands on
    for t in result.tracks:
        meets[(t.net, t.layer)] |= {key(t.points[0]), key(t.points[-1])}
    for v in result.vias:
        for layer in (FRONT, BACK):
            meets[(v.net, layer)].add(key(v.at))
    for t in result.tracks:
        first = (t.net, t.layer, key(t.points[0]))
        here = meets[(t.net, t.layer)]
        pts = np.asarray(t.points, float)
        ks = np.round(pts * 1e4).astype(np.int64)
        for kx, ky in ks[np.isin(ks[:, 0], [k[0] for k in here])]:
            if (int(kx), int(ky)) in here:
                join(first, (t.net, t.layer, (int(kx), int(ky))))
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
    nodes: dict[str, list[tuple]] = defaultdict(list)
    for n in list(parent):
        nodes[n[0]].append(n)
    for net in nets:
        pads = {num for num, _ in ends[net]}
        if len(pads) != 2:
            problems.append(f"{net} reaches {len(pads)} contact pads, not 2")
        roots = {find(n) for n in nodes[net]}
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
        segs = len(geoms)
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
        # (the tracks' segments against each other only as near as two of them can touch;
        # the vias and pads, few, against all as near as each can: else every segment
        # meets its neighbours a pitch off, many millions of pairs)
        tree = shapely.STRtree(g)
        lines, rest = np.arange(segs), np.arange(segs, len(geoms))
        reach = 2 * float(rad[:segs].max()) if segs else 0.0
        i, j = tree.query(g[lines], predicate="dwithin", distance=reach)
        i = lines[i]
        if len(rest):
            reach = float(rad[rest].max() + rad.max())
            i2, j2 = tree.query(g[rest], predicate="dwithin", distance=reach)
            i, j = np.concatenate([i, rest[i2]]), np.concatenate([j, j2])
        keep = (i != j) & (net_arr[i] != net_arr[j])
        i, j = i[keep], j[keep]
        i, j = np.minimum(i, j), np.maximum(i, j)
        if len(i):
            pairs = np.unique(np.stack([i, j], 1), axis=0)
            i, j = pairs[:, 0], pairs[:, 1]
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


def to_kicad(result: Layout, name: str = "pillowbox", tracks: bool = True) -> Any:
    """The layout as a gerbonara KiCad board: the foil's outline on Edge.Cuts, the folds on
    Dwgs.User, the glue tab and the flaps as filled polygons on User.1 (for stiffeners), the
    tracks (``tracks``: else left out, for ``kicad_text``), vias and the plug's contacts
    (footprint J1), and the cable's GND zone on both copper layers (left unfilled: KiCad
    fills it); on a page that holds it all with a margin, centred (``page``)."""
    from gerbonara.cad.kicad import base_types as kbt
    from gerbonara.cad.kicad import footprints as kfp
    from gerbonara.cad.kicad import graphical_primitives as kgr
    from gerbonara.cad.kicad import pcb as kpcb
    from gerbonara.cad.kicad import primitives as kpr
    from gerbonara.cad.kicad.base_types import AtPos, Net, Stroke, XYCoord
    from gerbonara.cad.kicad.sexp import Atom

    board = kpcb.Board.empty_board()
    board.legacy_footprints = None  # (gerbonara cannot write an empty legacy list)
    (ox, oy), (pw, ph) = page(result)
    board.paper = kbt.PageSettings(page_format="User", width=pw, height=ph)
    board.nets[0] = ""
    nets = sorted({t.net for t in result.tracks} | {"GND"})
    for net in nets:
        board.net_id(net)

    def xy(p: Point) -> XYCoord:
        return XYCoord(round(p[0] + ox, 6), round(p[1] + oy, 6))

    def stroke(width: float) -> Stroke:
        return Stroke(width=width, type=Atom.solid)

    for ring in (result.board.exterior, *result.board.interiors):
        pts = list(ring.coords)
        for a, b in itertools.pairwise(pts):
            board.add(kgr.Line(start=xy(a), end=xy(b), layer="Edge.Cuts", stroke=stroke(0.05)))
    for poly in result.stiffeners:
        board.add(
            kgr.Polygon(
                pts=[xy(p) for p in list(poly.exterior.coords)[:-1]],
                layer="User.1",
                stroke=stroke(0.05),
                fill=True,
            )
        )
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

    for track in result.tracks if tracks else ():
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
                at=AtPos(round(pad.at[0] + ox, 6), round(pad.at[1] + oy, 6), 0),
                size=XYCoord(*pad.size),
                layers=[FRONT, "F.Mask"],
                net=net,
            )
        )
    board.add(plug)

    if result.ground is not None:
        zone = kpr.Zone(net=board.net_id("GND"), net_name="GND", layers=[FRONT, BACK], name="GND")
        zone.connect_pads.clearance = min(result.clearance, result.cable_clearance)
        zone.min_thickness = result.width
        polys = getattr(result.ground, "geoms", [result.ground])
        ring = max(polys, key=lambda g: g.area).exterior
        zone.polygon = kpr.ZonePolygon(pts=[xy(p) for p in list(ring.coords)[:-1]])
        board.add(zone)
    return board


def kicad_project(result: Layout, name: str) -> dict:
    """A minimal KiCad project: the design rules the layout keeps (mesh trace and space,
    vias), as the default net class."""
    w, c = result.width, min(result.clearance, result.cable_clearance)
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


def kicad_text(result: Layout, board: Any) -> str:
    """The KiCad board file: ``board`` (made without the tracks: gerbonara takes minutes
    over a mesh's millions of segments) with the layout's tracks written in as text, each
    copper layer's in a process of its own (one after the other where there are none: in
    the browser)."""
    nets = {n: board.net_id(n) for n in {t.net for t in result.tracks}}  # (before: see below)
    text = board.serialize().rstrip()  # (which leaves the board's nets a list)
    offset, _ = page(result)
    jobs = [
        (i, layer, offset, [(nets[t.net], t.width, list(t.points), t.arcs)
                            for t in result.tracks if t.layer == layer])
        for i, layer in enumerate((FRONT, BACK))
    ]  # fmt: skip
    parts: list[str] = []
    if sys.platform != "emscripten" and sum(len(j[2]) for j in jobs) > 200:
        import concurrent.futures
        import multiprocessing

        try:
            ctx = multiprocessing.get_context("forkserver")
            with concurrent.futures.ProcessPoolExecutor(2, mp_context=ctx) as pool:
                parts = list(pool.map(_tracks_text, jobs))
        except (OSError, RuntimeError, concurrent.futures.process.BrokenProcessPool):
            parts = []
    parts = parts or [_tracks_text(j) for j in jobs]
    return text[:-1] + "\n" + "\n".join(p for p in parts if p) + ")\n"


def _tracks_text(job: tuple[int, str, Point, list]) -> str:
    """One copper layer's tracks as KiCad segments and arcs, moved by the page's offset
    (their uuids made up: unique per layer and segment)."""
    index, layer, (ox, oy), tracks = job
    out: list[str] = []
    k = 0
    for net, width, points, arcs in tracks:
        points = [(x + ox, y + oy) for x, y in points]
        if arcs:
            arcs = [
                ((a[0] + ox, a[1] + oy), None if m is None else (m[0] + ox, m[1] + oy),
                 (b[0] + ox, b[1] + oy))
                for a, m, b in arcs
            ]  # fmt: skip
        tail = f'(width {width}) (layer "{layer}") (net {net})'
        if arcs:
            for a, m, b in arcs:
                mid = "" if m is None else f" (mid {m[0]:.6f} {m[1]:.6f})"
                kind = "segment" if m is None else "arc"
                out.append(
                    f"  ({kind} (start {a[0]:.6f} {a[1]:.6f}){mid} (end {b[0]:.6f} {b[1]:.6f}) "
                    f'{tail} (uuid "{index:08x}-0000-4000-8000-{k:012x}"))'
                )
                k += 1
            continue
        for (x1, y1), (x2, y2) in itertools.pairwise(points):
            out.append(
                f"  (segment (start {x1:.6f} {y1:.6f}) (end {x2:.6f} {y2:.6f}) {tail} "
                f'(uuid "{index:08x}-0000-4000-8000-{k:012x}"))'
            )
            k += 1
    return "\n".join(out)


def render_stack(board: Any, result: Layout | None = None) -> Any:
    """The board's copper, mask, outline, drawing and drill layers as a gerbonara layer
    stack (zones unfilled: left out); the tracks the layout's (``result``: drawn straight,
    the board made without them), else the board's."""
    from gerbonara import apertures as ap
    from gerbonara import graphic_objects as go
    from gerbonara.cad.kicad.base_types import LAYER_MAP_K2G
    from gerbonara.layers import LayerStack
    from gerbonara.utils import MM

    stack = LayerStack()
    layers = {k: g for k, g in LAYER_MAP_K2G.items() if g in stack}
    own = () if result is None else (*board.track_segments, *board.track_arcs)
    for obj in (*board.graphic_objects(), *board.track_segments, *board.track_arcs):
        if (layer := layers.get(obj.layer)) and obj not in own:
            stack[layer].objects.extend(obj.render())
    (ox, oy), _ = page(result) if result is not None else ((0.0, 0.0), None)

    def moved(p: Point) -> Point:  # (onto the board's page, as ``to_kicad`` put it)
        return (p[0] + ox, p[1] + oy)

    for track in result.tracks if result is not None else ():
        objects = stack[layers[track.layer]].objects
        aperture = ap.CircleAperture(track.width, unit=MM)
        if track.arcs:
            for a, m, b in track.arcs:
                a, b = moved(a), moved(b)
                m = None if m is None else moved(m)
                if m is None:
                    objects.append(go.Line(a[0], -a[1], b[0], -b[1], aperture=aperture, unit=MM))
                    continue
                # (the arc's centre from its ends and middle: KiCad's file gives the middle,
                # not the centre; y flipped, as gerbonara draws KiCad's y down)
                (ax, ay), (mx, my), (bx, by) = (a[0], -a[1]), (m[0], -m[1]), (b[0], -b[1])
                d = 2 * (ax * (my - by) + mx * (by - ay) + bx * (ay - my))
                if abs(d) < 1e-12:  # (straight)
                    objects.append(go.Line(ax, ay, bx, by, aperture=aperture, unit=MM))
                    continue
                sa, sm, sb = ax * ax + ay * ay, mx * mx + my * my, bx * bx + by * by
                cx = (sa * (my - by) + sm * (by - ay) + sb * (ay - my)) / d
                cy = (sa * (bx - mx) + sm * (ax - bx) + sb * (mx - ax)) / d
                turn = (mx - ax) * (by - my) - (my - ay) * (bx - mx)  # (< 0: clockwise)
                objects.append(go.Arc(ax, ay, bx, by, cx - ax, cy - ay, aperture=aperture,
                                      clockwise=turn < 0, unit=MM))  # fmt: skip
            continue
        for (x1, y1), (x2, y2) in itertools.pairwise(moved(p) for p in track.points):
            objects.append(go.Line(x1, -y1, x2, -y2, aperture=aperture, unit=MM))
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
    board = to_kicad(result, name, tracks=False)
    pcb_file, pro_file = out / f"{name}.kicad_pcb", out / f"{name}.kicad_pro"
    pcb_file.write_text(kicad_text(result, board))
    pro_file.write_text(json.dumps(kicad_project(result, name), indent=2))
    stack = render_stack(board, result)
    gerbers = out / f"{name}-gerbers"
    stack.save_to_directory(gerbers, board_name=name)
    svgs = []
    for side in ("top", "bottom"):
        svg = out / f"{name}-{side}.svg"
        svg.write_text(str(stack.to_pretty_svg(side=side)))
        svgs.append(svg)
    return [pcb_file, pro_file, gerbers, *svgs]


def debug_svg(result: Layout) -> str:
    """The meshes for debugging, as an SVG: F.Cu and B.Cu side by side over the foil's
    outline and folds, each mesh trace a colour of its own, each partition's traces a colour
    family (hue) of their own, the partitions outlined dashed."""
    x0, y0, x1, y1 = result.board.bounds
    w, h, gap = x1 - x0, y1 - y0, 10.0

    def path(points: Iterable[Point], dx: float, closed: bool = False) -> str:
        pts = [f"{x - x0 + dx:.3f},{y - y0:.3f}" for x, y in points]
        return "M" + " L".join(pts) + (" Z" if closed else "")

    def colours(sizes: Sequence[int]) -> list[str]:
        out = []
        for k, size in enumerate(sizes):
            hue = 360 * k / len(sizes)
            for i in range(size):  # (darker to lighter, the hue turned a little within)
                t = i / max(size - 1, 1)
                out.append(f"hsl({hue + 24 * (t - 0.5):.0f},{80 - 20 * t:.0f}%,{30 + 30 * t:.0f}%)")
        return out

    def outline(dx: float) -> list[str]:
        rings = [result.board.exterior, *result.board.interiors]
        out = [
            f'<path d="{path(r.coords, dx, True)}" fill="{"#fafaf7" if i == 0 else "#fff"}" '
            'stroke="#888" stroke-width="0.15"/>'
            for i, r in enumerate(rings)
        ]
        out += [
            f'<path d="{path(sample([seg]), dx)}" fill="none" stroke="#bbb" stroke-width="0.12" '
            'stroke-dasharray="1 0.6"/>'
            for seg in result.folds
        ]
        return out

    body = []
    for k, layer in enumerate((FRONT, BACK)):
        dx = k * (w + gap)
        name = layer.replace(".", "-")
        body.append(f'<g id="{name}" inkscape:groupmode="layer" inkscape:label="{layer}">')
        body += outline(dx)
        m = result.meshes.get(layer)
        if m is not None:
            for part in m.parts:
                for g in getattr(part, "geoms", [part]):
                    body.append(
                        f'<path d="{path(g.exterior.coords, dx, True)}" fill="none" stroke="#555" '
                        'stroke-width="0.1" stroke-dasharray="0.8 0.5"/>'
                    )
            cols = colours(m.groups or (len(m.traces),))
            for i, t in enumerate(m.traces):
                body.append(
                    f'<path d="{path(t, dx)}" fill="none" stroke="{cols[i % len(cols)]}" '
                    f'stroke-width="{result.width:.3f}" stroke-linejoin="round" '
                    f'stroke-linecap="round"><title>{layer} trace {i + 1}</title></path>'
                )
        body.append(
            f'<text x="{dx + 2:.1f}" y="{h + 6:.1f}" font-family="sans-serif" '
            f'font-size="5">{layer}</text>'
        )
        body.append("</g>")
    W, H = 2 * w + gap, h + 10
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'width="{W:.3f}mm" height="{H:.3f}mm" viewBox="-2 -2 {W + 4:.3f} {H + 4:.3f}">\n'
        f'<rect x="-2" y="-2" width="{W + 4:.3f}" height="{H + 4:.3f}" fill="#fff"/>\n'
        + "\n".join(body)
        + "\n</svg>\n"
    )


def preview_json(result: Layout, offset: Point = (0.0, 0.0)) -> dict:
    """The layout for the UI's previews, compact: each copper layer's tracks as flat
    [x, y, x, y, ...] lists (mm, pattern coordinates, rounded to µm), the vias, the plug's
    pads, the foil's bounds (``bbox``) and the sheet ``offset`` of the 2D view."""

    def flat(points: Iterable[Point]) -> list[float]:
        return [round(c, 3) for p in points for c in p]

    lengths = result.net_lengths()
    longest = result.longest_trace()
    spacing, skew, density = result.spacing(), result.skew(), result.density()
    average = result.average_space()
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
                "traces": len(m.traces),
                "spacing": spacing[layer].to_dict(),
                "density": density[layer].to_dict() if layer in density else None,
                "average_space": round(average[layer], 4) if layer in average else None,
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
