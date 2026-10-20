"""Security mesh layout from a closed space-filling curve, after

    A. Bedel, Y. Coudert-Osmont, J. Martínez, R. I. Nishat, S. Whitesides, S. Lefebvre:
    "Closed space-filling curves with controlled orientation for 3D printing",
    Computer Graphics Forum 41(2), 2022, pp. 473-492, doi:10.1111/cgf.14488
    (reference code: https://github.com/mfx-inria/controllable-space-filling-curve, MIT).

The paper fills a polygon with one closed curve at an even spacing. Here that curve is the
mesh's centre line: its ``n`` traces are offsets of it, each a closed loop opened where the
curve runs out through the exit cell. The curve's spacing is ``n`` pitches at the least, so
the traces of neighbouring runs keep a pitch apart; where it is wider, the traces spread out
to share it evenly (the paper's per-segment area), so no gap opens wider than the spacing's
excess.

The steps follow the paper:

1. *Segments.* The area is split into the given zones (the folding pattern's panels: the
   paper's material zones), each zone's part into its pieces.
2. *Graph* (section 3.2). Seeds on a triangular grid, jittered, relaxed by Lloyd iterations
   into a centroidal Voronoi tessellation of each segment (shrunk by half a spacing); the
   cells' edges, clipped by the segment, form a planar graph whose vertices have degree three.
3. *Initial cycles* (3.3.1). A perfect matching of the graph (Edmonds); the edges it leaves
   out cover every vertex with disjoint cycles.
4. *Refinement and one cycle* (3.3.2). A vertex at each cell's centre, joined to the cell's
   corners; each centre is threaded into a cycle edge of its cell, the cycles are joined by
   split-and-reconnect moves and, failing those, doubled edges.
5. *Zoning.* The paper's zoning objective counts the curve's crossings of zone borders; here
   each segment's cycle is complete before the segments are joined, along a spanning tree,
   each join one split-and-reconnect across the shared border: two crossings per join, the
   least a closed curve through all segments can have. (The paper's stochastic optimizer,
   3.3.3, then has nothing left to improve: no alignment or orientation objective is set.)
6. *Geometry* (3.4). The curve is smoothed and relaxed towards an even spacing within its
   zone (the per-zone CVT objective: zone borders and the area's edge stand as mirrors).
7. *Room between the runs* (not in the paper, whose curve is a line of no width). Each run
   here carries a ribbon of all the traces, so where two runs part, the room between them
   grows up to a ribbon's width before another run fits: islands. The curve is grown into
   that room (as by differential growth: nearby runs repel, bends bulge where there is
   room), its tight bends rounded without pulling them back, and the traces spread to
   share what is left, in bends only as far as keeps neighbouring traces' skew down.

Steps 2 and 6 differ in their means: the Voronoi diagram is of points (no orientation field,
so no needles), and the geometry is relaxed by moving each vertex to the middle between its
neighbours across the curve (the CVT gradient across a run; a step per iteration, with a
Laplacian smoothing) instead of an L-BFGS solve.
"""

from __future__ import annotations

import math
import random
import sys

import numpy as np
import shapely
from shapely.geometry import LineString, Polygon

from yanartas_pillowbox import progress
from yanartas_pillowbox.mesh import (
    DOWN,
    LEFT,
    UP,
    Grid,
    Mesh,
    MeshError,
    Piece,
    Point,
    resample,
    sample_arcs,
)

try:  # (the settling's Rust core, on all cores: rust/python; the browser has its wasm)
    import yanartas_mesh as _native
except ImportError:  # pragma: no cover
    _native = None

SPACING = 1.0  # the curve's target spacing, in multiples of its least (n pitches)
SEED_SPACING = 1.4  # the CVT seeds' spacing, in target spacings (the cycle comes out sparser)
LLOYD = 6  # Lloyd iterations of the seeds
LLOYD_CURVE = 20  # CVT steps of the curve
SPREAD = 1.3  # the traces spread over at most this many target spacings
SMOOTH = 10  # the pitch of the traces smoothed over this many vertices either way
GAIN = 3.0  # the Laplacian weight per relative excess length
REPAIR = 100  # steps pushing runs apart (at most)
WINDOW = 1.5  # parts of the curve nearer than this many least spacings along it: one run
FINE = 4  # the traces offset from the curve split this many times finer
RAMP = 3  # ... ramped in over this many vertices off the tongue
MARGIN = 0.02  # ... at a pitch this much above the least (but at the exit)
SIMPLIFY = 0.002  # the traces simplified within this (mm; well within the margin)
LOOP = 3.0  # loops the traces' offsets leave in tight bends: cut out up to this many spacings long
ARCS = 0.002  # drawn in lines and arcs (``arcs``): within this of the traces (mm)
INSIDE = 0.9  # traces inside a bend keep within this share of its radius
PUSH_MARGIN = 1.04  # runs closer than this many times their least spacing: pushed apart
BEND_SLACK = 0.85  # bends this much tighter than the tightest: smoothed (U-turns sit at it)
GROW = 150  # steps growing the curve into the room left between its runs (at most)
REACH = 1.06  # ... runs nearer than this many least spacings repel each other
GROW_RATE = 0.5  # ... the share of the room a bend bulges into per step
HARD = 10  # repair steps before bends still too sharp are smoothed the hard way
STALL = 10  # ... until it has grown less than 0.2 % over this many steps
STRAIGHT = 0.1  # bends gentler than this many least spacings' curvature: straight (skew)
SETTLE = 40  # steps settling each trace into the middle of the room either side of it
SETTLE_RATE = 0.5  # ... the share of the way there a step goes
SETTLE_REACH = 3.0  # ... copper looked for this many pitches out (beyond: a hole, moved into)
SETTLE_PIN = 1.5  # ... bends tighter than this many pitches' radius do not move inwards
SETTLE_COOL = 2.0  # ... the moves dying down over the steps as (1 - step / steps) to this
SETTLE_STEP = 0.35  # ... the traces held at this many pitches between vertices
SETTLE_STILL = 0.005  # ... moves shorter than this many pitches: none
SETTLE_BAND = 1.0  # ... traces within this many pitches of length of each other: not steered
SETTLE_LEAP = 0.34  # ... a vertex moved at most this many of the steps between vertices
SETTLE_TUNE = 3.0  # ... a trace this many pitches behind (or ahead): steered at full strength
SETTLE_STEER = 0.6  # ... the share of its bends' depth a step grows (or straightens) them by
SETTLE_SPAN = 25  # ... (where along the curve it gains more, over this many places)
SETTLE_STEER_COOL = 2.0  # ... (the steering dying down as the moves, to this)
SETTLE_TIP = 1.0  # ... U-turns tighter than this many pitches per trace's radius: tips
SETTLE_REACH_OUT = 1.0  # ... leaning out along their axis by this share of the room
SETTLE_FILL = 2.0  # ... down the slope of the traces' density (into holes) by this much
SETTLE_FILL_BLUR = 0.5  # ... (the density blurred over this many pitches per trace)
SETTLE_BEND = 2  # ... the bends it grows (or straightens): this many vertices either way
SETTLE_SMOOTH = 3  # ... jitter smoothed this many times a step
SETTLE_FINISH = 10  # ... then all smoothed this many times (kept clear)
SCALE = 4  # ... (the steps and the tips' lean for this many traces; more: in proportion)
MATCH = 20  # steps matching the settled traces' lengths (taking it out of the longer)
# (the band above how far the leads swing to and fro through the bends: else every swing is cut)
MATCH_BAND = 15.0  # ... no trace more than this many pitches ahead of the shortest
MATCH_RATE = 0.5  # ... the share of their bends' depth a step straightens them by, at most
ATTEMPTS = 8  # tries with fresh seeds when a graph comes out degenerate


# ----------------------------------------------------------------------------- frame
class _Frame:
    """A frame in which the exit cell's open side is its top (-y) side: the given side
    turned or mirrored there."""

    def __init__(self, side: int) -> None:
        self.side = side

    def fwd(self, xy: np.ndarray) -> np.ndarray:
        x, y = xy[:, 0], xy[:, 1]
        if self.side == UP:
            return np.stack([x, y], 1)
        if self.side == DOWN:
            return np.stack([x, -y], 1)
        if self.side == LEFT:
            return np.stack([y, x], 1)
        return np.stack([y, -x], 1)  # RIGHT

    def inv(self, xy: np.ndarray) -> np.ndarray:
        x, y = xy[:, 0], xy[:, 1]
        if self.side == UP:
            return np.stack([x, y], 1)
        if self.side == DOWN:
            return np.stack([x, -y], 1)
        if self.side == LEFT:
            return np.stack([y, x], 1)
        return np.stack([-y, x], 1)

    def geom(self, g: shapely.Geometry) -> shapely.Geometry:
        return shapely.transform(g, self.fwd)


# ----------------------------------------------------------------------------- segments
def _polygons(g: shapely.Geometry) -> list[Polygon]:
    return [p for p in shapely.get_parts(g) if isinstance(p, Polygon) and not p.is_empty]


def _regions(area: shapely.Geometry, zones: list[Polygon], least: float) -> list[Polygon]:
    """The area cut into the zones' pieces (and what no zone covers), pieces too small to
    take a curve left out."""
    out: list[Polygon] = []
    rest = area
    for z in zones:
        out += _polygons(shapely.intersection(area, z))
        rest = shapely.difference(rest, z)
    out += _polygons(rest)
    return [r for r in out if r.area >= least]


# ----------------------------------------------------------------------------- curve
def _curve(
    area: shapely.Geometry,
    zones: list[Polygon],
    spacing: float,
    mouth: tuple[Point, Point],
    seed: int,
) -> tuple[np.ndarray, list[Polygon], np.ndarray, int, int]:
    """The closed curve through the segments the exit's can reach, by the Rust core
    (``graph::curve``; see ARCHITECTURE.md, 2. to 5.): its vertices from the tongue's end at
    ``mouth[0]`` round to its other end (the tongue, out through the exit and back, closes
    it), the regions, each vertex's region, the cells and the regions left out. Here, what
    needs shapely: the regions, the segments' domains (each region's pieces shrunk by half a
    spacing) and the borders between regions."""
    regions = _regions(area, zones, 2 * spacing**2)
    segments = [
        (ri, d)
        for ri, r in enumerate(regions)
        for d in _polygons(r.buffer(-spacing / 2))
        if d.area >= spacing**2
    ]
    if not segments:
        raise MeshError("no room for the mesh")
    try:
        pts, region, cells, left = _core().curve_graph(
            [(ri, [np.asarray(r.coords, float)[:-1] for r in _rings(d)]) for ri, d in segments],
            _shared_borders(regions, spacing),
            (tuple(map(float, mouth[0])), tuple(map(float, mouth[1]))),
            spacing,
            seed,
            {"seed_spacing": SEED_SPACING, "lloyd": LLOYD, "attempts": ATTEMPTS},
            lambda step, steps: progress.report("graph", step, steps),
        )
    except ValueError as e:
        raise MeshError(str(e)) from e
    return np.asarray(pts), regions, np.asarray(region), int(cells), int(left)


def _shared_borders(
    regions: list[Polygon], spacing: float
) -> list[tuple[int, int, list[np.ndarray]]]:
    """The regions that share a border at least two spacings long, longest first: each
    pair with its border's lines (the longest first)."""
    tree = shapely.STRtree(regions)
    pairs = []
    a_idx, b_idx = tree.query(regions, predicate="intersects")
    for i, j in zip(a_idx, b_idx, strict=True):
        if i < j:
            border = shapely.line_merge(
                shapely.intersection(regions[i].boundary, regions[j].buffer(1e-6))
            )
            if border.length >= 2 * spacing:
                lines = sorted(_lines(border), key=lambda ln: -ln.length)
                pairs.append((border.length, int(i), int(j), lines))
    pairs.sort(key=lambda p: -p[0])
    return [(i, j, [np.asarray(ln.coords, float) for ln in lines]) for _, i, j, lines in pairs]


def _lines(g: shapely.Geometry) -> list[LineString]:
    return [p for p in shapely.get_parts(g) if isinstance(p, LineString) and p.length > 0]


# ----------------------------------------------------------------------------- geometry
def _relax(
    curve: np.ndarray,
    tongue: np.ndarray,
    area: shapely.Geometry,
    regions: list[Polygon],
    spacing: float,
    least: float,
    pitch: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, int]:
    """The curve, relaxed by the Rust core (``curve::relax``; see ARCHITECTURE.md, 6. and 7.):
    ``curve`` an open polyline from the tongue's left end round to its right end, the tongue
    closing it. Returned closed (the tongue last), with the number of vertices before the
    tongue's. Here, what needs shapely: the regions' rings and area, the area's edge and the
    borders between regions (points along them)."""
    step = spacing / 8  # (the edge's points: half the finer relaxing step apart)
    edge = np.vstack([resample(np.asarray(r.coords), step) for r in _rings(area)])
    p, k = _core().relax_curve(
        np.ascontiguousarray(curve, float),
        np.ascontiguousarray(tongue, float),
        [[np.asarray(r.coords, float) for r in _rings(z)] for z in regions],
        sum(r.area for r in regions) / spacing,
        edge,
        np.ascontiguousarray(_borders(regions, area, step), float),
        spacing,
        least,
        pitch,
        tuple(float(v) for v in rng.random(2) * spacing / 3),
        {
            "lloyd_curve": LLOYD_CURVE,
            "gain": GAIN,
            "push_margin": PUSH_MARGIN,
            "window": WINDOW,
            "bend_slack": BEND_SLACK,
            "grow": GROW,
            "reach": REACH,
            "grow_rate": GROW_RATE,
            "hard": HARD,
            "stall": STALL,
            "repair": REPAIR,
            "inside": INSIDE,
        },
        lambda step, steps: progress.report("relax", step, steps),
    )
    return np.asarray(p), int(k)


def _borders(regions: list[Polygon], area: shapely.Geometry, step: float) -> np.ndarray:
    """Points along the borders between regions (the folds; not the area's edge)."""
    edge = area.boundary.buffer(1e-6)
    lines = shapely.difference(shapely.union_all([r.boundary for r in regions]), edge)
    pts = [resample(shapely.get_coordinates(ln), step) for ln in _lines(shapely.line_merge(lines))]
    return np.vstack(pts) if pts else np.zeros((0, 2))


def _unlooped(ring: np.ndarray, most: float) -> np.ndarray:
    """The closed trace without the small loops an offset can leave in a tight bend (where
    it crosses itself, the shorter way round, if no longer than ``most``, cut out)."""
    for _ in range(50):
        m = len(ring)
        segs = shapely.linestrings(np.stack([ring, np.roll(ring, -1, axis=0)], 1))
        a, b = shapely.STRtree(segs).query(segs, predicate="crosses")
        gap = np.abs(a - b)
        keep = (a < b) & (np.minimum(gap, m - gap) > 1)
        if not keep.any():
            return ring
        seg = np.hypot(*np.diff(np.vstack([ring, ring[:1]]), axis=0).T)
        run = np.concatenate([[0.0], np.cumsum(seg)])
        best = None
        for i, j in zip(a[keep], b[keep], strict=True):
            inner = run[j] - run[i + 1]  # (from i + 1 to j)
            outer = run[m] - inner
            size = min(inner, outer)
            if size <= most and (best is None or size < best[0]):
                best = (size, int(i), int(j), inner <= outer)
        if best is None:
            return ring
        _, i, j, inside = best
        x = shapely.get_coordinates(shapely.intersection(segs[i], segs[j]))[0]
        if inside:  # (vertices i + 1 .. j out)
            ring = np.vstack([ring[: i + 1], [x], ring[j + 1 :]])
        else:  # (vertices j + 1 .. i out, round the end)
            ring = np.vstack([[x], ring[i + 1 : j + 1]])
    return ring


def _opened(ring: np.ndarray, cut: Polygon) -> np.ndarray:
    """The closed trace ``ring`` opened at the exit: the one run of its vertices within
    ``cut`` taken out, its ends where it crosses into ``cut`` (the rest of it as it is)."""
    inside = shapely.contains_xy(cut, ring[:, 0], ring[:, 1])
    m = len(ring)
    starts = [i for i in range(m) if inside[i - 1] and not inside[i]]
    stops = [i for i in range(m) if not inside[i] and inside[(i + 1) % m]]
    if len(starts) != 1 or len(stops) != 1:
        raise MeshError("a trace does not leave through the exit")
    s, e = starts[0], stops[0]
    path = np.roll(ring, -s, axis=0)[: (e - s) % m + 1]
    edge = cut.boundary

    def cross(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        q = shapely.get_coordinates(LineString([a, b]).intersection(edge))
        return q[np.argmin(np.hypot(*(q - b).T))] if len(q) else a

    return np.vstack([[cross(ring[s - 1], ring[s])], path, [cross(ring[(e + 1) % m], ring[e])]])


def _longest(g: shapely.Geometry) -> LineString:
    """The line, or the longest of its pieces once joined."""
    g = shapely.line_merge(g) if not isinstance(g, LineString) else g
    return g if isinstance(g, LineString) else max(shapely.get_parts(g), key=lambda p: p.length)


def _rings(g: shapely.Geometry) -> list[shapely.LinearRing]:
    return [r for poly in _polygons(g) for r in (poly.exterior, *poly.interiors)]


def _lanes(
    p: np.ndarray,
    k: int,
    area: shapely.Geometry,
    n: int,
    pitch: float,
    spacing: float,
    exact: np.ndarray,
) -> list[np.ndarray]:
    """The ``n`` traces round the closed curve ``p`` (vertices ``k`` on: the tongue's), as
    closed polylines, by the Rust core (``lanes::lanes``): offsets of the curve at a pitch
    that shares the spacing to the next run on each side evenly (the area's edge counts as a
    run's middle), never below ``pitch`` (with a margin; exactly where ``exact``: the
    tongue's legs), in bends only as far as keeps skew down."""
    rings = [resample(np.asarray(r.coords), spacing / 2) for r in _rings(area)]
    out = _core().offset_lanes(
        np.ascontiguousarray(p, float),
        k,
        np.vstack([c[:-1] for c in rings]),
        np.vstack([c[1:] for c in rings]),
        n,
        pitch,
        spacing,
        [bool(x) for x in exact],
        {
            "spread": SPREAD,
            "smooth": SMOOTH,
            "fine": FINE,
            "ramp": float(RAMP),
            "margin": MARGIN,
            "inside": INSIDE,
            "window": WINDOW,
            "straight": STRAIGHT,
        },
    )
    return [np.asarray(t) for t in out]


# ----------------------------------------------------------------------------- settling
def _settle(
    lines: list[np.ndarray],
    pitch: float,
    area: shapely.Geometry,
    regions: list[Polygon],
    keep: shapely.Geometry,
) -> list[np.ndarray]:
    """The traces, each settled on its own into the room around it, then matched in length,
    by the Rust core (rust/core; see ARCHITECTURE.md, Settling): natively its extension
    (yanartas_mesh, on all cores), in the browser its WebAssembly build. Here, what needs
    shapely: the edge's points (the area's edge, and the zones' borders but where the
    traces cross them at the curve's joins, where they stay as laid), the zones' rings, and
    what is left as laid (``keep``: the exit, the neck)."""
    step = SETTLE_STEP * pitch
    far = SETTLE_REACH * pitch
    edge = np.vstack([resample(np.asarray(r.coords), step / 2) for r in _rings(area)])
    borders = _borders(regions, area, step / 2)
    xs = shapely.get_coordinates(
        shapely.intersection(
            shapely.MultiLineString(lines), shapely.union_all([r.boundary for r in regions])
        )
    )
    if len(borders) and len(xs):
        near_x = Grid(xs, far).nearest(borders)
        clear = (near_x < 0) | (np.hypot(*(borders - xs[np.maximum(near_x, 0)]).T) > far)
        edge = np.vstack([edge, borders[clear]])
    elif len(borders):
        edge = np.vstack([edge, borders])
    settle = _core().settle_traces

    def report(d: dict) -> None:
        progress.report(d.pop("phase"), d.pop("step"), d.pop("steps"), **d)

    out = settle(
        [np.ascontiguousarray(t, float) for t in lines],
        pitch,
        np.ascontiguousarray(edge, float),
        [[np.asarray(r.coords, float) for r in _rings(z)] for z in regions],
        [[np.asarray(r.coords, float) for r in _rings(g)] for g in _polygons(keep)],
        _params(len(lines)),
        report,
    )
    return [np.asarray(t) for t in out]


def _core() -> object:
    """The Rust core (rust/core): natively its extension ``yanartas_mesh``, in the browser
    its WebAssembly build behind the same calls."""
    core = _native if _native is not None else _browser_core()
    if core is None:
        raise MeshError(
            "the mesh layout needs its Rust core: install yanartas-mesh (rust/python), "
            "or in the browser build its WebAssembly (artifact/build.py)"
        )
    return core


def _browser_core() -> object | None:
    """In the browser (Pyodide), the WebAssembly build the web worker loaded
    (``self.yanartasMesh``), behind the extension's calls; else none."""
    if sys.platform != "emscripten":
        return None
    import types

    import js  # type: ignore[import-not-found]
    from pyodide.ffi import create_proxy, to_js  # type: ignore[import-not-found]

    mesh = getattr(js, "yanartasMesh", None)
    if mesh is None:
        return None

    def f64(a: np.ndarray) -> object:
        return to_js(np.ascontiguousarray(a, float).ravel())

    def u32(a: list[int]) -> object:
        return to_js(np.asarray(a, np.uint32))

    def flat(points: list[np.ndarray]) -> tuple[object, object]:
        both = np.vstack(points) if points else np.zeros((0, 2))
        return f64(both), u32([len(q) for q in points])

    def obj(d: dict) -> object:
        return to_js(d, dict_converter=js.Object.fromEntries)

    def unflat(points: object, lens: object) -> list[np.ndarray]:
        pts = np.asarray(points.to_py(), float).reshape(-1, 2)
        return np.split(pts, np.cumsum(np.asarray(lens.to_py(), int))[:-1])

    def call(fn, *args, report=None):  # noqa: ANN001, ANN002, ANN202
        hook = create_proxy(report) if report is not None else None
        try:
            return fn(*args, hook)
        finally:
            if hook is not None:
                hook.destroy()

    def settle_traces(lines, pitch, edge, zones, keep, params, report):  # noqa: ANN001, ANN202
        rings = [r for z in zones for r in z]
        held = [r for z in keep for r in z]
        out = call(
            mesh.settle, *flat(lines), pitch, f64(edge), *flat(rings),
            u32([len(z) for z in zones]), *flat(held), u32([len(z) for z in keep]),
            obj(params), report=lambda o: report(o.to_py()),
        )  # fmt: skip
        return unflat(out.points, out.lens)

    def relax_curve(*a: object) -> tuple[np.ndarray, int]:
        curve, tongue, regions, target, edge, borders, spacing, least, pitch = a[:9]
        offset, params, report = a[9:]
        rings = [r for z in regions for r in z]
        out = call(
            mesh.relax_curve, f64(curve), f64(tongue), *flat(rings),
            u32([len(z) for z in regions]), target, f64(edge), f64(borders), spacing, least,
            pitch, f64(np.array(offset)), obj(params), report=report,
        )  # fmt: skip
        return np.asarray(out.points.to_py(), float).reshape(-1, 2), int(out.k)

    def offset_lanes(p, k, edge_a, edge_b, n, pitch, spacing, exact, params):  # noqa: ANN001, ANN202
        out = mesh.offset_lanes(
            f64(p), k, f64(edge_a), f64(edge_b), n, pitch, spacing,
            to_js(np.asarray(exact, np.uint8)), obj(params),
        )  # fmt: skip
        return unflat(out.points, out.lens)

    def curve_graph(segments, borders, mouth, spacing, seed, params, report):  # noqa: ANN001, ANN202
        rings = [r for _, rs in segments for r in rs]
        lines = [ln for _, _, ls in borders for ln in ls]
        try:
            out = call(
                mesh.curve_graph, u32([r for r, _ in segments]), *flat(rings),
                u32([len(rs) for _, rs in segments]),
                u32([v for i, j, _ in borders for v in (i, j)]),
                u32([len(ls) for _, _, ls in borders]), *flat(lines),
                f64(np.array(mouth)), spacing, seed >> 32, seed & 0xFFFFFFFF, obj(params),
                report=report,
            )  # fmt: skip
        except Exception as e:  # (pyodide's JsException: what the core refused)
            raise ValueError(str(e)) from e
        pts = np.asarray(out.points.to_py(), float).reshape(-1, 2)
        return pts, list(out.region.to_py()), int(out.cells), int(out.left)

    def fit_arcs(lines, tol):  # noqa: ANN001, ANN202
        out = mesh.fit_arcs(*flat(lines), tol)
        rows = np.asarray(out.rows.to_py(), float).reshape(-1, 7)
        return np.split(rows, np.cumsum(np.asarray(out.counts.to_py(), int))[:-1])

    return types.SimpleNamespace(
        fit_arcs=fit_arcs,
        settle_traces=settle_traces,
        relax_curve=relax_curve,
        offset_lanes=offset_lanes,
        curve_graph=curve_graph,
    )


def _params(traces: int = SCALE) -> dict[str, float]:
    """The settling's constants, by the Rust core's names for them, for ``traces`` traces
    (the holes left where a ribbon's bends meet grow with its width: more steps for them,
    and U-turn tips leaning out further into them)."""
    more = max(1.0, traces / SCALE)
    return {
        "steps": round(SETTLE * more),
        "rate": SETTLE_RATE,
        "reach": SETTLE_REACH,
        "pin": SETTLE_PIN,
        "cool": SETTLE_COOL,
        "step": SETTLE_STEP,
        "still": SETTLE_STILL,
        "band": SETTLE_BAND,
        "leap": SETTLE_LEAP,
        "tune": SETTLE_TUNE,
        "steer": SETTLE_STEER,
        "span": SETTLE_SPAN,
        "steer_cool": SETTLE_STEER_COOL,
        "tip": SETTLE_TIP * more,
        "reach_out": SETTLE_REACH_OUT * more,
        "fill": SETTLE_FILL,
        "fill_blur": SETTLE_FILL_BLUR,
        "bend": SETTLE_BEND,
        "smooth": SETTLE_SMOOTH,
        "finish": SETTLE_FINISH,
        "match_steps": MATCH,
        "match_band": MATCH_BAND,
        "match_rate": MATCH_RATE,
    }


# ----------------------------------------------------------------------------- generator
def generate(
    mask: shapely.Geometry,
    exit_corner: Point,
    exit_side: int,
    traces: int,
    pitch: float,
    seed: int | str | None = 0,
    zones: tuple[Polygon, ...] | list[Polygon] = (),
    arcs: bool = False,
    neck: LineString | None = None,
) -> Mesh:
    """The mesh over ``mask``: ``traces`` nets at ``pitch`` (trace plus space) round a closed
    space-filling curve, out through the exit cell (as ``kimesh.generate``: its corner with
    the smallest x and y ``exit_corner``, its side ``exit_side`` open). ``zones`` (the
    folding pattern's panels) are filled one by one and joined across their borders as
    seldom as can be; ``seed`` makes the layout repeatable."""
    if traces < 1:
        raise MeshError("need at least one trace")
    n = traces
    c = 2 * n * pitch
    least = n * pitch
    spacing = SPACING * least
    frame = _Frame(exit_side)
    ox, oy = exit_corner
    cell = frame.geom(shapely.box(ox, oy, ox + c, oy + c))
    x0, y0, _, _ = cell.bounds
    area = frame.geom(mask)
    # (the exit's leads run on from the open side: nothing of the mesh beyond it)
    area = shapely.difference(area, shapely.box(x0 - pitch, y0 - 4 * c, x0 + c + pitch, y0))
    if not area.buffer(1e-6).contains(shapely.box(x0, y0, x0 + c, y0 + 1.5 * spacing)):
        raise MeshError("no room for the mesh's exit cell")
    ym, ytop = y0 + spacing, y0 - least
    # The tongue's legs run straight through the exit cell to its mouth: the curve keeps
    # out of the cell up to there (its traces' pitch there is the least).
    area = shapely.difference(area, shapely.box(x0, y0 - 4 * c, x0 + c, ym))
    rng = random.Random(seed)
    nrng = np.random.default_rng(rng.getrandbits(64))
    # The tongue: two legs, a run's spacing apart, straight up through the exit cell (and
    # on along the neck, its corridor kept out of the area as the cell).
    ax, bx = x0 + c / 4, x0 + 3 * c / 4
    centre = None
    if neck is not None:
        q = np.asarray(frame.geom(neck).coords, float)
        q[0] = (x0 + c / 2, ym)
        if LineString(q).length > 1e-6:
            centre = LineString(q).simplify(1e-9)  # (no points in line: one offset each way)
    if centre is None:
        legs = (np.array([(ax, ym)]), np.array([(bx, ym)]))
        inward = np.array([0.0, 1.0])
    else:
        area = shapely.difference(area, centre.buffer(spacing, cap_style="flat"))
        legs = tuple(
            np.asarray(_longest(shapely.offset_curve(centre, d, join_style="round")).coords)
            for d in (spacing / 2, -spacing / 2)
        )
        if abs(legs[0][0][0] - ax) > abs(legs[1][0][0] - ax):
            legs = legs[::-1]
        tail = np.asarray(centre.coords)[-2:]
        inward = (tail[1] - tail[0]) / np.linalg.norm(tail[1] - tail[0])
    area = shapely.union_all(_polygons(area))  # (no slivers of lines or points left)
    la, lb = legs  # (each from the exit cell's mouth on to the curve's)
    pts, regions, _, cells, left = _curve(
        area,
        [frame.geom(z) for z in zones],
        spacing,
        (tuple(la[-1] + inward * spacing / 2), tuple(lb[-1] + inward * spacing / 2)),
        rng.getrandbits(64),
    )
    tongue = np.vstack([lb[::-1], [(bx, ytop), (ax, ytop)], la])
    curve = np.vstack([la[-1:], pts, lb[-1:]])
    progress.report("graph", cells=cells)
    p, k = _relax(curve, tongue, area, regions, spacing, least, pitch, nrng)
    progress.report("relax", vertices=len(p))
    cut = shapely.box(x0, ytop - c, x0 + c, y0)  # (within the leads' corridor)
    out = []
    exact = np.zeros(len(p), bool)  # (the tongue's legs: the traces at the pitch)
    exact[k:] = p[k:, 1] < y0 + spacing / 4
    if centre is not None:  # (and along the neck, but where it opens out)
        along = shapely.line_locate_point(centre, shapely.points(p[k:]))
        exact[k:] |= along < centre.length - 0.75 * spacing
    lines = []
    for ring in _lanes(p, k, area, n, pitch, spacing, exact):
        lines.append(_opened(_unlooped(ring, LOOP * spacing), cut))
    if SETTLE:
        # (the tongue: its leads beyond the area's edge, its legs through the exit cell and
        # along the neck, as laid at the pitch; all else settles, the curve's turns round
        # it too, or holes are left either side of it)
        keep = shapely.box(x0, ytop - c, x0 + c, ym)
        if centre is not None:
            keep = shapely.union_all([keep, centre.buffer(spacing, cap_style="flat")])
        progress.report("lanes", traces=len(lines))
        lines = _settle(lines, pitch, area, regions, keep)
    progress.report("match", 1, 1)
    shapes: list[tuple[Piece, ...] | None] = []
    if arcs:
        tol = ARCS * pitch / 0.3
        for rows in _core().fit_arcs([np.ascontiguousarray(xy, float) for xy in lines], tol):
            ends = frame.inv(np.asarray(rows, float)[:, 1:].reshape(-1, 2)).reshape(-1, 3, 2)
            pieces = tuple(
                (
                    (float(a[0]), float(a[1])),
                    (float(m[0]), float(m[1])) if kind else None,
                    (float(b[0]), float(b[1])),
                )
                for kind, (a, m, b) in zip(np.asarray(rows)[:, 0], ends, strict=True)
            )
            shapes.append(pieces)
            out.append(np.asarray(sample_arcs(pieces, tol)))
    else:
        for xy in lines:
            line = LineString(xy)
            tol = SIMPLIFY * pitch / 0.3
            fast = line.simplify(tol, preserve_topology=False)
            line = fast if fast.is_simple else line.simplify(tol, preserve_topology=True)
            out.append(frame.inv(np.asarray(line.coords)))
            shapes.append(None)
    # net 1 outermost: its ends farthest from the exit's middle
    mid = frame.inv(np.array([[(ax + bx) / 2, y0]]))[0]
    order = sorted(range(len(out)), key=lambda i: -math.dist(out[i][0], mid))
    nets = tuple(tuple((float(x), float(y)) for x, y in out[i]) for i in order)
    shaped = tuple(shapes[i] for i in order) if arcs else None
    return Mesh(nets, c, cells, left, exit_corner, "sfc", shaped)
