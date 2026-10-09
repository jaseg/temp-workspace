"""Payload: inscribed box, per-dimension maximize, and the box fit."""

import itertools
import math
from dataclasses import replace

import pytest

from yanartas_pillowbox import payload as P
from yanartas_pillowbox.config import Config, ConfigError
from yanartas_pillowbox.geometry import build_cross_section, build_model3d, build_pattern
from yanartas_pillowbox.server import create_app
from yanartas_pillowbox.svg import extract_config, render_svg

D = Config.defaults()
BOXES = {
    "default": D,
    "wide-flat": D.with_values(
        width=120, height=20, length=60, payload_width=75, payload_depth=50, payload_height=8
    ),
    "steep": D.with_values(width=50, height=22.5, payload_width=20, payload_height=15),
}
PAYLOADS = [(30, 100, 14), (60, 40, 10), (10, 200, 30), (80, 25, 5)]


@pytest.fixture(params=list(BOXES), ids=list(BOXES))
def box(request):
    return BOXES[request.param]


def pts3(part):
    p = part["positions"]
    return [(p[i], p[i + 1], p[i + 2]) for i in range(0, len(p), 3)]


def assert_inside_mesh(cfg):
    """Independent containment check against the folded 3D mesh: no panel vertex above the
    payload's footprint is lower than its top, and no end-wall vertex across its width is
    closer to the centre than its end."""
    pw, pd, ph = cfg.payload_width, cfg.payload_depth, cfg.payload_height
    for part in build_model3d(cfg)["parts"]:
        for x, y, z in pts3(part):
            if abs(x) > pw / 2:
                continue
            if part["kind"] == "panel":
                assert abs(z) >= ph / 2 - 1e-6, (part["name"], x, y, z)
            elif part["kind"] == "flap":
                assert abs(y) >= pd / 2 - 1e-6, (part["name"], x, y, z)


def rect_segment_distance(a, b, w, h):
    """Distance from the centred rectangle |x| <= w/2, |z| <= h/2 to segment ab (sampled
    finely; segments are short)."""
    best = math.inf
    for i in range(9):
        x = a[0] + (b[0] - a[0]) * i / 8
        z = a[1] + (b[1] - a[1]) * i / 8
        best = min(best, math.hypot(max(abs(x) - w / 2, 0), max(abs(z) - h / 2, 0)))
    return best


# ------------------------------------------------------------------ fit test
def test_default_payload_fits():
    assert P.fits(D)
    assert_inside_mesh(D)


def test_fits_matches_section(box):
    """The cross-section clearance is the distance to the interior outline the section view
    draws (the material's inner surface, t/2 inside the mid-surface)."""
    section = build_cross_section(box, samples=1500)
    w, h = box.payload_width, box.payload_height
    brute = min(
        rect_segment_distance(a, b, w, h)
        for a, b in itertools.pairwise(section["interior"] + section["interior"][:1])
    )
    assert P.section_clearance(box.body, w, h) == pytest.approx(brute, abs=2e-3)


def box_point_distance(cfg, p):
    """Distance from point p to the payload box (0 inside)."""
    half = (cfg.payload_width / 2, cfg.payload_depth / 2, cfg.payload_height / 2)
    return math.hypot(*(max(abs(c) - h, 0.0) for c, h in zip(p, half, strict=True)))


MARGIN_CASES = {
    "default": D,
    "no-margin": D.with_values(payload_margin=0),
    "tight-length": D.with_values(payload_depth=117, payload_height=10, payload_margin=1.5),
    "wide": D.with_values(
        width=120,
        height=30,
        length=60,
        payload_width=90,
        payload_depth=40,
        payload_height=8,
        payload_margin=2,
    ),
    "thin-tall": D.with_values(payload_width=6, payload_height=17, payload_margin=0.5),
    "thick": D.with_values(thickness=2, height=24, width=70, payload_width=40, payload_height=14),
}


@pytest.mark.parametrize("cfg", list(MARGIN_CASES.values()), ids=list(MARGIN_CASES))
def test_clearance_is_true_distance_to_surface(cfg):
    """Brute force: the smallest distance from the payload box to any vertex of a fine mesh of
    the folded box (panels, end-wall flaps, glue tab) equals the computed clearance. Mesh
    vertices only sample the surface, so they can overestimate it slightly, never under. The
    model is the material's mid-surface, half a thickness beyond the surface that counts."""
    c = P.clearance(cfg)
    assert c is not None and c > 0
    model = build_model3d(cfg, step=0.25, rows=60)
    nearest = min(box_point_distance(cfg, p) for part in model["parts"] for p in pts3(part))
    nearest -= cfg.thickness / 2
    assert nearest >= c - 1e-5
    assert nearest <= c + 0.02


def test_margin_controls_fit():
    c = P.clearance(D)
    assert P.fits(D.with_values(payload_margin=math.floor(c * 100) / 100))
    assert not P.fits(D.with_values(payload_margin=c + 0.01))
    # End walls: clearance along the length is exactly (length - depth) / 2.
    cfg = D.with_values(payload_depth=D.length - 1, payload_margin=0)
    assert P.clearance(cfg) == pytest.approx(0.5)


def test_too_large_payload_does_not_fit():
    assert not P.fits(D.with_values(payload_depth=D.length + 0.1))
    assert not P.fits(D.with_values(payload_height=D.height))
    assert not P.fits(D.with_values(payload_width=D.width))


def test_empty_payload():
    cfg = D.with_values(payload_height=0)
    assert P.is_empty(cfg) and P.fits(cfg)
    assert P.summary(cfg)["empty"]


# ------------------------------------------------------------------ maximize
@pytest.mark.parametrize("field", ["payload_width", "payload_depth", "payload_height"])
def test_maximize_is_tight(box, field):
    out = P.maximize(box, field)
    assert P.fits(out)
    assert_inside_mesh(out)
    # Only that field changed, and a little more does not fit.
    assert replace(out, **{field: getattr(box, field)}) == box
    assert not P.fits(replace(out, **{field: getattr(out, field) + 0.02}))


def test_maximize_height_touches_the_inner_surface(box):
    """With no margin the largest payload touches the material's inner surface."""
    box = replace(box, payload_margin=0)
    out = P.maximize(box, "payload_height")
    assert P.section_clearance(out.body, out.payload_width, out.payload_height) == pytest.approx(
        0, abs=0.011
    )


def test_maximize_depth_is_midline_length(box):
    out = P.maximize(box, "payload_depth")
    assert out.payload_depth == pytest.approx(box.length - 2 * box.payload_margin)


@pytest.mark.parametrize("field", ["payload_width", "payload_depth", "payload_height"])
def test_maximize_keeps_margin_exactly(box, field):
    out = P.maximize(box, field)
    assert P.clearance(out) == pytest.approx(box.payload_margin, abs=0.011)


def test_maximize_impossible():
    with pytest.raises(P.PayloadError) as info:
        P.maximize(D.with_values(payload_height=D.height), "payload_width")
    assert info.value.field == "payload_height"
    with pytest.raises(P.PayloadError):
        P.maximize(D.with_values(payload_width=D.width), "payload_height")
    with pytest.raises(P.PayloadError) as info:  # cross-section already breaks the margin
        P.maximize(D.with_values(payload_height=14), "payload_depth")
    assert info.value.field == "payload_width"


# ------------------------------------------------------------------ fit box
def test_pattern_area_matches_pattern_bbox(box):
    x0, y0, x1, y1 = build_pattern(box).bbox
    assert P.pattern_area(box) == pytest.approx((x1 - x0) * (y1 - y0), rel=1e-9)


@pytest.mark.parametrize("dims", PAYLOADS, ids=[f"{w}x{d}x{h}" for w, d, h in PAYLOADS])
def test_fit_box_holds_payload_and_only_touches_body(dims):
    pw, pd, ph = dims
    cfg = D.with_values(payload_width=pw, payload_depth=pd, payload_height=ph)
    out = P.fit_box(cfg)
    assert P.fits(out)
    assert_inside_mesh(out)
    unchanged = {"width": out.width, "length": out.length, "height": out.height}
    assert replace(cfg, **unchanged) == out  # glue tab and thickness kept
    assert out.length == pytest.approx(max(pd + 2 * cfg.payload_margin, 10))
    assert P.clearance(out) == pytest.approx(cfg.payload_margin, abs=0.011)  # tight


def brute_force_min_area(cfg, n_heights=12):
    """Independent search: for each height on a grid, the narrowest valid box that fits."""
    best = math.inf
    ph = cfg.payload_height
    for i in range(1, n_heights + 1):
        height = ph + (cfg.payload_width * 0.6) * i / n_heights
        lo, hi = cfg.payload_width, cfg.payload_width * 4 + 50
        try:
            if not P.fits(
                cfg.with_values(
                    height=height, width=hi, length=cfg.payload_depth + 2 * cfg.payload_margin
                )
            ):
                continue
        except ConfigError:
            continue
        for _ in range(22):
            mid = (lo + hi) / 2
            try:
                ok = P.fits(
                    cfg.with_values(
                        height=height, width=mid, length=cfg.payload_depth + 2 * cfg.payload_margin
                    )
                )
            except ConfigError:
                ok = False
            lo, hi = (lo, mid) if ok else (mid, hi)
        cand = cfg.with_values(
            height=height, width=hi, length=cfg.payload_depth + 2 * cfg.payload_margin
        )
        best = min(best, P.pattern_area(cand))
    return best


@pytest.mark.parametrize("dims", PAYLOADS[:2], ids=[f"{w}x{d}x{h}" for w, d, h in PAYLOADS[:2]])
def test_fit_box_minimizes_pattern_area(dims):
    pw, pd, ph = dims
    cfg = D.with_values(payload_width=pw, payload_depth=pd, payload_height=ph)
    out = P.fit_box(cfg)
    # 0.01 mm rounding of width/height costs well under 0.2 % of the area.
    assert P.pattern_area(out) <= brute_force_min_area(cfg) * 1.002


def test_fit_box_errors():
    with pytest.raises(P.PayloadError):
        P.fit_box(D.with_values(payload_width=0))
    with pytest.raises(P.PayloadError):  # would need a box wider than the 1000 mm limit
        P.fit_box(D.with_values(payload_width=999, payload_height=300))


# ------------------------------------------------------------------ persistence / export / API
def test_payload_is_persisted_but_not_drawn_in_svg():
    cfg = D.with_values(payload_width=33.3, payload_depth=77.7, payload_height=11.1)
    svg = render_svg(cfg)
    assert extract_config(svg) == cfg  # stored in the embedded config ...
    body = svg[svg.index("</metadata>") :]
    assert "payload" not in body.lower() and "<rect" not in body  # ... but never drawn


def test_api(tmp_path):
    client = create_app(tmp_path / "s.json").test_client()
    cfg = D.to_dict()
    r = client.post("/api/payload", json={"config": cfg, "action": "fit"})
    assert r.status_code == 200 and P.fits(Config.from_dict(r.get_json()["config"]))
    r = client.post(
        "/api/payload", json={"config": cfg, "action": "maximize", "field": "payload_height"}
    )
    assert (
        r.get_json()["config"]["payload_height"] == P.maximize(D, "payload_height").payload_height
    )
    bad = {**cfg, "payload_height": cfg["height"]}
    r = client.post(
        "/api/payload", json={"config": bad, "action": "maximize", "field": "payload_width"}
    )
    assert r.status_code == 422 and "payload_height" in r.get_json()["errors"]
    assert client.post("/api/payload", json={"config": cfg, "action": "x"}).status_code == 400
    data = client.post("/api/render", json={"config": cfg}).get_json()
    assert data["payload"] == {
        "width": 30,
        "depth": 100,
        "height": 13,
        "margin": 1,
        "clearance": round(P.clearance(D), 4),
        "empty": False,
        "fits": True,
    }
