"""Local Flask server: the web UI plus a small JSON API (see ``api``)."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_from_directory

from yanartas_pillowbox import api
from yanartas_pillowbox.persistence import load_config, save_config
from yanartas_pillowbox.scad import render_scad
from yanartas_pillowbox.svg import SvgImportError, extract_config

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}


class State:
    def __init__(self, settings_path: Path) -> None:
        self.settings_path = settings_path
        self.lock = threading.Lock()
        self.config = load_config(settings_path)


def _json_route(view: Callable[[Any], Any]) -> Callable[[], Any]:
    """A JSON route: the view gets the parsed request JSON; ``ApiError`` becomes its reply."""

    @wraps(view)
    def wrapper() -> Any:
        if not request.is_json:
            return jsonify(error="expected application/json"), 415
        try:
            return view(request.get_json(silent=True))
        except api.ApiError as exc:
            return jsonify(exc.reply), exc.status

    return wrapper


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

    @app.get("/")
    def index() -> Response:
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/api/defaults")
    def defaults() -> Response:
        return jsonify(api.defaults())

    @app.get("/api/config")
    def get_config() -> Response:
        with state.lock:
            return jsonify(config=state.config.to_dict())

    @app.put("/api/config")
    @_json_route
    def put_config(data: Any) -> Any:
        cfg = api.parse_config(data)
        with state.lock:
            state.config = cfg
            try:
                save_config(state.settings_path, cfg)
            except OSError as exc:
                log.warning("Could not save %s: %s", state.settings_path, exc)
                return jsonify(config=cfg.to_dict(), saved=False, error=str(exc))
        return jsonify(config=cfg.to_dict(), saved=True)

    @app.post("/api/render")
    @_json_route
    def render(data: Any) -> Any:
        return jsonify(api.render(api.parse_config(data)))

    @app.post("/api/scad")
    @_json_route
    def scad(data: Any) -> Any:
        """``{config}`` -> OpenSCAD source of the box's interior."""
        return Response(render_scad(api.parse_config(data)), mimetype="application/x-openscad")

    @app.post("/api/pcb")
    @_json_route
    def pcb_preview(data: Any) -> Any:
        """``{config}`` -> the PCB layout's copper for the previews."""
        return jsonify(api.pcb_preview(api.parse_config(data)))

    @app.get("/api/progress")
    def layout_progress() -> Response:
        """How far the PCB layout in progress has got (polled while it runs)."""
        return jsonify(api.layout_progress())

    @app.post("/api/pcb/files")
    @_json_route
    def pcb_files(data: Any) -> Any:
        """``{config}`` -> zip of the PCB layout's KiCad, Gerber and SVG files."""
        return Response(api.pcb_files(api.parse_config(data)), mimetype="application/zip")

    @app.post("/api/payload")
    @_json_route
    def payload_action(data: Any) -> Any:
        return jsonify(api.payload_action(data))

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
