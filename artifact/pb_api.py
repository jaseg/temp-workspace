"""The web UI's JSON API, served in the browser (Pyodide) instead of by Flask.

Mirrors yanartas_pillowbox/server.py route for route, calling the same modules. Settings
persistence is the caller's job (browser storage): GET /api/config gets the stored config
passed in as ``stored`` and validates it; PUT /api/config only validates.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

from yanartas_pillowbox import dimensions as dims
from yanartas_pillowbox import payload
from yanartas_pillowbox.config import Config, ConfigError, SchemaVersionError, field_specs_json
from yanartas_pillowbox.geometry import build_cross_section, build_model3d, build_pattern
from yanartas_pillowbox.presets import presets_json
from yanartas_pillowbox.scad import render_scad
from yanartas_pillowbox.svg import SvgImportError, extract_config, render_svg, sheet_offset

JSON = "application/json"


def _reply(status: int, data: Any, content_type: str = JSON) -> str:
    body = data if isinstance(data, str) else json.dumps(data)
    return json.dumps({"status": status, "type": content_type, "body": body})


def _config(body: str | None) -> Config | str:
    """The request's config, or a ready error reply."""
    try:
        data = json.loads(body or "null")
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        return _reply(400, {"error": "expected a JSON object", "errors": {}})
    data = data.get("config", data)
    try:
        return Config.from_dict(data)
    except SchemaVersionError as exc:
        return _reply(422, {"error": str(exc), "errors": {}})
    except ConfigError as exc:
        return _reply(422, {"error": "invalid configuration", "errors": exc.errors})


def handle(method: str, path: str, body: str | None, stored: str | None) -> str:
    if method == "GET" and path == "/api/defaults":
        return _reply(
            200,
            {
                "config": Config.defaults().to_dict(),
                "fields": field_specs_json(),
                "payload_presets": presets_json(),
            },
        )
    if method == "GET" and path == "/api/config":
        # Like persistence.load_config: anything unusable falls back to the defaults.
        cfg = Config.defaults()
        if stored:
            with contextlib.suppress(ValueError, TypeError):
                cfg = Config.from_dict(json.loads(stored), require_version=True)
        return _reply(200, {"config": cfg.to_dict()})
    if method == "PUT" and path == "/api/config":
        cfg = _config(body)
        if not isinstance(cfg, Config):
            return cfg
        return _reply(200, {"config": cfg.to_dict(), "saved": True})
    if method == "POST" and path == "/api/render":
        cfg = _config(body)
        if not isinstance(cfg, Config):
            return cfg
        pattern = build_pattern(cfg)
        section = build_cross_section(cfg)
        return _reply(
            200,
            {
                "config": cfg.to_dict(),
                "svg": render_svg(cfg, pattern),
                "model": build_model3d(cfg, pattern),
                "section": section,
                "info": pattern.info,
                "payload": payload.summary(cfg),
                "dimensions": {
                    "pattern": dims.to_json(
                        dims.pattern_dimensions(cfg, pattern, sheet_offset(pattern))
                    ),
                    "section": dims.to_json(dims.section_dimensions(cfg, section)),
                    "model": dims.to_json(dims.model_dimensions(cfg)),
                },
            },
        )
    if method == "POST" and path == "/api/scad":
        cfg = _config(body)
        if not isinstance(cfg, Config):
            return cfg
        return _reply(200, render_scad(cfg), "text/plain")
    if method == "POST" and path == "/api/payload":
        cfg = _config(body)
        if not isinstance(cfg, Config):
            return cfg
        request = json.loads(body or "{}")
        try:
            if request.get("action") == "fit":
                out = payload.fit_box(cfg)
            elif request.get("action") == "maximize":
                out = payload.maximize(cfg, str(request.get("field")))
            else:
                return _reply(400, {"error": "unknown action", "errors": {}})
        except payload.PayloadError as exc:
            return _reply(422, {"error": str(exc), "errors": {exc.field: str(exc)}})
        return _reply(200, {"config": out.to_dict()})
    if method == "POST" and path == "/api/import":
        if not body:
            return _reply(400, {"error": "No file was uploaded."})
        try:
            cfg = extract_config(body)
        except SvgImportError as exc:
            return _reply(400, {"error": str(exc)})
        return _reply(200, {"config": cfg.to_dict()})
    return _reply(404, {"error": f"no route {method} {path}"})
