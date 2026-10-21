"""The built-in FPC cable: its layout in the pattern, its folds, and where it goes in the box."""

import itertools
import math

import pytest
from helpers import is_closed_loop, polyline, self_intersections
from shapely.geometry import LineString, Point, Polygon

from yanartas_pillowbox import fpc
from yanartas_pillowbox.config import Config, ConfigError
from yanartas_pillowbox.geometry import (
    Arc,
    FoldDirection,
    FoldedCable,
    Line,
    build_cross_section,
    build_model3d,
    build_pattern,
)

D = Config.defaults()
CONFIGS = {
    "default": D,
    "down": D.with_values(fpc_cable="down"),
    "entry": D.with_values(fpc_entry_offset=20),  # (higher up the edge)
    # (the meshes' exits wider than the cable: its stub widened for them)
    "wide": D.with_values(mesh_trace_space=1.0, mesh_traces=10),
    "long": D.with_values(fpc_cable_length=180),  # (more rows)
    "ears": D.with_values(fpc_cable_inset=1.5, fpc_plug_length=6),
    "no-lid": D.with_values(end_wall_gap=0),
    "sharp": D.with_values(fpc_corner_radius=0, fpc_cable_gap=2),
    "thin": D.with_values(thickness=0, fpc_pins=20, fpc_pitch=0.3),
    "thick": D.with_values(height=40, thickness=1, fpc_pins=40, fpc_cable_length=150),
}


@pytest.fixture(params=list(CONFIGS), ids=list(CONFIGS))
def cfg(request):
    return CONFIGS[request.param]


def cable_segments(pattern):
    """The outline's segments that belong to no face of the box: the cable's cut."""
    keys = {_key(s) for f in pattern.faces for s in f.boundary}
    return [s for s in pattern.outline.segments if _key(s) not in keys]


def _key(seg):
    r = lambda p: (round(p[0], 6), round(p[1], 6))  # noqa: E731
    return (*sorted((r(seg.start), r(seg.end))), r(seg.point_at(0.5)))


def test_outline_stays_one_simple_loop(cfg):
    pattern = build_pattern(cfg)
    assert is_closed_loop(pattern.outline.segments)
    assert self_intersections(polyline(pattern.outline.segments, 16)) == []


def test_folded_cable_is_straight_and_as_long_as_set(cfg):
    """With every corner folded flat, every corner of the centreline lies on one line through
    the junction's middle, out of the edge, and the tip reaches the set length past the
    junction."""
    pattern = build_pattern(cfg)
    cable = pattern.cable
    creases = tuple((f.segment.start, f.segment.end) for f in cable.corners)
    # (the clipped creases lie on the same lines as the layout's)
    y0 = cable.path[0][1]
    for i, p in enumerate(cable.path[1:]):
        q = fpc.unfold(p, i, creases)
        assert q[1] == pytest.approx(y0, abs=1e-9)
    tip = fpc.unfold(cable.path[-1], len(cable.path) - 2, creases)
    assert abs(tip[0] - cable.junction[0][0]) == pytest.approx(cfg.fpc_cable_length, abs=1e-9)


def test_corner_creases_lay_each_run_back_along_the_one_before(cfg):
    """Each crease is its corner square's diagonal from the outer to the inner corner:
    mirroring the outgoing run across it gives the incoming run, reversed."""
    cable = build_pattern(cfg).cable
    path = cable.path
    assert len(cable.corners) == len(path) - 2
    for fold, a, p, b in zip(cable.corners, path, path[1:], path[2:], strict=False):
        assert fold.segment.distance_to(p) < 1e-9  # through the corner's centre
        d_in = _unit(a, p)
        d_out = _unit(p, b)
        mirrored = fpc.reflect(
            (p[0] + d_out[0], p[1] + d_out[1]), (fold.segment.start, fold.segment.end)
        )
        assert mirrored == pytest.approx((p[0] - d_in[0], p[1] - d_in[1]), abs=1e-9)


def _unit(a, b):
    k = math.dist(a, b)
    return ((b[0] - a[0]) / k, (b[1] - a[1]) / k)


def test_creases_run_from_cut_to_cut(cfg):
    pattern = build_pattern(cfg)
    for fold in pattern.cable.folds:
        for p in (fold.segment.start, fold.segment.end):
            assert pattern.outline.distance_to(p) < 1e-6, fold.name
        for i in range(1, 20):
            assert pattern.outline.distance_to(fold.segment.point_at(i / 20)) > 1e-3


def test_cable_leaves_the_free_edge_at_its_entry(cfg):
    """The cable leaves the front panel's free straight edge (x = 0) where set (by default
    as low as it can, turning up; as high, turning down), outward, and turns up or down
    along it; the rest of the pattern is the same as without it."""
    pattern = build_pattern(cfg)
    plain = build_pattern(cfg.with_values(fpc_cable="none"))
    cable = pattern.cable
    (xa, ya), (xb, yb) = cable.junction
    assert xa == xb == 0
    assert abs(ya - yb) == pytest.approx(fpc.junction_width(cfg))
    lo, hi = fpc.entry_range(cfg)
    entry = hi - cfg.fpc_entry_offset if cfg.fpc_cable == "up" else lo + cfg.fpc_entry_offset
    assert (ya + yb) / 2 == pytest.approx(entry)
    # (the cable's centreline: in the junction's middle, or, widened, the cable's width of it
    # on the first turn's side)
    (x0, y0), (x1, y1), (x2, y2) = cable.path[:3]
    turn = -1 if cfg.fpc_cable == "up" else 1
    centre = entry + turn * (fpc.junction_width(cfg) - cable.width) / 2
    assert (x0, y0) == pytest.approx((0, centre)) and y1 == y0 and x1 < 0
    assert x2 == x1 and (y2 < y1 if cfg.fpc_cable == "up" else y2 > y1)
    # Everything off the free edge is cut as before; on it, only the cable's cut is new.
    mine = {_key(s) for s in pattern.outline.segments}
    for seg in plain.outline.segments:
        if seg.start[0] != 0 or seg.end[0] != 0:
            assert _key(seg) in mine
    for seg in cable_segments(pattern):
        assert all(p[0] <= 1e-9 for p in polyline([seg], 8))
    others = lambda p: [f for f in p.faces if f.name != "front-panel"]  # noqa: E731
    assert others(plain) == others(pattern)


def test_front_panel_keeps_its_edge(cfg):
    """The front panel's face runs along its whole free edge, the junction included."""
    pattern = build_pattern(cfg)
    face = pattern.face("front-panel")
    on_edge = [s for s in face.boundary if s.start[0] == 0 == s.end[0]]
    assert sum(s.length for s in on_edge) == pytest.approx(cfg.front_length)
    j0, j1 = pattern.cable.junction
    assert any({s.start, s.end} == {j0, j1} for s in on_edge)


def test_cable_keeps_its_clearance(cfg):
    """Away from where it leaves the edge, the cable's cut stays the clearance away from the
    rest of the pattern, and its rows the clearance from each other."""
    pattern = build_pattern(cfg)
    cable, gap = pattern.cable, cfg.fpc_cable_gap
    own = cable_segments(pattern)
    rest = [s for s in pattern.outline.segments if s not in own]
    near = cfg.fpc_cable_gap + cfg.fpc_cable_inset + 2 * cfg.fpc_corner_radius + 1e-3
    for seg in own:
        for i in range(21):
            p = seg.point_at(i / 20)
            if min(math.dist(p, q) for q in cable.junction) < near + cable.width:
                continue
            if abs(p[0]) < 1e-9:  # (the edge itself)
                continue
            assert min(s.distance_to(p) for s in rest) >= gap - 1e-6, p
    xs = [p[0] for p in cable.path[1::2]]  # one corner per row
    pitches = [abs(a - b) for a, b in itertools.pairwise(xs)]
    for k, pitch in enumerate(pitches):
        extra = cfg.fpc_cable_inset if k == len(pitches) - 1 else 0
        assert pitch == pytest.approx(cable.width + gap + extra)


def test_plug_end_is_square_and_sized(cfg):
    """The plug: the last plug length, as wide as the contacts' span plus the edge margins,
    its corners (and the steps to its ears) left sharp; every other corner of the cable
    rounded by at most the corner radius."""
    pattern = build_pattern(cfg)
    cable = pattern.cable
    assert cable.plug_width == pytest.approx(
        (cfg.fpc_pins - 1) * cfg.fpc_pitch + 2 * cfg.fpc_edge_margin
    )
    tip, before = cable.path[-1], cable.path[-2]
    d = _unit(before, tip)
    n = (-d[1], d[0])
    hp, plug = cable.plug_width / 2, cable.plug_length
    corners = [(tip[0] + k * hp * n[0], tip[1] + k * hp * n[1]) for k in (-1, 1)]
    if cable.plug_width > cable.width:
        base = (tip[0] - plug * d[0], tip[1] - plug * d[1])
        corners += [(base[0] + k * hp * n[0], base[1] + k * hp * n[1]) for k in (-1, 1)]
    ends = [q for s in pattern.outline.segments if isinstance(s, Line) for q in (s.start, s.end)]
    for c in corners:  # two straight cuts meet there
        assert sum(math.dist(c, q) < 1e-9 for q in ends) == 2, c
    arcs = [s for s in cable_segments(pattern) if isinstance(s, Arc)]
    if cfg.fpc_corner_radius == 0:
        assert arcs == []
    else:
        assert arcs and all(a.radius <= cfg.fpc_corner_radius + 1e-9 for a in arcs)
        assert max(a.radius for a in arcs) == pytest.approx(cfg.fpc_corner_radius)


def test_down_mirrors_up():
    up, down = build_pattern(D), build_pattern(D.with_values(fpc_cable="down"))
    length = D.front_length
    mirrored = {_key(_mirror(s, length)) for s in cable_segments(up)}
    assert mirrored == {_key(s) for s in cable_segments(down)}
    folds = {f.name: f for f in down.cable.folds}
    for fold in up.cable.folds:
        assert _key(_mirror(fold.segment, length)) == _key(folds[fold.name].segment)
        assert fold.direction == folds[fold.name].direction


def _mirror(seg, length):
    from yanartas_pillowbox.geometry import _mirror as mirror

    return mirror(seg, length)


def test_rows_are_as_few_as_fit_and_their_turns_spread_evenly():
    """Every length takes as few rows as fit with the turns at the sides (clear of the end
    sections beside the edge); the slack moves all turns in from their sides alike, so the
    tip (needing no room for a turn) ends at its side; a single row runs to the side before
    it turns."""
    e, gap = D.end_wall_gap, D.fpc_cable_gap
    mid = fpc.layout(D).path[0][1]  # (the centreline's start: as low as it goes, turning up)
    sides = (D.front_length - e - gap, e + gap)  # (up: the first row runs to the second)
    rows = lambda cable: (len(cable.path) - 1) // 2  # noqa: E731
    # (one row, its tip just short of the side: the stub, half the corner, then the row)
    stub, h = gap + D.fpc_cable_inset + D.thickness, fpc.cable_width(D) / 2
    one = fpc.layout(D.with_values(fpc_cable_length=math.floor(mid - sides[1] - stub - h)))
    assert rows(one) == 1 and one.path[-1][1] - sides[1] < 1
    for length in (100, 200, 320):
        cable = fpc.layout(D.with_values(fpc_cable_length=length))
        turns = [mid - p[1] for p in cable.path[2:-1]]  # (along the edge, up from the middle)
        right, left = turns[0::4] + turns[1::4], turns[2::4] + turns[3::4]
        w = cable.width
        assert max(right) - min(right) < 1e-9 and max(left or [0]) - min(left or [0]) < 1e-9
        top, bottom = mid - sides[1], mid - sides[0]
        if left:
            assert math.isclose(top - right[0], left[0] - bottom, abs_tol=1e-9)
        assert top - w / 2 - right[0] > 1  # the slack moved the turns in
        tip = mid - cable.path[-1][1]
        assert min(abs(tip - bottom), abs(tip - top)) < 1e-6


def test_cable_widens_the_pattern_only_beside_the_edge():
    """The cable sticks out beside the front panel's free edge only, its rows outward (to
    -x); a longer one adds rows further out."""
    plain = build_pattern(D.with_values(fpc_cable="none")).bbox
    default = build_pattern(D).bbox
    assert default[1:] == pytest.approx(plain[1:])
    cable = build_pattern(D).cable
    assert default[0] == pytest.approx(cable.path[1][0] - cable.width / 2)
    long = build_pattern(D.with_values(fpc_cable_length=180)).bbox
    assert long[0] < default[0] and long[1:] == pytest.approx(plain[1:])


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"fpc_pins": 30.5}, "fpc_pins"),
        ({"fpc_pins": 200, "fpc_pitch": 1}, "fpc_pins"),  # longer than the free edge
        ({"fpc_cable_inset": 16}, "fpc_cable_inset"),  # no cable left
        ({"fpc_cable": "front"}, "fpc_cable"),  # (an old value)
        ({"fpc_cable_length": 2.0 + 10}, None),  # (the minimum is the plug: fine)
    ],
)
def test_validation(changes, field):
    if field is None:
        assert Config.defaults().with_values(**changes)
        return
    with pytest.raises(ConfigError) as info:
        Config.defaults().with_values(**changes)
    assert field in info.value.errors, info.value.errors


def test_cutouts_are_independent_of_the_cable():
    """The FPC cutouts cut the inner flaps, the cable leaves the front panel's edge."""
    cfg = D.with_values(fpc_cutout="both")
    pattern = build_pattern(cfg)
    assert pattern.cable is not None
    plain = build_pattern(cfg.with_values(fpc_cable="none"))
    for name in ("back-top-flap", "back-bottom-flap"):
        assert pattern.face(name) == plain.face(name)


def test_default_pins_hold_the_default_curve_mesh():
    """The default plug has room for the default space-filling curve mesh's ends (its
    partitions' traces, two ends each, both sides) and the GND pins between them."""
    cfg = D.with_values(mesh_algorithm="sfc")
    n = int(cfg.mesh_partitions * cfg.mesh_traces)
    assert cfg.mesh_nets == n == 12
    ends = 4 * n
    assert D.fpc_pins >= 1 + ends + ends // 4
    assert D.mesh_nets == D.mesh_traces  # (KiMesh: no partitions)


def test_junction_and_wall_folds(cfg):
    """The cable folds into the box along the junction, and onto the front panel straight
    across the first row, where (folded back over the stub) it gets back to a thickness
    short of the junction."""
    cable = build_pattern(cfg).cable
    names = [f.name for f in cable.folds]
    assert names[:3] == ["cable-junction", "cable-corner-1", "cable-wall"]
    junction, wall = cable.folds[0].segment, cable.folds[2].segment
    # The junction fold runs along the junction, out to the (rounded) cut on both sides.
    (x, ya), (_, yb) = cable.junction
    assert junction.start[0] == pytest.approx(x) and junction.end[0] == pytest.approx(x)
    ys = sorted((junction.start[1], junction.end[1]))
    assert ys[0] <= min(ya, yb) + 1e-9 and ys[1] >= max(ya, yb) - 1e-9
    # The wall fold: across the first row, at r = -t once straightened.
    p, q = cable.path[1], cable.path[2]
    d = _unit(p, q)
    assert abs((wall.end[0] - wall.start[0]) * d[0] + (wall.end[1] - wall.start[1]) * d[1]) < 1e-9
    assert wall.length == pytest.approx(cable.width, abs=1e-6)
    creases = tuple((f.segment.start, f.segment.end) for f in cable.corners)
    mid = fpc.unfold(wall.point_at(0.5), 1, creases)
    assert mid[0] - x == pytest.approx(-cfg.thickness, abs=1e-9)


def _panel(shell, panel, k, n=2000):
    """The panel's mid-surface (k = 0) or the surface offset k into the box, sampled."""
    point, normal, w = (
        (shell.front_point, shell.front_normal, shell.front.width)
        if panel == "front"
        else (shell.back_point, shell.back_normal, shell.back.width)
    )
    out = []
    for i in range(n + 1):
        (x, z), (nx, nz) = point(w * i / n), normal(w * i / n)
        out.append((x - k * nx, z - k * nz))
    return out


def _dist(p, pts):
    return LineString(pts).distance(Point(p))


def test_folded_cable_route(cfg):
    """In the box: the stub (with the first corner square) on the inside of the back panel,
    from the glued edge into the box; the layer folded back over it two thicknesses off the
    panel; the rest on along the inside of the front panel, as long as set."""
    pattern = build_pattern(cfg)
    folded = FoldedCable(cfg, pattern.cable)
    t, shell = cfg.thickness, cfg.shell
    stub = folded.stub
    assert stub == pytest.approx(cfg.fpc_cable_gap + cfg.fpc_cable_inset + t + pattern.cable.width)
    # It leaves where the front panel's free edge rests against the back panel.
    assert math.dist(folded.stub_at(0), shell.front_point(0)) < 0.05 * t + 1e-9
    back, front = _panel(shell, "back", t), _panel(shell, "front", t)
    layer = _panel(shell, "back", 2 * t)
    for d in (0.0, stub / 2, stub):
        assert _dist(folded.stub_at(d), back) < 0.01
    for r in (-stub, -stub / 2, -2 * t):
        assert _dist(folded.section(r), layer) < 0.01
    # The wall fold, at r = -t: onto the front panel (the layers a thickness apart there).
    a, b = folded.section(-t - 1e-6), folded.section(-t + 1e-6)
    assert math.dist(a, b) < 1e-5
    if t > 0:
        assert _dist(folded.section(-t), back) == pytest.approx(t, rel=0.2)
    length = cfg.fpc_cable_length
    for r in (0.0, length / 2, min(length, 100.0)):
        assert _dist(folded.section(r), front) < 0.01
    # Arc length along the section: as long as the cable from the first fold.
    rs = [-stub + (length + stub) * i / 4000 for i in range(4001)]
    pts = [folded.section(r) for r in rs]
    total = sum(math.dist(a, b) for a, b in itertools.pairwise(pts))
    assert total == pytest.approx(length + stub, abs=0.05)  # (the chords cut its two corners)
    d = [folded.stub_at(stub * i / 400) for i in range(401)]
    assert sum(math.dist(a, b) for a, b in itertools.pairwise(d)) == pytest.approx(stub, rel=1e-4)


def test_folded_cable_stays_inside_the_box(cfg):
    """Every point of the folded cable lies inside the closed shell's section (its
    mid-surfaces)."""
    model = build_model3d(cfg)
    section = build_cross_section(cfg)
    b = cfg.shell
    shell = Polygon([*_panel(b, "front", 0), *_panel(b, "back", 0)]).buffer(1e-4)
    pos = model["cable"]["positions"]
    for i in range(0, len(pos), 3):
        x, _, z = pos[i : i + 3]
        assert shell.contains(Point(x, z)), (x, z)
    for line in section["cable"]:
        assert all(shell.contains(Point(*p)) for p in line)


def _flap_walls(cfg, x):
    """The box's Y of the inner flaps' walls (mid-surfaces: top end, bottom end) at X = x
    across the box, on the back panel's side (the back panel's u there, by bisection)."""
    shell, e, lf = cfg.shell, cfg.end_wall_gap, cfg.front_length
    back = shell.back
    lo, hi = 0.0, back.width  # (X falls with u along the back panel)
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if shell.back_x - back.x(mid) > x else (lo, mid)
    z = back.z((lo + hi) / 2)
    return lf / 2 - (e + z), lf / 2 - (lf - e - z)


def _first_corner(cfg):
    """The folded cable's stub and first corner square (the triangle of two layers and the
    run back over it lie within it): box points of a grid over them, flat."""
    pattern = build_pattern(cfg)
    folded = FoldedCable(cfg, pattern.cable)
    cable = pattern.cable
    (x0, _), (x1, _) = cable.path[0], cable.path[1]
    (_, ya), (_, yb) = cable.junction  # (across the stub: as wide as the junction)
    h = cable.width / 2
    xs = [x0 + (x1 - h - x0) * i / 40 for i in range(41)]  # (to the square's far side)
    return [folded.map(0, (x, ya + (yb - ya) * k / 8)) for x in xs for k in range(9)]


def test_first_corner_clears_the_inner_flaps(cfg):
    """Folded into the box, the cable's stub and its first corner (the triangle) stay clear
    of the inner flaps' walls: by the clearance, past half the flap's thickness; and at the
    default entry as near the end it turns away from as that allows (the rest of the
    cable, along the front panel, is not checked)."""
    t, gap = cfg.thickness, cfg.fpc_cable_gap
    least = math.inf
    for x, y, _ in _first_corner(cfg):
        top, bottom = _flap_walls(cfg, x)
        assert bottom + t / 2 + 0.9 * gap < y < top - t / 2 - 0.9 * gap, (x, y, top, bottom)
        least = min(least, (y - bottom) if cfg.fpc_cable == "up" else (top - y))
    if cfg.fpc_entry_offset == 0:  # (no nearer than needed: a thickness more, at most)
        assert least - t / 2 - gap < 2 * t + 0.05, least


def test_cable_in_the_3d_model(cfg):
    model = build_model3d(cfg)
    cable = model["cable"]
    n = len(cable["positions"]) // 3
    assert n and all(0 <= i < n for i in cable["indices"])
    # (its fold lines and cut edges with it, not with the box's)
    assert not [line for line in model["lines"] if line["category"] == "cable"]
    assert [line["name"] for line in cable["lines"]] == [
        f.name for f in build_pattern(cfg).cable.folds
    ]
    # One cut line along both sides and the plug's end, plus the stub's two sides.
    assert len(cable["cuts"]) == 3


def test_cable_is_isometric_in_the_3d_model(cfg):
    """The folded cable is the flat one bent: the run past the first corner keeps its
    length along the strip and its width across it."""
    pattern = build_pattern(cfg)
    folded = FoldedCable(cfg, pattern.cable)
    cable = pattern.cable
    (_, y0), q = cable.path[0], cable.path[1]
    for v in (-cable.width / 2, 0.0, cable.width / 2):
        pts = [folded.map(0, (x, y0 + v)) for x in [q[0] * i / 50 for i in range(51)]]
        assert sum(math.dist(a, b) for a, b in itertools.pairwise(pts)) == pytest.approx(
            abs(q[0]), rel=1e-4
        )
    p0, p1 = (folded.map(1, (q[0] + k, q[1] - 5)) for k in (-cable.width / 2, cable.width / 2))
    assert math.dist(p0, p1) == pytest.approx(cable.width, rel=1e-6)


def test_fold_directions_follow_the_route():
    """Seen from the outside (the print side), the cable folds into the box at the junction
    (mountain: away from the viewer), and flat back over the stub (mountain too); printing
    inside flips every fold."""
    out = build_pattern(D.with_values(fpc_cable_length=180)).cable
    ins = build_pattern(D.with_values(fpc_cable_length=180, print_side="inside")).cable
    assert out.folds[0].direction == FoldDirection.MOUNTAIN
    assert out.folds[1].direction == FoldDirection.MOUNTAIN
    for a, b in zip(out.folds, ins.folds, strict=True):
        assert {a.direction, b.direction} == set(FoldDirection)


def test_cross_section_shows_the_cable():
    section = build_cross_section(D)
    stub, rest = section["cable"]
    folded = FoldedCable(D, build_pattern(D).cable)
    assert stub[0] == pytest.approx(list(folded.stub_at(0)), abs=1e-6)
    assert rest[-1] == pytest.approx(list(folded.section(D.fpc_cable_length)), abs=1e-6)
    assert build_cross_section(D.with_values(fpc_cable="none"))["cable"] is None


def test_the_junction_widens_for_the_meshes_exits():
    """Wider than the cable where the meshes' exits need it: by as much as they need, the
    stub widening on the side away from the first turn up to the first corner's far side
    (the rows as wide as the cable)."""
    assert fpc.junction_width(D) == fpc.cable_width(D)
    wide = CONFIGS["wide"]
    assert fpc.junction_width(wide) == pytest.approx(fpc.exit_width(wide))
    assert fpc.junction_width(wide) > fpc.cable_width(wide) + 5
    cable = fpc.layout(wide)
    (_, ya), (_, yb) = cable.junction
    w, wj = fpc.cable_width(wide), fpc.junction_width(wide)
    bottom = max(ya, yb)  # (turning up: widened downwards, to the outside of the turn)
    deep = cable.path[1][0] - w / 2  # (the first corner's far side)
    assert any(p == pytest.approx((deep, bottom)) for p in cable.outline)
    assert abs(cable.path[0][1] - (bottom - wj + w / 2)) < 1e-9
