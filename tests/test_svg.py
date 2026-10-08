import json
import math

import pytest
from helpers import parse_path, q, self_intersections, svg_elements

from yanartas_pillowbox.config import Config
from yanartas_pillowbox.geometry import build_pattern
from yanartas_pillowbox.svg import (
    CONFIG_NS,
    INKSCAPE_NS,
    MARGIN,
    SvgImportError,
    extract_config,
    render_svg,
)

INK_LABEL = f"{{{INKSCAPE_NS}}}label"

CONFIGS = [
    Config.defaults(),
    Config.defaults().with_values(thumb_notch=True, label=True, label_text='Hi <&> "there"'),
    Config.defaults().with_values(
        width=33.3,
        length=77.7,
        arc_mode="sagitta",
        sagitta=6.25,
        thickness=0.0,
        stroke_width=0.025,
        glue_tab_taper=0,
        color_cut="#123456",
        color_fold_glue="#abcdef",
    ),
]


@pytest.fixture(params=range(len(CONFIGS)))
def cfg(request):
    return CONFIGS[request.param]


def _path(root, path_id):
    return root.find(f".//{q('path')}[@id='{path_id}']")


def test_outline_is_one_closed_path(cfg):
    root = svg_elements(render_svg(cfg))
    cut_layer = root.find(f"{q('g')}[@id='cut']")
    paths = cut_layer.findall(q("path"))
    assert len(paths) == 1
    d = paths[0].get("d")
    cmds, segs = parse_path(d)
    assert cmds.count("M") == 1 and cmds[0] == "M"
    assert cmds[-1] == "Z" and cmds.count("Z") == 1
    # The last drawn point coincides with the start: Z adds no extra segment.
    first = segs[0].start
    last = segs[-1].end
    assert math.dist(first, last) < 1e-6
    pts = [segs[0].start]
    for s in segs:
        pts.extend(s.sample(48)[1:])
    assert self_intersections(pts) == []


def test_svg_arcs_reproduce_geometry(cfg):
    """Parsing the emitted path gives back the same contour (catches flag mistakes)."""
    pat = build_pattern(cfg)
    root = svg_elements(render_svg(cfg, pat))
    _, segs = parse_path(_path(root, "cut-outline").get("d"))
    dx, dy = MARGIN - pat.bbox[0], MARGIN - pat.bbox[1]
    assert len(segs) == len(pat.outline.segments)
    for mine, theirs in zip(pat.outline.segments, segs, strict=True):
        for t in (0.25, 0.5, 0.75):
            a, b = mine.point_at(t), theirs.point_at(t)
            assert math.dist((a[0] + dx, a[1] + dy), b) < 1e-5


def test_canvas_is_bbox_plus_margin(cfg):
    pat = build_pattern(cfg)
    root = svg_elements(render_svg(cfg, pat))
    w = pat.bbox[2] - pat.bbox[0] + 2 * MARGIN
    h = pat.bbox[3] - pat.bbox[1] + 2 * MARGIN
    assert root.get("width").endswith("mm") and root.get("height").endswith("mm")
    assert float(root.get("width")[:-2]) == pytest.approx(w, abs=1e-6)
    assert float(root.get("height")[:-2]) == pytest.approx(h, abs=1e-6)
    assert [float(v) for v in root.get("viewBox").split()] == pytest.approx([0, 0, w, h], abs=1e-6)

    # Measure the drawn geometry independently: it must sit exactly MARGIN from each edge.
    xs, ys = [], []
    for el in root.iter(q("path")):
        _, segs = parse_path(el.get("d"))
        for s in segs:
            x0, y0, x1, y1 = s.bbox()
            xs += [x0, x1]
            ys += [y0, y1]
    assert min(xs) == pytest.approx(MARGIN, abs=1e-5)
    assert min(ys) == pytest.approx(MARGIN, abs=1e-5)
    assert max(xs) == pytest.approx(w - MARGIN, abs=1e-5)
    assert max(ys) == pytest.approx(h - MARGIN, abs=1e-5)


def test_layers_and_colors(cfg):
    root = svg_elements(render_svg(cfg))
    expected = {
        "cut": cfg.color_cut,
        "fold-straight": cfg.color_fold_straight,
        "fold-curved": cfg.color_fold_curved,
        "fold-glue": cfg.color_fold_glue,
    }
    if cfg.label:
        expected["label"] = cfg.color_label
    layers = root.findall(q("g"))
    assert {g.get("id") for g in layers} == set(expected)
    for g in layers:
        assert g.get(f"{{{INKSCAPE_NS}}}groupmode") == "layer"
        assert g.get(INK_LABEL)
        color = expected[g.get("id")]
        children = list(g)
        assert children
        for el in children:
            if el.tag == q("text"):
                assert el.get("fill") == color
                continue
            assert el.get("stroke") == color
            assert el.get("fill") == "none"
            assert float(el.get("stroke-width")) == pytest.approx(cfg.stroke_width)
            assert el.get("style") is None and el.get("class") is None
            assert "stroke-dasharray" not in el.attrib
    assert root.find(f".//{q('style')}") is None


def test_default_colors_are_distinct():
    cfg = Config.defaults()
    colors = [cfg.color_cut, cfg.color_fold_straight, cfg.color_fold_curved, cfg.color_fold_glue]
    assert len(set(colors)) == 4


def test_fold_paths_are_open_and_single(cfg):
    root = svg_elements(render_svg(cfg))
    for layer in ("fold-straight", "fold-curved", "fold-glue"):
        for el in root.find(f"{q('g')}[@id='{layer}']"):
            cmds, segs = parse_path(el.get("d"))
            assert cmds.count("M") == 1 and "Z" not in cmds and len(segs) == 1


def test_fold_paths_do_not_overlap_cut_in_svg(cfg):
    root = svg_elements(render_svg(cfg))
    _, outline = parse_path(_path(root, "cut-outline").get("d"))
    for layer in ("fold-straight", "fold-curved", "fold-glue"):
        for el in root.find(f"{q('g')}[@id='{layer}']"):
            _, (seg,) = parse_path(el.get("d"))
            for p in (seg.start, seg.end):
                assert min(s.distance_to(p) for s in outline) < 1e-5
            for i in range(1, 40):
                p = seg.point_at(i / 40)
                assert min(s.distance_to(p) for s in outline) > 1e-3


def test_metadata_embedded(cfg):
    root = svg_elements(render_svg(cfg))
    el = root.find(f"{q('metadata')}/{{{CONFIG_NS}}}config")
    assert el is not None and el.get("version") == "1"
    data = json.loads(el.text)
    assert data["version"] == 1


def test_round_trip(cfg):
    restored = extract_config(render_svg(cfg))
    assert restored == cfg
    assert restored.to_dict() == cfg.to_dict()


def test_round_trip_bytes():
    cfg = CONFIGS[1]
    assert extract_config(render_svg(cfg).encode()) == cfg


@pytest.mark.parametrize(
    ("svg", "message"),
    [
        ('<svg xmlns="http://www.w3.org/2000/svg"/>', "no embedded"),
        ("not xml at all", "not valid"),
        ('<html xmlns="http://www.w3.org/1999/xhtml"/>', "not an SVG"),
        ('<!DOCTYPE svg [<!ENTITY a "b">]><svg xmlns="http://www.w3.org/2000/svg"/>', "DOCTYPE"),
    ],
)
def test_import_errors(svg, message):
    with pytest.raises(SvgImportError, match=message):
        extract_config(svg)


def _with_meta(text: str) -> str:
    svg = render_svg(Config.defaults())
    start = svg.index('generator="')
    start = svg.index(">", start) + 1
    end = svg.index("</pillowbox:config>")
    return svg[:start] + text + svg[end:]


def test_import_incompatible_version():
    with pytest.raises(SvgImportError, match="schema version 2"):
        extract_config(_with_meta(json.dumps({"version": 2, "width": 50})))
    with pytest.raises(SvgImportError, match="no schema version"):
        extract_config(_with_meta(json.dumps({"width": 50})))


def test_import_corrupt_or_invalid():
    with pytest.raises(SvgImportError, match="corrupt"):
        extract_config(_with_meta("{nope"))
    with pytest.raises(SvgImportError, match="invalid"):
        extract_config(_with_meta(json.dumps({"version": 1, "width": -5})))
