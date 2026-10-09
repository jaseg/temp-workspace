import json
import math
import re
import shutil
import subprocess

import pytest
from helpers import self_intersections

from yanartas_pillowbox import payload
from yanartas_pillowbox.config import Config
from yanartas_pillowbox.geometry import _interior, wall_layout
from yanartas_pillowbox.scad import render_scad

D = Config.defaults()
CONFIGS = {
    "default": D,
    "no-walls": D.with_values(interior_walls=False),
    "thick": D.with_values(thickness=1.5, width=60, height=24),
    "fpc": D.with_values(fpc_cutout="both"),
}


@pytest.fixture(params=list(CONFIGS), ids=list(CONFIGS))
def cfg(request):
    return CONFIGS[request.param]


def polygons(src: str) -> dict[str, list[tuple[float, float]]]:
    """The polygon of each ``module name() { polygon([...]); }`` in the source."""
    out = {}
    for name, body in re.findall(r"module (\w+)\(\) \{\s*polygon\(\[(.*?)\]\);", src, re.S):
        out[name] = [(float(x), float(y)) for x, y in re.findall(r"\[(\S+), (\S+)\]", body)]
    return out


def inside(poly, p) -> bool:
    x, y = p
    hit = False
    for (ax, ay), (bx, by) in zip(poly, (*poly[1:], poly[0]), strict=True):
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            hit = not hit
    return hit


def y_bounds(poly, x):
    """Y values where the vertical line at ``x`` crosses the polygon."""
    ys = []
    for (ax, ay), (bx, by) in zip(poly, (*poly[1:], poly[0]), strict=True):
        if (ax - x) * (bx - x) < 0:
            ys.append(ay + (by - ay) * (x - ax) / (bx - ax))
    return sorted(ys)


def test_source_structure(cfg):
    src = render_scad(cfg)
    polys = polygons(src)
    walls = cfg.interior_walls
    expected = {"main_section", "main_plan"} | ({"end_section", "end_plan"} if walls else set())
    assert set(polys) == expected
    for poly in polys.values():
        assert not self_intersections(poly)
    assert 'color("SkyBlue") main_space();' in src
    assert ('color("Orchid") end_spaces();' in src) == walls
    assert "%payload();" in src
    config = json.loads(re.search(r"^// config: (.*)$", src, re.M)[1])
    assert Config.from_dict(config) == cfg


# The curves are sampled as polygons, a few micrometres inside the true surfaces.
CHORD = 0.01


def test_main_space_is_the_interior(cfg):
    """Section: the panels' inner surfaces. Plan, in the middle: the interior length, less
    the interior walls' offset and thickness at each end."""
    polys = polygons(render_scad(cfg))
    section = polys["main_section"]
    exact = _interior(cfg.body, 1)
    assert min(x for x, _ in section) == pytest.approx(min(x for x, _ in exact), abs=1e-4)
    assert max(x for x, _ in section) == pytest.approx(max(x for x, _ in exact), abs=1e-4)
    assert y_bounds(section, 0) == pytest.approx([-cfg.height / 2, cfg.height / 2], abs=CHORD)
    half = cfg.length / 2
    if cfg.interior_walls:
        half -= cfg.interior_wall_offset + cfg.thickness
    assert y_bounds(polys["main_plan"], 0) == pytest.approx([-half, half], abs=CHORD)


def test_end_space_lies_between_flap_and_interior_wall(cfg):
    if not cfg.interior_walls:
        pytest.skip("no interior walls")
    polys = polygons(render_scad(cfg))
    t, half = cfg.thickness, cfg.length / 2
    # In the middle: the offset (the clear gap) along the box, under the bridge across it.
    assert y_bounds(polys["end_plan"], 0) == pytest.approx(
        [half - cfg.interior_wall_offset, half], abs=CHORD
    )
    assert y_bounds(polys["end_section"], 0) == pytest.approx(
        [-cfg.height / 2, cfg.height / 2 - t], abs=CHORD
    )
    # Across the walls' span, the interior wall's thickness separates it from the main space
    # (measured along Y: t / cos of the wall's angle).
    layout = wall_layout(cfg)
    xs = sorted(cfg.body.back_point(u)[0] for u in (layout.ua, layout.ub))
    for i in range(1, 20):
        x, e = xs[0] + (xs[1] - xs[0]) * i / 20, 1e-3
        end = polys["end_plan"]
        k = (y_bounds(end, x + e)[0] - y_bounds(end, x - e)[0]) / (2 * e)
        gap = y_bounds(end, x)[0] - y_bounds(polys["main_plan"], x)[-1]
        assert gap == pytest.approx(t * math.hypot(1, k), rel=0.02), x


def test_payload_fits_in_main_space(cfg):
    if not payload.fits(cfg):
        pytest.skip("payload does not fit this box")
    polys = polygons(render_scad(cfg))
    w, d, h = cfg.payload_width / 2, cfg.payload_depth / 2, cfg.payload_height / 2
    for sx in (-1, 1):
        for sy in (-1, 1):
            assert inside(polys["main_plan"], (sx * w, sy * d))
            assert inside(polys["main_section"], (sx * w, sy * h))


def test_api_scad(tmp_path):
    from yanartas_pillowbox.server import create_app

    client = create_app(tmp_path / "s.json").test_client()
    r = client.post("/api/scad", json={"config": D.to_dict()})
    assert r.status_code == 200 and r.mimetype == "application/x-openscad"
    assert r.get_data(as_text=True) == render_scad(D)
    assert client.post("/api/scad", json={"config": {"width": -1}}).status_code == 422


@pytest.mark.skipif(not shutil.which("openscad"), reason="OpenSCAD not installed")
def test_openscad_renders(tmp_path):
    """OpenSCAD accepts the source and builds a closed solid of it."""
    src = tmp_path / "box.scad"
    src.write_text(render_scad(D))
    out = tmp_path / "box.off"
    subprocess.run(["openscad", "-o", str(out), str(src)], check=True, capture_output=True)
    assert out.read_text().startswith("OFF")
