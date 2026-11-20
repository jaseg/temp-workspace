"""Single-shot behaviour of one tap gate of the delay-line TDC (see ../docs/scope-frontend.md).

A 50 R line (terminated, driven from 50 R) carries a step. One gate taps it:
  two-diode gate   strobe+ -Ca- A -|>|- S -|>|- K -Ck- strobe-   output = (V(A)+V(K))/2
  one-diode gate   S -|>|- H -Ch- strobe (negative pulse)        output = V(H)
Each run starts from the DC state (hold nodes bled back to bias) and fires one strobe.

  python3 tap_gate.py
"""
from __future__ import annotations

import dataclasses
import multiprocessing as mp
import os
import re
import subprocess
import tempfile

import numpy as np

import frontend as f
import wave as w


@dataclasses.dataclass
class G:
    kind: int = 2             # diodes per gate
    vp: float = 1.5           # strobe pulse amplitude at the gate, per side, V
    width: float = 100e-12    # strobe pulse width at half height
    tr: float = 40e-12        # strobe edges, 0-100 %
    vb: float = 0.5           # reverse bias per side
    c: float = 1e-12          # hold capacitor(s)
    rb: float = 20e3          # bleed to bias
    a: float = 0.2            # line level before/after the step: -a .. +a
    t_in: float = 2e-9
    t_s: float = 2e-9
    imbalance: float = 0.0    # two-diode gate: relative strobe amplitude error of the negative side
    c_out: float = 2e-12      # comparator input


def build(g: G) -> str:
    d = f.Deck()
    d.add("* tap gate")
    d.add(f.MODELS)
    d.add(f"Vs s_e 0 pwl(0 {-2 * g.a} {g.t_in:.6g} {-2 * g.a} {g.t_in + 1e-12:.6g} {2 * g.a})")
    d.add("Rs s_e s 50")
    d.add("Rt s 0 50")
    t0, t1, t2, t3 = g.t_s, g.t_s + g.tr, g.t_s + g.tr + g.width - g.tr, g.t_s + g.width + g.tr

    def strobe(name, node, amp):
        d.add(f"V{name} {name}_e 0 pwl(0 0 {t0:.6g} 0 {t1:.6g} {amp} {t2:.6g} {amp} {t3:.6g} 0)")
        d.add(f"R{name} {name}_e {node} 50")
        d.add(f"R{name}t {node} 0 50")       # the strobe line continues, terminated
    if g.kind == 2:
        strobe("sp", "stp", 2 * g.vp)
        strobe("sn", "stn", -2 * g.vp * (1 + g.imbalance))
        d.add("Xd1 a s dpk")
        d.add("Xd2 s k dpk")
        d.add(f"Ca a stp {g.c}")
        d.add(f"Ck k stn {g.c}")
        d.add(f"Vba vba 0 {-g.vb}")
        d.add(f"Vbk vbk 0 {g.vb}")
        d.add(f"Rba a vba {g.rb}")
        d.add(f"Rbk k vbk {g.rb}")
        d.add("Roa a out 20k")
        d.add("Rok k out 20k")
    else:
        strobe("sn", "stn", -2 * g.vp)
        d.add("Xd1 s h dpk")
        d.add(f"Ch h stn {g.c}")
        d.add(f"Vbk vbk 0 {g.vb}")
        d.add(f"Rbk h vbk {g.rb}")
        d.add("Roh h out 10k")
    d.add(f"Cout out 0 {g.c_out}")
    tend = g.t_s + 30e-9
    d.add(".options klu reltol=3e-4 abstol=1e-12 vntol=1e-7")
    d.add(f".tran 1p {tend:.6g} 0 2p")
    hold = "(v(a)+v(k))/2" if g.kind == 2 else "v(h)"
    for name, dt in (("o1", 1e-9), ("o5", 5e-9), ("o20", 20e-9)):
        d.add(f".meas tran {name} find par('{hold}') at={g.t_s + dt:.6g}")
    d.add(f".meas tran smax max v(s) from={g.t_s - 0.2e-9:.6g} to={g.t_s + 1e-9:.6g}")
    d.add(f".meas tran smin min v(s) from={g.t_s - 0.2e-9:.6g} to={g.t_s + 1e-9:.6g}")
    d.add(".end")
    return "\n".join(d.lines) + "\n"


def run(g: G) -> dict[str, float]:
    with tempfile.NamedTemporaryFile("w", suffix=".cir", delete=False) as fh:
        fh.write(build(g))
        path = fh.name
    try:
        r = subprocess.run(["ngspice", "-b", path], capture_output=True, text=True, timeout=300)
    finally:
        os.unlink(path)
    out = {m.group(1): float(m.group(2)) for m in re.finditer(r"^(o1|o5|o20|smax|smin)\s*=\s*([-+0-9.eE]+)", r.stdout, re.M)}
    if len(out) != 5:
        raise RuntimeError(r.stdout[-1500:] + r.stderr[-800:])
    return out


def point(args):
    g, x = args
    return x, run(g)


def characterise(pool, g: G) -> dict:
    xs = np.arange(-0.4e-9, 0.6001e-9, 0.02e-9)
    res = pool.map(point, [(dataclasses.replace(g, t_in=g.t_s - x), float(x)) for x in xs])
    v = np.array([r["o1"] for _, r in res])
    lo, hi = v[:4].mean(), v[-4:].mean()
    n = (v - lo) / (hi - lo)
    quiet = run(dataclasses.replace(g, a=0.0, t_in=1))
    late = res[-1][1]
    return dict(eff=(hi - lo) / (2 * g.a), pedestal=(hi + lo) / 2 - (0 if g.kind == 2 else g.vb),
                tr=w.crossing(xs, n, 0.9) - w.crossing(xs, n, 0.1), kick=quiet["smax"] - quiet["smin"],
                droop5=(late["o5"] - quiet["o5"]) / (late["o1"] - quiet["o1"]), droop20=(late["o20"] - quiet["o20"]) / (late["o1"] - quiet["o1"]),
                ped0=quiet["o1"] - (0 if g.kind == 2 else g.vb))


CASES = [
    ("2 diodes, 1.5 V strobe, bias 0.5 V, 1 pF", G()),
    ("2 diodes, 1.0 V strobe, bias 0.3 V, 1 pF", G(vp=1.0, vb=0.3)),
    ("2 diodes, 1.5 V, 5 % strobe imbalance", G(imbalance=0.05)),
    ("2 diodes, 1.5 V, 160 ps strobe", G(width=160e-12)),
    ("2 diodes, 1.5 V, 0.47 pF", G(c=0.47e-12)),
    ("1 diode, 1.5 V strobe, bias 0.5 V, 1 pF", G(kind=1)),
    ("1 diode, 1.0 V strobe, bias 0.3 V, 1 pF", G(kind=1, vp=1.0, vb=0.3)),
    ("1 diode, 1.65 V strobe (+10 %)", G(kind=1, vp=1.65)),
]

if __name__ == "__main__":
    print("%-42s %5s %9s %8s %9s %10s %10s" % ("gate", "eff", "pedestal", "10-90", "kick-out", "left@5ns", "left@20ns"))
    with mp.Pool(4) as pool:
        for label, g in CASES:
            r = characterise(pool, g)
            print("%-42s %4.0f%% %6.0f mV %5.0f ps %6.0f mV %9.0f%% %9.0f%%" % (
                label, r["eff"] * 100, r["ped0"] * 1e3, r["tr"] * 1e12, r["kick"] * 1e3, r["droop5"] * 100, r["droop20"] * 100), flush=True)
