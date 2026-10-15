import json
import math
import re
import shutil
import subprocess

import pytest
from helpers import self_intersections

from yanartas_pillowbox import payload
from yanartas_pillowbox.config import Config
from yanartas_pillowbox.geometry import _interior, lid_layout
from yanartas_pillowbox.scad import render_scad

D = Config.defaults()
CONFIGS = {
    "default": D,
    "stacked": D.with_values(end_wall_gap=0),
    "wide-gap": D.with_values(end_wall_gap=30, length=70, payload_depth=50),
    "thick": D.with_values(thickness=1.5, width=60, height=24, lid_offset=1.5, fpc_cable="none"),
    "fpc": D.with_values(fpc_cutout="both", fpc_cable="none"),
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
    walls = cfg.end_wall_gap > 0
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
    """Section: the panels' inner surfaces. Plan, in the middle: the interior length."""
    polys = polygons(render_scad(cfg))
    section = polys["main_section"]
    exact = _interior(cfg.body, 1)
    assert min(x for x, _ in section) == pytest.approx(min(x for x, _ in exact), abs=1e-4)
    assert max(x for x, _ in section) == pytest.approx(max(x for x, _ in exact), abs=1e-4)
    assert y_bounds(section, 0) == pytest.approx([-cfg.height / 2, cfg.height / 2], abs=CHORD)
    half = cfg.length / 2
    assert y_bounds(polys["main_plan"], 0) == pytest.approx([-half, half], abs=CHORD)


def test_end_space_lies_between_the_end_walls(cfg):
    """In plan, between the inner wall's outer surface and the outer wall's inner surface:
    the gap along the box in the middle, a thickness beyond the main space everywhere. In
    section, from the lid's inner surface up to the front panel's inner surface, across the
    lid's width."""
    if cfg.end_wall_gap == 0:
        pytest.skip("walls stacked: no end space")
    polys = polygons(render_scad(cfg))
    t, half, e = cfg.thickness, cfg.length / 2, cfg.end_wall_gap
    end, main = polys["end_plan"], polys["main_plan"]
    assert y_bounds(end, 0) == pytest.approx([half + t, half + t + e], abs=CHORD)
    body, lid = cfg.body, lid_layout(cfg)
    # The lid's inner surface, in the middle: half a thickness inside its mid-surface, which
    # lies the front panel's sagitta below the lid level.
    lid_inner = body.z_shift + lid.level - body.front.sagitta + t / 2
    assert y_bounds(polys["end_section"], 0) == pytest.approx(
        [lid_inner, cfg.height / 2], abs=CHORD
    )
    assert lid_inner <= -cfg.height / 2 - t + 1e-9  # outside the back panel
    # Across the widened end section, past the body's sides, to where the lid's and the
    # front panel's inner surfaces meet (the section's ends are single points).
    section = polys["end_section"]
    xs = sorted(x for x, _ in section)
    edges = sorted(body.front_point(u)[0] for u in (0.0, body.front.width))
    assert xs[0] < edges[0] and xs[-1] > edges[1]
    for x in (xs[0], xs[-1]):
        assert len([q for q in section if q[0] == x]) == 1
    # Across the box, the inner wall's thickness separates the end space from the main space
    # (measured along Y: t / cos of the wall's angle; away from the tight corners, where this
    # first-order estimate no longer holds for thick material).
    lo, hi = body.inner_glue[0], body.inner_fold[0]
    for i in range(2, 19):
        x, d = lo + (hi - lo) * i / 20, 1e-3
        k = (y_bounds(end, x + d)[0] - y_bounds(end, x - d)[0]) / (2 * d)
        gap = y_bounds(end, x)[0] - y_bounds(main, x)[-1]
        assert gap == pytest.approx(t * math.hypot(1, k), rel=0.02, abs=1e-4), x
        # ... and the space is at least the gap long (the outer wall curves away from it).
        top, bottom = y_bounds(end, x)[0], y_bounds(end, x)[-1]
        assert bottom - top >= e - 1e-3 - t


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
