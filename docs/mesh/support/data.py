"""Loading the recorded cases (mesh_cases.json; its schema: export_mesh_cases.py)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import shapely

SHARED = ("graphs", "reassigned", "merged", "relax", "lanes", "unlooped", "opened", "settle")


def load(path: str | Path = "mesh_cases.json") -> dict:
    """The recording, each case's ``same_as`` references resolved (by name, case)."""
    data = json.loads(Path(path).read_text())
    by_name = {c["name"]: c for c in data["cases"]}
    for c in data["cases"]:
        for k in SHARED:
            if isinstance(c[k], dict) and "same_as" in c[k]:
                c[k] = by_name[c[k]["same_as"]][k]
    data["by_name"] = by_name
    return data


def geom(wkt: str) -> shapely.Geometry:
    return shapely.from_wkt(wkt)


def pts(a: list) -> list[tuple[float, float]]:
    return [tuple(q) for q in a]


def arr(a: list) -> np.ndarray:
    return np.asarray(a, float).reshape(-1, 2)
