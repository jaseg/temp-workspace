"""The web UI's JSON API, apart from its transport: the Flask server (``server.py``) and the
in-browser build (``artifact/pb_api.py``) answer every request through these functions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from yanartas_pillowbox import dimensions as dims
from yanartas_pillowbox import payload, progress
from yanartas_pillowbox.config import Config, ConfigError, SchemaVersionError, field_specs_json
from yanartas_pillowbox.geometry import build_cross_section, build_model3d, build_pattern
from yanartas_pillowbox.presets import presets_json
from yanartas_pillowbox.svg import render_svg, sheet_offset


class ApiError(Exception):
    """A request the API refuses: the HTTP ``status`` and the JSON ``reply`` to answer with."""

    def __init__(self, status: int, reply: dict[str, Any]) -> None:
        super().__init__(reply.get("error"))
        self.status = status
        self.reply = reply


def parse_config(data: Any) -> Config:
    """The config of a request's JSON (``{"config": {...}}``, or the config itself)."""
    if not isinstance(data, dict):
        raise ApiError(400, {"error": "expected a JSON object", "errors": {}})
    data = data.get("config", data)
    try:
        return Config.from_dict(data)
    except SchemaVersionError as exc:
        raise ApiError(422, {"error": str(exc), "errors": {}}) from None
    except ConfigError as exc:
        raise ApiError(422, {"error": "invalid configuration", "errors": exc.errors}) from None


def defaults() -> dict[str, Any]:
    return {
        "config": Config.defaults().to_dict(),
        "fields": field_specs_json(),
        "payload_presets": presets_json(),
    }


def render(cfg: Config) -> dict[str, Any]:
    """Everything the previews show: the SVG, the 3D model, the cross-section, the derived
    values, the payload and the preview-only dimensions (never part of the exported SVG)."""
    pattern = build_pattern(cfg)
    section = build_cross_section(cfg)
    return {
        "config": cfg.to_dict(),
        "svg": render_svg(cfg, pattern),
        "model": build_model3d(cfg, pattern),
        "section": section,
        "info": pattern.info,
        "payload": payload.summary(cfg),
        "dimensions": {
            # (and where the inner end walls stand, seen on the front panel: dashed arcs)
            "pattern": [
                *dims.to_json(dims.pattern_dimensions(cfg, pattern, sheet_offset(pattern))),
                *dims.landing_outlines(cfg, pattern, sheet_offset(pattern)),
            ],
            "section": dims.to_json(dims.section_dimensions(cfg, section)),
            "model": dims.to_json(dims.model_dimensions(cfg)),
        },
    }


_progress: dict[str, Any] | None = None  # the PCB layout's latest progress event
forward: Callable[[dict[str, Any]], None] | None = None  # (also given each, when set)


def _track(event: dict[str, Any]) -> None:
    global _progress
    _progress = event
    if forward is not None:
        forward(event)


def layout_progress() -> dict[str, Any]:
    """``{progress}``: how far the PCB layout in progress (or the last) has got (``progress``'s
    event; null before any)."""
    return {"progress": _progress}


_last: dict[str, Any] = {}  # the last PCB layout (and its files): {config, layout, zip}


def _pcb_layout(cfg: Config) -> tuple[Any, Any]:
    """The PCB layout (``pcb``: heavy dependencies, imported on demand). The last one is
    kept: the files of the layout the previews just showed are made from it, not laid out
    again (minutes, for the curve's mesh)."""
    try:
        from yanartas_pillowbox import pcb
    except ImportError as exc:  # (shapely or gerbonara missing)
        raise ApiError(
            501, {"error": f"PCB layout unavailable here: {exc}", "errors": {}}
        ) from None
    if _last.get("config") == cfg:
        return pcb, _last["layout"]
    global _progress
    _progress = None
    progress.begin()
    try:
        with progress.listening(_track):
            result = pcb.layout(cfg)
    except pcb.PcbError as exc:
        raise ApiError(422, {"error": str(exc), "errors": {}}) from None
    except progress.Cancelled:
        raise ApiError(409, {"error": "the mesh layout was cancelled", "cancelled": True,
                             "errors": {}}) from None  # fmt: skip
    _last.clear()
    _last.update(config=cfg, layout=result)
    return pcb, result


def cancel_layout() -> dict[str, Any]:
    """Stop the PCB layout under way (its request then answers 409, ``cancelled``)."""
    progress.cancel()
    return {"cancelled": True}


def pcb_preview(cfg: Config) -> dict[str, Any]:
    """The PCB layout's copper for the previews (``pcb.preview_json``), in the 2D view's
    sheet coordinates too (``offset``)."""
    pcb, layout = _pcb_layout(cfg)
    return pcb.preview_json(layout, sheet_offset(build_pattern(cfg)))


def pcb_files(cfg: Config) -> bytes:
    """The PCB layout's KiCad, Gerber and SVG files, zipped."""
    pcb, layout = _pcb_layout(cfg)
    if _last.get("zip") is None:
        _last["zip"] = pcb.export_zip(layout)
    return _last["zip"]


def payload_action(request: Any) -> dict[str, Any]:
    """``{config, action: "fit" | "maximize", field?}`` -> ``{config}`` (not saved)."""
    cfg = parse_config(request)
    try:
        if request.get("action") == "fit":
            out = payload.fit_box(cfg)
        elif request.get("action") == "maximize":
            out = payload.maximize(cfg, str(request.get("field")))
        else:
            raise ApiError(400, {"error": "unknown action", "errors": {}})
    except payload.PayloadError as exc:
        raise ApiError(422, {"error": str(exc), "errors": {exc.field: str(exc)}}) from None
    return {"config": out.to_dict()}
