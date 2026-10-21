"""The flex-PCB layout: a security mesh on each side of the foil, its traces out through the
FPC cable to the plug, and the exports (KiCad, Gerber, SVG)."""

import itertools
import json
import math
from collections import defaultdict

import pytest
import shapely
from shapely.geometry import LineString, Point, Polygon, box

from yanartas_pillowbox import pcb
from yanartas_pillowbox.cli import main
from yanartas_pillowbox.config import Config

D = Config.defaults()


@pytest.fixture(scope="module")
def layout():
    return pcb.layout(D)


def copper(result, layer):
    """Every piece of copper on a layer, with its net (pads: F.Cu only)."""
    out = []
    for t in result.tracks:
        if t.layer == layer:
            out.append((LineString(t.points).buffer(t.width / 2), t.net))
    for v in result.vias:
        out.append((Point(v.at).buffer(pcb.VIA_SIZE / 2), v.net))
    if layer == pcb.FRONT:
        for p in result.pads:
            (x, y), (sx, sy) = p.at, p.size
            out.append(
                (box(x - sx / 2, y - sy / 2, x + sx / 2, y + sy / 2), p.net or f"nc{p.number}")
            )
    return out


def test_pinout():
    """GND, then the mesh's ends in groups of four between GND pins, the rest free."""
    pins = pcb.pinout(30, 4)
    assert pins[:21] == [
        "GND", "M1", "M2", "M3", "M4", "GND", "M5", "M6", "M7", "M8", "GND",
        "M9", "M10", "M11", "M12", "GND", "M13", "M14", "M15", "M16", "GND",
    ]  # fmt: skip
    assert pins[21:] == [None] * 9
    with pytest.raises(pcb.PcbError):
        pcb.pinout(20, 4)


def test_meshes_cover_both_sides(layout):
    """Four loops per side, 2.4 mm cells at 0.15/0.15, every cell inside reached."""
    for layer in (pcb.FRONT, pcb.BACK):
        m = layout.meshes[layer]
        assert len(m.traces) == 4 and m.cell == pytest.approx(2.4)
        assert m.unreached == 0 and m.cells > 1000
    nets = {t.net for t in layout.tracks}
    assert {f"MESH_{s}{i}" for s in "FB" for i in range(1, 5)} <= nets


def test_plug_contacts_carry_the_pinout(layout):
    n = D.mesh_nets
    pins = pcb.pinout(int(D.fpc_pins), n)
    pads = {p.number: p for p in sorted(layout.pads, key=lambda p: p.number)}
    assert sorted(pads) == list(range(1, int(D.fpc_pins) + 1))
    # Each mesh loop's two ends: mirrored within its side's ends.
    ends = 2 * n
    for j, signal in enumerate(pins, start=1):
        if signal is None:
            assert pads[j].net is None
        elif signal == "GND":
            assert pads[j].net == "GND"
        else:
            i = int(signal[1:]) - 1
            side, k = ("F", i) if i < ends else ("B", i - ends)
            assert pads[j].net == f"MESH_{side}{min(k, ends - 1 - k) + 1}"
    # Pin pitch across the plug, along its end.
    xs = [pads[j].at for j in range(1, int(D.fpc_pins) + 1)]
    for a, b in itertools.pairwise(xs):
        assert math.dist(a, b) == pytest.approx(D.fpc_pitch)


def test_each_mesh_net_runs_from_contact_to_contact(layout):
    """The tracks and vias of each mesh net form one chain between its two contacts."""

    def key(p):
        return (round(p[0], 4), round(p[1], 4))

    graph = defaultdict(set)
    for t in layout.tracks:
        for a, b in zip(t.points, t.points[1:], strict=False):
            ka, kb = (t.net, t.layer, key(a)), (t.net, t.layer, key(b))
            graph[ka].add(kb)
            graph[kb].add(ka)
    for v in layout.vias:  # a via joins its layers
        a, b = (v.net, pcb.FRONT, key(v.at)), (v.net, pcb.BACK, key(v.at))
        graph[a].add(b)
        graph[b].add(a)
    for net in {t.net for t in layout.tracks if t.net.startswith("MESH_")}:
        pads = [p for p in layout.pads if p.net == net]
        assert len(pads) == 2
        # Where the contact's track starts: the inner end of its pad.
        starts = [
            n
            for n in graph
            if n[0] == net
            and n[1] == pcb.FRONT
            and any(math.dist(n[2], p.at) <= max(p.size) / 2 + 1e-3 for p in pads[:1])
        ]
        assert starts
        seen, todo = set(starts), list(starts)
        while todo:
            for m in graph[todo.pop()]:
                if m not in seen:
                    seen.add(m)
                    todo.append(m)
        assert any(math.dist(n[2], pads[1].at) <= max(pads[1].size) / 2 + 1e-3 for n in seen)
        assert all(n[0] == net for n in seen)


def test_copper_keeps_its_clearance(layout):
    """Different nets on a layer stay at least the trace space apart (a DRC of the
    layout's own geometry); every piece of copper lies on the foil."""
    for layer in (pcb.FRONT, pcb.BACK):
        parts = copper(layout, layer)
        geoms = [g for g, _ in parts]
        tree = shapely.STRtree(geoms)
        a, b = tree.query(geoms, predicate="dwithin", distance=layout.clearance - 1e-4)
        bad = [
            (parts[i][1], parts[j][1])
            for i, j in zip(a, b, strict=True)
            if i < j and parts[i][1] != parts[j][1]
        ]
        assert bad == [], bad[:5]
        assert all(layout.board.contains(g) for g in geoms)


def test_mesh_keeps_off_the_edges(layout):
    edge = layout.board.boundary
    for t in layout.tracks:
        if t.net.startswith("MESH_") and len(t.points) > 100:  # the mesh loops themselves
            assert LineString(t.points).distance(edge) >= D.mesh_edge_clearance - t.width / 2 - 1e-6


def test_meshes_exit_at_the_junction(layout):
    """Each layer's exit cell sits at the cable's junction on the front panel's free edge
    (x = 0), open towards the cable: the front one against it, the back one half a cell
    further in (and offset along the edge); every loop's two ends leave towards -x, within
    the junction."""
    from yanartas_pillowbox.geometry import build_pattern

    cable = build_pattern(D).cable
    (x, ya), (_, yb) = cable.junction
    lo, hi = sorted((ya, yb))
    front, back = layout.meshes[pcb.FRONT], layout.meshes[pcb.BACK]
    assert front.origin[0] == pytest.approx(x)
    assert back.origin[0] == pytest.approx(x + front.cell / 2)
    for m in (front, back):
        assert lo < m.origin[1] and m.origin[1] + m.cell < hi
        for a, b in m.ends:
            assert a[0] == pytest.approx(m.origin[0]) and b[0] == pytest.approx(m.origin[0])
            assert m.origin[1] < a[1] < m.origin[1] + m.cell
    # The traces run on into the cable from there, at the mesh's pitch, out of the edge.
    starts = [t.points for t in layout.tracks if t.net.startswith("MESH_") and len(t.points) < 50]
    assert starts and all(min(p[0] for p in pts) < x - 1 for pts in starts)


def test_cable_down():
    """Turning down along the edge, the cable carries the mesh just the same."""
    result = pcb.layout(D.with_values(fpc_cable="down"))
    assert pcb.verify(result) == []
    assert all(m.unreached == 0 for m in result.meshes.values())


def test_vias_keep_off_the_cable_folds(layout):
    pattern = __import__("yanartas_pillowbox.geometry", fromlist=["x"]).build_pattern(D)
    folds = [LineString([f.segment.start, f.segment.end]) for f in pattern.cable.folds]
    for v in layout.vias:
        assert min(f.distance(Point(v.at)) for f in folds) >= pcb.FOLD_CLEARANCE - 1e-9


def test_longer_cables_route_round_their_turns():
    result = pcb.layout(D.with_values(fpc_cable_length=200))
    assert len(result.meshes) == 2
    parts = copper(result, pcb.FRONT)
    cable = [(g, n) for g, n in parts if not n.startswith("MESH_") or g.length < 2000]
    geoms = [g for g, _ in cable]
    a, b = shapely.STRtree(geoms).query(
        geoms, predicate="dwithin", distance=result.clearance - 1e-4
    )
    assert not [1 for i, j in zip(a, b, strict=True) if i < j and cable[i][1] != cable[j][1]]


def test_errors():
    with pytest.raises(pcb.PcbError, match="FPC cable"):
        pcb.layout(D.with_values(fpc_cable="none"))
    with pytest.raises(pcb.PcbError, match="pins"):
        pcb.layout(D.with_values(fpc_pins=12))


def test_export(layout, tmp_path):
    from gerbonara.cad.kicad.pcb import Board

    name = "box"
    paths = pcb.export(layout, tmp_path, name)
    assert [p.name for p in paths] == [
        f"{name}.kicad_pcb", f"{name}.kicad_pro", f"{name}-gerbers",
        f"{name}-top.svg", f"{name}-bottom.svg",
    ]  # fmt: skip
    board = Board.open(tmp_path / f"{name}.kicad_pcb")
    segments = sum(len(t.points) - 1 for t in layout.tracks)
    assert len(board.track_segments) == segments
    assert len(board.vias) == len(layout.vias)
    (fp,) = board.footprints
    assert len(fp.pads) == int(D.fpc_pins)
    assert [z.net_name for z in board.zones] == ["GND"]
    assert {line.layer for line in board.lines} >= {"Edge.Cuts", "Dwgs.User"}
    gerbers = {p.name for p in (tmp_path / f"{name}-gerbers").iterdir()}
    assert {
        f"{name}-F_Cu.gbr",
        f"{name}-B_Cu.gbr",
        f"{name}-Edge_Cuts.gbr",
        f"{name}-PTH.drl",
    } <= gerbers
    rules = json.loads((tmp_path / f"{name}.kicad_pro").read_text())["net_settings"]["classes"][0]
    assert rules["clearance"] == pytest.approx(D.mesh_trace_space)


def test_export_draws_arcs(layout, tmp_path):
    """A track in lines and arcs goes out as those: KiCad track arcs through their middles."""
    import copy
    import dataclasses

    from gerbonara.cad.kicad.pcb import Board

    t = next(t for t in layout.tracks if t.net.startswith("MESH"))
    (a, b), rest = t.points[:2], t.points[1:]
    mid = ((a[0] + b[0]) / 2 + 0.01, (a[1] + b[1]) / 2)
    pieces = ((a, mid, b), *((p, None, q) for p, q in itertools.pairwise(rest)))
    result = copy.copy(layout)
    result.tracks = [dataclasses.replace(u, arcs=pieces) if u is t else u for u in layout.tracks]
    pcb.export(result, tmp_path, "arcs")
    board = Board.open(tmp_path / "arcs.kicad_pcb")
    (arc,) = board.track_arcs
    assert (arc.start.x, arc.mid.x, arc.end.x) == pytest.approx((a[0], mid[0], b[0]))
    assert len(board.track_segments) == sum(len(u.points) - 1 for u in layout.tracks) - 1


def test_preview_json(layout):
    data = pcb.preview_json(layout, (10.0, 20.0))
    assert set(data["layers"]) == {"front", "back"}
    assert data["offset"] == [10.0, 20.0] and len(data["bbox"]) == 4
    assert len(data["pads"]) == 4 * int(D.fpc_pins) and len(data["vias"]) == 2 * len(layout.vias)
    assert data["meshes"]["front"]["unreached"] == 0
    # (the average space: no less than the set least, as the layout never undercuts it)
    for side in ("front", "back"):
        average = data["meshes"][side]["average_space"]
        assert data["space"] * 0.98 < average < 2 * data["space"]


def test_cli(tmp_path, capsys):
    assert main(["pcb", "-o", str(tmp_path), "--set", "mesh_traces=2"]) == 0
    assert (tmp_path / "pillowbox.kicad_pcb").exists()
    assert "1.2 mm" in capsys.readouterr().err
    assert main(["pcb", "-o", str(tmp_path), "--set", "fpc_cable=none"]) == 2


def test_api_routes(tmp_path):
    import io
    import zipfile

    from yanartas_pillowbox.server import create_app

    client = create_app(tmp_path / "s.json").test_client()
    small = D.with_values(mesh_traces=2).to_dict()
    r = client.post("/api/pcb", json={"config": small})
    assert r.status_code == 200 and r.json["meshes"]["front"]["cell"] == pytest.approx(1.2)
    r = client.post("/api/pcb", json={"config": {**small, "fpc_cable": "none"}})
    assert r.status_code == 422 and "FPC cable" in r.json["error"]
    r = client.post("/api/pcb/files", json={"config": small})
    assert r.status_code == 200 and r.mimetype == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(r.data)).namelist()
    assert "pillowbox.kicad_pcb" in names and "pillowbox-gerbers/pillowbox-F_Cu.gbr" in names


@pytest.mark.parametrize("offset", ["cell", "cell_trace"])
def test_back_mesh_grid_offset(offset):
    """The back mesh's grid is offset from the front one's by half a cell (plus, optionally,
    a trace width: then its traces lie over the front traces' gaps), in x and y."""
    result = pcb.layout(D.with_values(mesh_back_offset=offset))
    front, back = result.meshes[pcb.FRONT], result.meshes[pcb.BACK]
    shift = front.cell / 2 + (D.mesh_trace_width if offset == "cell_trace" else 0.0)
    for axis in (0, 1):
        d = (back.origin[axis] - front.origin[axis]) % front.cell
        assert d == pytest.approx(shift, abs=1e-9)
    assert back.unreached == 0


def test_trace_lengths(layout):
    """Each mesh net's length: its loop and its two runs along the cable."""
    lengths = layout.net_lengths()
    net, longest = layout.longest_trace()
    assert longest == max(v for n, v in lengths.items() if n.startswith("MESH_"))
    for m_net, trace in zip(("MESH_F1",), layout.meshes[pcb.FRONT].traces, strict=False):
        loop = sum(math.dist(a, b) for a, b in itertools.pairwise(trace))
        assert lengths[m_net] > loop + 2 * D.fpc_cable_length  # (the cable runs, both ways)
    data = pcb.preview_json(layout)
    assert data["longest_trace"] == {"net": net, "length": pytest.approx(longest, abs=1e-3)}
    assert max(data["meshes"][s]["longest"] for s in ("front", "back")) == pytest.approx(
        longest, abs=1e-3
    )


def test_verify_passes_and_catches_opens_and_shorts(layout):
    """The electrical check: every mesh net one piece from contact to contact, no copper of
    two nets touching. It passes on a layout and finds an open and a short put in."""
    import copy

    assert pcb.verify(layout) == []
    broken = copy.deepcopy(layout)
    t = next(t for t in broken.tracks if t.net == "MESH_F2" and len(t.points) > 100)
    i = len(t.points) // 2
    t.points, rest = t.points[:i], t.points[i + 1 :]  # (a gap: the net is open)
    broken.tracks.append(pcb.Track(rest, t.layer, t.net, t.width))
    assert any("MESH_F2 is open" in p for p in pcb.verify(broken))
    shorted = copy.deepcopy(layout)
    a = next(t for t in shorted.tracks if t.net == "MESH_F1" and len(t.points) > 100)
    b = next(t for t in shorted.tracks if t.net == "MESH_F2" and len(t.points) > 100)
    shorted.tracks.append(pcb.Track((a.points[50], b.points[50]), a.layer, "MESH_F1", a.width))
    assert any("short between" in p and "MESH_F2" in p for p in pcb.verify(shorted))


def test_layout_fails_safe(monkeypatch, tmp_path):
    """A layout that fails its check is not given out: an error instead (the UI shows it)."""
    from yanartas_pillowbox.server import create_app

    monkeypatch.setattr(pcb, "verify", lambda result: ["MESH_F1 is open (made up)"])
    with pytest.raises(pcb.PcbError, match="failed its check"):
        pcb.layout(D)
    client = create_app(tmp_path / "s.json").test_client()
    r = client.post("/api/pcb", json={"config": D.with_values(mesh_traces=2).to_dict()})
    assert r.status_code == 422 and "MESH_F1 is open" in r.json["error"]


def test_mesh_metrics(layout):
    """Spacing profile and pair skew of each mesh, in the preview."""
    data = pcb.preview_json(layout)
    for side in ("front", "back"):
        m = data["meshes"][side]
        assert m["algorithm"] == "kimesh"
        sp = m["spacing"]
        assert sp["below"] == 0 and sp["within"] > 0.8 * sp["measured"]  # (KiMesh: exact)
        assert [p["nets"][0][-1] + p["nets"][1][-1] for p in m["skew"]] == ["12", "23", "34"]
        assert all(0 <= p["total"] <= p["local"] + 1e-6 for p in m["skew"])


def _ports_only(mask, corner, side, n, pitch, seed=0, zones=(), arcs=False, partitions=()):
    """A stand-in for the curve's layout: ``n`` nested U-turns in each exit cell (its open
    side to -x), net 1 outermost."""
    from yanartas_pillowbox import mesh

    corners = list(corner) if partitions else [corner]
    c = 2 * n * pitch
    traces = tuple(
        (
            (cx, cy + (j + 0.5) * pitch),
            (cx + (n - j) * pitch, cy + (j + 0.5) * pitch),
            (cx + (n - j) * pitch, cy + c - (j + 0.5) * pitch),
            (cx, cy + c - (j + 0.5) * pitch),
        )
        for cx, cy in corners
        for j in range(n)
    )
    if not partitions:
        return mesh.Mesh(traces, c, 1, 0, corner, "sfc")
    return mesh.Mesh(
        traces, c, 1, 0, corners[0], "sfc", None, (n,) * len(corners), tuple(partitions)
    )


def test_space_filling_curve_is_wired_in(monkeypatch):
    """The curve layout: each layer's area in partitions of equal area, laid out at once
    (each its traces, its port in turn along the junction, its stem; the panels as zones),
    the partitions' traces together the layer's mesh (its own tests run it on small areas;
    a full-size run is slow, below)."""
    from yanartas_pillowbox import sfc
    from yanartas_pillowbox.geometry import build_pattern

    seen = []

    def fake(mask, corner, side, n, pitch, seed=0, zones=(), arcs=False, partitions=(), stems=()):
        seen.append((len(zones), n, [p.area for p in partitions], len(corner), len(stems)))
        return _ports_only(mask, corner, side, n, pitch, partitions=partitions)

    monkeypatch.setattr(sfc, "generate", fake)
    cfg = D.with_values(mesh_algorithm="sfc")
    result = pcb.layout(cfg)
    count, each = int(cfg.mesh_partitions), int(cfg.mesh_traces)
    n = count * each
    zones = len(pcb.mesh_zones(build_pattern(D)))
    assert [(z, k, e, s) for z, k, _, e, s in seen] == [(zones, each, count, count)] * 2
    for *_, areas, _, _ in seen:  # (the partitions of a layer: of equal area)
        assert len(areas) == count and max(areas) - min(areas) < 0.03 * max(areas)
    data = pcb.preview_json(result)
    assert data["meshes"]["front"]["algorithm"] == "sfc"
    assert data["meshes"]["front"]["traces"] == n
    m = result.meshes[pcb.FRONT]
    assert m.groups == (each,) * count and len(m.parts) == count
    assert m.cell == pytest.approx(2 * each * (D.mesh_trace_width + 0.15))
    # (pairs only within a partition)
    assert len(result.skew()[pcb.FRONT]) == count * (each - 1)
    pads = [p for p in result.pads if p.net and p.net.startswith("MESH_")]
    assert len(pads) == 4 * n <= D.fpc_pins
    assert pcb.verify(result) == []


def test_partitions_need_pins(monkeypatch):
    """The plug must hold every partition's ends: too few pins are an error, not cut."""
    with pytest.raises(pcb.PcbError, match="pins"):
        pcb.layout(D.with_values(mesh_algorithm="sfc", mesh_partitions=4))


def test_mesh_zones_join_faces_but_across_folds_and_slits():
    """The front panel's small pieces by its flaps' ends, out past its straight fold's line,
    are of a piece with it (no fold between): one zone; all else as the faces."""
    from yanartas_pillowbox.geometry import build_pattern

    pattern = build_pattern(D)
    zones = pcb.mesh_zones(pattern)
    names = [f.name for f in pattern.faces]
    pieces = [n for n in names if n.startswith("front-") and n.endswith(("-left", "-right"))]
    assert len(pieces) == 4 and len(zones) == len(names) - 4
    faces = {f.name: Polygon(pcb.sample(f.boundary)) for f in pattern.faces}
    (front,) = [z for z in zones if z.contains(faces["front-panel"].representative_point())]
    assert front.area == pytest.approx(sum(faces[n].area for n in ["front-panel", *pieces]))
    assert front.geom_type == "Polygon"


def test_layout_progress_reaches_the_api(monkeypatch, tmp_path):
    """What the mesh layout reports while it runs is polled at /api/progress: its stage
    (the layer), phase, step and the whole layout's share done (the mean of
    all the parts laid out at once)."""
    from yanartas_pillowbox import progress, sfc
    from yanartas_pillowbox.server import create_app

    def fake(mask, corner, side, n, pitch, seed=0, zones=(), arcs=False, partitions=(), stems=()):
        progress.report("settle", 20, 40, vertices=1000)
        return _ports_only(mask, corner, side, n, pitch, partitions=partitions)

    monkeypatch.setattr(sfc, "generate", fake)
    client = create_app(tmp_path / "s.json").test_client()
    config = D.with_values(mesh_traces=2, mesh_algorithm="sfc").to_dict()
    assert client.post("/api/pcb", json={"config": config}).status_code == 200
    e = client.get("/api/progress").json["progress"]  # (the sides run at once: either)
    assert e["stage"].split()[0] in ("F.Cu", "B.Cu") and (e["phase"], e["step"], e["steps"]) == (
        "settle",
        20,
        40,
    )
    assert e["vertices"] == 1000 and 0.2 < e["done"] < 1


@pytest.mark.slow
def test_space_filling_curve_full_size():
    """The default box with the curve layout: checked (open, shorts) by the layout itself,
    every panel reached, the space mostly within the nominal one -5 / +20 %."""
    result = pcb.layout(D.with_values(mesh_algorithm="sfc"))
    assert pcb.verify(result) == []
    for m in result.meshes.values():
        assert m.algorithm == "sfc" and m.unreached == 0
    for sp in result.spacing().values():
        assert sp.under < 0.01 * sp.measured and sp.within > 0.6 * sp.measured
