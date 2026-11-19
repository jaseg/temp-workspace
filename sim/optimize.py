"""Sampler optimisation on the existing board: VCCIO1, strobe through U2 or bypassing it,
and the bridge bias. Sampler measured alone (ideal step on SPL_HS), as in experiments.aperture.

  python3 optimize.py      # writes ../results/optimize.json
"""
from __future__ import annotations

import dataclasses
import json
import multiprocessing as mp
import os

import numpy as np

import experiments as e
import frontend as f

ROUT = {1.2: 30.0, 1.8: 20.0, 2.5: 15.0, 3.3: 12.0}     # FPGA buffer, estimate from the DC drive spec
STROBE = {
    "U2 limiting": dict(topology="redriver", rd_gain_db=20.0, rd_eq_db=0.0),
    "U2 linear": dict(topology="redriver", rd_gain_db=0.0, rd_eq_db=5.6),
    **{f"bypass, VCCIO {v} V": dict(topology="direct", vccio=v, fpga_rout=ROUT[v]) for v in ROUT},
}
VBIAS = [-0.10, 0.0, 0.10, 0.20, 0.30, 0.40, 0.55, 0.70]   # VBIAS_K = GNDS + vbias, VBIAS_A = GNDS - vbias


def curve(pool, name: str, tr: float, vbias: float, r_bridge: float = 91.0) -> dict | None:
    kw = dict(STROBE[name])
    kw.setdefault("vccio", 1.2)
    kw.setdefault("fpga_rout", ROUT[kw["vccio"]])
    base = dataclasses.replace(f.Params(), **kw, fpga_tr=tr, vbias=vbias, r_bridge=r_bridge, stim="ideal",
                               t_prep=0.5e-9, t_strobe=5e-9, t_tail=4e-9)
    d = 0.7e-9

    def scan(xs):
        return pool.map(e.sample_point, [(dataclasses.replace(base, t_stim=base.t_strobe + d - x), float(x)) for x in xs])

    first = scan([1.5e-9])[0]
    if not first["eff"] > 0.01:
        return dict(strobe=name, fpga_tr=tr, vbias=vbias, r_bridge=r_bridge, eff=first["eff"], usable=False)
    pts = scan(np.arange(-1.5e-9, 1.5001e-9, 0.1e-9))
    x = np.array([q["x"] for q in pts]); v = np.array([q["v"] for q in pts])
    lo, hi = np.mean(v[:3]), np.mean(v[-3:])
    n = (v - lo) / (hi - lo)
    ins = np.flatnonzero((n > 0.03) & (n < 0.97))
    if len(ins):
        a, b = x[max(ins[0] - 1, 0)], x[min(ins[-1] + 1, len(x) - 1)]
        pts += scan(np.setdiff1d(np.round(np.linspace(a, b, 21), 13), np.round(x, 13)))
    pts.sort(key=lambda q: q["x"])
    x = np.array([q["x"] for q in pts]); v = np.array([q["v"] for q in pts])
    n = (v - lo) / (hi - lo)
    import wave as w
    t50 = w.crossing(x, n, 0.5)
    return dict(strobe=name, fpga_tr=tr, vbias=vbias, r_bridge=r_bridge, usable=True, x=x.tolist(), n=n.tolist(),
                tr_10_90=w.crossing(x, n, 0.9) - w.crossing(x, n, 0.1), gain=(hi - lo) / (2 * base.ideal_step),
                eff=float(np.mean([q["eff"] for q in pts[-3:]])), overshoot=float(np.nanmax(n) - 1),
                undershoot=float(-np.nanmin(n)),
                # how far the response still is from its end value 0.5 ns after the 50 % point
                tail=float(1 - np.interp(t50 + 0.5e-9, x, n)))


def main() -> None:
    path = os.path.join(e.RES, "optimize.json")
    out = json.load(open(path)) if os.path.exists(path) else []
    done = {(r["strobe"], r["fpga_tr"], r["vbias"], r["r_bridge"]) for r in out}
    jobs = [(n, 300e-12, vb, 91.0) for n in STROBE for vb in VBIAS]
    jobs += [(n, tr, vb, 91.0) for n in ("U2 limiting", "bypass, VCCIO 3.3 V", "bypass, VCCIO 2.5 V") for tr in (150e-12, 600e-12) for vb in VBIAS]
    with mp.Pool(4) as pool:
        for job in jobs:
            if job in done:
                continue
            r = curve(pool, *job)
            out.append(r)
            print(job, "eff %.3f" % r["eff"] if not r["usable"] else "tr %.0f ps gain %.2f eff %.2f over %.2f tail %.2f" % (
                r["tr_10_90"] * 1e12, r["gain"], r["eff"], r["overshoot"], r["tail"]), flush=True)
            json.dump(out, open(path, "w"), indent=1)


if __name__ == "__main__":
    main()
