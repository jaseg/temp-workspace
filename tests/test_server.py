import io
import json
import logging

import pytest

from yanartas_pillowbox.config import Config
from yanartas_pillowbox.persistence import load_config, save_config
from yanartas_pillowbox.server import create_app
from yanartas_pillowbox.svg import render_svg


@pytest.fixture
def settings(tmp_path):
    return tmp_path / "yanartas-pillowbox.json"


@pytest.fixture
def client(settings):
    return create_app(settings).test_client()


def test_index_and_assets(client):
    r = client.get("/")
    assert r.status_code == 200 and b"<pb-preview2d" in r.data
    for asset in (
        "/static/js/app.js",
        "/static/css/app.css",
        "/static/vendor/three/three.module.min.js",
        "/static/vendor/three/OrbitControls.js",
    ):
        assert client.get(asset).status_code == 200, asset


def test_rejects_foreign_host(client):
    assert client.get("/api/config", headers={"Host": "evil.example"}).status_code == 403


def test_defaults(client):
    data = client.get("/api/defaults").get_json()
    assert data["config"] == Config.defaults().to_dict()
    assert {f["name"] for f in data["fields"]} == set(data["config"]) - {"version"}


def test_render(client):
    r = client.post("/api/render", json={"config": Config.defaults().to_dict()})
    assert r.status_code == 200
    data = r.get_json()
    assert data["svg"].startswith("<?xml")
    assert data["model"]["parts"]
    assert data["section"]["front"] and data["section"]["depth"] == 20
    assert data["info"]["box_depth"] == 20


def test_render_validation_errors(client):
    r = client.post("/api/render", json={"config": {"width": -1, "color_cut": "x"}})
    assert r.status_code == 422
    assert set(r.get_json()["errors"]) >= {"width", "color_cut"}


def test_render_requires_json(client):
    assert client.post("/api/render", data="width=5").status_code == 415


def test_put_config_persists(client, settings):
    cfg = Config.defaults().with_values(width=70, label=True)
    r = client.put("/api/config", json={"config": cfg.to_dict()})
    assert r.status_code == 200
    assert json.loads(settings.read_text())["width"] == 70
    assert client.get("/api/config").get_json()["config"] == cfg.to_dict()
    # A new app instance (i.e. a restart) restores it.
    restarted = create_app(settings).test_client()
    assert restarted.get("/api/config").get_json()["config"] == cfg.to_dict()


def test_put_invalid_config_not_saved(client, settings):
    r = client.put("/api/config", json={"config": {"width": "x"}})
    assert r.status_code == 422
    assert not settings.exists()


def test_import_raw_and_multipart(client):
    cfg = Config.defaults().with_values(width=52.5, thumb_notch=True, color_cut="#00FFFF")
    svg = render_svg(cfg)
    r = client.post("/api/import", data=svg, content_type="image/svg+xml")
    assert r.status_code == 200 and r.get_json()["config"] == cfg.to_dict()
    r = client.post(
        "/api/import",
        data={"file": (io.BytesIO(svg.encode()), "box.svg")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200 and r.get_json()["config"] == cfg.to_dict()


def test_import_errors(client):
    r = client.post(
        "/api/import",
        data='<svg xmlns="http://www.w3.org/2000/svg"/>',
        content_type="image/svg+xml",
    )
    assert r.status_code == 400 and "no embedded" in r.get_json()["error"]
    assert client.post("/api/import", data=b"").status_code == 400


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "[]",
        '{"width": 50}',
        '{"version": 99, "width": 50}',
        '{"version": 1, "width": -3}',
        "\x00\x01",
    ],
)
def test_bad_settings_file_falls_back(settings, content, caplog):
    settings.write_text(content)
    with caplog.at_level(logging.WARNING):
        assert load_config(settings) == Config.defaults()
        client = create_app(settings).test_client()
    assert client.get("/api/config").get_json()["config"] == Config.defaults().to_dict()
    assert caplog.records


def test_save_load_round_trip(settings):
    cfg = Config.defaults().with_values(label=True, label_text="ünïcødé")
    save_config(settings, cfg)
    assert load_config(settings) == cfg
