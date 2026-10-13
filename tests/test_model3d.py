"""The 3D model must be the 2D pattern, folded: every mesh face is an isometric image of the
corresponding pattern face, faces stay attached along their folds, and the closed state is
consistent (seam closes, flaps stand on their end walls, no extra creases)."""

import itertools
import math
from dataclasses import replace

import pytest
from helpers import loop_area, polyline

from yanartas_pillowbox.config import Config
from yanartas_pillowbox.crosssection import max_height
from yanartas_pillowbox.geometry import (
    FoldedBox,
    build_cross_section,
    build_model3d,
    build_pattern,
    lid_layout,
    max_lid_offset,
)

D = Config.defaults()
CONFIGS = {
    "default": D,
    "stacked": D.with_values(end_wall_gap=0),
    "wide-gap": D.with_values(end_wall_gap=35, length=60),
    "thin-material": D.with_values(thickness=0),
    "steepest-arc": D.with_values(
        width=50, height=max_height(50, 0.4), glue_tab_taper=15, end_wall_gap=0
    ),
    # The lids as far off the back panel as the end sections can widen (to 45 degrees).
    "max-offset": D.with_values(lid_offset=math.floor(max_lid_offset(D.body) * 100) / 100),
    "shallow": D.with_values(height=6, length=200, thickness=1),
    "thick": D.with_values(width=70, height=24, thickness=2, glue_tab_width=15),
    "fpc": D.with_values(fpc_cutout="both", fpc_cutout_width=20),
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
    cfg, pattern, _, _ = case
    # + a lid at each end, and the front panel's two wings over each gap
    lid = lid_layout(cfg)
    extra = 0 if lid is None else 2 + (4 if lid.spread > 0 else 0)
    assert len(pattern.faces) == 7 + extra
    faces = pattern.faces
    for face in faces:  # closed, consistently oriented loops
        loop = face.boundary
        for a, b in zip(loop, (*loop[1:], loop[0]), strict=True):
            assert math.dist(a.end, b.start) < 1e-9, face.name
    # Every cut segment bounds exactly one face (two along a slit), every fold exactly two.
    for seg in pattern.outline.segments:
        owners = [f.name for f in faces if any(same_segment(seg, s) for s in f.boundary)]
        assert len(owners) == 1, (seg, owners)
    for slit in pattern.slits:
        for seg in slit:
            owners = [f.name for f in faces if any(same_segment(seg, s) for s in f.boundary)]
            assert len(owners) == 2, (seg, owners)
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


def test_part_outlines_run_along_the_face_boundary(case):
    """Each part's ``outline`` (used to draw the inner end flaps through the paper) is a
    closed loop of its own vertices, all on its pattern face's boundary, going round once."""
    _, pattern, _, parts = case
    for face in pattern.faces:
        part = parts[face.name]
        flat, loop = pts2(part), part["outline"]
        assert len(set(loop)) == len(loop) and max(loop) < len(flat)
        for i in loop:
            assert min(seg.distance_to(flat[i]) for seg in face.boundary) < 1e-5, face.name
        pts = [flat[i] for i in loop]
        area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1], strict=True))
        assert abs(area) / 2 == pytest.approx(abs(loop_area(face.boundary)), rel=0.01), face.name


def _dist_to_polyline(q, pts):
    best = math.inf
    for a, b in itertools.pairwise(pts):
        ab = [b[i] - a[i] for i in range(3)]
        ll = sum(c * c for c in ab)
        t = 0 if ll == 0 else max(0, min(1, sum((q[i] - a[i]) * ab[i] for i in range(3)) / ll))
        best = min(best, math.dist(q, [a[i] + t * ab[i] for i in range(3)]))
    return best


def test_cut_edges_are_drawn_where_they_fold_to(case):
    """The 3D model's ``cuts`` are the pattern's cut edges, folded: every cut segment (the
    outline, the slits) of a face other than the inner end flaps (drawn through the paper)
    lies on them, and theirs don't."""
    cfg, pattern, model, _ = case
    box = FoldedBox(cfg)
    cuts = model["cuts"]
    segments = [*pattern.outline.segments, *(seg for slit in pattern.slits for seg in slit)]
    for seg in segments:
        owners = [f for f in pattern.faces if any(same_segment(seg, s) for s in f.boundary)]
        for t in (0.25, 0.5, 0.75):
            p = seg.point_at(t)
            for face in owners:  # (a slit's two sides fold to different places)
                if face.kind == "flap" and face.name.startswith("back-"):
                    continue
                q = box.map(face.name, p)
                d = min(_dist_to_polyline(q, c) for c in cuts)
                assert d < 5e-3, (face.name, p, d)  # (chords of 0.25 mm on the curves)
    # The inner end flaps' own cut edges are not among them.
    for end in ("top", "bottom"):
        face = pattern.face(f"back-{end}-flap")
        x = (face.x0 + face.x1) / 2
        lo, hi = face.y_range(x)
        q = box.map(face.name, (x, lo if end == "top" else hi))
        assert min(_dist_to_polyline(q, c) for c in cuts) > 0.1


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
    """The back panel's glue fold sits a thickness outside the front panel's free edge, and
    the glue tab lies on the outside of the front panel: its mid-surface is t from the
    front panel's along its whole width."""
    cfg, _, _, parts = case
    box = FoldedBox(cfg)
    body, t = box.body, cfg.thickness
    wf, wb = body.front.width, body.back.width
    front = [body.front_point(wf * i / 4000) for i in range(4001)]
    for i in range(11):
        y = cfg.end_wall_gap + cfg.edge_length * i / 10  # along the back panel
        edge, fold = box.map("front-panel", (0, y)), box.map("back-panel", (wf + wb, y))
        # The fold's mid-surface point is on the front's tangent at its edge, offset by t.
        s = body.edge_sine
        assert fold[2] == pytest.approx(edge[2], abs=1e-9)
        assert edge[0] - fold[0] == pytest.approx(t / s, abs=1e-9)
        assert edge[1] == fold[1]
    tab = parts["glue-tab"]
    for (x, _), p in zip(pts2(tab), pts3(tab), strict=True):
        if x - wf - wb <= body.tab_lead + 1e-9:
            continue  # the lead from the glue fold to the panel's edge
        d = min(seg_dist((p[0], p[2]), a, b) for a, b in itertools.pairwise(front))
        assert d == pytest.approx(t, abs=1e-5), (x, p)


def test_flaps_stand_on_the_end_walls(case):
    """Each flap stands on its own end wall, the cylinder through its panel's crease; the
    outer (front) wall lies outside the inner (back) wall, the end wall gap plus a thickness
    apart on the centreline (mid-surface to mid-surface: a clear gap of the end wall gap)."""
    cfg, pattern, _, parts = case
    box = FoldedBox(cfg)
    body, t, e = box.body, cfg.thickness, cfg.end_wall_gap
    half, half_front = cfg.edge_length / 2, cfg.front_length / 2
    for end in ("top", "bottom"):
        for side in ("front", "back"):
            part = parts[f"{side}-{end}-flap"]
            for (x, _), p in zip(pts2(part), pts3(part), strict=True):
                lo, hi = pattern.face(f"{side}-panel").y_range(x)
                crease = box.map(f"{side}-panel", (x, lo if end == "top" else hi))
                assert p[0] == pytest.approx(crease[0], abs=POS_TOL), (side, end, x)
                assert p[1] == pytest.approx(crease[1], abs=POS_TOL), (side, end, x)
    # Outer wall at least the gap outside the inner wall everywhere across the box (|Y| =
    # half its panel's length - crease depth, at the same X) ...
    for i in range(1, 64):
        u = body.front.width * i / 64
        x = body.front_point(u)[0]
        outer = half_front - body.front.z(u)
        inner = half - (body.z_shift - body.surface_z("back", 0.0, x))
        assert inner <= outer - e + 1e-9
    # ... and the gap plus a thickness outside it on the centreline.
    top = {
        side: box.map(f"{side}-top-flap", (x, 0.5 * sum(pattern.face(f"{side}-panel").y_range(x))))
        for side, x in (
            ("front", body.front.width / 2),
            ("back", body.front.width + body.back.width / 2),
        )
    }
    assert top["front"][1] - top["back"][1] == pytest.approx(e + t, abs=1e-9)


def _surface_gap(body, panel, offset, x, z):
    return z - body.surface_z(panel, offset, x)


def test_flap_edges_meet_the_body_surfaces(case):
    """The outer (front) flaps' cut edge is flush with the back panel's outer surface, or
    with an end wall gap their fold into the lid is where the lid's mid-surface lies on top
    of the back panel (at least a thickness outside its mid-surface, touching somewhere).
    The inner (back) flaps' cut edge meets the front panel's inner surface (or, near the
    corners where that dips below, runs along the chord). Exact at the polyline's
    vertices, to well under 0.01 mm in between. An FPC cutout cuts the inner edge back
    further."""
    cfg, pattern, _, _ = case
    box = FoldedBox(cfg)
    body, t = box.body, cfg.thickness
    wf, wb = body.front.width, body.back.width
    lid = lid_layout(cfg)
    plain = None if cfg.fpc_cutout == "none" else build_pattern(replace(cfg, fpc_cutout="none"))
    for end in ("top", "bottom"):
        clearances = []
        for i in range(1, 200):
            # Outer flap.
            x = wf * i / 200
            lo, hi = pattern.face(f"front-{end}-flap").y_range(x)
            p = box.map(f"front-{end}-flap", (x, lo if end == "top" else hi))
            if lid is None:
                gap = _surface_gap(body, "back", t / 2, p[0], p[2])
                assert abs(gap) < 0.01 + 1e-3 * t, ("outer", end, x, gap)
            else:  # (the back panel's outward normal is -Z)
                clearances.append(-_surface_gap(body, "back", t, p[0], p[2]))
                if i == 1:  # also at the corners, where the lid may touch
                    for xc in (0.0, wf):
                        q = box.map(
                            f"front-{end}-flap",
                            (xc, pattern.face(f"front-{end}-flap").y_range(xc)[end == "bottom"]),
                        )
                        clearances.append(-_surface_gap(body, "back", t, q[0], q[2]))
            # Inner flap.
            x = wf + wb * i / 200
            lo, hi = pattern.face(f"back-{end}-flap").y_range(x)
            p = box.map(f"back-{end}-flap", (x, lo if end == "top" else hi))
            gap = _surface_gap(body, "front", -t / 2, p[0], p[2])
            tol = 0.01 + 1e-3 * t
            on_chord = abs(p[2] - body.z_shift) < 1e-6
            if plain is not None:
                plo, phi = plain.face(f"back-{end}-flap").y_range(x)
                if abs((lo, hi)[end == "bottom"] - (plo, phi)[end == "bottom"]) > 1e-9:
                    assert gap < 1e-6, ("FPC cutout", end, x, gap)  # cut back below
                    continue
            assert on_chord or abs(gap) < tol, ("inner", end, x, gap)
            if on_chord:
                assert gap > -1e-6  # trimmed to the chord only where the surface is lower
        if lid is not None:  # floating the lid offset off the back panel where closest
            assert min(clearances) == pytest.approx(cfg.lid_offset, abs=1e-3 * t + 1e-9), end
    if lid is None:
        # At the panels' apexes, exactly: the outer flap reaches Z = -(h/2 + t), the inner
        # +h/2.
        cut = body.front_cuts[len(body.front_cuts) // 2][1]
        top_outer = box.map("front-top-flap", (wf / 2, -cut))
        expected = body.surface_z("back", t / 2, top_outer[0])
        assert top_outer[2] == pytest.approx(expected, abs=1e-9)


def test_lids_cover_the_gap(case):
    """Each lid lies on the outside of the back panel, never closer than a thickness to its
    mid-surface, ruled along the box; it starts at the outer wall's top and ends the
    overlap beyond the inner wall's outer surface (measured along the box)."""
    cfg, pattern, _, parts = case
    lid = lid_layout(cfg)
    if lid is None:
        assert not [p for p in parts.values() if p["kind"] == "lid"]
        return
    box = FoldedBox(cfg)
    body, t, e = box.body, cfg.thickness, cfg.end_wall_gap
    half = cfg.edge_length / 2
    for end, sign in (("top", 1), ("bottom", -1)):
        part = parts[f"front-{end}-lid"]
        assert part["kind"] == "lid"
        face = pattern.face(f"front-{end}-lid")
        for (x, y), p in zip(pts2(part), pts3(part), strict=True):
            # On or outside the back panel's outer surface (a thickness out, mid to mid).
            assert p[2] <= body.surface_z("back", t, p[0]) + POS_TOL, (end, x, y)
            # Ruled along the box: the height depends on x only.
            fz = body.front.z_ext(x)  # (the front panel's profile, continued past its edges)
            assert p[2] == pytest.approx(body.z_shift + lid.level - fz, abs=POS_TOL)
            lo, hi = face.y_range(x)
            if abs(y - (hi if end == "top" else lo)) < 1e-9:  # the fold: on the outer wall
                outer_wall = half + e - fz
                assert sign * p[1] == pytest.approx(outer_wall, abs=POS_TOL)
        # The free edge (a polyline through exact samples; checked at the samples): the
        # overlap beyond the inner wall's outer surface.
        for x, depth in lid.depth:
            if not 0 < x < body.front.width:
                continue
            y = lid.level - depth
            q = box.map(f"front-{end}-lid", (x, y if end == "top" else cfg.front_length - y))
            inner_wall = half - (body.z_shift - body.surface_z("back", 0.0, q[0]))
            assert sign * q[1] == pytest.approx(inner_wall + t / 2 - cfg.lid_overlap, abs=1e-9)


def test_closed_dimensions(case):
    cfg, _, model, _ = case
    allp = [p for part in model["parts"] for p in pts3(part)]
    zs = [p[2] for part in model["parts"] if part["kind"] != "tab" for p in pts3(part)]
    ys = [p[1] for p in allp]
    xs = [p[0] for p in allp]
    t, h = cfg.thickness, cfg.height
    # Mid-surface, centred on the interior: the front panel half the material above it, the
    # outer flaps' edges flush with the back panel's outer surface, the material below it
    # (or the lids, on top of the back panel, at their lowest in the middle).
    assert max(zs) == pytest.approx(h / 2 + t / 2, abs=1e-6)
    lid = lid_layout(cfg)
    if lid is None:
        assert min(zs) == pytest.approx(-(h / 2 + t), abs=0.01)
    else:
        lowest = cfg.body.z_shift + lid.level - cfg.body.front.sagitta
        assert min(zs) == pytest.approx(lowest, abs=1e-6)
        assert lowest <= -(h / 2 + 1.5 * t) + 1e-9
    # (with lids, the widened outer walls reach past the front panel's ends by the drop)
    overall = cfg.front_length + (0 if lid_layout(cfg) is None else 2 * lid_layout(cfg).drop)
    assert max(ys) - min(ys) == pytest.approx(overall, abs=POS_TOL)
    assert model["bounds"]["length"] == pytest.approx(overall)
    assert model["interior"] == {"width": cfg.width, "length": cfg.length, "height": cfg.height}
    assert max(xs) - min(xs) == pytest.approx(model["bounds"]["width"], rel=1e-4)
    assert model["bounds"]["width"] > cfg.width or t == 0
    for sec in (cfg.body.front, cfg.body.back):
        assert sec.closed_width < sec.width  # bending shortens the chord


# ------------------------------------------------------------------ body cross-section
def polyline_length(pts):
    return sum(math.dist(a, b) for a, b in itertools.pairwise(pts))


def test_cross_section_matches_pattern_and_mesh(case):
    cfg, _, _, parts = case
    sec = build_cross_section(cfg)
    body = cfg.body
    front, back = sec["front"], sec["back"]
    # Each panel's section is exactly its flat width long (no stretching) ...
    assert polyline_length(front) == pytest.approx(body.front.width, rel=1e-4)
    assert polyline_length(back) == pytest.approx(body.back.width, rel=1e-4)
    # ... joined at the straight fold; at the glued edge the glue fold sits t / sin(alpha)
    # outside the front panel's free edge (the tab wraps around it).
    assert math.dist(front[-1], back[0]) < 1e-9
    assert math.dist(back[-1], front[0]) == pytest.approx(cfg.thickness / body.edge_sine, abs=1e-5)
    # The glue tab starts at the glue fold and lies t outside the front panel.
    tab = sec["glue_tab"]
    assert tab[0] == pytest.approx(back[-1], abs=1e-6)
    assert polyline_length(tab) == pytest.approx(cfg.glue_tab_width, rel=1e-4)
    fine = [body.front_point(body.front.width * i / 4000) for i in range(4001)]
    for q in tab:
        if math.dist(q, tab[0]) > body.tab_lead + 1e-6:
            d = min(seg_dist(q, a, b) for a, b in itertools.pairwise(fine))
            assert d == pytest.approx(cfg.thickness, abs=1e-5)
    # The interior: corners at +-width/2, inner surfaces at +-height/2.
    inner = sec["inner"]
    assert inner["fold"][0] - inner["glue"][0] == pytest.approx(cfg.width, abs=1e-5)
    assert inner["front_apex"][1] == pytest.approx(cfg.height / 2, abs=1e-5)
    assert inner["back_apex"][1] == pytest.approx(-cfg.height / 2, abs=1e-5)
    # The material outlines are t wide around the panels' and the tab's mid-surfaces.
    for band, mid in zip(sec["material"], (front, back, tab), strict=True):
        n = len(band) // 2
        assert n == len(mid)
        for a, b, m in zip(band[:n], reversed(band[n:]), mid, strict=True):
            assert math.dist(a, b) == pytest.approx(cfg.thickness, abs=1e-5)
            assert math.dist(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), m) < 1e-5
    # The interior outline runs corner to corner, t/2 inside the mid-surfaces.
    outline = sec["interior"]
    assert inner["glue"] in outline and inner["fold"] in outline
    for q in outline:
        assert inner["glue"][0] - 1e-6 <= q[0] <= inner["fold"][0] + 1e-6
        d = min(seg_dist(q, a, b) for c in (front, back) for a, b in itertools.pairwise(c))
        if q not in (inner["glue"], inner["fold"]):
            assert d == pytest.approx(cfg.thickness / 2, abs=2e-3 * body.front.width)
    x0, z0, x1, z1 = sec["bbox"]
    for x, z in outline:
        assert x0 - 1e-6 <= x <= x1 + 1e-6 and z0 - 1e-6 <= z <= z1 + 1e-6
    # Every 3D panel vertex, seen along the length, lies on the section curve.
    tol = 2e-3 * body.front.width  # chord sag of the sampled section polyline
    for name, curve in (("front-panel", front), ("back-panel", back)):
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
