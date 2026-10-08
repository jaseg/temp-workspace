"""Dimension annotations must show the input parameters, measured on the real geometry."""

import math

import pytest
from helpers import parse_path, q, svg_elements

from yanartas_pillowbox import dimensions as dm
from yanartas_pillowbox.config import Config
from yanartas_pillowbox.geometry import FoldedBox, build_cross_section, build_pattern
from yanartas_pillowbox.server import create_app
from yanartas_pillowbox.svg import render_svg, sheet_offset

D = Config.defaults()
CONFIGS = {
    "default": D,
    "zero-thickness": D.with_values(thickness=0, glue_tab_width=20),
    "no-taper": D.with_values(glue_tab_taper=0),
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
    assert {d.param for d in dims} == expected


def test_pattern_dimensions_measure_their_parameter(cfg):
    pattern = build_pattern(cfg)
    for d in dm.pattern_dimensions(cfg, pattern, sheet_offset(pattern)):
        assert measured(d) == pytest.approx(d.value, abs=1e-9), d.param
        assert d.value == pytest.approx(expected_value(cfg, d.param)), d.param
        assert dm.fmt(expected_value(cfg, d.param)) in d.label


def test_pattern_dimensions_sit_on_the_exported_geometry(cfg):
    """Measured points lie on the paths of the downloaded SVG (same coordinates). The
    height's far end is where the opposite fold lands, thickness/2 beyond the flap's cut
    edge."""
    pattern = build_pattern(cfg)
    root = svg_elements(render_svg(cfg, pattern))
    segs = [s for el in root.iter(q("path")) for s in parse_path(el.get("d"))[1]]
    for d in dm.pattern_dimensions(cfg, pattern, sheet_offset(pattern)):
        for i, p in enumerate(d.points):
            dist = min(s.distance_to(p) for s in segs)
            if d.param == "height" and i == 1:
                assert dist == pytest.approx(cfg.thickness / 2, abs=1e-5)
            else:
                assert dist < 1e-5, (d.param, p)


def test_length_dimension_runs_along_the_midline(cfg):
    pattern = build_pattern(cfg)
    dx, dy = sheet_offset(pattern)
    length = next(d for d in dm.pattern_dimensions(cfg, pattern, (dx, dy)) if d.param == "length")
    for p, fold in zip(length.points, ("front-top", "front-bottom"), strict=True):
        apex = pattern.fold(fold).segment.point_at(0.5)
        assert p == pytest.approx((apex[0] + dx, apex[1] + dy))
    assert length.at == pytest.approx(cfg.panel_width / 2 + dx)  # drawn on the midline


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
def test_section_dimensions(cfg):
    section = build_cross_section(cfg)
    dims = {d.param: d for d in dm.section_dimensions(cfg, section)}
    assert set(dims) == {"height", "width", "circumference"}
    height = dims["height"]
    assert measured(height) == pytest.approx(cfg.height, rel=1e-9)
    assert dm.fmt(cfg.height) in height.label
    # The height is measured between the apexes of the front and back panel curves.
    assert list(height.points[1]) in section["front"]
    assert height.points[0] == pytest.approx((height.points[1][0], -height.points[1][1]))
    # The driving width: fold to fold across the section.
    width = dims["width"]
    assert measured(width) == pytest.approx(cfg.width, abs=1e-5)  # 1e-6 mm rounding
    assert dm.fmt(cfg.width) in width.label
    assert width.points[0][1] == width.points[1][1] == 0  # both straight folds, Z = 0
    # Half the circumference: the arc length of the front panel.
    half = dims["circumference"]
    assert measured(half) == pytest.approx(cfg.circumference / 2, rel=1e-4)
    assert [list(p) for p in half.points] == section["front"]


# ------------------------------------------------------------------ 3D model
def test_model_dimensions(cfg):
    box = FoldedBox(cfg)
    w, edge, s_f = cfg.panel_width, cfg.edge_length, cfg.fold_sagitta
    dims = {d.param: d for d in dm.model_dimensions(cfg)}
    assert set(dims) == {"length", "width", "height"}

    length = dims["length"]  # along the front panel's midline, apex to apex
    assert math.dist(*length.points) == pytest.approx(cfg.length)
    apexes = [box.map("front-panel", (w / 2, y)) for y in (s_f, edge - s_f)]
    for p, a in zip(length.points, apexes, strict=True):
        assert math.dist(p, a) < 1e-9

    height = dims["height"]
    assert math.dist(*height.points) == pytest.approx(cfg.height)
    assert dm.fmt(cfg.height) in height.label

    width = dims["width"]  # fold to fold across the box
    assert math.dist(*width.points) == pytest.approx(cfg.width, rel=1e-9)
    # (drawn at the -Y end of the box, i.e. flat y = edge length)
    fold_ends = [box.map("front-panel", (x, edge)) for x in (0.0, w)]
    for p in width.points:
        assert min(math.dist(p, e) for e in fold_ends) < 1e-9

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
    }
    assert {d["param"] for d in dims["section"]} == {"width", "height", "circumference"}
    assert {d["param"] for d in dims["model"]} == {"width", "length", "height"}
    for view in dims.values():
        for d in view:
            assert d["label"] and d["kind"] and d["points"]
