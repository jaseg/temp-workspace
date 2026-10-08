"""The 3D model must be the 2D pattern, folded: every mesh face is an isometric image of the
corresponding pattern face, faces stay attached along their folds, and the closed state is
consistent (seam closes, flaps overlap on the end wall, no extra creases)."""

import itertools
import math

import pytest
from helpers import loop_area, polyline

from yanartas_pillowbox.config import Config
from yanartas_pillowbox.crosssection import max_sagitta, sagitta_offset
from yanartas_pillowbox.geometry import (
    FoldedBox,
    build_cross_section,
    build_model3d,
    build_pattern,
)

D = Config.defaults()
CONFIGS = {
    "default": D,
    "thin-material": D.with_values(thickness=0),
    "steepest-arc": D.with_values(width=50, height=2 * max_sagitta(50), glue_tab_taper=15),
    "shallow": D.with_values(height=6, length=200, thickness=1),
    "square-tab": D.with_values(glue_tab_taper=0, glue_tab_width=25),
    "big": D.with_values(width=300, length=160, height=110, glue_tab_width=40, glue_tab_taper=30),
}

LEN_TOL = 2e-3  # relative: chord vs. arc on ~1 mm triangles across the curved cross-section
POS_TOL = 1e-5  # mm: positions are rounded to 1e-6 mm in the payload


@pytest.fixture(params=list(CONFIGS), ids=list(CONFIGS), scope="module")
def case(request):
    cfg = CONFIGS[request.param]
    pattern = build_pattern(cfg)
    model = build_model3d(cfg, pattern)
    return cfg, pattern, model, {p["name"]: p for p in model["parts"]}


def pts2(part):
    f = part["flat"]
    return [(f[i], f[i + 1]) for i in range(0, len(f), 2)]


def pts3(part):
    p = part["positions"]
    return [(p[i], p[i + 1], p[i + 2]) for i in range(0, len(p), 3)]


def tris(part):
    idx = part["indices"]
    return [tuple(idx[i : i + 3]) for i in range(0, len(idx), 3)]


def tri_area(a, b, c):
    if len(a) == 2:
        return abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    return math.hypot(*n) / 2


def normal(a, b, c):
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    k = math.hypot(*n)
    return tuple(c / k for c in n)


def same_segment(a, b, tol=1e-9):
    """True if b is a or a reversed (same kind, endpoints and midpoint)."""
    if type(a) is not type(b):
        return False
    ends = (a.start, a.end, a.point_at(0.5))
    for cand in (b, b.reversed()):
        if all(
            math.dist(p, q) < tol
            for p, q in zip(ends, (cand.start, cand.end, cand.point_at(0.5)), strict=True)
        ):
            return True
    return False


# ------------------------------------------------------------------ the 2D faces tile the pattern
def test_faces_tile_the_pattern(case):
    _, pattern, _, _ = case
    faces = pattern.faces
    assert len(faces) == 7
    for face in faces:  # closed, consistently oriented loops
        loop = face.boundary
        for a, b in zip(loop, (*loop[1:], loop[0]), strict=True):
            assert math.dist(a.end, b.start) < 1e-9, face.name
    # Every cut segment bounds exactly one face, every fold exactly two.
    for seg in pattern.outline.segments:
        owners = [f.name for f in faces if any(same_segment(seg, s) for s in f.boundary)]
        assert len(owners) == 1, (seg, owners)
    for fold in pattern.folds:
        owners = [f.name for f in faces if any(same_segment(fold.segment, s) for s in f.boundary)]
        assert len(owners) == 2, (fold.name, owners)
    # ... and the face areas add up to the area enclosed by the cut outline.
    total = sum(abs(loop_area(f.boundary)) for f in faces)
    assert total == pytest.approx(abs(loop_area(pattern.outline.segments)), rel=1e-9)


# ------------------------------------------------------------------ mesh <-> 2D faces
def test_one_mesh_part_per_face(case):
    _, pattern, _, parts = case
    assert set(parts) == {f.name for f in pattern.faces}
    for face in pattern.faces:
        assert parts[face.name]["kind"] == face.kind


def test_mesh_flat_coords_cover_their_face(case):
    """The mesh's flat triangulation lies inside its pattern face and covers all of it."""
    _, pattern, _, parts = case
    for face in pattern.faces:
        part = parts[face.name]
        flat = pts2(part)
        boundary = polyline(list(face.boundary), 256)
        for p in flat:
            assert face.x0 - 1e-6 <= p[0] <= face.x1 + 1e-6
            lo, hi = face.y_range(p[0])
            # 1e-4: coordinates are rounded to 1e-6 mm, and where the boundary is steep a
            # 1e-6 shift in x moves its y by much more.
            assert lo - 1e-4 <= p[1] <= hi + 1e-4, (face.name, p)
            on_edge = min(seg.distance_to(p) for seg in face.boundary) < 1e-5
            assert on_edge or point_in_polygon(p, boundary), (face.name, p)
        mesh_area = sum(tri_area(*(flat[i] for i in t)) for t in tris(part))
        face_area = abs(loop_area(face.boundary))
        assert mesh_area == pytest.approx(face_area, rel=2e-3), face.name


def test_mesh_is_isometric_to_pattern(case):
    """Folding never stretches: every triangle has the same edge lengths and area in 3D as in
    the flat pattern (up to the chord error of ~1 mm triangles on curved surfaces)."""
    _, _, _, parts = case
    for name, part in parts.items():
        flat, pos = pts2(part), pts3(part)
        assert len(flat) == len(pos)
        for t in tris(part):
            for i, j in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                l2, l3 = math.dist(flat[i], flat[j]), math.dist(pos[i], pos[j])
                assert abs(l3 - l2) <= LEN_TOL * l2 + POS_TOL, (name, t, l2, l3)
            a2 = tri_area(*(flat[i] for i in t))
            a3 = tri_area(*(pos[i] for i in t))
            assert abs(a3 - a2) <= 2 * LEN_TOL * a2 + 1e-4, (name, t)


def test_mesh_matches_folding_map(case):
    cfg, _, _, parts = case
    box = FoldedBox(cfg)
    for name, part in parts.items():
        for p2, p3 in zip(pts2(part), pts3(part), strict=True):
            assert math.dist(box.map(name, p2), p3) < POS_TOL


def test_faces_stay_attached_along_folds(case):
    """Both faces adjacent to a fold put every fold point at the same 3D position, so the
    mesh has no gaps or tears along folds."""
    cfg, pattern, _, _ = case
    box = FoldedBox(cfg)
    for fold in pattern.folds:
        owners = [
            f.name for f in pattern.faces if any(same_segment(fold.segment, s) for s in f.boundary)
        ]
        for i in range(33):
            p = fold.segment.point_at(i / 32)
            a, b = (box.map(n, p) for n in owners)
            assert math.dist(a, b) < 1e-9, (fold.name, owners, p)


def test_fold_lines_lie_on_their_faces(case):
    cfg, pattern, model, _ = case
    box = FoldedBox(cfg)
    lines = {ln["name"]: ln for ln in model["lines"]}
    assert set(lines) == {f.name for f in pattern.folds}
    for fold in pattern.folds:
        owner = next(
            f.name for f in pattern.faces if any(same_segment(fold.segment, s) for s in f.boundary)
        )
        pts = lines[fold.name]["points"]
        assert lines[fold.name]["category"] == fold.category.value
        for i, q in enumerate(pts):
            p = fold.segment.point_at(i / (len(pts) - 1))
            assert math.dist(box.map(owner, p), q) < POS_TOL


def test_no_hidden_creases_inside_faces(case):
    """Within a face the surface is smooth: adjacent triangles never meet at a sharp angle.
    (The old model had a ridge across every flap.)"""
    _, _, _, parts = case
    for name, part in parts.items():
        pos = pts3(part)
        edge_tris: dict[tuple[int, int], list[tuple[float, float, float]]] = {}
        for t in tris(part):
            n = normal(*(pos[i] for i in t))
            for i, j in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                edge_tris.setdefault((min(i, j), max(i, j)), []).append(n)
        for ns in edge_tris.values():
            if len(ns) == 2:
                cos = abs(sum(a * b for a, b in zip(*ns, strict=True)))
                assert cos > math.cos(math.radians(15)), name


# ------------------------------------------------------------------ closed-state consistency
def test_box_closes_along_glued_seam(case):
    cfg, _, _, _ = case
    box = FoldedBox(cfg)
    w, g = cfg.panel_width, cfg.glue_tab_width
    for i in range(11):
        y = cfg.edge_length * i / 10
        # The front panel's free (cut) edge meets the glue-tab fold of the back panel ...
        assert math.dist(box.map("front-panel", (0, y)), box.map("back-panel", (2 * w, y))) < 1e-9
        # ... and the glue tab lies flat against the inside of the front panel.
        for a in (0.0, g / 2, g):
            p_tab = box.map("glue-tab", (2 * w + a, y))
            assert math.dist(p_tab, box.map("front-panel", (a, y))) < 1e-9


def test_flaps_overlap_on_common_end_wall(case):
    """Front and back flaps of one end lie on the same end wall (no midline fold): seen along
    the depth axis, every flap point sits on the opposite panel's crease."""
    cfg, _, _, parts = case
    box = FoldedBox(cfg)
    w = cfg.panel_width
    for end in ("top", "bottom"):
        for side, other in (("front", "back"), ("back", "front")):
            part = parts[f"{side}-{end}-flap"]
            for (x, _), p in zip(pts2(part), pts3(part), strict=True):
                # Same arc position on the other panel: x mirrored about the middle fold.
                xo = 2 * w - x
                u = xo - w if other == "back" else xo
                f = sagitta_offset(w, cfg.fold_sagitta, u)
                crease = box.map(f"{other}-panel", (xo, f if end == "top" else cfg.edge_length - f))
                assert p[0] == pytest.approx(crease[0], abs=POS_TOL), (side, end, x)
                assert p[1] == pytest.approx(crease[1], abs=POS_TOL), (side, end, x)


def test_flap_edge_closes_against_opposite_crease(case):
    """Each flap's cut edge runs parallel to the opposite panel's crease on the end wall, offset
    by the thickness allowance (exactly onto it when thickness = 0)."""
    cfg, pattern, _, _ = case
    box = FoldedBox(cfg)
    w, t = cfg.panel_width, cfg.thickness
    for end in ("top", "bottom"):
        cut_f = pattern.face(f"front-{end}-flap")
        for i in range(1, 32):
            x = w * i / 32
            lo, hi = cut_f.y_range(x)
            y_edge = lo if end == "top" else hi
            edge = box.map(f"front-{end}-flap", (x, y_edge))
            # Same arc position on the back panel (mirror: x_back = 2W - x).
            bf = pattern.face(f"back-{end}-flap")
            blo, bhi = bf.y_range(2 * w - x)
            crease_y = bhi if end == "top" else blo
            crease = box.map(f"back-{end}-flap", (2 * w - x, crease_y))
            assert edge[0] == pytest.approx(crease[0], abs=1e-9)
            assert edge[1] == pytest.approx(crease[1], abs=1e-9)
            gap = abs(edge[2] - crease[2])
            assert gap <= t / 2 + 1e-9
            if t == 0:
                assert gap < 1e-9


def test_closed_dimensions(case):
    cfg, _, model, _ = case
    allp = [p for part in model["parts"] for p in pts3(part)]
    zs = [p[2] for p in allp]
    ys = [p[1] for p in allp]
    xs = [p[0] for p in allp]
    assert max(zs) - min(zs) == pytest.approx(cfg.height, rel=1e-6)
    assert max(ys) - min(ys) == pytest.approx(cfg.edge_length, abs=POS_TOL)
    assert model["bounds"]["midline_length"] == cfg.length
    assert max(xs) - min(xs) == pytest.approx(model["bounds"]["width"], rel=1e-6)
    assert model["bounds"]["width"] == pytest.approx(cfg.width, rel=1e-9)  # the input width
    assert model["bounds"]["width"] < cfg.panel_width  # bending shortens the chord


# ------------------------------------------------------------------ body cross-section
def polyline_length(pts):
    return sum(math.dist(a, b) for a, b in itertools.pairwise(pts))


def test_cross_section_matches_pattern_and_mesh(case):
    cfg, _, model, parts = case
    sec = build_cross_section(cfg)
    front, back = sec["front"], sec["back"]
    assert "tab" not in sec  # the section view does not show the glue tab
    # Each panel's section is exactly one panel width long (no stretching) ...
    assert polyline_length(front) == pytest.approx(cfg.panel_width, rel=1e-4)
    assert polyline_length(back) == pytest.approx(cfg.panel_width, rel=1e-4)
    # ... the two panels form one closed loop, joined at the two straight folds ...
    assert math.dist(front[-1], back[0]) < 1e-9
    assert math.dist(back[-1], front[0]) < 1e-9
    folds = {f["category"]: f["point"] for f in sec["folds"]}
    assert folds["straight"] == pytest.approx([sec["width"] / 2, 0], abs=1e-6)
    assert folds["glue"] == pytest.approx([-sec["width"] / 2, 0], abs=1e-6)
    # ... with the box's closed width and height.
    xs = [p[0] for p in front + back]
    zs = [p[1] for p in front + back]
    assert max(xs) - min(xs) == pytest.approx(model["bounds"]["width"], rel=1e-6)
    assert max(zs) - min(zs) == pytest.approx(cfg.height, rel=1e-6)
    # Every 3D panel and tab vertex, seen along the length, lies on the section curve.
    tol = 2e-3 * cfg.panel_width  # chord sag of the sampled section polyline
    for name, curve in (("front-panel", front), ("back-panel", back), ("glue-tab", front)):
        for p in pts3(parts[name]):
            d = min(seg_dist((p[0], p[2]), a, b) for a, b in itertools.pairwise(curve))
            assert d < tol, (name, p)


# ------------------------------------------------------------------ helpers
def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    ll = dx * dx + dy * dy
    t = 0 if ll == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ll))
    return math.dist(p, (a[0] + t * dx, a[1] + t * dy))


def point_in_polygon(p, poly):
    edges = list(zip(poly, poly[1:] + poly[:1], strict=True))
    inside = False
    for (x0, y0), (x1, y1) in edges:
        crosses = (y0 > p[1]) != (y1 > p[1])
        if crosses and p[0] < x0 + (p[1] - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside
