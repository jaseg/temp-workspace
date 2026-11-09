"""One STEP model through OCCT (FreeCAD 1.1.3's Part module): import, check, measure, mesh, booleans.

Run with FreeCAD's python:  occt_model.py <file.step> <out.json>
Each stage is timed on its own; a stage that raises is recorded and the rest still run.
The boolean stage uses the largest solid S of the model and checks the results against
inclusion-exclusion, which needs no reference answer:
  V(S u T) + V(S n T) = V(S) + V(T)   and   V(S - T) = V(S) - V(S n T)
with T a copy of S moved by 5 % of its bounding-box diagonal along a generic direction
(transversal intersections everywhere), and S u S, S - S (exactly coincident copy).
"""

import json
import math
import sys
import time

sys.path.append(sys.argv[3] if len(sys.argv) > 3 else "")

import FreeCAD  # noqa: E402
import Part  # noqa: E402

path, out = sys.argv[1], sys.argv[2]
res = {"file": path, "kernel": "occt", "occt": Part.OCC_VERSION, "freecad": ".".join(FreeCAD.Version()[:3])}


def stage(name, fn):
    t = time.perf_counter()
    try:
        v = fn()
        res[name + "_s"] = time.perf_counter() - t
        return v
    except Exception as e:  # noqa: BLE001
        res[name + "_s"] = time.perf_counter() - t
        res[name + "_error"] = f"{type(e).__name__}: {e}"[:300]
        return None
    finally:
        json.dump(res, open(out, "w"))  # partial result survives a crash or timeout


shape = stage("read", lambda: Part.read(path))
if shape is not None and not shape.isNull():
    solids = shape.Solids
    res.update(solids=len(solids), shells=len(shape.Shells), faces=len(shape.Faces), edges=len(shape.Edges))
    res["valid"] = stage("check", shape.isValid)
    res["volume"] = stage("volume", lambda: sum(s.Volume for s in solids))
    res["area"] = stage("area", lambda: shape.Area)
    bb = shape.BoundBox
    diag = bb.DiagonalLength
    res["bbox_diag"] = diag
    tri = stage("mesh", lambda: shape.tessellate(diag * 1e-3))
    if tri is not None:
        res["triangles"] = len(tri[1])

    if solids:
        S = max(solids, key=lambda s: abs(s.Volume))
        vs = S.Volume
        res["s_volume"] = vs
        d = FreeCAD.Vector(0.577, 0.4, 0.712)
        d.normalize()
        T = S.copy()
        T.translate(d * (0.05 * S.BoundBox.DiagonalLength))

        def op(name, f, *args):
            r = stage(name, lambda: f(*args))
            if r is not None:
                res[name + "_valid"] = r.isValid()
                res[name + "_vol"] = r.Volume
            return r

        u = op("fuse", S.fuse, T)
        c = op("common", S.common, T)
        k = op("cut", S.cut, T)
        if u is not None and c is not None:
            res["ie_union_err"] = abs(u.Volume + c.Volume - 2 * vs) / abs(vs)
        if k is not None and c is not None:
            res["ie_cut_err"] = abs(k.Volume - (vs - c.Volume)) / abs(vs)
        S2 = S.copy()
        su = op("self_fuse", S.fuse, S2)
        if su is not None:
            res["self_fuse_err"] = abs(su.Volume - vs) / abs(vs)
        sc = op("self_cut", S.cut, S2)
        if sc is not None:
            res["self_cut_err"] = abs(sc.Volume) / abs(vs)
res["done"] = True
json.dump(res, open(out, "w"))
print(json.dumps({k: v for k, v in res.items() if not isinstance(v, float) or math.isfinite(v)}))
