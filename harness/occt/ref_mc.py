"""Kernel-independent reference for the boolean stage: V(S), V(S n T) by Monte Carlo point classification.

  ref_mc.py <file.step> <out.json> <freecad-lib> [N]
S is the model's largest solid and T = S moved by 5 % of its bbox diagonal along (0.577, 0.4, 0.712),
exactly as occt_model.py builds them. Classifying points against the *input* solid only (no boolean)
gives V(S n T) with a standard error of about sqrt(p(1-p)/N) of the box volume, enough to catch a
boolean that is wrong by more than a few percent. V(S u T) = 2V(S) - V(S n T), V(S - T) = V(S) - V(S n T).
"""

import json
import random
import sys

sys.path.append(sys.argv[3])
import FreeCAD as App  # noqa: E402
import Part  # noqa: E402

path, out, n = sys.argv[1], sys.argv[2], int(sys.argv[4]) if len(sys.argv) > 4 else 3000
res = {"file": path, "n": n}
sh = Part.read(path)
if sh.Solids:
    S = max(sh.Solids, key=lambda s: abs(s.Volume))
    d = App.Vector(0.577, 0.4, 0.712)
    d.normalize()
    off = d * (0.05 * S.BoundBox.DiagonalLength)
    bb = S.BoundBox
    bv = bb.XLength * bb.YLength * bb.ZLength
    rng = random.Random(1)
    ins = both = 0
    for _ in range(n):
        p = App.Vector(rng.uniform(bb.XMin, bb.XMax), rng.uniform(bb.YMin, bb.YMax), rng.uniform(bb.ZMin, bb.ZMax))
        a = S.isInside(p, 1e-6, True)
        ins += a
        if a and S.isInside(p - off, 1e-6, True):
            both += 1
    pa, pb = ins / n, both / n
    res.update(
        bbox_vol=bv,
        v_s_mc=pa * bv,
        v_s_exact=S.Volume,
        v_common_mc=pb * bv,
        v_common_se=(pb * (1 - pb) / n) ** 0.5 * bv,
    )
json.dump(res, open(out, "w"))
print(json.dumps(res))
