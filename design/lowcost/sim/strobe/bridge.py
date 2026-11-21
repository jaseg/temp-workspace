"""Re-run the sampler bridge deck (sim/scope_sampler.py, case D: fixed +/-1 V bias, 10 R source,
balun, shorted clip stub) with the simulated strobe-chain waveform instead of its ideal ramp.

The chain output is a 50 R source (behavioural model), so its Thevenin voltage is 2 * v(out into 50 R);
it replaces Vdrv/Rdrv of the deck.  python3 bridge.py
"""
from __future__ import annotations

import dataclasses
import json
import multiprocessing as mp
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "sim"))
import scope_sampler as ss  # noqa: E402
import wave as w  # noqa: E402

import chain  # noqa: E402

_orig_build = ss.build
WAVE: dict = {}


def build(p: ss.P) -> str:
    text = _orig_build(p)
    if not WAVE:
        return text
    t, v = WAVE["t"], WAVE["v"]
    tt = t - WAVE["t50"] + p.t_strobe + 50e-12
    keep = (tt > p.t_strobe - 0.8e-9) & (tt < p.t_strobe + 1.5e-9)
    tt, vv = tt[keep], v[keep]
    idx = np.unique(np.r_[0, np.searchsorted(tt, np.arange(tt[0], tt[-1], 2e-12)), len(tt) - 1])
    pts = [(0.0, vv[0])] + list(zip(tt[idx], vv[idx]))
    pts = [(a, b) for a, b in pts if a >= 0]
    pwl = " ".join(f"{a:.5g} {2 * (b - vv[0]):.5g}" for a, b in pts)
    return re.sub(r"^Vdrv drv_e 0 pwl\(.*\)$", f"Vdrv drv_e 0 pwl({pwl})", text, count=1, flags=re.M)


ss.build = build


def step_response(pool, p: ss.P, label: str) -> dict:
    def scan(xs):
        return pool.map(ss.point, [(dataclasses.replace(p, t_in=p.t_strobe - x), float(x)) for x in xs])
    pts = scan(np.arange(-1.0e-9, 1.0001e-9, 0.1e-9))
    x = np.array([q["x"] for q in pts]); v = np.array([q["v"] for q in pts])
    lo, hi = v[:3].mean(), v[-3:].mean()
    n = (v - lo) / (hi - lo)
    ins = np.flatnonzero((n > 0.03) & (n < 0.97))
    if len(ins):
        a, b = x[max(ins[0] - 1, 0)], x[min(ins[-1] + 1, len(x) - 1)]
        pts += scan(np.setdiff1d(np.round(np.linspace(a, b, 17), 13), np.round(x, 13)))
    pts.sort(key=lambda q: q["x"])
    x = np.array([q["x"] for q in pts]); v = np.array([q["v"] for q in pts])
    n = (v - lo) / (hi - lo)
    quiet = ss.run(dataclasses.replace(p, t_in=p.t_strobe + 10e-9, v_ls=-p.in_step / 2))
    return dict(label=label, x=x.tolist(), n=n.tolist(), tr=(w.crossing(x, n, 0.9) - w.crossing(x, n, 0.1)) * 1e12,
                overshoot=float(n.max() - 1), gain=(hi - lo) / p.in_step,
                eff=float(np.mean([q["eff"] for q in pts[-3:]])), drive=quiet["pk_drive"], kick=quiet["kick_pp"])


def chain_wave(name, tr, split, scale=1.0):
    r = chain.edge(chain.CHAINS[name], tr=tr, duty=0.5, split=split, tstop=5e-9)
    a, m, b, lo, hi = chain.t1090(r["t"], r["v(out)"])
    return dict(t=r["t"], v=lo + (r["v(out)"] - lo) * scale, t50=m, tr=(b - a), step=(hi - lo) * scale)


CASES = [
    # label, chain, fpga tr, split, step scale, deck params
    ("ideal 3 V / 40 ps step, 50 ps stub (reference D)", None, 0, "", 1, dict()),
    ("2xTRF, 50 % duty (4.6 V step), 80 ps stub", "2xTRF", 600e-12, "nominal", 1, dict(stub_td=80e-12)),
    ("2xTRF, low duty (2.4 V step), 80 ps stub", "2xTRF", 600e-12, "nominal", 2.4 / 4.59, dict(stub_td=80e-12)),
    ("2xTRF, 50 % duty, pessimistic edge, 80 ps stub", "2xTRF", 600e-12, "pess", 1, dict(stub_td=80e-12)),
    ("2xTRF, 50 % duty, 60 ps stub", "2xTRF", 600e-12, "nominal", 1, dict(stub_td=60e-12)),
    ("2xTRF, 50 % duty, step -25 % (3.4 V), 60 ps stub", "2xTRF", 600e-12, "nominal", 0.75, dict(stub_td=60e-12)),
    ("2xTRF, 50 % duty, step -40 % (2.75 V), 60 ps stub", "2xTRF", 600e-12, "nominal", 0.6, dict(stub_td=60e-12)),
    ("2xTRF, 50 % duty, FPGA 300 ps, 60 ps stub", "2xTRF", 300e-12, "nominal", 1, dict(stub_td=60e-12)),
    ("2xTRF, 50 % duty, pessimistic edge, 60 ps stub", "2xTRF", 600e-12, "pess", 1, dict(stub_td=60e-12)),
    ("2xTRF, 50 % duty, step -25 %, 80 ps stub", "2xTRF", 600e-12, "nominal", 0.75, dict(stub_td=80e-12)),
    ("2xTRF, 50 % duty, step -40 %, 80 ps stub, bias +/-0.6 V", "2xTRF", 600e-12, "nominal", 0.6, dict(stub_td=80e-12, v_rev=1.2)),
    ("2xTRF+GVA, low duty (4.8 V step), 60 ps stub", "TRF+GVA", 600e-12, "nominal", 4.78 / 7.18, dict(stub_td=60e-12)),
]

if __name__ == "__main__":
    only = sys.argv[1:]
    out = []
    path = os.path.join(HERE, "bridge_results.json")
    if os.path.exists(path):
        out = json.load(open(path))
    for i, (label, name, tr, split, scale, kw) in enumerate(CASES):
        if only and str(i) not in only:
            continue
        WAVE.clear()
        if name:
            WAVE.update(chain_wave(name, tr, split, scale))
        p = ss.P(r_in=10.0, **kw)
        with mp.Pool(4) as pool:
            r = step_response(pool, p, label)
        if WAVE:
            r.update(strobe_tr=WAVE["tr"] * 1e12, strobe_step=WAVE["step"])
        out = [o for o in out if o["label"] != label] + [r]
        print("%-50s aperture %4.0f ps  overshoot %3.0f %%  gain %.2f  eff %3.0f %%  drive %.2f V  kick %3.0f mVpp" % (
            label, r["tr"], r["overshoot"] * 100, r["gain"], r["eff"] * 100, r["drive"], r["kick"] * 1e3), flush=True)
        with open(path, "w") as fh:
            json.dump(out, fh, indent=1)
