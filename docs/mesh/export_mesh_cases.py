"""Export the curve mesh's test cases for the notebook (``mesh.ipynb``).

Runs the original implementation (``yanartas_pillowbox.partition.partition``, then
``yanartas_pillowbox.sfc.generate`` with its Rust core) on a few small cases and writes
``mesh_cases.json`` next to this script: each case's input, its partitions (what the first
notebook, ``../partition``, produces), each step's inputs and outputs, and the mesh. Run
from the repository, the package and its Rust core installed (``uv run python
docs/mesh/export_mesh_cases.py``); it builds ``recorder/`` (cargo) on first use.

Everything is recorded by wrapping the implementation's own functions and the core's entry
points while ``generate`` runs, so it is what they computed; nothing here repeats their
logic. The one exception is the cells each graph build starts from, which the core does not
return: ``recorder/`` (a small Rust program on the unmodified core) computes them with the
core's ``graph::cells``, from the same key, in the same order, as the build's first try.

JSON schema
-----------
Geometry is WKT at full precision; a *polyline* is a list of [x, y]; a *rings* value is a
polygon as a list of rings (outline first, then holes), each a list of [x, y] (not closed).

{
  "version": 1,
  "constants": {name: number, ...},        # sfc.py's module constants
  "cases": [
    {
      "name": str, "note": str,
      "input": {
        "mask": WKT, "zones": [WKT], "ports": [WKT], "exits": [[x, y]], "side": int,
        "traces": int, "pitch": float, "seed": int, "arcs": bool
      },
      "partitions": [{"area": WKT, "port": WKT, "reach": float}],   # partition.partition
      "graphs": [                             # each _curve call, in order (1 to 3)
        {
          "regions": [WKT], "owner": [int], "spacing": float, "key": hex,
          "openings": [[[x, y], [x, y]]],
          "segments": [[int, rings]],         # the core's input: region, domain
          "borders": [[int, int, [polyline]]],
          "params": {name: number},
          "cells": [[rings]],                 # recorder: each segment's cells, first try
          "curves": [[polyline, [int]]],      # the core's output: vertices, their regions
          "ncells": int, "lost": [int]
        }
      ],
      "reassigned": [int] | null,             # _reassigned's owners (null: none moved)
      "merged": {"regions": [WKT], "owner": [int]} | null,
      "relax": [                              # per partition: the core's relax_curve
        {"curve": polyline, "stem": polyline, "regions": [rings], "target": float,
         "edge": polyline, "borders": polyline, "spacing": float, "least": float,
         "pitch": float, "offset": [x, y], "params": {name: number},
         "out": polyline, "k": int}
      ],
      "lanes": [                              # per partition: the core's offset_lanes
        {"p": polyline, "k": int, "edge_a": polyline, "edge_b": polyline, "n": int,
         "pitch": float, "spacing": float, "exact": [bool], "params": {name: number},
         "out": [polyline]}
      ],
      "unlooped": [[float, polyline]],        # _unlooped: most, result (its ring: the
                                              # lanes' traces, in order)
      "opened": [[WKT, polyline]],            # _opened: cut, result (its ring: the
                                              # unlooped's result, in order)
      "settle": {                             # _settle
        "lines": [polyline], "pitch": float, "area": WKT, "regions": [WKT], "keep": WKT,
        "groups": [int], "ribbon": int,
        "phases": [{"phases": int, "out": [polyline]}],   # the core's settle_traces calls
        "out": [polyline]
      },
      "output": {                             # the core's smooth_traces or fit_arcs
        "call": "smooth_traces" | "fit_arcs", "edges": [polyline],   # (its lines:
        "args": {name: number}, "out": [polyline] | [[[7 numbers]]]  # settle's out)
      },
      "mesh": {"traces": [polyline], "unreached": int, "cells": int, "groups": [int]}
    }
  ]
}
A case whose steps up to the output are those of an earlier case has, for each such key
("graphs", "reassigned", "merged", "relax", "lanes", "unlooped", "opened", "settle"), the
value {"same_as": <that case's name>}.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import shapely

from yanartas_pillowbox import mesh, partition, sfc

HERE = Path(__file__).parent
OUT = HERE / "mesh_cases.json"
TARGET = Path(os.environ.get("CARGO_TARGET_DIR", HERE / "recorder" / "target"))
RECORDER = TARGET / "release" / "cells-recorder"
PITCH, TRACES = 0.3, 2
PORT = 2 * TRACES * PITCH


def wkt(g: shapely.Geometry) -> str:
    return shapely.to_wkt(g, rounding_precision=-1)


def pl(a: Any) -> list:
    return np.asarray(a, float).tolist()


def rings(r: Any) -> list:
    return [pl(x) for x in r]


def case_inputs() -> list[dict]:
    """Small cases (a few hundred cells of the curve's graph each): the steps' ports run in
    seconds to a minute each."""

    def make(
        name: str,
        note: str,
        mask: shapely.Geometry,
        zones: list,
        count: int,
        seed: int,
        arcs: bool = False,
    ) -> dict:
        y0 = (mask.bounds[1] + mask.bounds[3]) / 2 - count * PORT / 2
        ports = [shapely.box(0, y0 + k * PORT, PORT, y0 + (k + 1) * PORT) for k in range(count)]
        exits = [(0.0, y0 + k * PORT) for k in range(count)]
        return dict(
            name=name,
            note=note,
            mask=mask,
            zones=zones,
            ports=ports,
            exits=exits,
            seed=seed,
            arcs=arcs,
        )

    box = shapely.box
    return [
        make(
            "one",
            "one partition, one panel: the whole pipeline at its simplest",
            box(0, 0, 10, 7),
            [box(0, 0, 10, 7)],
            1,
            1,
        ),
        make(
            "fold",
            "one partition over two panels: their curves joined across the fold",
            box(0, 0, 14, 9),
            [box(0, 0, 7, 9), box(7, 0, 14, 9)],
            1,
            2,
        ),
        make(
            "partitions",
            "two partitions over two panels: two curves, stems side by side",
            box(0, 0, 16, 10),
            [box(0, 0, 8, 10), box(8, 0, 16, 10)],
            2,
            3,
        ),
        make(
            "hole",
            "a mounting hole in the panel: cells clipped round it, the curve round it",
            box(0, 0, 12, 9).difference(box(6, 3, 8.5, 5.5)),
            [box(0, 0, 12, 9)],
            1,
            4,
        ),
        make(
            "arcs",
            "the fold case drawn in lines and arcs (arc fitting instead of smoothing)",
            box(0, 0, 14, 9),
            [box(0, 0, 7, 9), box(7, 0, 14, 9)],
            1,
            2,
            arcs=True,
        ),
    ]


def recorded_cells(
    key: bytes, spacing: float, params: dict, openings: list, segments: list
) -> list:
    """The recorder's cells: per segment, its cells (each its rings)."""
    if not RECORDER.exists():
        subprocess.run(
            [
                "cargo",
                "build",
                "--release",
                "--manifest-path",
                str(HERE / "recorder" / "Cargo.toml"),
            ],
            check=True,
            env={**os.environ, "CARGO_TARGET_DIR": str(TARGET)},
        )
    words = [key.hex(), repr(spacing), repr(params["seed_spacing"]), str(params["lloyd"])]
    words.append(str(len(openings)))
    for a, b in openings:
        words += [repr(float(v)) for v in (*a, *b)]
    words.append(str(len(segments)))
    for _, rs in segments:
        words.append(str(len(rs)))
        for r in rs:
            words.append(str(len(r)))
            words += [repr(float(v)) for q in r for v in q]
    got = subprocess.run(
        [str(RECORDER)], input=" ".join(words), capture_output=True, text=True, check=True
    ).stdout.split()
    pos = 0

    def take() -> str:
        nonlocal pos
        pos += 1
        return got[pos - 1]

    out = []
    for _ in segments:
        cells = []
        for _ in range(int(take())):
            cell = []
            for _ in range(int(take())):
                m = int(take())
                cell.append([[float(take()), float(take())] for _ in range(m)])
            cells.append(cell)
        out.append(cells)
    return out


class Recording:
    """The core's entry points, each call recorded (``sfc._core`` returns this)."""

    def __init__(self, core: Any, rec: dict) -> None:
        self.core, self.rec = core, rec

    def curve_graph(self, segments, borders, openings, spacing, key, params, report):
        found, cells, lost = self.core.curve_graph(
            segments, borders, openings, spacing, key, params, report
        )
        self.rec["graphs"][-1].update(
            segments=[[int(ri), rings(rs)] for ri, rs in segments],
            borders=[[int(i), int(j), [pl(ln) for ln in lines]] for i, j, lines in borders],
            params=dict(params),
            cells=recorded_cells(key, spacing, params, openings, segments),
            curves=[[pl(p), [int(r) for r in reg]] for p, reg in found],
            ncells=int(cells),
            lost=[int(r) for r in lost],
        )
        return found, cells, lost

    def relax_curve(self, curve, stem, regions, target, edge, borders, spacing, least, pitch,
                    offset, params, report):  # fmt: skip
        p, k = self.core.relax_curve(
            curve,
            stem,
            regions,
            target,
            edge,
            borders,
            spacing,
            least,
            pitch,
            offset,
            params,
            report,
        )
        self.rec["relax"].append(
            dict(
                curve=pl(curve),
                stem=pl(stem),
                regions=[rings(z) for z in regions],
                target=float(target),
                edge=pl(edge),
                borders=pl(borders),
                spacing=float(spacing),
                least=float(least),
                pitch=float(pitch),
                offset=[float(v) for v in offset],
                params=dict(params),
                out=pl(p),
                k=int(k),
            )
        )
        return p, k

    def offset_lanes(self, p, k, edge_a, edge_b, n, pitch, spacing, exact, params):
        out = self.core.offset_lanes(p, k, edge_a, edge_b, n, pitch, spacing, exact, params)
        self.rec["lanes"].append(
            dict(
                p=pl(p),
                k=int(k),
                edge_a=pl(edge_a),
                edge_b=pl(edge_b),
                n=int(n),
                pitch=float(pitch),
                spacing=float(spacing),
                exact=[bool(x) for x in exact],
                params=dict(params),
                out=[pl(t) for t in out],
            )
        )
        return out

    def settle_traces(self, lines, pitch, edge, zones, keep, params, report, groups=None,
                      base=None):  # fmt: skip
        out = self.core.settle_traces(lines, pitch, edge, zones, keep, params, report, groups, base)
        self.rec["settle"]["phases"].append(
            {"phases": int(params["phases"]), "out": [pl(t) for t in out]}
        )
        return out

    def smooth_traces(self, lines, tol, max_turn, pitch=0.0, edges=None, give=0.0):
        out = self.core.smooth_traces(lines, tol, max_turn, pitch, edges, give)
        self.rec["output"] = dict(
            call="smooth_traces",
            edges=[pl(e) for e in edges],
            args=dict(tol=tol, max_turn=max_turn, pitch=pitch, give=give),
            out=[pl(t) for t in out],
        )
        return out

    def fit_arcs(self, lines, tol, pitch=0.0, most=0.0, edges=None, max_turn=0.0, give=0.0):
        out = self.core.fit_arcs(lines, tol, pitch, most, edges, max_turn, give)
        self.rec["output"] = dict(
            call="fit_arcs",
            edges=[pl(e) for e in edges],
            args=dict(tol=tol, pitch=pitch, most=most, max_turn=max_turn, give=give),
            out=[pl(r) for r in out],
        )
        return out


def record(spec: dict) -> dict:
    rec: dict = {"name": spec["name"], "note": spec["note"]}
    rec["input"] = {
        "mask": wkt(spec["mask"]),
        "zones": [wkt(z) for z in spec["zones"]],
        "ports": [wkt(p) for p in spec["ports"]],
        "exits": [list(e) for e in spec["exits"]],
        "side": mesh.LEFT,
        "traces": TRACES,
        "pitch": PITCH,
        "seed": spec["seed"],
        "arcs": spec["arcs"],
    }
    parts = partition.partition(
        spec["mask"], spec["zones"], spec["ports"], (1.0, 0.0), PORT, spec["seed"]
    )
    rec["partitions"] = [
        {"area": wkt(p.area), "port": wkt(p.port), "reach": p.reach} for p in parts
    ]
    rec.update(
        graphs=[],
        reassigned=None,
        merged=None,
        relax=[],
        lanes=[],
        unlooped=[],
        opened=[],
        settle={"phases": []},
    )
    saved = {
        n: getattr(sfc, n)
        for n in ("_core", "_curve", "_reassigned", "_merged", "_unlooped", "_opened", "_settle")
    }
    core = sfc._core()
    proxy = Recording(core, rec)

    def curve(regions, owner, spacing, openings, key):
        rec["graphs"].append(
            dict(
                regions=[wkt(r) for r in regions],
                owner=[int(o) for o in owner],
                spacing=float(spacing),
                key=key.hex(),
                openings=[[[float(v) for v in a], [float(v) for v in b]] for a, b in openings],
            )
        )
        return saved["_curve"](regions, owner, spacing, openings, key)

    def reassigned(*a):
        out = saved["_reassigned"](*a)
        rec["reassigned"] = out
        return out

    def merged(*a):
        out = saved["_merged"](*a)
        if out is not None:
            rec["merged"] = {"regions": [wkt(r) for r in out[0]], "owner": list(out[1])}
        return out

    def unlooped(ring, most):
        out = saved["_unlooped"](ring, most)
        rec["unlooped"].append([float(most), pl(out)])
        return out

    def opened(ring, cut):
        out = saved["_opened"](ring, cut)
        rec["opened"].append([wkt(cut), pl(out)])
        return out

    def settle(lines, pitch, area, regions, keep, groups=None, ribbon=None):
        rec["settle"].update(
            lines=[pl(t) for t in lines],
            pitch=float(pitch),
            area=wkt(area),
            regions=[wkt(r) for r in regions],
            keep=wkt(keep),
            groups=list(groups),
            ribbon=int(ribbon),
        )
        out = saved["_settle"](lines, pitch, area, regions, keep, groups, ribbon)
        rec["settle"]["out"] = [pl(t) for t in out]
        return out

    sfc._core = lambda: proxy
    sfc._curve, sfc._reassigned, sfc._merged = curve, reassigned, merged
    sfc._unlooped, sfc._opened, sfc._settle = unlooped, opened, settle
    try:
        m = sfc.generate(
            spec["mask"],
            spec["exits"],
            mesh.LEFT,
            TRACES,
            PITCH,
            seed=spec["seed"],
            zones=spec["zones"],
            arcs=spec["arcs"],
            partitions=[p.area for p in parts],
            stems=[p.reach for p in parts],
        )
    finally:
        for n, f in saved.items():
            setattr(sfc, n, f)
    rec["mesh"] = {
        "traces": [pl(t) for t in m.traces],
        "unreached": int(m.unreached),
        "cells": int(m.cells),
        "groups": list(m.groups),
    }
    return rec


def main() -> None:
    names = [n for n in dir(sfc) if n.isupper() and isinstance(getattr(sfc, n), (int, float))]
    data = {
        "version": 1,
        "constants": {n: getattr(sfc, n) for n in sorted(names)},
        "cases": [record(spec) for spec in case_inputs()],
    }
    shared = ("graphs", "reassigned", "merged", "relax", "lanes", "unlooped", "opened", "settle")
    for i, c in enumerate(data["cases"]):
        for earlier in data["cases"][:i]:
            if "same_as" not in str(earlier["graphs"])[:20] and all(
                c[k] == earlier[k] for k in shared
            ):
                for k in shared:
                    c[k] = {"same_as": earlier["name"]}
                break
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    for c in data["cases"]:
        if isinstance(c["graphs"], dict):
            print(
                f"{c['name']:>11}: steps as {c['graphs']['same_as']}, "
                f"output {c['output']['call']}, traces {[len(t) for t in c['mesh']['traces']]}"
            )
            continue
        g = c["graphs"]
        print(
            f"{c['name']:>11}: graphs {len(g)}, cells {[x['ncells'] for x in g]}, "
            f"lost {[x['lost'] for x in g]}, curve vertices {[len(r['out']) for r in c['relax']]}, "
            f"traces {[len(t) for t in c['mesh']['traces']]}, unreached {c['mesh']['unreached']}"
        )
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KiB)")


if __name__ == "__main__":
    main()
