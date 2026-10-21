"""The layout's steps timed and checkpointed: each step's inputs written as it runs, and that
step run again alone from them, as it ran."""

import numpy as np
import pytest
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


def test_a_run_clears_the_last_runs_checkpoints(tmp_path, monkeypatch):
    """A run's checkpoints replace the last run's (the numbering from 000 again); a resume
    neither writes nor clears any."""
    monkeypatch.setenv("YANARTAS_CHECKPOINT", str(tmp_path))
    (tmp_path / "keep.txt").write_text("not a checkpoint")
    p = 0.3
    area = shapely.box(0, 0, 6, 4 * p)
    lines = [np.column_stack([np.linspace(0, 6, 60), np.full(60, (j + 0.5) * p)]) for j in range(4)]
    sfc._settle(lines, p, area, [area], shapely.Polygon(), [0, 0, 1, 1], 4)
    first = sorted(f.name for f in tmp_path.glob("*.json.gz"))
    (tmp_path / "099-x-stale.in.json.gz").write_bytes(b"")
    sfc._settle(lines, p, area, [area], shapely.Polygon(), [0, 0, 1, 1], 4)
    again = sorted(f.name for f in tmp_path.glob("*.json.gz"))
    assert again == first and first[0].startswith("000-")
    checkpoint.resume(tmp_path / first[0])
    assert sorted(f.name for f in tmp_path.glob("*.json.gz")) == first
    assert (tmp_path / "keep.txt").exists()


def test_a_cancelled_layout_stops():
    """Cancelled, a layout stops at its next progress report (and the Rust core's loops at
    their next step); the next one runs again."""
    from yanartas_pillowbox import progress

    p = 0.3
    area = shapely.box(0, 0, 6, 4 * p)
    lines = [np.column_stack([np.linspace(0, 6, 60), np.full(60, (j + 0.5) * p)]) for j in range(4)]
    try:
        progress.cancel()
        with pytest.raises(progress.Cancelled):
            sfc._settle(lines, p, area, [area], shapely.Polygon(), [0, 0, 1, 1], 4)
    finally:
        progress.begin()
    assert len(sfc._settle(lines, p, area, [area], shapely.Polygon(), [0, 0, 1, 1], 4)) == 4
