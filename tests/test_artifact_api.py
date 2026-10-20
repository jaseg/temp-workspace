"""The in-browser API (artifact/pb_api.py) answers like the Flask server."""

import importlib.util
import io
import json
from pathlib import Path

import pytest

from yanartas_pillowbox.config import Config
from yanartas_pillowbox.server import create_app
from yanartas_pillowbox.svg import render_svg

_spec = importlib.util.spec_from_file_location(
    "pb_api", Path(__file__).parents[1] / "artifact/pb_api.py"
)
pb_api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pb_api)


@pytest.fixture
def client(tmp_path):
    return create_app(tmp_path / "s.json").test_client()


def call(method, path, content=None, stored=None):
    reply = json.loads(pb_api.serve(method, path, content, stored))
    return reply["status"], reply["content"]


def same(flask_response, status, content):
    assert flask_response.status_code == status
    if flask_response.mimetype == "application/json":
        assert flask_response.get_json() == json.loads(content)
    else:
        assert flask_response.get_data(as_text=True) == content


@pytest.mark.parametrize(
    ("method", "path", "data"),
    [
        ("GET", "/api/defaults", None),
        ("GET", "/api/config", None),
        ("PUT", "/api/config", {"config": {"payload_width": 30}}),
        ("PUT", "/api/config", {"config": {"payload_width": -1}}),
        ("PUT", "/api/config", {"config": {"version": 1}}),
        ("POST", "/api/render", {"config": {}}),
        ("POST", "/api/render", {"config": {"material_thickness": 0.5}}),
        ("POST", "/api/scad", {"config": {}}),
        ("POST", "/api/payload", {"config": {}, "action": "fit"}),
        ("POST", "/api/payload", {"config": {}, "action": "maximize", "field": "payload_width"}),
        ("POST", "/api/payload", {"config": {}, "action": "bogus"}),
        ("POST", "/api/pcb", {"config": {"mesh_traces": 2}}),
        ("POST", "/api/pcb", {"config": {"fpc_cable": "none"}}),
        ("GET", "/api/progress", None),
    ],
)
def test_routes_match_server(client, method, path, data):
    content = None if data is None else json.dumps(data)
    expected = client.open(path, method=method, data=content, content_type="application/json")
    same(expected, *call(method, path, content))


def test_import_matches_server(client):
    svg = render_svg(Config.from_dict({"payload_width": 31}))
    expected = client.post(
        "/api/import",
        data={"file": (io.BytesIO(svg.encode()), "box.svg")},
        content_type="multipart/form-data",
    )
    same(expected, *call("POST", "/api/import", svg))
    assert call("POST", "/api/import", "")[0] == 400


def test_stored_config():
    cfg = Config.from_dict({"payload_width": 33}).to_dict()
    assert json.loads(call("GET", "/api/config", stored=json.dumps(cfg))[1])["config"] == cfg
    for bad in ("{", "[]", json.dumps({**cfg, "version": 1})):
        got = json.loads(call("GET", "/api/config", stored=bad)[1])["config"]
        assert got == Config.defaults().to_dict()


def test_pcb_files_travel_base64(client):
    """The PCB files' zip: binary, so base64-encoded in the reply (pyshim.js decodes it)."""
    import base64
    import zipfile

    content = json.dumps({"config": {"mesh_traces": 2}})
    reply = json.loads(pb_api.serve("POST", "/api/pcb/files", content, None))
    assert reply["status"] == 200 and reply["type"] == "application/zip"
    assert reply["encoding"] == "base64"
    names = zipfile.ZipFile(io.BytesIO(base64.b64decode(reply["content"]))).namelist()
    expected = client.post("/api/pcb/files", data=content, content_type="application/json")
    assert names == zipfile.ZipFile(io.BytesIO(expected.data)).namelist()


def test_the_build_ships_every_module_the_api_imports():
    """Each of the package's modules a shipped one imports is shipped too (else the browser
    fails at its first use, as the PCB layout's partitions once did)."""
    import ast

    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location("build", root / "artifact/build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    shipped = set(build.PY_MODULES)
    pkg = root / "src/yanartas_pillowbox"
    for name in shipped:
        tree = ast.parse((pkg / f"{name}.py").read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "yanartas_pillowbox":
                needed = {a.name for a in node.names if (pkg / f"{a.name}.py").exists()}
            elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "yanartas_pillowbox."
            ):
                needed = {node.module.split(".")[1]}
            else:
                continue
            assert needed <= shipped, (name, needed - shipped)
