"""Serialize a pillow box pattern to laser-ready SVG, and read the config back out of one.

Conventions (see README): 1 user unit = 1 mm, canvas = pattern bbox + ``MARGIN`` on every
side, all lines black: one solid closed ``<path>`` for the cut outline, and open dashed paths
for folds, grouped by fold direction seen from the print side (mountain: dash-dot, valley:
dashed). Every style is a plain presentation attribute, each line type is its own Inkscape
layer, and the full config is stored as JSON in ``<metadata>``.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from yanartas_pillowbox import __version__
from yanartas_pillowbox.config import (
    STROKE_WIDTH,
    Config,
    ConfigError,
    SchemaVersionError,
    check_version,
)
from yanartas_pillowbox.geometry import (
    Arc,
    FoldDirection,
    Line,
    Pattern,
    Point,
    Polyline,
    Segment,
    build_pattern,
)

MARGIN = 10.0  # mm on every side

SVG_NS = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
SODIPODI_NS = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
CONFIG_NS = "https://github.com/jaseg/yanartas-pillowbox/ns/config"

ET.register_namespace("", SVG_NS)
ET.register_namespace("inkscape", INKSCAPE_NS)
ET.register_namespace("sodipodi", SODIPODI_NS)
ET.register_namespace("pillowbox", CONFIG_NS)

LINE_COLOR = "#000000"
LABEL_SIZE = 3.0  # mm, at most; smaller on small faces

# Layer id, Inkscape label, stroke-dasharray in mm (None: solid). Origami convention:
# valley folds dashed, mountain folds dash-dot.
LAYERS: dict[str, tuple[str, str, str | None]] = {
    "cut": ("cut", "Cut", None),
    FoldDirection.MOUNTAIN: ("fold-mountain", "Fold - mountain", "3 1.5 0.5 1.5"),
    FoldDirection.VALLEY: ("fold-valley", "Fold - valley", "3 2"),
}


class SvgImportError(ValueError):
    """The SVG has no usable embedded configuration. The message is user-facing."""


def fmt(v: float) -> str:
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def path_data(segments: list[Segment] | tuple[Segment, ...], offset: Point, close: bool) -> str:
    dx, dy = offset

    def pt(p: Point) -> str:
        return f"{fmt(p[0] + dx)},{fmt(p[1] + dy)}"

    parts = [f"M {pt(segments[0].start)}"]
    for seg in segments:
        if isinstance(seg, Polyline):
            parts.extend(f"L {pt(q)}" for q in seg.points[1:])
        elif isinstance(seg, Line):
            parts.append(f"L {pt(seg.end)}")
        elif isinstance(seg, Arc):
            r = fmt(seg.radius)
            parts.append(f"A {r},{r} 0 {int(seg.large_arc)},{int(seg.sweep_flag)} {pt(seg.end)}")
    if close:
        parts.append("Z")
    return " ".join(parts)


def _layer(root: ET.Element, key: str) -> tuple[ET.Element, str | None]:
    layer_id, label, dash = LAYERS[key]
    g = ET.SubElement(
        root,
        f"{{{SVG_NS}}}g",
        {
            "id": layer_id,
            f"{{{INKSCAPE_NS}}}groupmode": "layer",
            f"{{{INKSCAPE_NS}}}label": label,
        },
    )
    return g, dash


def sheet_offset(pattern: Pattern) -> Point:
    """Translation from flat-pattern coordinates to SVG user units (mm)."""
    return (MARGIN - pattern.bbox[0], MARGIN - pattern.bbox[1])


def render_svg(cfg: Config, pattern: Pattern | None = None) -> str:
    pattern = pattern or build_pattern(cfg)
    min_x, min_y, max_x, max_y = pattern.bbox
    width = (max_x - min_x) + 2 * MARGIN
    height = (max_y - min_y) + 2 * MARGIN
    offset = sheet_offset(pattern)
    stroke_w = fmt(STROKE_WIDTH)

    root = ET.Element(
        f"{{{SVG_NS}}}svg",
        {
            "version": "1.1",
            "width": f"{fmt(width)}mm",
            "height": f"{fmt(height)}mm",
            "viewBox": f"0 0 {fmt(width)} {fmt(height)}",
            f"{{{INKSCAPE_NS}}}document-units": "mm",
        },
    )
    ET.SubElement(
        root, f"{{{SVG_NS}}}title"
    ).text = f"Pillow box {fmt(cfg.width)} x {fmt(cfg.length)} x {fmt(cfg.height)} mm"
    meta = ET.SubElement(root, f"{{{SVG_NS}}}metadata", {"id": "pillowbox-metadata"})
    cfg_el = ET.SubElement(
        meta,
        f"{{{CONFIG_NS}}}config",
        {
            "version": str(cfg.to_dict()["version"]),
            "generator": f"yanartas-pillowbox {__version__}",
        },
    )
    cfg_el.text = json.dumps(cfg.to_dict(), ensure_ascii=False)

    def stroke_attrs(dash: str | None) -> dict[str, str]:
        attrs = {
            "fill": "none",
            "stroke": LINE_COLOR,
            "stroke-width": stroke_w,
            "stroke-linejoin": "round",
        }
        if dash is None:
            attrs["stroke-linecap"] = "round"
        else:  # butt caps keep dashes and dots at their nominal lengths
            attrs["stroke-linecap"] = "butt"
            attrs["stroke-dasharray"] = dash
        return attrs

    g, dash = _layer(root, "cut")
    ET.SubElement(
        g,
        f"{{{SVG_NS}}}path",
        {
            "id": "cut-outline",
            "d": path_data(pattern.outline.segments, offset, close=True),
            **stroke_attrs(dash),
        },
    )
    for i, hole in enumerate(pattern.holes):  # FPC notches through the interior walls' folds
        ET.SubElement(
            g,
            f"{{{SVG_NS}}}path",
            {
                "id": f"cut-notch-{i + 1}",
                "d": path_data(hole.segments, offset, close=True),
                **stroke_attrs(dash),
            },
        )

    for direction in FoldDirection:
        folds = [f for f in pattern.all_folds if f.direction == direction]
        if not folds:
            continue
        g, dash = _layer(root, direction)
        for fold in folds:
            ET.SubElement(
                g,
                f"{{{SVG_NS}}}path",
                {
                    "id": f"fold-{fold.name}",
                    "d": path_data([fold.segment], offset, close=False),
                    **stroke_attrs(dash),
                },
            )

    _labels(root, cfg, pattern, offset)

    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n' + body + "\n"


def face_labels(cfg: Config, pattern: Pattern) -> list[tuple[str, Point, float]]:
    """(text, centre, font size) of the labels:

    * on the back panel, which side of the box the print side (the side facing the viewer)
      ends up on;
    * on the front panel, just inside each curved fold, which end of the box that is (front
      end: the top of the pattern, like the FPC cutout setting);
    * on every oval panel, which way its print side faces once folded. The flaps keep the
      panels' orientation; the interior walls, two folds further on, face the other way."""
    printed_out = cfg.print_side == "outside"

    def facing(outward: bool) -> str:
        return "outside" if outward == printed_out else "inside"

    out = []
    back, front = pattern.face("back-panel"), pattern.face("front-panel")
    xb, xf = (back.x0 + back.x1) / 2, (front.x0 + front.x1) / 2
    out.append((facing(True), (xb, sum(back.y_range(xb)) / 2), LABEL_SIZE))
    top, bottom = front.y_range(xf)
    out.append(("front end", (xf, top + 2 * LABEL_SIZE), LABEL_SIZE))
    out.append(("back end", (xf, bottom - 2 * LABEL_SIZE), LABEL_SIZE))
    for face in (*pattern.faces, *pattern.wall_faces):
        if face.kind not in ("flap", "wall"):
            continue
        xm = (face.x0 + face.x1) / 2
        lo, hi = face.y_range(xm)
        size = min(LABEL_SIZE, (hi - lo) / 3)
        out.append((facing(face.kind == "flap"), (xm, (lo + hi) / 2), size))
    return out


def _labels(root: ET.Element, cfg: Config, pattern: Pattern, offset: Point) -> None:
    g = ET.SubElement(
        root,
        f"{{{SVG_NS}}}g",
        {
            "id": "labels",
            f"{{{INKSCAPE_NS}}}groupmode": "layer",
            f"{{{INKSCAPE_NS}}}label": "Labels",
        },
    )
    for text, (x, y), size in face_labels(cfg, pattern):
        el = ET.SubElement(
            g,
            f"{{{SVG_NS}}}text",
            {
                "x": fmt(x + offset[0]),
                "y": fmt(y + offset[1] + 0.35 * size),  # vertically centred on the point
                "font-family": "sans-serif",
                "font-size": fmt(size),
                "text-anchor": "middle",
                "fill": LINE_COLOR,
                "stroke": "none",
            },
        )
        el.text = text


def extract_config(svg_text: str | bytes) -> Config:
    """Read the embedded configuration back out of a generated SVG."""
    if isinstance(svg_text, bytes):
        try:
            svg_text = svg_text.decode("utf-8")
        except UnicodeDecodeError:
            raise SvgImportError("The file is not a UTF-8 encoded SVG.") from None
    # Generated files never contain a DTD; refusing them rules out entity-expansion tricks.
    if "<!DOCTYPE" in svg_text or "<!ENTITY" in svg_text:
        raise SvgImportError("SVG files with a DOCTYPE are not supported.")
    try:
        root = ET.fromstring(svg_text.lstrip("﻿"))
    except ET.ParseError as exc:
        raise SvgImportError(f"The file is not valid SVG/XML ({exc}).") from None
    if root.tag != f"{{{SVG_NS}}}svg":
        raise SvgImportError("The file is not an SVG document.")

    el = root.find(f".//{{{SVG_NS}}}metadata/{{{CONFIG_NS}}}config")
    if el is None or not (el.text or "").strip():
        raise SvgImportError(
            "This SVG has no embedded yanartas-pillowbox configuration. Only files generated "
            "by yanartas-pillowbox can be imported."
        )
    try:
        data = json.loads(el.text or "")
    except json.JSONDecodeError:
        raise SvgImportError("The embedded configuration is corrupt (invalid JSON).") from None
    if not isinstance(data, dict):
        raise SvgImportError("The embedded configuration is corrupt (not a JSON object).")
    try:
        check_version(data, required=True)
        return Config.from_dict(data, require_version=True)
    except SchemaVersionError as exc:
        raise SvgImportError(f"Incompatible configuration: {exc}.") from None
    except ConfigError as exc:
        raise SvgImportError(f"The embedded configuration is invalid: {exc}") from None
