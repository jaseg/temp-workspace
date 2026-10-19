"""The flex-PCB layout: a security mesh on each side of the foil, its traces out through the
FPC cable to the plug, and the exports (KiCad, Gerber, SVG)."""

import itertools
import json
import math
from collections import defaultdict

import pytest
import shapely
from shapely.geometry import LineString, Point, box

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
    pins = pcb.pinout(int(D.fpc_pins), int(D.mesh_traces))
    pads = {p.number: p for p in sorted(layout.pads, key=lambda p: p.number)}
    assert sorted(pads) == list(range(1, int(D.fpc_pins) + 1))
    # Each mesh loop's two ends: mirrored within its side's eight ends.
    for j, signal in enumerate(pins, start=1):
        if signal is None:
            assert pads[j].net is None
        elif signal == "GND":
            assert pads[j].net == "GND"
        else:
            i = int(signal[1:]) - 1
            side, k = ("F", i) if i < 8 else ("B", i - 8)
            assert pads[j].net == f"MESH_{side}{min(k, 7 - k) + 1}"
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


def test_preview_json(layout):
    data = pcb.preview_json(layout, (10.0, 20.0))
    assert set(data["layers"]) == {"front", "back"}
    assert data["offset"] == [10.0, 20.0] and len(data["bbox"]) == 4
    assert len(data["pads"]) == 4 * int(D.fpc_pins) and len(data["vias"]) == 2 * len(layout.vias)
    assert data["meshes"]["front"]["unreached"] == 0


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
