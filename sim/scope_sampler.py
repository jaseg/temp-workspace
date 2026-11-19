"""Sampler proposed for the oscilloscope variant (see ../docs/scope-frontend.md).

Differences from the yanartas-sensors bridge, each one a finding of the first study:
  * strobe is a large limited step (fast driver), not a redriver output
  * the step is clipped to a pulse on the single-ended side, then passed through a
    balun, so the bridge rails float (no AC ground on the bridge side)
  * series resistors sit at the diodes, small, and only terminate the balun
  * real reverse bias, larger than the signal
  * small hold capacitor with the buffer next to it
  * single-ended input, driven by a buffer (BUF802) through 50 R

  python3 scope_sampler.py        # runs the sweep and writes ../results/scope-sampler.json
"""
from __future__ import annotations

import dataclasses
import json
import multiprocessing as mp
import os
import re
import subprocess
import tempfile

import numpy as np

import frontend as f
import wave as w

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")


@dataclasses.dataclass
class P:
    v_step: float = 3.0          # strobe driver step into 50 R, V
    tr: float = 40e-12           # its 10-90 % edge
    stub_td: float = 50e-12      # one-way delay of the shorted clip stub
    r_series: float = 25.0       # per rail, at the diodes
    v_rev: float = 2.0           # V(cathode rail) - V(anode rail) at idle
    r_bias: float = 2e3
    c_hold: float = 2.2e-12      # hold capacitor plus buffer input
    l_leak: float = 0.3e-9       # balun leakage, differential
    l_cm: float = 1e-6           # balun common-mode inductance
    c_par: float = 0.3e-12       # each rail to ground: balun winding, pads
    balun: bool = True           # False: rails driven from ground-referenced complementary sources
    bootstrap: bool = False      # bias supplies ride on the buffered hold voltage
    r_in: float = 50.0           # between the input buffer and the bridge
    in_bw: float = 0.0           # input buffer -3 dB, Hz; 0 = ideal 1 ps step
    in_step: float = 0.2         # V
    t_strobe: float = 2e-9
    t_in: float = 2e-9
    t_tail: float = 3e-9
    v_ls: float = 0.0


def build(p: P) -> str:
    d = f.Deck()
    d.add("* scope sampler")
    d.add(f.MODELS)
    tr = p.tr / 0.8
    # strobe driver and clip stub (single-ended side)
    if p.balun:
        d.add(f"Vdrv drv_e 0 pwl(0 0 {p.t_strobe:.6g} 0 {p.t_strobe + tr:.6g} {2 * p.v_step})")
        d.add("Rdrv drv_e drv 50")
        d.trace("drv", "clip", 3.0)
        d.trace("clip", "stub_end", 0, td=p.stub_td)
        d.add("Rstub stub_end 0 0.05")
        d.trace("clip", "bal_in", 2.0)
        # 1:1 transmission-line balun as a common-mode choke
        k = 1 - p.l_leak / (2 * p.l_cm)
        d.add(f"Lb1 bal_in bal_a {p.l_cm}")
        d.add(f"Lb2 0 bal_b {p.l_cm}")
        d.add(f"Kb Lb1 Lb2 {k:.9f}")
        d.add("Rcm1 bal_in bal_a 2k")      # ferrite loss, keeps the choke from ringing
        d.add("Rcm2 0 bal_b 2k")
        d.add("Rterm bal_a bal_b 1k")
        for n in ("a", "b"):
            d.add(f"Cpar{n} bal_{n} 0 {p.c_par}")
            d.cap0402(f"cblk{n}", f"bal_{n}", f"rail_{n}", "1n")
    else:
        # the yanartas arrangement: each rail fed from a ground-referenced 50 R source with its own stub
        for n, s in (("a", 1), ("b", -1)):
            d.add(f"Vdrv{n} drv_e{n} 0 pwl(0 0 {p.t_strobe:.6g} 0 {p.t_strobe + tr:.6g} {s * p.v_step})")
            d.add(f"Rdrv{n} drv_e{n} clip{n} 50")
            d.trace(f"clip{n}", f"stub_end{n}", 0, td=p.stub_td)
            d.add(f"Rstub{n} stub_end{n} 0 0.05")
            d.cap0402(f"cblk{n}", f"clip{n}", f"rail_{n}", "1n")
            d.add(f"Cpar{n} rail_{n} 0 {p.c_par}")
    # bias: anode rail negative, cathode rail positive
    # With bootstrap the bias is referred to the hold voltage (unity buffer, slow in
    # reality, 1 ns here), so at equilibrium the rails are centred on the signal and
    # no common-mode current flows into the rail capacitance during the strobe.
    d.add("Rboot ls_b boot 1k")
    d.add("Cboot boot 0 1p")
    d.add(f"Eboot ls_b 0 ls 0 {1 if p.bootstrap else 0}")
    d.add(f"Vba vba boot {-p.v_rev / 2}")
    d.add(f"Vbk vbk boot {p.v_rev / 2}")
    d.add(f"Rba rail_a vba {p.r_bias}")
    d.add(f"Rbk rail_b vbk {p.r_bias}")
    d.add(f"Ra rail_a ka {p.r_series}")
    d.add(f"Rk rail_b kk {p.r_series}")
    for side in ("ls", "hs"):
        d.add(f"Xda_{side} ka {side} dpk")
        d.add(f"Xdk_{side} {side} kk dpk")
    # input: buffer output through 50 R
    a, b = -p.in_step / 2, p.in_step / 2
    d.add(f"Vin in_e 0 pwl(0 {a} {p.t_in:.6g} {a} {p.t_in + 1e-12:.6g} {b})")
    if p.in_bw:
        d.add("Rbw in_e in_f 1k")
        d.add(f"Cbw in_f 0 {1 / (2 * np.pi * p.in_bw * 1e3):.5g}")
        d.add("Ebuf in_b 0 in_f 0 1")
    else:
        d.add("Ebuf in_b 0 in_e 0 1")
    d.add(f"Rin in_b hs {p.r_in}")
    d.add(f"Ch ls 0 {p.c_hold}")
    d.add(f".ic v(ls)={p.v_ls:.9g}")
    tend = p.t_strobe + p.t_tail
    d.add(".options klu reltol=3e-4 abstol=1e-12 vntol=1e-7")
    d.add(f".tran 1p {tend + 5e-12:.6g} 0 2p")
    d.add(f".meas tran end_ls find v(ls) at={tend:.6g}")
    d.add(".meas tran pk_drive max par('v(ka)-v(kk)')")
    d.add(".meas tran kick_pp pp v(hs)")
    d.add(".end")
    return "\n".join(d.lines) + "\n"


def run(p: P) -> dict[str, float]:
    err = ""
    for tmax in ("2p", "1.7p", "1.3p", "1p"):
        with tempfile.NamedTemporaryFile("w", suffix=".cir", delete=False) as fh:
            fh.write(build(p).replace(" 0 2p\n", f" 0 {tmax}\n"))
            path = fh.name
        try:
            r = subprocess.run(["ngspice", "-b", path], capture_output=True, text=True, timeout=600)
        finally:
            os.unlink(path)
        out = {m.group(1): float(m.group(2)) for m in re.finditer(r"^(end_ls|pk_drive|kick_pp)\s*=\s*([-+0-9.eE]+)", r.stdout, re.M)}
        if len(out) == 3:
            return out
        err = r.stdout[-1500:] + r.stderr[-1500:]
    raise RuntimeError(err)


def point(args: tuple[P, float]) -> dict:
    """Steady-state held voltage for one strobe delay, as in frontend.steady_state."""
    p, x = args
    dv = 0.02
    r0, r1 = run(p), run(dataclasses.replace(p, v_ls=p.v_ls + dv))
    d0, d1 = r0["end_ls"] - p.v_ls, r1["end_ls"] - p.v_ls - dv
    eff = -(d1 - d0) / dv
    return dict(x=x, v=p.v_ls + d0 / eff if eff > 1e-4 else float("nan"), eff=eff, pk=r0["pk_drive"], kick=r0["kick_pp"])


def step_response(pool, p: P, label: str) -> dict:
    """x = strobe edge time minus input step time (the pulse arrives a fixed delay later)."""
    def scan(xs):
        return pool.map(point, [(dataclasses.replace(p, t_in=p.t_strobe - x), float(x)) for x in xs])
    pts = scan(np.arange(-1.0e-9, 1.0001e-9, 0.1e-9))
    x = np.array([q["x"] for q in pts]); v = np.array([q["v"] for q in pts])
    lo, hi = v[:3].mean(), v[-3:].mean()
    n = (v - lo) / (hi - lo)
    ins = np.flatnonzero((n > 0.03) & (n < 0.97))
    if len(ins):
        a, b = x[max(ins[0] - 1, 0)], x[min(ins[-1] + 1, len(x) - 1)]
        pts += scan(np.setdiff1d(np.round(np.linspace(a, b, 41), 13), np.round(x, 13)))
    pts.sort(key=lambda q: q["x"])
    x = np.array([q["x"] for q in pts]); v = np.array([q["v"] for q in pts])
    n = (v - lo) / (hi - lo)
    quiet = run(dataclasses.replace(p, t_in=p.t_strobe + 10e-9, v_ls=-p.in_step / 2))
    return dict(label=label, params=dataclasses.asdict(p), x=x.tolist(), v=v.tolist(), n=n.tolist(),
                tr_10_90=w.crossing(x, n, 0.9) - w.crossing(x, n, 0.1), overshoot=float(n.max() - 1),
                gain=(hi - lo) / p.in_step, eff=float(np.mean([q["eff"] for q in pts[-3:]])),
                drive_peak=quiet["pk_drive"], kickout_pp=quiet["kick_pp"])


SWEEP = [
    ("A  floating rails, fixed bias, 50 R source", P()),
    ("B  A + bootstrapped bias", P(bootstrap=True)),
    ("C  B + 10 R source (proposed)", P(bootstrap=True, r_in=10.0)),
    ("C  behind a 3.1 GHz buffer", P(bootstrap=True, r_in=10.0, in_bw=3.1e9)),
    ("C  rails not floating (no balun, same pulse amplitude)", P(bootstrap=True, r_in=10.0, balun=False)),
    ("C  edge 80 ps", P(bootstrap=True, r_in=10.0, tr=80e-12)),
    ("C  edge 150 ps", P(bootstrap=True, r_in=10.0, tr=150e-12)),
    ("C  pulse 60 ps (30 ps stub)", P(bootstrap=True, r_in=10.0, stub_td=30e-12)),
    ("C  pulse 160 ps (80 ps stub)", P(bootstrap=True, r_in=10.0, stub_td=80e-12)),
    ("C  step 2 V, bias 1.2 V", P(bootstrap=True, r_in=10.0, v_step=2.0, v_rev=1.2)),
    ("C  hold 10 pF", P(bootstrap=True, r_in=10.0, c_hold=10e-12)),
    ("C  hold 1 pF", P(bootstrap=True, r_in=10.0, c_hold=1e-12)),
]

if __name__ == "__main__":
    out = []
    with mp.Pool(4) as pool:
        for label, p in SWEEP:
            r = step_response(pool, p, label)
            out.append(r)
            print("%-52s tr %4.0f ps  overshoot %3.0f %%  gain %.2f  eff %3.0f %%  drive %.2f V  kickout %3.0f mVpp" % (
                label, r["tr_10_90"] * 1e12, r["overshoot"] * 100, r["gain"], r["eff"] * 100, r["drive_peak"], r["kickout_pp"] * 1e3), flush=True)
            with open(os.path.join(RES, "scope-sampler.json"), "w") as fh:
                json.dump(out, fh, indent=1)
