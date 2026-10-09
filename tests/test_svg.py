import json
import math

import pytest
from helpers import parse_path, q, self_intersections, svg_elements

from yanartas_pillowbox.config import SCHEMA_VERSION, STROKE_WIDTH, Config
from yanartas_pillowbox.geometry import FoldDirection, build_pattern
from yanartas_pillowbox.svg import (
    CONFIG_NS,
    INKSCAPE_NS,
    LAYERS,
    MARGIN,
    SvgImportError,
    extract_config,
    face_labels,
    render_svg,
    sheet_offset,
)

INK_LABEL = f"{{{INKSCAPE_NS}}}label"

CONFIGS = [
    Config.defaults(),
    Config.defaults().with_values(print_side="inside", glue_tab_taper=0),
    Config.defaults().with_values(height=12, glue_tab_width=20),
    Config.defaults().with_values(
        width=33.3,
        length=77.7,
        height=12.5,
        thickness=0.0,
        glue_tab_taper=0,
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
    """Parsing the emitted paths gives back the same contour and folds (catches arc flag
    mistakes)."""
    pat = build_pattern(cfg)
    root = svg_elements(render_svg(cfg, pat))
    dx, dy = sheet_offset(pat)
    _, segs = parse_path(_path(root, "cut-outline").get("d"))
    assert len(segs) == len(pat.outline.segments)
    pairs = list(zip(pat.outline.segments, segs, strict=True))
    for fold in pat.folds:
        pairs.append((fold.segment, parse_path(_path(root, f"fold-{fold.name}").get("d"))[1][0]))
    for mine, theirs in pairs:
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


FOLD_LAYERS = {"fold-mountain": FoldDirection.MOUNTAIN, "fold-valley": FoldDirection.VALLEY}


def fold_elements(root):
    for layer in FOLD_LAYERS:
        g = root.find(f"{q('g')}[@id='{layer}']")
        yield from (g if g is not None else [])


def test_layers_and_line_styles(cfg):
    """All lines black; the cut is solid, folds are dashed by direction (mountain dash-dot,
    valley dashed), one Inkscape layer per line type."""
    pattern = build_pattern(cfg)
    root = svg_elements(render_svg(cfg, pattern))
    present = {d for d in FoldDirection if any(f.direction == d for f in pattern.folds)}
    layers = [g for g in root.findall(q("g")) if g.get("id") != "labels"]
    assert {g.get("id") for g in layers} == {"cut"} | {LAYERS[d][0] for d in present}
    for g in layers:
        assert g.get(f"{{{INKSCAPE_NS}}}groupmode") == "layer"
        assert g.get(INK_LABEL)
        children = list(g)
        assert children
        for el in children:
            assert el.get("stroke") == "#000000"
            assert el.get("fill") == "none"
            assert float(el.get("stroke-width")) == pytest.approx(STROKE_WIDTH) == 0.1
            assert el.get("style") is None and el.get("class") is None
            if g.get("id") == "cut":
                assert "stroke-dasharray" not in el.attrib
            else:
                assert el.get("stroke-dasharray") == LAYERS[FOLD_LAYERS[g.get("id")]][2]
    assert root.find(f".//{q('style')}") is None


def test_fold_dash_patterns_differ():
    mountain, valley = LAYERS[FoldDirection.MOUNTAIN][2], LAYERS[FoldDirection.VALLEY][2]
    assert mountain and valley and mountain != valley
    assert len(mountain.split()) == 4  # dash-dot
    assert len(valley.split()) == 2  # dashed


def test_folds_grouped_by_direction(cfg):
    pattern = build_pattern(cfg)
    root = svg_elements(render_svg(cfg, pattern))
    for fold in pattern.folds:
        el = root.find(f".//{q('path')}[@id='fold-{fold.name}']")
        layer = next(g for g in root.findall(q("g")) if el in list(g))
        assert FOLD_LAYERS[layer.get("id")] == fold.direction


def test_fold_paths_are_open_and_single(cfg):
    root = svg_elements(render_svg(cfg))
    els = list(fold_elements(root))
    pattern = build_pattern(cfg)
    assert len(els) == len(pattern.all_folds)
    assert len(pattern.wall_folds) == (4 if cfg.interior_walls else 0)  # two per end
    for el in els:
        cmds, segs = parse_path(el.get("d"))
        assert cmds.count("M") == 1 and "Z" not in cmds
        # Body folds are one line or arc; the bridge folds one polyline each.
        assert len(segs) == 1 or el.get("id").startswith(("fold-top-", "fold-bottom-"))


def _near_bbox(seg, p, tol):
    x0, y0, x1, y1 = seg.bbox()
    return x0 - tol <= p[0] <= x1 + tol and y0 - tol <= p[1] <= y1 + tol


def test_fold_paths_do_not_overlap_cut_in_svg(cfg):
    root = svg_elements(render_svg(cfg))
    _, outline = parse_path(_path(root, "cut-outline").get("d"))
    for el in fold_elements(root):
        _, segs = parse_path(el.get("d"))
        for p in (segs[0].start, segs[-1].end):
            assert min(s.distance_to(p) for s in outline) < 1e-5
        # (bridge folds are polylines of many short pieces: a few points on each suffice)
        steps = 40 if len(segs) == 1 else 2
        for seg in segs:
            for i in range(1, steps):
                p = seg.point_at(i / steps)
                near = [s for s in outline if _near_bbox(s, p, 1e-3)]
                assert min((s.distance_to(p) for s in near), default=1.0) > 1e-3


def test_metadata_embedded(cfg):
    root = svg_elements(render_svg(cfg))
    el = root.find(f"{q('metadata')}/{{{CONFIG_NS}}}config")
    assert el is not None and el.get("version") == str(SCHEMA_VERSION)
    data = json.loads(el.text)
    assert data["version"] == SCHEMA_VERSION


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
    with pytest.raises(SvgImportError, match="schema version 6"):
        extract_config(_with_meta(json.dumps({"version": 6, "width": 50})))
    with pytest.raises(SvgImportError, match="no schema version"):
        extract_config(_with_meta(json.dumps({"width": 50})))


def test_import_corrupt_or_invalid():
    with pytest.raises(SvgImportError, match="corrupt"):
        extract_config(_with_meta("{nope"))
    with pytest.raises(SvgImportError, match="invalid"):
        extract_config(_with_meta(json.dumps({"version": SCHEMA_VERSION, "width": -5})))


def test_print_inside_only_flips_fold_indicators():
    """Printing on the inside keeps the geometry identical and just turns every fold into a
    valley fold (dashed instead of dash-dot)."""
    out = svg_elements(render_svg(Config.defaults()))
    ins_cfg = Config.defaults().with_values(print_side="inside")
    ins = svg_elements(render_svg(ins_cfg))
    paths = lambda root: {el.get("id"): el.get("d") for el in root.iter(q("path"))}  # noqa: E731
    assert paths(ins) == paths(out)
    assert (ins.get("width"), ins.get("height")) == (out.get("width"), out.get("height"))
    assert {g.get("id") for g in ins.findall(q("g"))} == {"cut", "fold-valley", "labels"}
    for el in ins.find(f"{q('g')}[@id='fold-valley']"):
        assert el.get("stroke-dasharray") == LAYERS[FoldDirection.VALLEY][2]
    assert {f.direction for f in build_pattern(ins_cfg).folds} == {FoldDirection.VALLEY}
    assert extract_config(render_svg(ins_cfg)) == ins_cfg


@pytest.mark.parametrize("walls", [False, True])
def test_face_labels(walls):
    """A text layer says on the back panel which side of the box the print side ends up on,
    marks the front and back end once each on the front panel (near its curved folds), and
    tells on every oval panel which way its print side faces: outside for the flaps, inside
    for the interior walls (flipped when printing on the inside). Text is filled, not
    stroked, and sits inside its face."""
    for side in ("outside", "inside"):
        other = "inside" if side == "outside" else "outside"
        cfg = Config.defaults().with_values(print_side=side, interior_walls=walls)
        pattern = build_pattern(cfg)
        root = svg_elements(render_svg(cfg, pattern))
        layer = root.find(f"{q('g')}[@id='labels']")
        assert layer.get(INK_LABEL) == "Labels"
        texts = [el.text for el in layer.iter(q("text"))]
        assert texts.count("front end") == texts.count("back end") == 1
        assert texts.count(side) == 1 + 4  # back panel and the four flaps
        assert texts.count(other) == (2 if walls else 0)  # the interior walls
        for el in layer.iter(q("text")):
            assert el.get("fill") == "#000000" and el.get("stroke") == "none"
            assert 0 < float(el.get("font-size")) <= 3
        faces = {f.name: f for f in (*pattern.faces, *pattern.wall_faces)}
        for text, (x, y), _ in face_labels(cfg, pattern):
            inside = [
                n
                for n, f in faces.items()
                if f.x0 < x < f.x1 and f.y_range(x)[0] < y < f.y_range(x)[1]
            ]
            assert len(inside) == 1, (text, inside)
            name = inside[0]
            if text.endswith("end"):
                assert name == "front-panel"
                top, bottom = faces[name].y_range(x)
                assert min(y - top, bottom - y) < 10  # near the curved fold
                assert (y - top < bottom - y) == (text == "front end")
            elif name.endswith("wall"):
                assert text == other
            else:
                assert text == side and name in ("back-panel", *(n for n in faces if "flap" in n))
            if name != "front-panel":  # centred on its face
                assert x == pytest.approx((faces[name].x0 + faces[name].x1) / 2)
