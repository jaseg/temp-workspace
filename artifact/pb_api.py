"""The web UI's JSON API, served in the browser (Pyodide) instead of by Flask.

Routes requests like yanartas_pillowbox/server.py does, to the same ``api`` functions.
Settings persistence is the caller's job (browser storage): GET /api/config gets the stored
config passed in as ``stored`` and validates it; PUT /api/config only validates.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

from yanartas_pillowbox import api
from yanartas_pillowbox.config import Config
from yanartas_pillowbox.scad import render_scad
from yanartas_pillowbox.svg import SvgImportError, extract_config

JSON = "application/json"


def _reply(status: int, data: Any, content_type: str = JSON) -> str:
    body = data if isinstance(data, str) else json.dumps(data)
    return json.dumps({"status": status, "type": content_type, "body": body})


def _route(method: str, path: str, body: str | None, stored: str | None) -> str:
    if method == "GET" and path == "/api/defaults":
        return _reply(200, api.defaults())
    if method == "GET" and path == "/api/config":
        # Like persistence.load_config: anything unusable falls back to the defaults.
        cfg = Config.defaults()
        if stored:
            with contextlib.suppress(ValueError, TypeError):
                cfg = Config.from_dict(json.loads(stored), require_version=True)
        return _reply(200, {"config": cfg.to_dict()})
    if method == "POST" and path == "/api/import":
        if not body:
            return _reply(400, {"error": "No file was uploaded."})
        try:
            cfg = extract_config(body)
        except SvgImportError as exc:
            return _reply(400, {"error": str(exc)})
        return _reply(200, {"config": cfg.to_dict()})

    try:
        data = json.loads(body or "null")
    except json.JSONDecodeError:
        data = None
    if method == "PUT" and path == "/api/config":
        return _reply(200, {"config": api.parse_config(data).to_dict(), "saved": True})
    if method == "POST" and path == "/api/render":
        return _reply(200, api.render(api.parse_config(data)))
    if method == "POST" and path == "/api/scad":
        return _reply(200, render_scad(api.parse_config(data)), "text/plain")
    if method == "POST" and path == "/api/payload":
        return _reply(200, api.payload_action(data))
    return _reply(404, {"error": f"no route {method} {path}"})


def handle(method: str, path: str, body: str | None, stored: str | None) -> str:
    try:
        return _route(method, path, body, stored)
    except api.ApiError as exc:
        return _reply(exc.status, exc.body)
