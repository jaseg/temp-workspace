"""Serialize a pillow box pattern to laser-ready SVG, and read the config back out of one.

Conventions (see README): 1 user unit = 1 mm, canvas = pattern bbox + ``MARGIN`` on every
side, one closed ``<path>`` for the cut outline, solid open paths for folds, every style as a
plain presentation attribute, one Inkscape layer per line category, and the full config as
JSON in ``<metadata>``.
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
    FoldCategory,
    Line,
    Pattern,
    Point,
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

# Layer id, Inkscape label, config color attribute.
LAYERS: dict[str, tuple[str, str, str]] = {
    "cut": ("cut", "Cut", "color_cut"),
    FoldCategory.STRAIGHT: ("fold-straight", "Fold - straight", "color_fold_straight"),
    FoldCategory.CURVED: ("fold-curved", "Fold - curved flaps", "color_fold_curved"),
    FoldCategory.GLUE: ("fold-glue", "Fold - glue tab", "color_fold_glue"),
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
        if isinstance(seg, Line):
            parts.append(f"L {pt(seg.end)}")
        elif isinstance(seg, Arc):
            r = fmt(seg.radius)
            parts.append(f"A {r},{r} 0 {int(seg.large_arc)},{int(seg.sweep_flag)} {pt(seg.end)}")
    if close:
        parts.append("Z")
    return " ".join(parts)


def _layer(root: ET.Element, key: str, cfg: Config) -> tuple[ET.Element, str]:
    layer_id, label, color_attr = LAYERS[key]
    g = ET.SubElement(
        root,
        f"{{{SVG_NS}}}g",
        {
            "id": layer_id,
            f"{{{INKSCAPE_NS}}}groupmode": "layer",
            f"{{{INKSCAPE_NS}}}label": label,
        },
    )
    return g, getattr(cfg, color_attr)


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

    def stroke_attrs(color: str) -> dict[str, str]:
        return {
            "fill": "none",
            "stroke": color,
            "stroke-width": stroke_w,
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
        }

    g, color = _layer(root, "cut", cfg)
    ET.SubElement(
        g,
        f"{{{SVG_NS}}}path",
        {
            "id": "cut-outline",
            "d": path_data(pattern.outline.segments, offset, close=True),
            **stroke_attrs(color),
        },
    )

    for category in FoldCategory:
        folds = [f for f in pattern.folds if f.category == category]
        g, color = _layer(root, category, cfg)
        for fold in folds:
            ET.SubElement(
                g,
                f"{{{SVG_NS}}}path",
                {
                    "id": f"fold-{fold.name}",
                    "d": path_data([fold.segment], offset, close=False),
                    **stroke_attrs(color),
                },
            )

    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n' + body + "\n"


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
