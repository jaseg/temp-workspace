"""Export the partitioner's test cases for the notebook (``partition.ipynb``).

Runs the original implementation (``yanartas_pillowbox.partition.partition``) on a few
small, representative cases and writes ``partition_cases.json`` next to this script: each
case's input, the geometry after each major step, and the output. The notebook ports the
algorithm and checks itself against this file. Run from the repository (the package and
its Rust core installed, e.g. ``uv run python docs/partition/export_cases.py``).

The intermediates are recorded by wrapping the implementation's own functions while
``partition.partition`` runs, so they are exactly what it computed; nothing here repeats
its logic.

JSON schema
-----------
Geometry is WKT at full precision (``shapely.to_wkt(g, rounding_precision=-1)``); an
*owner* is a list with each cell's partition (an index into the ports), in cell order.

{
  "version": 1,
  "shapely": str, "numpy": str,             # versions the file was made with
  "constants": {name: number, ...},         # partition.py's module constants used
  "cases": [
    {
      "name": str, "note": str,             # short name; what the case demonstrates
      "input": {
        "area": WKT, "zones": [WKT], "ports": [WKT],
        "inward": [x, y], "width": float, "seed": int
      },
      "setup": {                            # _Cells.__init__: once per call
        "lanes": [WKT],                     # each port's strip
        "ends": [[x, y]],                   # each strip end's pinned cell seed
        "voronoi": {"cells": [WKT], "zone": [int], "front": [int]},  # cells(): as made
        "cells": {"cells": [WKT], "zone": [int], "front": [int]},    # after the end boxes
        "walls": {"a": [int], "b": [int], "length": [float]},       # _walls (a < b)
        "nbrs": [[int]],                    # each cell's neighbours, walls >= 0.99 width
        "loose": [[int]],                   # ... walls >= 1e-3
        "area": [float], "held": [float], "want": [float],
        "probes": {"xy": [[x, y]], "always": [bool]}  # _Necks: points; outline-near
      },
      "attempts": [                         # _Cells.attempt, in order
        {
          "weighted": owner,                # _weighted (the -1s handed on: see "grown")
          "grown": owner,                   # every cell given a partition
          "refined": owner,                 # _refine
          "widened": owner,                 # _widened
          "balanced": owner,                # _refine guarded by _Necks.spares
          "necks": int,                     # _Necks.left after it
          "off": float                      # (max - min) / max of the partitions' areas
        }
      ],
      "chosen": int,                        # the attempt finished
      "pinched": owner,                     # _pinched on the chosen attempt
      "output": [{"area": WKT, "port": WKT, "reach": float}],  # partition()'s result
      "error": null | str                   # partition()'s MeshError, if it raised
    }
  ]
}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from shapely.geometry import Polygon

from yanartas_pillowbox import partition as P

OUT = Path(__file__).with_name("partition_cases.json")
PORT = 1.2  # a port's width: 2 traces at 0.3 mm pitch, out and back


def wkt(g: shapely.Geometry) -> str:
    return shapely.to_wkt(g, rounding_precision=-1)


def ports(count: int, x: float, y: float) -> list[Polygon]:
    """``count`` ports in a row up the junction at x, centred on y."""
    y0 = y - count * PORT / 2
    return [shapely.box(x, y0 + k * PORT, x + PORT, y0 + (k + 1) * PORT) for k in range(count)]


def leads(area: shapely.Geometry, ps: list[Polygon]) -> shapely.Geometry:
    """The area less the leads' strip left of the ports (as ``pcb`` cuts it)."""
    x = ps[0].bounds[0]
    return area.difference(shapely.box(x - 1, ps[0].bounds[1], x, ps[-1].bounds[3]))


def case_inputs() -> list[dict]:
    box = shapely.box(0, 0, 40, 28)
    halves = [shapely.box(0, 0, 20, 28), shapely.box(20, 0, 40, 28)]
    out = []
    ps = ports(3, 0, 14)
    out.append(dict(
        name="typical",
        note="a rectangle over two panels, 3 partitions: the usual run, borders bend to the fold",
        area=leads(box, ps), zones=halves, ports=ps, seed=1,
    ))  # fmt: skip
    ps = ports(1, 0, 14)
    out.append(dict(
        name="single",
        note="one partition: it is the whole area, nothing to balance",
        area=leads(box, ps), zones=halves, ports=ps, seed=2,
    ))  # fmt: skip
    ps = ports(6, 0, 14)
    out.append(dict(
        name="six",
        note="6 partitions from one row of exits: crowded exits, middle strips longest",
        area=leads(box, ps), zones=halves, ports=ps, seed=3,
    ))  # fmt: skip
    # Two lobes joined by a corridor 2.4 wide: the area itself narrow (no neck counted).
    dumb = shapely.union_all([
        shapely.box(0, 0, 18, 28), shapely.box(18, 12.8, 26, 15.2), shapely.box(26, 0, 44, 28),
    ])  # fmt: skip
    ps = ports(3, 0, 14)
    out.append(dict(
        name="dumbbell",
        note="two lobes through a one-cell corridor: no even split exists (an error)",
        area=leads(dumb, ps), zones=[dumb], ports=ps, seed=4,
    ))  # fmt: skip
    # A fold slanting down past the ports' strips: the strips' order changes.
    ps = ports(3, 0, 14)
    low = Polygon([(0, 0), (40, 0), (40, 5), (0, 17)])
    high = Polygon([(0, 17), (40, 5), (40, 28), (0, 28)])
    out.append(dict(
        name="fold-at-exits",
        note="a fold slanting past the exits: the strips' order rearranged, each end in one panel",
        area=leads(box, ps), zones=[low, high], ports=ps, seed=5,
    ))  # fmt: skip
    # An L with a flap: partitions reach round corners; necks appear and are widened.
    ell = shapely.union_all([shapely.box(0, 0, 30, 28), shapely.box(30, 0, 52, 10)])
    ps = ports(4, 0, 14)
    out.append(dict(
        name="necks",
        note="an L-shaped area, 4 partitions: necks found and widened, several attempts",
        area=leads(ell, ps), zones=[shapely.box(0, 0, 30, 28), shapely.box(30, 0, 52, 10)],
        ports=ps, seed=NECK_SEED,
    ))  # fmt: skip
    return out


NECK_SEED = 11


def record(spec: dict) -> dict:
    rec: dict = {"name": spec["name"], "note": spec["note"]}
    rec["input"] = {
        "area": wkt(spec["area"]), "zones": [wkt(z) for z in spec["zones"]],
        "ports": [wkt(p) for p in spec["ports"]], "inward": [1.0, 0.0], "width": PORT,
        "seed": spec["seed"],
    }  # fmt: skip
    setup: dict = {}
    attempts: list[dict] = []
    final: dict = {}
    cur: dict = {}
    saved = {
        name: getattr(P, name) for name in ("cells", "_weighted", "_refine", "_widened", "_pinched")
    }
    init, attempt = P._Cells.__init__, P._Cells.attempt

    def cells(*a: Any, **k: Any) -> Any:
        polys, zone, front = saved["cells"](*a, **k)
        setup["voronoi"] = {
            "cells": [wkt(p) for p in polys], "zone": list(zone), "front": list(front)
        }  # fmt: skip
        return polys, zone, front

    def weighted(*a: Any, **k: Any) -> Any:
        o = saved["_weighted"](*a, **k)
        cur["weighted"] = o.tolist()
        return o

    def refine(owner: np.ndarray, *a: Any, **k: Any) -> np.ndarray:
        # (the attempt's owner after the -1s are handed on: what the first refine gets)
        if "grown" not in cur:
            cur["grown"] = owner.tolist()
        o = saved["_refine"](owner, *a, **k)
        cur["balanced" if k.get("guard") or len(a) > 5 else "refined"] = o.tolist()
        return o

    def widened(*a: Any, **k: Any) -> Any:
        o = saved["_widened"](*a, **k)
        cur["widened"] = o.tolist()
        return o

    def pinched(*a: Any, **k: Any) -> Any:
        o = saved["_pinched"](*a, **k)
        final["pinched"] = o.tolist()
        return o

    def init_(self: P._Cells, *a: Any, **k: Any) -> None:
        init(self, *a, **k)
        n = self.necks
        setup.update(
            lanes=[wkt(g) for g in self.lanes],
            cells={
                "cells": [wkt(p) for p in self.arr], "zone": list(self.zone),
                "front": list(self.front),
            },
            nbrs=[[j for j, _ in v] for v in self.nbrs],
            loose=[[j for j, _ in v] for v in self.loose],
            area=self.area.tolist(), held=self.held.tolist(), want=self.want.tolist(),
        )  # fmt: skip
        ends = []
        for s in self.lanes:  # (as _Cells.__init__ computes them)
            d = shapely.get_coordinates(s) @ self.inv
            c = np.asarray(s.centroid.coords[0])
            mid = c + self.inv * (float(d.max()) - float(c @ self.inv))
            ends.append((mid + self.inv * P.CELL * self.width / 2).tolist())
        setup["ends"] = ends
        walls = P._walls(list(self.arr))
        setup["walls"] = {"a": walls[0].tolist(), "b": walls[1].tolist(),
                          "length": shapely.length(walls[2]).tolist()}  # fmt: skip
        setup["probes"] = {
            "xy": shapely.get_coordinates(n.probes).tolist(), "always": n.always.tolist()
        }  # fmt: skip

    def finished(self: P._Cells, owner: np.ndarray) -> list[P.Partition]:
        final["chosen"] = next(i for i, a in enumerate(attempts) if a["balanced"] == owner.tolist())
        return finish(self, owner)

    def attempt_(self: P._Cells, rng: Any) -> tuple[np.ndarray, int]:
        cur.clear()
        owner, necks = attempt(self, rng)
        have = np.bincount(owner, self.area, len(self.front)) + self.held
        off = float((have.max() - have.min()) / have.max())
        attempts.append({**cur, "necks": int(necks), "off": off})
        return owner, necks

    finish = P._Cells.finished
    P.cells, P._weighted, P._refine = cells, weighted, refine
    P._widened, P._pinched = widened, pinched
    P._Cells.__init__, P._Cells.attempt, P._Cells.finished = init_, attempt_, finished
    try:
        fn = getattr(P.partition, "__wrapped__", P.partition)
        parts = fn(spec["area"], spec["zones"], spec["ports"], (1.0, 0.0), PORT, spec["seed"])
        rec["error"] = None
    except P.MeshError as e:
        parts, rec["error"] = [], str(e)
    finally:
        for name, f in saved.items():
            setattr(P, name, f)
        P._Cells.__init__, P._Cells.attempt, P._Cells.finished = init, attempt, finish
    rec["setup"] = setup
    rec["attempts"] = attempts
    rec["chosen"] = final.get("chosen")  # (the attempt finished: the last, if several)
    rec["pinched"] = final.get("pinched")
    rec["output"] = [{"area": wkt(p.area), "port": wkt(p.port), "reach": p.reach} for p in parts]
    return rec


def main() -> None:
    names = [
        "LLOYD", "CELL", "STRIP", "STAGGER", "FOLD", "NOISE", "FIELD", "WAVES", "ITERATIONS",
        "SMOOTH", "ACROSS", "BALANCE", "HOPS", "ATTEMPTS", "UNEVEN", "LOPSIDED", "NECK",
        "PART", "WALL", "WIDEN",
    ]  # fmt: skip
    data = {
        "version": 1, "shapely": shapely.__version__, "numpy": np.__version__,
        "constants": {n: getattr(P, n) for n in names},
        "cases": [record(spec) for spec in case_inputs()],
    }  # fmt: skip
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    for c in data["cases"]:
        tries = [(a["necks"], round(a["off"], 3)) for a in c["attempts"]]
        print(f"{c['name']:>14}: {len(c['setup']['cells']['cells'])} cells, attempts {tries}, "
              f"chosen {c['chosen']}, error {c['error']}")  # fmt: skip
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KiB)")


if __name__ == "__main__":
    main()
