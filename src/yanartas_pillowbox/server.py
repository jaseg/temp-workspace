"""Local Flask server: the web UI plus a small JSON API."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_from_directory

from yanartas_pillowbox import dimensions as dims
from yanartas_pillowbox import payload
from yanartas_pillowbox.config import Config, ConfigError, SchemaVersionError, field_specs_json
from yanartas_pillowbox.geometry import build_cross_section, build_model3d, build_pattern
from yanartas_pillowbox.persistence import load_config, save_config
from yanartas_pillowbox.svg import SvgImportError, extract_config, render_svg, sheet_offset

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}


class State:
    def __init__(self, settings_path: Path) -> None:
        self.settings_path = settings_path
        self.lock = threading.Lock()
        self.config = load_config(settings_path)


def create_app(settings_path: Path) -> Flask:
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
    state = State(settings_path)
    app.extensions["pillowbox"] = state

    @app.before_request
    def _check_host() -> Any:
        # Guard against DNS rebinding: only answer requests addressed to the loopback host.
        host = (request.host or "").rsplit(":", 1)[0].strip("[]")
        if host not in ALLOWED_HOSTS:
            return jsonify(error="forbidden host"), 403
        return None

    @app.after_request
    def _no_cache(resp: Response) -> Response:
        resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    def parse_config_body() -> Config | tuple[Response, int]:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="expected a JSON object", errors={}), 400
        data = data.get("config", data)
        try:
            return Config.from_dict(data)
        except SchemaVersionError as exc:
            return jsonify(error=str(exc), errors={}), 422
        except ConfigError as exc:
            return jsonify(error="invalid configuration", errors=exc.errors), 422

    @app.get("/")
    def index() -> Response:
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/api/defaults")
    def defaults() -> Response:
        return jsonify(config=Config.defaults().to_dict(), fields=field_specs_json())

    @app.get("/api/config")
    def get_config() -> Response:
        with state.lock:
            return jsonify(config=state.config.to_dict())

    @app.put("/api/config")
    def put_config() -> Any:
        if not request.is_json:
            return jsonify(error="expected application/json"), 415
        cfg = parse_config_body()
        if not isinstance(cfg, Config):
            return cfg
        with state.lock:
            state.config = cfg
            try:
                save_config(state.settings_path, cfg)
            except OSError as exc:
                log.warning("Could not save %s: %s", state.settings_path, exc)
                return jsonify(config=cfg.to_dict(), saved=False, error=str(exc))
        return jsonify(config=cfg.to_dict(), saved=True)

    @app.post("/api/render")
    def render() -> Any:
        if not request.is_json:
            return jsonify(error="expected application/json"), 415
        cfg = parse_config_body()
        if not isinstance(cfg, Config):
            return cfg
        pattern = build_pattern(cfg)
        section = build_cross_section(cfg)
        return jsonify(
            config=cfg.to_dict(),
            svg=render_svg(cfg, pattern),
            model=build_model3d(cfg, pattern),
            section=section,
            info=pattern.info,
            payload=payload.summary(cfg),
            # Preview-only dimension annotations (never part of the exported SVG).
            dimensions={
                "pattern": dims.to_json(
                    dims.pattern_dimensions(cfg, pattern, sheet_offset(pattern))
                ),
                "section": dims.to_json(dims.section_dimensions(cfg, section)),
                "model": dims.to_json(dims.model_dimensions(cfg)),
            },
        )

    @app.post("/api/payload")
    def payload_action() -> Any:
        """``{config, action: "fit" | "maximize", field?}`` -> ``{config}`` (not saved)."""
        if not request.is_json:
            return jsonify(error="expected application/json"), 415
        body = request.get_json(silent=True) or {}
        cfg = parse_config_body()
        if not isinstance(cfg, Config):
            return cfg
        try:
            if body.get("action") == "fit":
                out = payload.fit_box(cfg)
            elif body.get("action") == "maximize":
                out = payload.maximize(cfg, str(body.get("field")))
            else:
                return jsonify(error="unknown action", errors={}), 400
        except payload.PayloadError as exc:
            return jsonify(error=str(exc), errors={exc.field: str(exc)}), 422
        return jsonify(config=out.to_dict())

    @app.post("/api/import")
    def import_svg() -> Any:
        upload = request.files.get("file")
        raw = upload.read() if upload is not None else request.get_data()
        if not raw:
            return jsonify(error="No file was uploaded."), 400
        try:
            cfg = extract_config(raw)
        except SvgImportError as exc:
            return jsonify(error=str(exc)), 400
        return jsonify(config=cfg.to_dict())

    return app
