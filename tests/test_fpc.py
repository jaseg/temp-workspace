"""The built-in FPC cable: its layout in the pattern and its folds."""

import itertools
import math

import pytest
from helpers import is_closed_loop, polyline, self_intersections

from yanartas_pillowbox import fpc
from yanartas_pillowbox.config import Config, ConfigError
from yanartas_pillowbox.geometry import Arc, Line, build_pattern

D = Config.defaults()
CONFIGS = {
    "default": D,
    "back": D.with_values(fpc_cable="back"),
    "long": D.with_values(fpc_cable_length=180),  # (more rows than fit beside the pattern)
    "ears": D.with_values(fpc_cable_inset=1.5, fpc_plug_length=6),
    "no-lid": D.with_values(end_wall_gap=0),
    "sharp": D.with_values(fpc_corner_radius=0, fpc_cable_gap=2),
    "thin": D.with_values(thickness=0, fpc_pins=20, fpc_pitch=0.3),
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
    the junction's middle, and the tip reaches the set length past the junction."""
    pattern = build_pattern(cfg)
    cable = pattern.cable
    creases = tuple((f.segment.start, f.segment.end) for f in cable.folds)
    # (the clipped creases lie on the same lines as the layout's)
    x0 = cable.path[0][0]
    for i, p in enumerate(cable.path[1:]):
        q = fpc.unfold(p, i, creases)
        assert q[0] == pytest.approx(x0, abs=1e-9)
    tip = fpc.unfold(cable.path[-1], len(cable.path) - 2, creases)
    assert abs(tip[1] - cable.junction[0][1]) == pytest.approx(cfg.fpc_cable_length, abs=1e-9)


def test_corner_creases_lay_each_run_back_along_the_one_before(cfg):
    """Each crease is its corner square's diagonal from the outer to the inner corner:
    mirroring the outgoing run across it gives the incoming run, reversed."""
    cable = build_pattern(cfg).cable
    path = cable.path
    assert len(cable.folds) == len(path) - 2
    for fold, a, p, b in zip(cable.folds, path, path[1:], path[2:], strict=False):
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


def test_cable_leaves_the_top_of_the_flap(cfg):
    """The cable leaves the top of the inner flap's edge, cut off level over exactly its
    width (like the FPC cutout); the rest of the flap keeps its height."""
    pattern = build_pattern(cfg)
    plain = build_pattern(cfg.with_values(fpc_cable="none"))
    cable = pattern.cable
    (xa, y), (xb, yb) = cable.junction
    assert y == yb and xb - xa == pytest.approx(fpc.cable_width(cfg))
    k = 0 if cable.end == "top" else 1
    flap, before = pattern.face(f"back-{cable.end}-flap"), plain.face(f"back-{cable.end}-flap")
    assert flap.y_range((xa + xb) / 2)[k] == pytest.approx(y)
    # (cut back only around the top, never added to)
    x0, x1 = flap.x0, flap.x1
    for i in range(1, 400):
        x = x0 + (x1 - x0) * i / 400
        if xa - 3 * cfg.fpc_corner_radius - 1 < x < xb + 3 * cfg.fpc_corner_radius + 1:
            continue
        assert flap.y_range(x)[k] == pytest.approx(before.y_range(x)[k], abs=0.05), x
    top = before.y_range((xa + xb) / 2)[k]
    assert abs(top - y) < 0.1 * cable.width  # (a shallow cut)


def test_cable_keeps_its_clearance(cfg):
    """Away from where it leaves the flap, the cable's cut stays the clearance away from the
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
            if abs(p[1] - cable.junction[0][1]) < 1e-9:  # (the flap's level edge itself)
                continue
            assert min(s.distance_to(p) for s in rest) >= gap - 1e-6, p
    ys = [p[1] for p in cable.path[1::2]]  # one corner per row
    pitches = [abs(a - b) for a, b in itertools.pairwise(ys)]
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


def test_back_end_mirrors_the_front_end():
    front, back = build_pattern(D), build_pattern(D.with_values(fpc_cable="back"))
    length = D.front_length
    mirrored = {_key(_mirror(s, length)) for s in cable_segments(front)}
    assert mirrored == {_key(s) for s in cable_segments(back)}


def _mirror(seg, length):
    from yanartas_pillowbox.geometry import _mirror as mirror

    return mirror(seg, length)


def test_default_cable_fits_the_pattern_and_longer_ones_grow_it():
    """The default cable fits beside the rest of the pattern; a longer one may add rows."""
    plain = build_pattern(D.with_values(fpc_cable="none")).bbox
    assert build_pattern(D).bbox == pytest.approx(plain)
    long = build_pattern(D.with_values(fpc_cable_length=180)).bbox
    assert long[1] < plain[1] and long[3] == pytest.approx(plain[3])


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"fpc_cutout": "front"}, "fpc_cutout"),  # the cable already cuts that flap
        ({"fpc_cutout": "both"}, "fpc_cutout"),
        ({"fpc_pins": 30.5}, "fpc_pins"),
        ({"fpc_pins": 200, "fpc_pitch": 1}, "fpc_pins"),  # wider than the inner flap
        ({"fpc_cable_inset": 8}, "fpc_cable_inset"),  # no cable left
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


def test_cutout_at_the_other_end_is_fine():
    cfg = D.with_values(fpc_cutout="back")
    assert build_pattern(cfg).cable is not None
