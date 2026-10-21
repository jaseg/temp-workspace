"""Cut a window out of a settling phase's checkpoint (``…-settle``/``-fill``/``-finish``
``.in.json.gz``, see ``yanartas_pillowbox.checkpoint``): a small case of the same step, run
in seconds (``run``), to look at one spot of a whole board's layout.

Each trace's runs in the window are traces of their own (their ends held, as a trace's
are), a pair's runs side by side next to each other, as the whole board's are, in groups of
their own; the zones, what is kept as laid and the edge's points cut to the window.

    uv run python scripts/crop_checkpoint.py IN.json.gz OUT.json.gz X0 Y0 X1 Y1
    uv run python scripts/crop_checkpoint.py --run OUT.json.gz [RESULT.json.gz]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import shapely

from yanartas_pillowbox import checkpoint


def crop(src: Path, dst: Path, box: tuple[float, float, float, float]) -> None:
    d = checkpoint.load(src)
    lines, pitch, edge, zones, keep, params, groups, *_ = d["args"]
    groups = groups or [0] * len(lines)
    w = shapely.box(*box)
    x0, y0, x1, y1 = box

    def runs(line: np.ndarray) -> list[np.ndarray]:
        inside = (line[:, 0] >= x0) & (line[:, 0] <= x1) & (line[:, 1] >= y0) & (line[:, 1] <= y1)
        out, k = [], 0
        while k < len(line):
            if not inside[k]:
                k += 1
                continue
            a = k
            while k < len(line) and inside[k]:
                k += 1
            if k - a >= 2:
                out.append(line[a:k])
        return out

    pieces = [(t, r) for t, line in enumerate(lines) for r in runs(np.asarray(line))]
    # (a pair's runs side by side: each run of a group's first trace, then the nearest run
    # of the next trace of its group, and so on; the rest each alone)
    used = [False] * len(pieces)
    order: list[tuple[int, int]] = []  # (piece, new group)
    g = 0
    for j, (t, r) in enumerate(pieces):
        if used[j] or (t > 0 and groups[t - 1] == groups[t]):
            continue
        used[j] = True
        order.append((j, g))
        cur, u = r, t + 1
        while u < len(lines) and groups[u] == groups[t]:
            near = [
                (shapely.LineString(cur).distance(shapely.LineString(pieces[k][1])), k)
                for k in range(len(pieces))
                if not used[k] and pieces[k][0] == u
            ]
            if not near or min(near)[0] > 2 * pitch:
                break
            k = min(near)[1]
            used[k] = True
            order.append((k, g))
            cur, u = pieces[k][1], u + 1
        g += 1
    for j in range(len(pieces)):
        if not used[j]:
            order.append((j, g))
            g += 1

    def cut(polys: list[list[np.ndarray]]) -> list[list[np.ndarray]]:
        out = []
        for rings in polys:
            poly = shapely.Polygon(rings[0], rings[1:]).intersection(w)
            for p in shapely.get_parts(poly):
                if isinstance(p, shapely.Polygon) and p.area > 0:
                    out.append(
                        [np.asarray(p.exterior.coords)]
                        + [np.asarray(i.coords) for i in p.interiors]
                    )
        return out

    e = np.asarray(edge)
    m = 3 * pitch
    e = e[(e[:, 0] >= x0 - m) & (e[:, 0] <= x1 + m) & (e[:, 1] >= y0 - m) & (e[:, 1] <= y1 + m)]
    args = (
        [pieces[j][1] for j, _ in order], pitch, e, cut(zones), cut(keep), params,
        [gg for _, gg in order],
    )  # fmt: skip
    checkpoint.save(dst, {"step": d["step"], "args": args, "kwargs": {},
                          "from": str(src), "box": list(box),
                          "traces": [pieces[j][0] for j, _ in order]})  # fmt: skip
    print(f"{len(order)} runs of {len({pieces[j][0] for j, _ in order})} traces, {g} groups")


def run(src: Path, dst: Path | None) -> None:
    out = checkpoint.resume(src)
    if dst is not None:
        checkpoint.save(dst, {"step": checkpoint.load(src)["step"], "out": out})
    print(f"{len(out)} traces")


if __name__ == "__main__":
    if sys.argv[1] == "--run":
        run(Path(sys.argv[2]), Path(sys.argv[3]) if len(sys.argv) > 3 else None)
    else:
        crop(Path(sys.argv[1]), Path(sys.argv[2]), tuple(float(v) for v in sys.argv[3:7]))
