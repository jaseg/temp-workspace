import itertools
import math
from dataclasses import replace

import pytest
from helpers import self_intersections

from yanartas_pillowbox.config import Config
from yanartas_pillowbox.crosssection import CrossSection, sagitta_offset
from yanartas_pillowbox.geometry import (
    Arc,
    FoldCategory,
    FoldDirection,
    FoldedBox,
    Line,
    arc_from_chord,
    build_pattern,
    fold_direction,
    lid_layout,
    print_side_normal,
)

CONFIGS = {
    "default": Config.defaults(),
    "stacked": Config.defaults().with_values(end_wall_gap=0),
    "deep": Config.defaults().with_values(width=40, height=16, thickness=1.5, end_wall_gap=0),
    "thick-lid": Config.defaults().with_values(
        width=80, height=20, thickness=1.5, glue_tab_width=15, lid_offset=3
    ),
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
    cfg = Config.defaults().with_values(thickness=0, end_wall_gap=0)
    pat = build_pattern(cfg)
    folds = {f.name: f.segment for f in pat.folds}
    radius = pat.info["front_fold_radius"]
    assert pat.info["back_fold_radius"] == pytest.approx(radius)
    theta = 2 * math.asin(cfg.body.front.width / 2 / radius)
    analytic = radius * theta
    for end in ("top", "bottom"):
        front, back = folds[f"front-{end}"], folds[f"back-{end}"]
        assert front.length == pytest.approx(analytic, rel=1e-12)
        assert back.length == pytest.approx(front.length, rel=1e-12)
    cut_arcs = [s for s in pat.outline.segments if isinstance(s, Arc)]
    assert len(cut_arcs) == 4
    for arc in cut_arcs:
        assert arc.length == pytest.approx(analytic, rel=1e-12)


def test_thickness_offsets_folds_and_flaps():
    """With material, the front (outer-flap) fold bows in height/2 and its flaps reach the
    back panel's outer surface; the back (inner-flap) fold bows in t more and its flaps stop
    at the front panel's inner surface."""
    cfg = Config.defaults().with_values(height=20, thickness=1.0, end_wall_gap=0)  # no lid
    info = build_pattern(cfg).info
    assert (info["front_fold_sagitta"], info["back_fold_sagitta"]) == pytest.approx((10, 11))
    # (on the centreline; the two panels' apexes are a fraction of t apart across the box)
    assert (info["front_cut_sagitta"], info["back_cut_sagitta"]) == pytest.approx(
        (11.5, 9.5), abs=0.01
    )
    # Each flap's apex-to-apex height across its wall:
    assert info["front_fold_sagitta"] + info["front_cut_sagitta"] == pytest.approx(21.5, abs=0.01)
    assert info["back_fold_sagitta"] + info["back_cut_sagitta"] == pytest.approx(20.5, abs=0.01)
    assert info["outer_height"] == pytest.approx(20 + 2)


def test_height_maps_to_sagitta():
    cfg = Config.defaults().with_values(height=22)
    assert build_pattern(cfg).info["front_fold_sagitta"] == pytest.approx(11)
    assert build_pattern(cfg).info["box_height"] == pytest.approx(22)


def test_length_is_the_midline_between_fold_apexes(cfg):
    """The input length is the interior length on the centreline. The back (inner-flap)
    folds' apexes are a thickness further apart (the inner walls' mid-surfaces), the front
    (outer-flap) folds' three thicknesses plus twice the end wall gap (the outer walls'
    mid-surfaces); the back panel's straight edges are ``length + height + 3 t`` long, the
    front panel's twice the gap longer, with the back panel centred on it."""
    pat = build_pattern(cfg)
    t, e = cfg.thickness, cfg.end_wall_gap
    for side, extra in (("front", 3 * t + 2 * e), ("back", t)):
        top = pat.fold(f"{side}-top").segment.point_at(0.5)
        bottom = pat.fold(f"{side}-bottom").segment.point_at(0.5)
        assert bottom[1] - top[1] == pytest.approx(cfg.length + extra, abs=1e-9)
        assert top[0] == pytest.approx(bottom[0])
    edge = cfg.length + cfg.height + 3 * t
    panels = pat.fold("panels").segment
    assert panels.length == pytest.approx(edge)
    assert (panels.start[1], panels.end[1]) == pytest.approx((e, e + edge))
    assert pat.fold("glue-tab").segment.length == pytest.approx(edge)
    front = pat.face("front-panel")
    assert front.y_range(front.x0) == pytest.approx((0, edge + 2 * e))
    assert pat.info["front_edge_length"] == pytest.approx(cfg.front_length)


def test_end_sections_widen_the_front_panel(cfg):
    """With an end wall gap, over the gap the front panel runs on past both edges (the
    wings) by the lid's spread, along its own fold arc continued; the wings' other edges
    are cut, and at the straight fold the wing stops short of the inner flap's cut edge."""
    pat = build_pattern(cfg)
    lid = lid_layout(cfg)
    e, wf, length = cfg.end_wall_gap, cfg.body.front.width, cfg.front_length
    on_fold = [pat.fold("panels").segment.distance_to((wf, y)) < 1e-9 for y in (e, length / 2)]
    assert on_fold == [True, True]
    if lid is None:
        assert not [f for f in pat.faces if "-left" in f.name or "-right" in f.name]
        return
    sp = lid.spread
    assert sp > 0
    main = pat.fold("front-top").segment
    assert (main.start, main.end) == ((0.0, 0.0), (wf, 0.0))  # the panel's own fold
    left, right = pat.fold("front-top-left").segment, pat.fold("front-top-right").segment
    for arc in (left, right):  # the same circle, continued
        assert arc.radius == pytest.approx(main.radius)
        assert arc.center == pytest.approx(main.center)
    assert left.start == pytest.approx((-sp, -lid.drop)) and left.end == (0.0, 0.0)
    assert right.start == (wf, 0.0) and right.end == pytest.approx((wf + sp, -lid.drop))
    for name, x in (("front-top-left", -sp / 2), ("front-top-right", wf + sp / 2)):
        wing = pat.face(name)
        lo, hi = wing.y_range(x)
        assert pat.outline.distance_to((x, lo)) > 1e-3  # the fold
        assert pat.outline.distance_to((x, hi)) < 1e-9  # cut, at the gap's end
        assert hi == pytest.approx(e) or name.endswith("right")
    # Clear of the inner flap: its cut edge stays above the right wing's cut.
    flap, wing = pat.face("back-top-flap"), pat.face("front-top-right")
    for i in range(1, 50):
        x = wf + sp * i / 50
        assert flap.y_range(x)[0] > wing.y_range(x)[1] + 0.2


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


@pytest.mark.parametrize("gap", [0, 10])
def test_fold_categories(gap):
    pat = build_pattern(Config.defaults().with_values(end_wall_gap=gap))
    cats = [f.category for f in pat.folds]
    # Four panel folds, and with a gap the wings' continuations of the front ones.
    assert cats.count(FoldCategory.CURVED) == (8 if gap else 4)
    assert cats.count(FoldCategory.STRAIGHT) == 1
    assert cats.count(FoldCategory.GLUE) == 1
    assert cats.count(FoldCategory.LID) == (2 if gap else 0)  # one lid at each end
    for f in pat.folds:
        straight = f.category in (FoldCategory.STRAIGHT, FoldCategory.GLUE)
        assert isinstance(f.segment, Line if straight else Arc)


def test_bbox_covers_everything(cfg):
    pat = build_pattern(cfg)
    x0, y0, x1, y1 = pat.bbox
    for p in pat.outline.polyline(64):
        assert x0 - 1e-9 <= p[0] <= x1 + 1e-9 and y0 - 1e-9 <= p[1] <= y1 + 1e-9
    spread = 0.0 if lid_layout(cfg) is None else lid_layout(cfg).spread  # the bands, at x < 0
    assert x1 - x0 == pytest.approx(cfg.circumference + cfg.glue_tab_width + spread)
    # The outer flaps, or with an end wall gap their lids, stick out furthest.
    lid = lid_layout(cfg)
    reach = cfg.body.front_cut_sagitta if lid is None else max(d for _, d in lid.depth) - lid.level
    assert y1 - y0 == pytest.approx(cfg.front_length + 2 * reach)


def test_lid_fold_mirrors_the_front_fold(cfg):
    """The outer flap's fold into the lid is the front panel's curved fold turned over: an
    arc of the same radius through the panel's corners' verticals at the lid level, bowing
    out of the panel. The lid's free edge runs the gap, less half a thickness, plus the
    overlap beyond the back panel's crease (in folded depth); the top and bottom lids mirror
    each other."""
    lid = lid_layout(cfg)
    pat = build_pattern(cfg)
    if cfg.end_wall_gap == 0:
        assert lid is None
        assert not [f for f in pat.folds if f.category is FoldCategory.LID]
        return
    body, t = cfg.body, cfg.thickness
    front, crease = pat.fold("front-top").segment, pat.fold("lid-top").segment
    assert crease.radius == pytest.approx(front.radius)
    # The lid's fold and the front fold continued over the wings run between the same two
    # points, where they meet: the flap is a lens.
    if lid.spread > 0:
        front_l, front_r = pat.fold("front-top-left").segment, pat.fold("front-top-right").segment
    else:
        front_l = front_r = front
    assert crease.start == pytest.approx(front_l.start)
    assert crease.end == pytest.approx(front_r.end)
    assert crease.start[1] == pytest.approx(lid.level / 2)
    assert crease.point_at(0.5)[1] == pytest.approx(lid.level - body.front.sagitta)
    assert lid.level <= -cfg.lid_offset  # the offset lifts it off its resting level
    bottom = pat.fold("lid-bottom").segment
    assert bottom.point_at(0.5) == pytest.approx(
        (crease.point_at(0.5)[0], cfg.front_length - crease.point_at(0.5)[1])
    )
    lid_face = pat.face("front-top-lid")
    g_x, p_x = body.glue_point[0], body.fold_point[0]
    for x, depth in lid.depth[1:-1]:
        x3 = body.front_x + body.front.x_ext(x)
        # The back panel's z(u) at the same X; beyond the back panel the edge runs level.
        crease_depth = body.z_shift - body.surface_z("back", 0.0, x3) if g_x <= x3 <= p_x else 0
        crease_depth = max(0.0, crease_depth)
        expected = cfg.end_wall_gap - t / 2 + cfg.lid_overlap + crease_depth
        assert depth == pytest.approx(expected, abs=1e-9)
        assert lid_face.y_range(x)[0] == pytest.approx(lid.level - depth, abs=1e-6)


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
    n = print_side_normal(FoldedBox(cfg), "front-panel", (cfg.body.front.width / 2, 60.0), 1e-3)
    assert n == pytest.approx((0, 0, 1), abs=1e-6)


@pytest.mark.parametrize("name", list(CONFIGS))
def test_all_folds_are_mountain_folds_from_the_print_side(name):
    """Seen from the outside every crease is convex: the panels fold around the interior, the
    flaps fold inwards and the glue tab folds back over the outside of the front panel.
    Classifying from either side of a fold agrees."""
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


def test_print_inside_flips_every_fold():
    for cfg in CONFIGS.values():
        inside = build_pattern(replace(cfg, print_side="inside"))
        assert {f.direction for f in inside.folds} == {FoldDirection.VALLEY}


# ------------------------------------------------------------------ FPC cutout
@pytest.mark.parametrize("which", ["none", "front", "back", "both"])
def test_fpc_cutout_flattens_only_the_chosen_inner_flaps(which):
    """The FPC cutout cuts the top of the inner (back) flaps' edge off level, over exactly
    the given width: front end = top of the pattern, back end = bottom. Outer flaps and the
    other end are untouched."""
    base = Config.defaults().with_values(thickness=0.6)
    plain = build_pattern(base)
    cfg = base.with_values(fpc_cutout=which, fpc_cutout_width=18)
    pat = build_pattern(cfg)
    assert pat.outline.is_continuous(1e-12)
    assert self_intersections(pat.outline.polyline(16)) == []
    flattened = {"none": set(), "front": {"top"}, "back": {"bottom"}, "both": {"top", "bottom"}}
    x0, x1 = cfg.body.front.width, cfg.body.front.width + cfg.body.back.width
    for end, k in (("top", 0), ("bottom", 1)):
        face, before = pat.face(f"back-{end}-flap"), plain.face(f"back-{end}-flap")
        xs = [x0 + (x1 - x0) * i / 2000 for i in range(1, 2000)]
        changed = [x for x in xs if abs(face.y_range(x)[k] - before.y_range(x)[k]) > 1e-9]
        if end in flattened[which]:
            assert max(changed) - min(changed) == pytest.approx(18, abs=0.05)
            assert abs(sum(changed) / len(changed) - (x0 + x1) / 2) < 1  # near the middle
            level = {round(face.y_range(x)[k], 9) for x in changed}
            assert len(level) == 1  # a single level cut
            # cut back, never added to
            for x in changed:
                assert (face.y_range(x)[k] - before.y_range(x)[k]) * (1 if k == 0 else -1) > 0
        else:
            assert changed == []
    for name in ("front-top-flap", "front-bottom-flap"):
        x = cfg.body.front.width / 2
        assert pat.face(name).y_range(x) == pytest.approx(plain.face(name).y_range(x))


def test_fpc_cutout_width_validated():
    from yanartas_pillowbox.config import ConfigError

    with pytest.raises(ConfigError) as info:
        Config.defaults().with_values(fpc_cutout="both", fpc_cutout_width=61)
    assert "fpc_cutout_width" in info.value.errors
    assert Config.defaults().with_values(fpc_cutout="none", fpc_cutout_width=61)  # unused
    assert Config.defaults().fpc_cutout == "none"
