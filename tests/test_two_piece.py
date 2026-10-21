"""The two-piece layout (``pieces = "two"``): two identical pieces, the second turned over,
each with an outer flap at one end and an inner flap at the other, the FPC cable on one side
and the glue tab on the other."""

import math
from dataclasses import replace

import pytest
import shapely
from helpers import is_closed_loop, polyline, self_intersections
from shapely.geometry import Polygon

from yanartas_pillowbox import partition, payload, pcb, scad
from yanartas_pillowbox.config import Config, ConfigError
from yanartas_pillowbox.crosssection import solve_shell, solve_two_piece
from yanartas_pillowbox.dimensions import model_dimensions, pattern_dimensions
from yanartas_pillowbox.geometry import (
    FoldDirection,
    FoldedBox,
    FoldedCable,
    build_cross_section,
    build_model3d,
    build_pattern,
    fold_direction,
    lid_layout,
)
from yanartas_pillowbox.svg import render_svg

TWO = Config.defaults().with_values(pieces="two", lid_offset=1.5)
CONFIGS = {
    "default": TWO,
    "stacked": TWO.with_values(end_wall_gap=0),
    "flat": TWO.with_values(thickness=0, lid_offset=0),
    "thick-lid": TWO.with_values(
        width=80, height=20, thickness=1.5, glue_tab_width=15, lid_offset=2, fpc_cable="none"
    ),
    "down": TWO.with_values(fpc_cable="down"),
    "cutout": TWO.with_values(fpc_cutout="both"),
}


@pytest.fixture(params=list(CONFIGS), ids=list(CONFIGS))
def cfg(request):
    return CONFIGS[request.param]


def test_the_shell_is_two_identical_panels_turned():
    """Both panels the same section, the second the first turned half a turn about the
    box's axis; the interior as asked, its corners turned alike."""
    shell = solve_two_piece(107, 48.5, 101, 0.2)
    assert shell.two_piece and shell.z_shift == 0
    assert shell.front.width == shell.back.width
    assert shell.front.sagitta == pytest.approx((48.5 + 0.2) / 2)
    for u in (0.0, 10.0, shell.front.width / 2, shell.front.width):
        (fx, fz), (bx, bz) = shell.front_point(u), shell.back_point(u)
        assert (bx, bz) == pytest.approx((-fx, -fz), abs=1e-9)
    assert shell.inner_fold == pytest.approx((-shell.inner_glue[0], -shell.inner_glue[1]))
    assert shell.inner_fold[0] - shell.inner_glue[0] == pytest.approx(107)
    # (the inner surfaces at the apexes: the interior's height)
    assert shell.front_point(shell.front.width / 2)[1] - 0.1 == pytest.approx(48.5 / 2)
    # About as wide as the one-piece panels together.
    one = solve_shell(107, 48.5, 101, 0.2)
    assert 2 * shell.front.width == pytest.approx(one.circumference, rel=1e-3)


def test_config_field_and_derived_lengths():
    assert Config.defaults().pieces == "one"
    with pytest.raises(ConfigError) as err:
        Config.defaults().with_values(pieces="three")
    assert "pieces" in err.value.errors
    cfg = TWO
    # One end wall gap per piece (at its outer flap); the other piece's ends a gap and a
    # thickness on.
    assert cfg.front_length == pytest.approx(cfg.edge_length + cfg.end_wall_gap)
    assert cfg.inner_offset == pytest.approx(cfg.end_wall_gap + cfg.thickness)
    one = replace(cfg, pieces="one")
    assert one.front_length == pytest.approx(one.edge_length + 2 * one.end_wall_gap)
    assert one.inner_offset == one.end_wall_gap


def test_outline_is_one_closed_contour_without_crossings(cfg):
    pat = build_pattern(cfg)
    assert is_closed_loop(pat.outline.segments)
    assert all(seg.length > 1e-6 for seg in pat.outline.segments)
    assert self_intersections(polyline(pat.outline.segments, 64)) == []
    assert pat.slits == () and pat.scraps == ()


def test_folds_end_on_the_outline_and_stay_off_it(cfg):
    pat = build_pattern(cfg)
    for fold in pat.folds:
        for p in (fold.segment.start, fold.segment.end):
            on_fold = any(o is not fold and o.segment.distance_to(p) < 1e-6 for o in pat.folds)
            assert pat.outline.distance_to(p) < 1e-6 or on_fold, (fold.name, p)
        for i in range(1, 50):
            assert pat.outline.distance_to(fold.segment.point_at(i / 50)) > 1e-3, fold.name


def test_one_panel_an_outer_and_an_inner_flap_and_a_glue_tab(cfg):
    pat = build_pattern(cfg)
    names = {f.name for f in pat.faces}
    assert {"front-panel", "front-top-flap", "back-bottom-flap", "glue-tab"} <= names
    assert not names & {"back-panel", "front-bottom-flap", "back-top-flap"}
    assert ("front-top-lid" in names) == (cfg.end_wall_gap > 0)
    w, lp, d = cfg.shell.front.width, cfg.front_length, cfg.inner_offset
    # The glue tab runs from where the other piece's free edge begins (its ends d on) to
    # this one's inner end.
    glue = pat.fold("glue-tab").segment
    assert glue.start == pytest.approx((w, d)) and glue.end == pytest.approx((w, lp))
    # The cable leaves the free edge (x = 0); the glue tab lies beyond the glue fold.
    if pat.cable is not None:
        assert all(p[0] == pytest.approx(0) for p in pat.cable.junction)
    assert pat.face("glue-tab").x0 == pytest.approx(w)


def test_every_fold_is_a_mountain_fold_from_the_print_side(cfg):
    pat = build_pattern(cfg)
    assert {f.direction for f in pat.folds} == {FoldDirection.MOUNTAIN}
    for fold in pat.folds:
        assert fold_direction(cfg, fold.segment.reversed(), pat.faces) == fold.direction
    inside = build_pattern(replace(cfg, print_side="inside"))
    assert {f.direction for f in inside.folds} == {FoldDirection.VALLEY}


def test_the_walls_stand_a_gap_and_a_thickness_apart_at_both_ends(cfg):
    """At each end one piece's outer wall stands the end wall gap and a thickness outside the
    other piece's inner wall (mid-surface to mid-surface, on the centreline); the inner
    walls stand the interior's length apart."""
    box, shell = FoldedBox(cfg), cfg.shell
    w, s, t, lp = shell.front.width, shell.front.sagitta, cfg.thickness, cfg.front_length
    outer = box.map("front-top-flap", (w / 2, s - 1))
    inner = box.map("back-bottom-flap", (w / 2, lp - s + 1))
    # (the other piece's: this one's turned)
    other_inner, other_outer = box.other(inner), box.other(outer)
    assert outer[1] - other_inner[1] == pytest.approx(cfg.end_wall_gap + t, abs=1e-9)
    assert inner[1] - other_outer[1] == pytest.approx(cfg.end_wall_gap + t, abs=1e-9)
    assert (other_inner[1] - t / 2) - (inner[1] + t / 2) == pytest.approx(cfg.length)


def test_each_glue_tab_lies_a_thickness_outside_the_other_pieces_free_edge(cfg):
    box, shell = FoldedBox(cfg), cfg.shell
    w, y = shell.front.width, cfg.front_length / 2
    other = [
        box.other(box.map("front-panel", (u, y)))
        for u in (k * cfg.glue_tab_width * 2 / 8000 for k in range(8001))
    ]
    # (past its lead: from the glue fold it first runs on along the free edge's tangent)
    for v in (shell.tab_lead + 0.5, cfg.glue_tab_width / 2, cfg.glue_tab_width):
        q = box.map("glue-tab", (w + v, y))
        near = min(math.hypot(q[0] - r[0], q[2] - r[2]) for r in other)
        assert near == pytest.approx(cfg.thickness, abs=2e-3), v


def test_the_model_holds_both_pieces(cfg):
    pat = build_pattern(cfg)
    model = build_model3d(cfg, pat)
    parts = model["parts"]
    assert len(parts) == 2 * len(pat.faces)
    first = [p for p in parts if p["piece"] == 1]
    second = [p for p in parts if p["piece"] == 2]
    for a, b in zip(first, second, strict=True):
        assert a["name"] == b["name"] and a["flat"] == b["flat"]
        assert b["positions"] == [-c for c in a["positions"]]
    assert len(model["lines"]) == 2 * len(pat.folds)
    assert len(model["cables"]) == (0 if pat.cable is None else 2)
    lid = lid_layout(cfg)
    drops = 0.0 if lid is None else 2 * lid.drop
    assert model["bounds"]["length"] == pytest.approx(cfg.front_length + cfg.inner_offset + drops)


def test_the_cross_section_shows_both_glue_tabs_and_cables(cfg):
    section = build_cross_section(cfg)
    assert len(section["glue_tabs"]) == 2 and len(section["material"]) == 4
    assert section["back"] == [[-x, -z] for x, z in section["front"]]
    if cfg.fpc_cable != "none":
        assert len(section["cable"]) == 4  # (each piece's stub and the rest)


def test_the_cable_clears_both_inner_flaps(cfg):
    """Folded into the box, the stub and first corner of the cable keep the clearance from
    the inner flaps at both ends: the other piece's at the top, this one's at the bottom."""
    if cfg.fpc_cable == "none":
        pytest.skip("no cable")
    pat = build_pattern(cfg)
    folded, box, shell = FoldedCable(cfg, pat.cable), FoldedBox(cfg), cfg.shell
    t, gap, lp, d = cfg.thickness, cfg.fpc_cable_gap, cfg.front_length, cfg.inner_offset
    sec = shell.front

    def u_at(x0, x):  # (the panel's u at X = x, within it: X rises with u)
        lo, hi = 0.0, sec.width
        for _ in range(80):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if x0 + sec.x(mid) < x else (lo, mid)
        return (lo + hi) / 2

    cable = pat.cable
    (x0, _), (x1, _) = cable.path[0], cable.path[1]
    (_, ya), (_, yb) = cable.junction
    h = cable.width / 2
    for i in range(41):
        for k in range(9):
            x, y, _ = folded.map(0, (x0 + (x1 - h - x0) * i / 40, ya + (yb - ya) * k / 8))
            # The other piece's inner wall (top): its u at X, the other's X turned.
            top = box.cy - (d + sec.z(u_at(shell.front_x, -x)))
            bottom = box.cy - (lp - sec.z(u_at(shell.front_x, x)))
            assert bottom + t / 2 + 0.9 * gap < y < top - t / 2 - 0.9 * gap, (x, y, top, bottom)


def test_dimensions_measure_the_interior():
    cfg = TWO
    pat = build_pattern(cfg)
    dims = {d.param: d.value for d in pattern_dimensions(cfg, pat, (0, 0)) if d.param}
    assert dims["length"] == pytest.approx(cfg.length)
    assert dims["height"] == pytest.approx(cfg.height, abs=0.01)
    assert dims["end_wall_gap"] == pytest.approx(cfg.end_wall_gap)
    assert dims["circumference"] == pytest.approx(cfg.shell.front.width)
    model = {d.param: d.value for d in model_dimensions(cfg)}
    for name in ("length", "height", "width", "end_wall_gap", "lid_offset", "lid_overlap"):
        assert model[name] == pytest.approx(getattr(cfg, name), abs=1e-6), name


def test_payload_clearance_and_interior_model():
    cfg = TWO
    assert payload.clearance(cfg) == pytest.approx(cfg.payload_clearance, abs=1e-3)
    text = scad.render_scad(cfg)
    assert "rotate([0, 180, 0]) mirror([0, 1, 0]) end_space();" in text


def test_svg_labels_say_to_make_two():
    text = render_svg(TWO)
    assert "make two" in text and "outer flap end" in text and "inner flap end" in text


def test_lid_offset_hint_uses_the_two_piece_shell():
    """The widest lid offset (and the width hint past it) come from the two-piece shell."""
    with pytest.raises(ConfigError) as err:
        Config.defaults().with_values(pieces="two", lid_offset=2.0)
    message = err.value.errors["lid_offset"]
    wide = float(message.rsplit("at least ", 1)[1].split(" mm")[0])
    Config.defaults().with_values(pieces="two", lid_offset=2.0, width=wide)


def test_the_pcb_covers_a_piece():
    """KiMesh over one piece: every face of it covered, the copper checks out."""
    layout = pcb.layout(TWO)
    assert pcb.verify(layout) == []
    assert all(m.unreached == 0 for m in layout.meshes.values())


def test_strips_keep_their_ends_off_a_fold():
    """Strips whose default order runs one up beside a fold closing in: another order (still
    rising to the middle and falling off) whose ends each lie on one side of it."""
    width = 4.0
    ports = [shapely.box(0, k * width, width, (k + 1) * width) for k in range(3)]
    # A fold across the area, closing in from the third port's side: the zones either side.
    fold = Polygon([(width, 3 * width + 2), (60, -10), (60, 40), (width, 40)])
    area = shapely.box(width, -20, 60, 40)
    zones = [area.difference(fold), area.intersection(fold)]

    def ends_clear(lanes):
        return all(
            any(
                z.buffer(1e-6).contains(
                    shapely.box(ln.bounds[2], ln.bounds[1], ln.bounds[2] + width, ln.bounds[3])
                )
                for z in zones
            )
            for ln in lanes
        )

    plain = partition.strips(ports, (1.0, 0.0), width)
    chosen = partition.strips(ports, (1.0, 0.0), width, zones)
    assert not ends_clear(plain) and ends_clear(chosen)
    depth = [s.bounds[2] for s in chosen]
    assert len(set(depth)) == 3  # (no two as long)
    # Nowhere room: a clear error.
    with pytest.raises(partition.MeshError, match="Cable entry"):
        partition.strips(ports, (1.0, 0.0), width, [shapely.box(width, -20, 9, 40)])
