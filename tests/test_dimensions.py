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
    "notched": D.with_values(thumb_notch=True, thumb_notch_radius=7.5),
    "sagitta-mode": D.with_values(arc_mode="sagitta", sagitta=8.25, glue_tab_width=20),
    "no-taper": D.with_values(glue_tab_taper=0),
    "big": D.with_values(
        width=300,
        length=160,
        depth=110,
        glue_tab_width=40,
        glue_tab_taper=30,
        thumb_notch=True,
        thumb_notch_radius=60,
    ),
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
    if d.kind == "radius":
        return math.dist(d.points[0], d.points[1])
    return dm.polyline_length(list(d.points))


def expected_value(cfg, param):
    if param == "depth" and cfg.arc_mode == "depth":
        return cfg.depth
    if param == "sagitta":
        return cfg.sagitta
    return getattr(cfg, param)


# ------------------------------------------------------------------ 2D pattern
def test_pattern_dimensions_cover_the_parameters(cfg):
    pattern = build_pattern(cfg)
    dims = dm.pattern_dimensions(cfg, pattern, sheet_offset(pattern))
    expected = {"width", "length", "glue_tab_width", cfg.arc_mode}
    if cfg.glue_tab_taper > 0:
        expected.add("glue_tab_taper")
    if cfg.thumb_notch:
        expected.add("thumb_notch_radius")
    assert {d.param for d in dims} == expected


def test_pattern_dimensions_measure_their_parameter(cfg):
    pattern = build_pattern(cfg)
    for d in dm.pattern_dimensions(cfg, pattern, sheet_offset(pattern)):
        assert measured(d) == pytest.approx(d.value, abs=1e-9), d.param
        if d.param == cfg.arc_mode:  # shown as the fold sagitta = depth / 2 (or sagitta)
            assert d.value == pytest.approx(cfg.fold_sagitta)
            assert dm.fmt(cfg.fold_sagitta) in d.label
        else:
            assert d.value == pytest.approx(expected_value(cfg, d.param)), d.param
            assert dm.fmt(expected_value(cfg, d.param)) in d.label


def test_pattern_dimensions_sit_on_the_exported_geometry(cfg):
    """Measured points lie on the paths of the downloaded SVG (same coordinates)."""
    pattern = build_pattern(cfg)
    root = svg_elements(render_svg(cfg, pattern))
    segs = [s for el in root.iter(q("path")) for s in parse_path(el.get("d"))[1]]
    for d in dm.pattern_dimensions(cfg, pattern, sheet_offset(pattern)):
        pts = d.points[1:] if d.kind == "radius" else d.points  # radius: skip the centre
        for p in pts:
            assert min(s.distance_to(p) for s in segs) < 1e-5, (d.param, p)


def test_outer_pattern_dimensions_are_outside_the_sheet(cfg):
    pattern = build_pattern(cfg)
    root = svg_elements(render_svg(cfg, pattern))
    w = float(root.get("width")[:-2])
    h = float(root.get("height")[:-2])
    for d in dm.pattern_dimensions(cfg, pattern, sheet_offset(pattern)):
        if d.param in ("width", "glue_tab_width"):
            assert d.at > h
        elif d.param == "length":
            assert d.at < 0
        elif d.param == "glue_tab_taper":
            assert d.at > w


def test_exported_svg_has_no_dimensions(cfg):
    svg = render_svg(cfg)
    assert "dim" not in svg.lower()


# ------------------------------------------------------------------ cross-section
def test_section_dimensions(cfg):
    section = build_cross_section(cfg)
    dims = {d.param: d for d in dm.section_dimensions(cfg, section)}
    depth = dims[cfg.arc_mode]
    assert measured(depth) == pytest.approx(cfg.box_depth, rel=1e-9)
    assert dm.fmt(cfg.box_depth) in depth.label
    # The depth is measured between the apexes of the front and back panel curves.
    assert list(depth.points[1]) in section["front"]
    assert depth.points[0] == pytest.approx((depth.points[1][0], -depth.points[1][1]))
    width = dims["width"]
    assert measured(width) == pytest.approx(cfg.width, rel=1e-3)  # arc length of the panel
    assert [list(p) for p in width.points] == section["front"]
    tab = dims["glue_tab_width"]
    assert measured(tab) == pytest.approx(cfg.glue_tab_width, rel=1e-3)
    closed = dims[None]  # derived closed width, not a parameter
    assert measured(closed) == pytest.approx(section["width"], abs=1e-5)  # 1e-6 mm rounding


# ------------------------------------------------------------------ 3D model
def test_model_dimensions(cfg):
    box = FoldedBox(cfg)
    dims = {d.param: d for d in dm.model_dimensions(cfg)}
    assert set(dims) == {"length", "width", cfg.arc_mode}

    length = dims["length"]
    assert math.dist(*length.points) == pytest.approx(cfg.length)
    # ... measured between the two ends of the straight fold between the panels.
    fold_ends = [box.map("front-panel", (cfg.width, y)) for y in (0.0, cfg.length)]
    for p in length.points:
        assert min(math.dist(p, e) for e in fold_ends) < 1e-9

    depth = dims[cfg.arc_mode]
    assert math.dist(*depth.points) == pytest.approx(cfg.box_depth)
    assert dm.fmt(cfg.box_depth) in depth.label

    width = dims["width"]
    assert dm.polyline_length(list(width.points)) == pytest.approx(cfg.width, rel=1e-3)
    n = len(width.points) - 1
    for i, p in enumerate(width.points):  # on the front panel, across its full width
        assert math.dist(p, box.map("front-panel", (cfg.width * i / n, cfg.length / 2))) < 1e-9

    for d in dims.values():  # drawing geometry is present
        assert len(d.line) >= 2 and d.label_at is not None and d.extensions


# ------------------------------------------------------------------ API
def test_render_returns_dimensions(tmp_path):
    client = create_app(tmp_path / "s.json").test_client()
    cfg = CONFIGS["notched"]
    data = client.post("/api/render", json={"config": cfg.to_dict()}).get_json()
    dims = data["dimensions"]
    assert {d["param"] for d in dims["pattern"]} >= {"width", "length", "thumb_notch_radius"}
    assert {d["param"] for d in dims["section"]} >= {"width", "depth", "glue_tab_width"}
    assert {d["param"] for d in dims["model"]} == {"width", "length", "depth"}
    for view in dims.values():
        for d in view:
            assert d["label"] and d["kind"] and d["points"]
