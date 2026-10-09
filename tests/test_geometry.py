import itertools
import math

import pytest
from helpers import self_intersections

from yanartas_pillowbox.config import Config
from yanartas_pillowbox.crosssection import sagitta_offset
from yanartas_pillowbox.geometry import (
    Arc,
    CrossSection,
    FoldCategory,
    FoldDirection,
    FoldedBox,
    Line,
    arc_from_chord,
    build_pattern,
    fold_direction,
    print_side_normal,
)

CONFIGS = {
    "default": Config.defaults(),
    "deep": Config.defaults().with_values(width=40, height=16, thickness=1.5),
    "shallow": Config.defaults().with_values(height=8, thickness=0),
    "no-taper": Config.defaults().with_values(glue_tab_taper=0, glue_tab_width=20),
    "big": Config.defaults().with_values(width=300, length=60, height=110, glue_tab_taper=24),
}


@pytest.fixture(params=list(CONFIGS), ids=list(CONFIGS))
def cfg(request):
    return CONFIGS[request.param]


def test_arc_from_chord_geometry():
    arc = arc_from_chord((0, 0), (60, 0), 15, (0, 1))
    assert arc.start == (0, 0) and arc.end == (60, 0)
    apex = arc.point_at(0.5)
    assert apex == pytest.approx((30, 15), abs=1e-9)
    assert arc.radius == pytest.approx((30**2 + 15**2) / 30)
    assert not arc.large_arc
    assert arc.bbox() == pytest.approx((0, 0, 60, 15), abs=1e-9)


def test_curved_fold_length_matches_closing_edge():
    """A flap closes against the opposite panel's crease (see test_model3d for the folded
    check): front and back creases have equal arc length, and with zero thickness so does
    the flap's cut edge."""
    cfg = Config.defaults().with_values(thickness=0)
    pat = build_pattern(cfg)
    folds = {f.name: f.segment for f in pat.folds}
    theta = 2 * math.asin(cfg.panel_width / 2 / pat.info["fold_radius"])
    analytic = pat.info["fold_radius"] * theta
    for end in ("top", "bottom"):
        front, back = folds[f"front-{end}"], folds[f"back-{end}"]
        assert front.length == pytest.approx(analytic, rel=1e-12)
        assert back.length == pytest.approx(front.length, rel=1e-12)
    cut_arcs = [s for s in pat.outline.segments if isinstance(s, Arc)]
    assert len(cut_arcs) == 4
    for arc in cut_arcs:
        assert arc.length == pytest.approx(analytic, rel=1e-12)


def test_thickness_makes_flap_edge_slightly_shorter():
    cfg = Config.defaults().with_values(thickness=1.0)
    pat = build_pattern(cfg)
    fold = next(f.segment for f in pat.folds if f.category is FoldCategory.CURVED)
    cut = next(s for s in pat.outline.segments if isinstance(s, Arc))
    assert pat.info["cut_sagitta"] == pytest.approx(pat.info["fold_sagitta"] - 0.5)
    assert 0 < fold.length - cut.length < 1.0


def test_height_maps_to_sagitta():
    cfg = Config.defaults().with_values(height=22)
    assert build_pattern(cfg).info["fold_sagitta"] == pytest.approx(11)
    assert build_pattern(cfg).info["box_height"] == pytest.approx(22)


def test_length_is_the_midline_between_fold_apexes(cfg):
    """The input length is the shortest distance between the two curved folds of a panel
    (apex to apex); the straight edges are ``length + height`` long."""
    pat = build_pattern(cfg)
    for side in ("front", "back"):
        top = pat.fold(f"{side}-top").segment.point_at(0.5)
        bottom = pat.fold(f"{side}-bottom").segment.point_at(0.5)
        assert bottom[1] - top[1] == pytest.approx(cfg.length, abs=1e-9)
        assert top[0] == pytest.approx(bottom[0])
    assert pat.fold("panels").segment.length == pytest.approx(cfg.length + cfg.height)


def test_outline_is_single_closed_contour(cfg):
    out = build_pattern(cfg).outline
    assert out.is_continuous(1e-12)
    assert math.dist(out.start, out.end) < 1e-9
    for seg in out.segments:
        assert seg.length > 1e-6


def test_outline_has_no_self_intersections(cfg):
    pts = build_pattern(cfg).outline.polyline(64)
    assert self_intersections(pts) == []


def test_fold_endpoints_on_outline_or_fold(cfg):
    pat = build_pattern(cfg)
    for fold in pat.folds:
        for p in (fold.segment.start, fold.segment.end):
            on_outline = pat.outline.distance_to(p) < 1e-6
            on_fold = any(o is not fold and o.segment.distance_to(p) < 1e-6 for o in pat.folds)
            assert on_outline or on_fold, (fold.name, p)


def test_folds_do_not_overlap_outline(cfg):
    pat = build_pattern(cfg)
    for fold in pat.folds:
        for i in range(1, 50):
            p = fold.segment.point_at(i / 50)
            assert pat.outline.distance_to(p) > 1e-3, (fold.name, i)


def test_fold_categories():
    pat = build_pattern(Config.defaults())
    cats = [f.category for f in pat.folds]
    assert cats.count(FoldCategory.CURVED) == 4
    assert cats.count(FoldCategory.STRAIGHT) == 1
    assert cats.count(FoldCategory.GLUE) == 1
    for f in pat.folds:
        assert isinstance(f.segment, Arc if f.category is FoldCategory.CURVED else Line)


def test_bbox_covers_everything(cfg):
    pat = build_pattern(cfg)
    x0, y0, x1, y1 = pat.bbox
    for p in pat.outline.polyline(64):
        assert x0 - 1e-9 <= p[0] <= x1 + 1e-9 and y0 - 1e-9 <= p[1] <= y1 + 1e-9
    assert x1 - x0 == pytest.approx(2 * cfg.panel_width + cfg.glue_tab_width)


def test_cross_section_is_unit_speed_and_bulges_by_sagitta():
    """The closed panel's cross-section keeps the panel width (no stretching) and has height
    profile f(u), the crease offset, so the box is exactly 2 * s_f deep."""
    for w, s_f in ((60, 10), (50, 10), (300, 55), (33.3, 3)):
        sec = CrossSection(w, s_f)
        n = 4000
        pts = [(sec.x(w * i / n), sec.z(w * i / n)) for i in range(n + 1)]
        arc_len = sum(math.dist(a, b) for a, b in itertools.pairwise(pts))
        assert arc_len == pytest.approx(w, rel=1e-6)
        assert sec.z(w / 2) == pytest.approx(s_f)
        for u in (0, w / 7, w / 3, w / 2, w):
            assert sec.z(u) == pytest.approx(sagitta_offset(w, s_f, u), abs=1e-12)
            assert sec.x(u) == pytest.approx(-sec.x(w - u), abs=1e-9)  # symmetric
        assert sec.x(w) - sec.x(0) == pytest.approx(sec.closed_width)
        assert sec.closed_width < w


def test_cross_section_rejects_arcs_that_cannot_close():
    with pytest.raises(ValueError):
        CrossSection(60, 0.21 * 60)


def test_print_side_is_the_outside():
    """The SVG's visible side (the print side) becomes the outside of the folded box: at the
    front panel's apex its normal points away from the box centre (+Z)."""
    cfg = Config.defaults()
    n = print_side_normal(FoldedBox(cfg), "front-panel", (cfg.panel_width / 2, 60.0), 1e-3)
    assert n == pytest.approx((0, 0, 1), abs=1e-6)


@pytest.mark.parametrize("name", list(CONFIGS))
def test_all_folds_are_mountain_folds_from_the_print_side(name):
    """Seen from the outside every crease is convex: the panels fold around the interior and
    the flaps and glue tab fold inwards. Classifying from either side of a fold agrees."""
    cfg = CONFIGS[name]
    pat = build_pattern(cfg)
    assert {f.direction for f in pat.folds} == {FoldDirection.MOUNTAIN}
    for fold in pat.folds:
        flipped = (
            Line(fold.segment.end, fold.segment.start)
            if isinstance(fold.segment, Line)
            else fold.segment.reversed()
        )
        assert fold_direction(cfg, flipped, pat.faces) == fold.direction
