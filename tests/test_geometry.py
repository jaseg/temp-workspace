import itertools
import math
from dataclasses import replace

import pytest
from helpers import loop_area, self_intersections

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
    print_side_normal,
    wall_layout,
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
    cfg = Config.defaults().with_values(thickness=0, interior_walls=False)
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
    cfg = Config.defaults().with_values(height=20, thickness=1.0)
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
    (outer-flap) folds' three thicknesses (the outer walls' mid-surfaces); the straight edges
    are ``length + height + 3 t`` long."""
    pat = build_pattern(cfg)
    t = cfg.thickness
    for side, extra in (("front", 3 * t), ("back", t)):
        top = pat.fold(f"{side}-top").segment.point_at(0.5)
        bottom = pat.fold(f"{side}-bottom").segment.point_at(0.5)
        assert bottom[1] - top[1] == pytest.approx(cfg.length + extra, abs=1e-9)
        assert top[0] == pytest.approx(bottom[0])
    assert pat.fold("panels").segment.length == pytest.approx(cfg.length + cfg.height + 3 * t)


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
    assert x1 - x0 == pytest.approx(cfg.circumference + cfg.glue_tab_width)
    # The outer flaps or the interior walls stick out furthest.
    reach = cfg.body.front_cut_sagitta
    if cfg.interior_walls:
        reach = max(reach, wall_layout(cfg).reach)
    assert y1 - y0 == pytest.approx(cfg.edge_length + 2 * reach)


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
    base = Config.defaults().with_values(thickness=0.6, interior_walls=False)
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


# ------------------------------------------------------------------ interior walls
WALL_CONFIGS = {
    "default": Config.defaults(),
    "offset-5": Config.defaults().with_values(interior_wall_offset=5),
    "thick": Config.defaults().with_values(width=70, height=24, thickness=2, glue_tab_width=15),
    "big": Config.defaults().with_values(
        width=300, length=160, height=110, glue_tab_width=40, glue_tab_taper=30
    ),
}


@pytest.mark.parametrize("cfg", list(WALL_CONFIGS.values()), ids=list(WALL_CONFIGS))
def test_interior_walls_layout(cfg):
    """Each inner flap continues into a bridge of the offset plus one thickness (wall
    mid-surface to wall mid-surface) and an interior wall reaching down to the back panel's
    inner surface. The bridge's folds follow its place under the front panel exactly, and
    bridge and wall are a little narrower than the inner flap."""
    pat = build_pattern(cfg)
    layout = wall_layout(cfg)
    t, body = cfg.thickness, cfg.body
    wf = body.front.width
    assert layout.strip == pytest.approx(cfg.interior_wall_offset + t)
    assert 0 < layout.ua < layout.ub < body.back.width
    folds = {f.name: f.segment for f in pat.wall_folds}
    assert set(folds) == {"top-bridge", "top-wall", "bottom-bridge", "bottom-wall"}
    for x, y in folds["top-bridge"].points[1:-1]:
        x3 = body.back_point(x - wf)[0]
        assert -y == pytest.approx(body.surface_z("front", -t, x3) - body.z_shift, abs=1e-9)
    # The interior wall's fold is the bridge's, shifted by the bridge length, and the wall's
    # free edge lies a wall height beyond it.
    for (xa, ya), (xb, yb) in zip(
        folds["top-bridge"].points, folds["top-wall"].points, strict=True
    ):
        assert (xb, yb) == pytest.approx((xa, ya - layout.strip))
    wall = next(f for f in pat.wall_faces if f.name == "top-wall")
    for u, d in layout.drops[1:-1]:
        lo, hi = wall.y_range(wf + u)
        assert hi - lo == pytest.approx(d, abs=1e-6)
        x3 = body.back_point(u)[0]
        expected = body.surface_z("front", -t, x3) - body.surface_z("back", -t / 2, x3)
        assert d == pytest.approx(expected, abs=1e-9)
    # Top and bottom ends mirror each other.
    edge = cfg.edge_length
    for (xa, ya), (xb, yb) in zip(
        folds["top-bridge"].points, folds["bottom-bridge"].points, strict=True
    ):
        assert (xb, yb) == pytest.approx((xa, edge - ya))
    # All folds of the walls are mountain folds from the outside, like the rest.
    assert {f.direction for f in pat.wall_folds} == {FoldDirection.MOUNTAIN}
    inside = build_pattern(replace(cfg, print_side="inside"))
    assert {f.direction for f in inside.wall_folds} == {FoldDirection.VALLEY}


def test_interior_walls_off_restore_the_plain_box():
    cfg = Config.defaults().with_values(interior_walls=False)
    pat = build_pattern(cfg)
    assert pat.wall_faces == pat.wall_folds == pat.holes == ()
    assert wall_layout(cfg) is None


@pytest.mark.parametrize("which", ["front", "back", "both"])
def test_fpc_cutout_notches_both_wall_folds(which):
    """With interior walls the FPC cutout notches the inner flap -> bridge and bridge ->
    interior wall folds: the folds stop at the notch, the bridge keeps its edge, and the
    inner flap and interior wall are cut back by the same depth over exactly the width."""
    cfg = Config.defaults().with_values(fpc_cutout=which, fpc_cutout_width=18)
    pat = build_pattern(cfg)
    ends = {"front": ["top"], "back": ["bottom"], "both": ["top", "bottom"]}[which]
    assert len(pat.holes) == 2 * len(ends)
    names = {f.name for f in pat.wall_folds}
    for end in ("top", "bottom"):
        split = {
            f"{end}-bridge-left",
            f"{end}-bridge-right",
            f"{end}-wall-left",
            f"{end}-wall-right",
        }
        assert (split <= names) == (end in ends)
    for flap_notch, wall_notch in zip(pat.holes[::2], pat.holes[1::2], strict=True):
        x0, _, x1, _ = flap_notch.bbox()
        assert x1 - x0 == pytest.approx(18, abs=1e-6)
        assert wall_notch.bbox()[2] - wall_notch.bbox()[0] == pytest.approx(18, abs=1e-6)
        # Same depth on both sides: the wall's notch mirrors the flap's about the fold, so
        # both cut away the same area.
        a1, a2 = abs(loop_area(flap_notch.segments)), abs(loop_area(wall_notch.segments))
        assert a1 == pytest.approx(a2, rel=1e-6)
        assert 0 < flap_notch.bbox()[3] - flap_notch.bbox()[1] < 2  # small and shallow
