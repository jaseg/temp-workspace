"""Dimension annotations must show the input parameters, measured on the real geometry."""

import math

import pytest
from helpers import parse_path, q, svg_elements

from yanartas_pillowbox import dimensions as dm
from yanartas_pillowbox.config import Config
from yanartas_pillowbox.geometry import FoldedBox, build_cross_section, build_pattern, lid_layout
from yanartas_pillowbox.server import create_app
from yanartas_pillowbox.svg import render_svg, sheet_offset

D = Config.defaults()
CONFIGS = {
    "default": D,
    "stacked": D.with_values(end_wall_gap=0),
    "zero-thickness": D.with_values(thickness=0, glue_tab_width=20),
    "no-taper": D.with_values(glue_tab_taper=0),
    "fpc-front": D.with_values(fpc_cutout="front"),
    "fpc-both": D.with_values(fpc_cutout="both"),
    "big": D.with_values(width=300, length=160, height=110, glue_tab_width=40, glue_tab_taper=30),
}


@pytest.fixture(params=list(CONFIGS), ids=list(CONFIGS))
def cfg(request):
    return CONFIGS[request.param]


def measured(d):
    """Re-measure a 2D dimension from its points."""
    (x1, y1), (x2, y2) = d.points[0], d.points[-1]
    if d.kind == "horizontal":
        return abs(x2 - x1)
    if d.kind == "vertical":
        return abs(y2 - y1)
    return dm.polyline_length(list(d.points))


def expected_value(cfg, param):
    if param == "circumference":  # computed, not an input
        return cfg.circumference
    return getattr(cfg, param)


# ------------------------------------------------------------------ 2D pattern
def test_pattern_dimensions_cover_the_parameters(cfg):
    pattern = build_pattern(cfg)
    dims = dm.pattern_dimensions(cfg, pattern, sheet_offset(pattern))
    expected = {"circumference", "length", "height", "glue_tab_width"}
    if cfg.glue_tab_taper > 0:
        expected.add("glue_tab_taper")
    if cfg.end_wall_gap > 0:
        expected |= {"end_wall_gap", "lid_overlap"}
    assert {d.param for d in dims} == expected


def test_pattern_dimensions_measure_their_parameter(cfg):
    pattern = build_pattern(cfg)
    for d in dm.pattern_dimensions(cfg, pattern, sheet_offset(pattern)):
        assert measured(d) == pytest.approx(d.value, abs=1e-9), d.param
        # The height runs to the inner flap's cut edge, which follows the front panel's
        # inner surface: exact on the front panel's apex, a fraction of t off the back's.
        tol = 0.01 * cfg.thickness if d.param == "height" else 1e-9
        assert d.value == pytest.approx(expected_value(cfg, d.param), abs=tol), d.param
        assert dm.fmt(expected_value(cfg, d.param)) in d.label


def test_pattern_dimensions_sit_on_the_exported_geometry(cfg):
    """Measured points lie on the paths of the downloaded SVG (same coordinates), or, for the
    interior length and height and the end wall gap, inside the folds by the material
    allowance: the interior length starts e + 1.5 t inside the front panel's folds (outer
    wall, gap, inner wall), the interior height t/2 inside the back panel's fold (its inner
    surface), the gap t/2 inside the front panel's fold (the outer wall's inner surface)."""
    pattern = build_pattern(cfg)
    root = svg_elements(render_svg(cfg, pattern))
    segs = [s for el in root.iter(q("path")) for s in parse_path(el.get("d"))[1]]
    t, e = cfg.thickness, cfg.end_wall_gap
    allowance = {
        ("length", 0): e + 1.5 * t,
        ("length", 1): e + 1.5 * t,
        ("height", 0): t / 2,
        ("end_wall_gap", 0): t / 2,
        ("end_wall_gap", 1): e + t / 2,
        # On the lid, over the inner wall's outer surface: checked below.
        ("lid_overlap", 1): None,
    }
    if cfg.fpc_cutout == "both":  # measured to where the edge would be without the cutout
        x = cfg.body.front.width + cfg.body.back.width / 2
        plain = build_pattern(cfg.with_values(fpc_cutout="none"))
        cut = pattern.face("back-top-flap").y_range(x)[0]
        allowance["height", 1] = cut - plain.face("back-top-flap").y_range(x)[0]
    dx, dy = sheet_offset(pattern)
    for d in dm.pattern_dimensions(cfg, pattern, (dx, dy)):
        for i, p in enumerate(d.points):
            if allowance.get((d.param, i), 0) is None:
                continue
            dist = min(s.distance_to(p) for s in segs)
            assert dist == pytest.approx(allowance.get((d.param, i), 0), abs=1e-4), (d.param, i)
        if d.param == "lid_overlap":
            # From the top lid's free edge into the lid, to where the inner wall's outer
            # surface lies under it (the lid's depth there, less the overlap).
            lid, x = lid_layout(cfg), d.points[0][0] - dx
            depth = next(dd for xx, dd in lid.depth if xx == pytest.approx(x))
            ys = sorted(q[1] - dy for q in d.points)
            assert ys == pytest.approx([lid.level - depth, lid.level - depth + cfg.lid_overlap])


def test_length_dimension_runs_along_the_midline(cfg):
    pattern = build_pattern(cfg)
    dx, dy = sheet_offset(pattern)
    length = next(d for d in dm.pattern_dimensions(cfg, pattern, (dx, dy)) if d.param == "length")
    inset = cfg.end_wall_gap + 1.5 * cfg.thickness
    for p, fold, k in zip(length.points, ("front-top", "front-bottom"), (1, -1), strict=True):
        apex = pattern.fold(fold).segment.point_at(0.5)
        assert p == pytest.approx((apex[0] + dx, apex[1] + dy + k * inset))
    # (drawn beside the midline, clear of the exported "front end"/"back end" labels)
    assert length.at == pytest.approx(cfg.body.front.width * 0.3 + dx)


def test_gap_dimension_continues_the_length(cfg):
    """The end wall gap is measured on the same line as the length, at the bottom end: from
    the inner wall's outer surface (a thickness beyond the interior's end) to the outer
    wall's inner surface."""
    pattern = build_pattern(cfg)
    offset = sheet_offset(pattern)
    dims = {d.param: d for d in dm.pattern_dimensions(cfg, pattern, offset)}
    if cfg.end_wall_gap == 0:
        assert "end_wall_gap" not in dims
        return
    gap, length = dims["end_wall_gap"], dims["length"]
    assert gap.at == length.at
    assert gap.points[0][0] == gap.points[1][0] == length.points[1][0]
    assert min(p[1] for p in gap.points) == pytest.approx(length.points[1][1] + cfg.thickness)
    assert gap.value == pytest.approx(cfg.end_wall_gap)


def test_tab_and_taper_are_on_the_same_side(cfg):
    """Both glue-tab dimensions are taken at the tab's bottom end."""
    pattern = build_pattern(cfg)
    dims = {d.param: d for d in dm.pattern_dimensions(cfg, pattern, sheet_offset(pattern))}
    if "glue_tab_taper" not in dims:
        pytest.skip("no taper")
    y_mid = (pattern.bbox[1] + pattern.bbox[3]) / 2 + sheet_offset(pattern)[1]
    for name in ("glue_tab_width", "glue_tab_taper"):
        assert all(p[1] > y_mid for p in dims[name].points), name


def test_outer_pattern_dimensions_are_outside_the_sheet(cfg):
    pattern = build_pattern(cfg)
    root = svg_elements(render_svg(cfg, pattern))
    w = float(root.get("width")[:-2])
    h = float(root.get("height")[:-2])
    for d in dm.pattern_dimensions(cfg, pattern, sheet_offset(pattern)):
        if d.param in ("circumference", "glue_tab_width"):
            assert d.at > h
        elif d.param == "glue_tab_taper":
            assert d.at > w


def test_exported_svg_has_no_dimensions(cfg):
    svg = render_svg(cfg)
    assert "dim" not in svg.lower()


# ------------------------------------------------------------------ cross-section
def on_outline(section, p, tol=1e-5):
    """Is p on the section's interior outline?"""
    loop = section["interior"]
    return min(seg_dist(p, a, b) for a, b in zip(loop, loop[1:] + loop[:1], strict=True)) < tol


def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    ll = dx * dx + dy * dy
    t = 0 if ll == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ll))
    return math.dist(p, (a[0] + t * dx, a[1] + t * dy))


def test_section_dimensions(cfg):
    section = build_cross_section(cfg, samples=400)
    dims = {d.param: d for d in dm.section_dimensions(cfg, section)}
    assert set(dims) == {"height", "width", "circumference"}
    # Interior height: between the panels' inner surfaces at their apexes.
    height = dims["height"]
    assert measured(height) == pytest.approx(cfg.height, abs=1e-5)
    assert dm.fmt(cfg.height) in height.label
    for p in height.points:
        assert on_outline(section, p, tol=2e-3 * cfg.width), p  # chord sag of the outline
    # The driving width: between the interior corners at the two side folds.
    width = dims["width"]
    assert measured(width) == pytest.approx(cfg.width, abs=1e-5)  # 1e-6 mm rounding
    assert dm.fmt(cfg.width) in width.label
    for p in width.points:  # the interior corners
        assert list(p) in section["interior"]
    if cfg.thickness == 0:  # the corners are the folds themselves
        folds = sorted([tuple(section["front"][-1]), tuple(section["back"][-1])])
        assert sorted(width.points) == pytest.approx(folds, abs=1e-5)
    # Part of the circumference: the arc length of the front panel's mid-surface.
    arc = dims["circumference"]
    assert measured(arc) == pytest.approx(cfg.body.front.width, rel=1e-4)
    assert [list(p) for p in arc.points] == section["front"]


# ------------------------------------------------------------------ 3D model
def test_model_dimensions(cfg):
    box = FoldedBox(cfg)
    body = box.body
    w, edge, t = body.front.width, cfg.edge_length, cfg.thickness
    e, front = cfg.end_wall_gap, cfg.front_length
    dims = {d.param: d for d in dm.model_dimensions(cfg)}
    extra = {"end_wall_gap", "lid_overlap", "lid_offset"} if e > 0 else set()
    assert set(dims) == {"length", "width", "height"} | extra

    length = dims["length"]  # along the back panel's midline, between the inner walls
    assert math.dist(*length.points) == pytest.approx(cfg.length)
    inset, wb = e + body.back.sagitta + t / 2, body.back.width
    ends = [box.map("back-panel", (w + wb / 2, y)) for y in (inset, front - inset)]
    for p, a in zip(length.points, ends, strict=True):
        assert math.dist(p, a) < 1e-9
    assert abs(length.points[0][1]) == pytest.approx(cfg.length / 2)  # the interior's ends

    if e > 0:  # from the inner wall's outer surface to the outer wall's inner surface
        gap = dims["end_wall_gap"]
        assert math.dist(*gap.points) == pytest.approx(e)
        ys = sorted(-p[1] for p in gap.points)
        assert ys == pytest.approx([cfg.length / 2 + t, cfg.length / 2 + t + e])
        overlap = dims["lid_overlap"]  # along the lid
        assert math.dist(*overlap.points) == pytest.approx(cfg.lid_overlap)
        # The lid offset: straight up (in the view) from where the lid would rest, a
        # thickness outside the back panel, to the lid, where it comes closest.
        offset = dims["lid_offset"]
        rest, lid_point = offset.points
        assert math.dist(rest, lid_point) == pytest.approx(cfg.lid_offset, abs=1e-9)
        assert rest[2] == pytest.approx(body.surface_z("back", t, rest[0]))
        assert lid_point[2] < rest[2]
        # (drawn on the back panel's side, which the 3D view shows up)
        for name in ("length", "end_wall_gap", "lid_overlap"):
            start, end = dims[name].extensions[0]
            assert end[2] < start[2], name

    height = dims["height"]  # between the panels' inner surfaces on the centreline
    assert math.dist(*height.points) == pytest.approx(cfg.height)
    assert dm.fmt(cfg.height) in height.label
    assert sorted(p[2] for p in height.points) == pytest.approx([-cfg.height / 2, cfg.height / 2])

    width = dims["width"]  # interior corner to interior corner, at the -Y end of the box
    assert math.dist(*width.points) == pytest.approx(cfg.width, rel=1e-9)
    xs = sorted(p[0] for p in width.points)
    assert xs == pytest.approx([body.inner_glue[0], body.inner_fold[0]])
    assert all(p[1] == pytest.approx(-edge / 2) for p in width.points)

    for d in dims.values():  # drawing geometry is present
        assert len(d.line) >= 2 and d.label_at is not None and d.extensions


# ------------------------------------------------------------------ API
def test_render_returns_dimensions(tmp_path):
    client = create_app(tmp_path / "s.json").test_client()
    data = client.post("/api/render", json={"config": D.to_dict()}).get_json()
    dims = data["dimensions"]
    assert {d["param"] for d in dims["pattern"]} == {
        "circumference",
        "length",
        "height",
        "glue_tab_width",
        "glue_tab_taper",
        "end_wall_gap",
        "lid_overlap",
    }
    assert {d["param"] for d in dims["section"]} == {"width", "height", "circumference"}
    model = {"width", "length", "height", "end_wall_gap", "lid_overlap", "lid_offset"}
    assert {d["param"] for d in dims["model"]} == model
    for view in dims.values():
        for d in view:
            assert d["label"] and d["kind"] and d["points"]
