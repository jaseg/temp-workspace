"""Runs every simulation behind the README and stores the numbers in ../results/*.json.

  python3 experiments.py            # everything (about half an hour on 4 cores)
  python3 experiments.py waves      # only one group: waves | aperture | system
"""
from __future__ import annotations

import dataclasses
import json
import multiprocessing as mp
import os
import sys

import numpy as np

import frontend as f
import wave as w

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")

# The four cases. The redriver's mode is not known from the data available (see README),
# so both of its possible behaviours are simulated.
CASES = {
    "redriver-linear": dict(topology="redriver", rd_gain_db=0.0, rd_eq_db=5.6, vccio=1.2, fpga_rout=30.0),
    "redriver-limiting": dict(topology="redriver", rd_gain_db=20.0, rd_eq_db=0.0, vccio=1.2, fpga_rout=30.0),
    "direct-1v2": dict(topology="direct", vccio=1.2, fpga_rout=30.0),
    "direct-3v3": dict(topology="direct", vccio=3.3, fpga_rout=12.0),
}
FPGA_TR = [150e-12, 300e-12, 600e-12]     # 20-80 %, unknown for this FPGA: swept
OVERDRIVE = [0.50, 0.65, 0.80]            # V, peak forward voltage the strobe puts across a bridge leg


def case(name: str, **kw) -> f.Params:
    return dataclasses.replace(f.Params(), **CASES[name], **kw)


# ------------------------------------------------------------------ waveforms
def strobe_shape(args: tuple[str, float]) -> dict:
    """Strobe pulse with the bridges held off, and the stimulus edge, for one case."""
    name, tr = args
    p = case(name, fpga_tr=tr, vbias=1.0, t_stim=6e-9, t_strobe=6e-9, mesh_td=1e-9, mesh_term=50.0)
    W = w.waves(p)
    t = W["t"]
    nt = W["nt_n"] - W["nt_p"]
    pk, fwhm, tpk = w.pulse(t, nt, p.t_strobe - 0.2e-9, p.t_strobe + 3e-9)
    out = dict(case=name, fpga_tr=tr, strobe_peak=pk, strobe_fwhm=fwhm, strobe_delay=tpk - p.t_strobe)
    for key, sig in (("fpga_pin", W["stim_a_p"] - W["stim_a_n"]), ("hs", W["hs_p"] - W["hs_n"]),
                     ("tdr_port", W["tdr_p"] - W["tdr_n"])):
        tr1090, amp, t50 = w.edge(t, sig, p.t_stim - 0.3e-9, p.t_stim + 2.5e-9)
        out[f"stim_{key}_tr"] = tr1090
        out[f"stim_{key}_amp"] = amp
        out[f"stim_{key}_delay"] = t50 - p.t_stim
    m = (t > p.t_stim - 0.5e-9) & (t < p.t_stim + 3e-9)
    out["wave"] = dict(t=(t[m] - p.t_stim).tolist(), strobe=(nt[m] + 2 * p.vbias).tolist(),
                       stim_hs=(W["hs_p"] - W["hs_n"])[m].tolist(),
                       stim_tdr=(W["tdr_p"] - W["tdr_n"])[m].tolist())
    return out


# ------------------------------------------------------- equivalent-time scans
def sample_point(args: tuple[f.Params, float]) -> dict:
    p, x = args
    r = f.steady_state(p)
    return dict(x=x, v=r["v_p"] - r["v_n"], eff=(r["eff_p"] + r["eff_n"]) / 2)


def aperture(pool: mp.pool.Pool, name: str, tr: float, vbias: float, shape: dict) -> dict:
    """Step response of the sampler alone: a 1 ps, 50 R step on SPL_HS, sampled at a
    sweep of strobe delays. x is the time of the strobe peak minus the time of the step."""
    base = case(name, fpga_tr=tr, vbias=vbias, stim="ideal", t_prep=0.5e-9, t_strobe=5e-9, t_tail=4e-9)
    d = shape["strobe_delay"]

    def scan(xs: np.ndarray) -> list[dict]:
        return pool.map(sample_point, [(dataclasses.replace(base, t_stim=base.t_strobe + d - x), float(x)) for x in xs])

    pts = scan(np.arange(-1.5e-9, 1.5001e-9, 0.1e-9))
    v = np.array([q["v"] for q in pts])
    x = np.array([q["x"] for q in pts])
    lo, hi = np.nanmean(v[:3]), np.nanmean(v[-3:])
    n = (v - lo) / (hi - lo)
    inside = np.flatnonzero((n > 0.03) & (n < 0.97))
    if len(inside):
        a, b = x[max(inside[0] - 1, 0)], x[min(inside[-1] + 1, len(x) - 1)]
        fine = np.setdiff1d(np.round(np.linspace(a, b, 25), 13), np.round(x, 13))
        pts += scan(fine)
    pts.sort(key=lambda q: q["x"])
    x = np.array([q["x"] for q in pts])
    v = np.array([q["v"] for q in pts])
    n = (v - lo) / (hi - lo)
    res = dict(case=name, fpga_tr=tr, vbias=vbias, x=x.tolist(), v=v.tolist(),
               eff=[q["eff"] for q in pts], gain=(hi - lo) / (2 * base.ideal_step),
               tr_10_90=w.crossing(x, n, 0.9) - w.crossing(x, n, 0.1),
               tr_20_80=w.crossing(x, n, 0.8) - w.crossing(x, n, 0.2))
    res["eff_plateau"] = float(np.mean(res["eff"][-3:]))
    return res


def system(pool: mp.pool.Pool, name: str, tr: float, vbias: float, shape: dict) -> dict:
    """What the instrument would record: FPGA edge through the splitter into an open
    1 ns line, sampled bridge voltage against strobe delay."""
    base = case(name, fpga_tr=tr, vbias=vbias, t_stim=6e-9, mesh_td=1e-9, t_tail=4e-9)
    d = shape["strobe_delay"]
    xs = np.arange(-0.6e-9, 4.2001e-9, 0.05e-9)
    pts = pool.map(sample_point, [(dataclasses.replace(base, t_strobe=base.t_stim + x - d), float(x)) for x in xs])
    return dict(case=name, fpga_tr=tr, vbias=vbias, x=[q["x"] for q in pts], v=[q["v"] for q in pts],
                eff=[q["eff"] for q in pts])


def save(name: str, obj) -> None:
    os.makedirs(RES, exist_ok=True)
    with open(os.path.join(RES, name), "w") as fh:
        json.dump(obj, fh, indent=1)


def load(name: str):
    with open(os.path.join(RES, name)) as fh:
        return json.load(fh)


def main() -> None:
    what = sys.argv[1:] or ["waves", "aperture", "system"]
    with mp.Pool(4) as pool:
        if "waves" in what:
            save("waves.json", pool.map(strobe_shape, [(n, tr) for n in CASES for tr in FPGA_TR]))
        shapes = {(s["case"], s["fpga_tr"]): s for s in load("waves.json")}
        if "aperture" in what:
            out = []
            for name in CASES:
                for tr in FPGA_TR:
                    s = shapes[(name, tr)]
                    for od in OVERDRIVE if tr == 300e-12 else [0.65]:
                        r = aperture(pool, name, tr, (s["strobe_peak"] - od) / 2, s)
                        r["overdrive"] = od
                        out.append(r)
                        print(name, tr, od, "vbias %.3f  tr10-90 %.0f ps  gain %.3f  eff %.3f" % (
                            r["vbias"], r["tr_10_90"] * 1e12, r["gain"], r["eff_plateau"]), flush=True)
                        save("aperture.json", out)
        if "system" in what:
            out = []
            for name in CASES:
                s = shapes[(name, 300e-12)]
                out.append(system(pool, name, 300e-12, (s["strobe_peak"] - 0.65) / 2, s))
                print("system", name, flush=True)
                save("system.json", out)


if __name__ == "__main__":
    main()
