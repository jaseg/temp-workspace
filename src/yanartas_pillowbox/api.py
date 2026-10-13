"""The web UI's JSON API, apart from its transport: the Flask server (``server.py``) and the
in-browser build (``artifact/pb_api.py``) answer every request through these functions."""

from __future__ import annotations

from typing import Any

from yanartas_pillowbox import dimensions as dims
from yanartas_pillowbox import payload
from yanartas_pillowbox.config import Config, ConfigError, SchemaVersionError, field_specs_json
from yanartas_pillowbox.geometry import build_cross_section, build_model3d, build_pattern
from yanartas_pillowbox.presets import presets_json
from yanartas_pillowbox.svg import render_svg, sheet_offset


class ApiError(Exception):
    """A request the API refuses: the HTTP ``status`` and the JSON ``body`` to answer with."""

    def __init__(self, status: int, body: dict[str, Any]) -> None:
        super().__init__(body.get("error"))
        self.status = status
        self.body = body


def parse_config(data: Any) -> Config:
    """The config of a request body (``{"config": {...}}``, or the config itself)."""
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
            "pattern": dims.to_json(dims.pattern_dimensions(cfg, pattern, sheet_offset(pattern))),
            "section": dims.to_json(dims.section_dimensions(cfg, section)),
            "model": dims.to_json(dims.model_dimensions(cfg)),
        },
    }


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
