"""The layout's steps timed and checkpointed: each step's inputs written as it runs, and that
step run again alone from them, as it ran."""

import numpy as np
import shapely

from yanartas_pillowbox import checkpoint, partition, sfc


def test_values_come_back_exactly(tmp_path):
    rng = np.random.default_rng(3)
    v = {
        "a": rng.random((5, 2)),
        "g": shapely.box(0, 0, 1, 2),
        "r": np.random.default_rng(7),
        "t": (1, [2.5, "x"], None),
        "p": partition.Partition(shapely.box(0, 0, 1, 1), shapely.box(0, 0, 0.1, 0.1), 2.0),
    }
    checkpoint.save(tmp_path / "v.json.gz", v)
    w = checkpoint.load(tmp_path / "v.json.gz")
    assert np.array_equal(w["a"], v["a"]) and w["a"].dtype == v["a"].dtype
    assert w["g"].equals(v["g"])
    assert w["r"].random() == np.random.default_rng(7).random()
    assert w["t"] == (1, [2.5, "x"], None)
    assert w["p"].area.equals(v["p"].area) and w["p"].reach == 2.0


def test_a_step_runs_again_from_its_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("YANARTAS_CHECKPOINT", str(tmp_path))
    p, n = 0.3, 4
    area = shapely.union_all([shapely.box(0, 0, 8, n * p), shapely.box(3, n * p, 4.5, n * p + 1.5)])
    x = np.linspace(0, 8, 160)
    lines = [np.column_stack([x, np.full(160, (j + 0.5) * p)]) for j in range(n)]
    checkpoint.reset()
    out = sfc._settle(lines, p, area, [area], shapely.Polygon(), [0, 0, 1, 1], n)
    steps = sorted(f.name for f in tmp_path.glob("*.in.json.gz"))
    assert [s.split("-")[-1].split(".")[0] for s in steps] == ["settle", "fill", "finish"]
    again = checkpoint.resume(tmp_path / steps[-1])
    assert all(np.array_equal(a, b) for a, b in zip(again, out, strict=True))
    assert {name for _, name in checkpoint.times()} >= {"settle", "fill", "finish"}
