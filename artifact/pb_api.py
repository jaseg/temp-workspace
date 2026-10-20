"""The web UI's JSON API, served in the browser (Pyodide) instead of by Flask.

Routes requests like yanartas_pillowbox/server.py does, to the same ``api`` functions.
Settings persistence is the caller's job (browser storage): GET /api/config gets the stored
config passed in as ``stored`` and validates it; PUT /api/config only validates. Binary
replies (the PCB files' zip) travel base64-encoded (``encoding``).
"""

from __future__ import annotations

import base64
import contextlib
import json
from typing import Any

from yanartas_pillowbox import api
from yanartas_pillowbox.config import Config
from yanartas_pillowbox.scad import render_scad
from yanartas_pillowbox.svg import SvgImportError, extract_config

JSON = "application/json"

try:  # (in the web worker: each progress event posted to the page, which shows the bar)
    import js  # type: ignore[import-not-found]

    def _post(event: dict[str, Any]) -> None:
        js.postMessage(js.JSON.parse(json.dumps({"progress": event})))

    api.forward = _post
except ImportError:  # (natively, under the tests)
    pass


def _reply(status: int, data: Any, content_type: str = JSON) -> str:
    if isinstance(data, bytes):
        content = base64.b64encode(data).decode()
        return json.dumps(
            {"status": status, "type": content_type, "content": content, "encoding": "base64"}
        )
    content = data if isinstance(data, str) else json.dumps(data)
    return json.dumps({"status": status, "type": content_type, "content": content})


def _route(method: str, path: str, content: str | None, stored: str | None) -> str:
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
        if not content:
            return _reply(400, {"error": "No file was uploaded."})
        try:
            cfg = extract_config(content)
        except SvgImportError as exc:
            return _reply(400, {"error": str(exc)})
        return _reply(200, {"config": cfg.to_dict()})

    try:
        data = json.loads(content or "null")
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
    if method == "GET" and path == "/api/progress":  # (pyshim.js answers it while busy)
        return _reply(200, api.layout_progress())
    if method == "POST" and path == "/api/pcb":
        return _reply(200, api.pcb_preview(api.parse_config(data)))
    if method == "POST" and path == "/api/pcb/files":
        return _reply(200, api.pcb_files(api.parse_config(data)), "application/zip")
    return _reply(404, {"error": f"no route {method} {path}"})


def serve(method: str, path: str, content: str | None, stored: str | None) -> str:
    try:
        return _route(method, path, content, stored)
    except api.ApiError as exc:
        return _reply(exc.status, exc.reply)
