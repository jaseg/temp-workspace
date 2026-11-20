"""Whole delay-line snapshot TDC: N two-diode gates on a tapped signal line, strobed by a
differential strobe line that runs past the taps in the opposite direction.

  signal  -> tap0 - tap1 - ... - tapN-1 -> 50 R
  50 R   <-  tap0 - tap1 - ... - tapN-1 <- strobe+ / strobe-   (counter-propagating)

Tap i samples the signal at  t_s + (N-1-i)*td_strobe  when the signal has travelled
i*td_signal, so neighbouring taps are td_signal + td_strobe apart in signal time.

  python3 tap_array.py
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
class A:
    n: int = 16
    td_sig: float = 30e-12       # signal line delay between taps
    td_st: float = 30e-12        # strobe line delay between taps
    z_sig: float = 50.0
    z_st: float = 50.0
    vp: float = 1.5              # strobe pulse launched per side
    width: float = 100e-12
    tr: float = 40e-12
    vb: float = 0.5
    c: float = 0.47e-12
    rb: float = 43e3
    r_iso: float = 0.0           # resistor between strobe line and each hold capacitor
    a: float = 0.3               # signal -a .. +a on the line
    rise: float = 150e-12        # signal edge, 10-90 %
    t_in: float = 2e-9
    t_s: float = 2e-9


def build(p: A) -> str:
    d = f.Deck()
    d.add("* tap array")
    d.add(f.MODELS)
    trs = p.rise / 0.8
    d.add(f"Vs s_e 0 pwl(0 {-2 * p.a} {p.t_in:.6g} {-2 * p.a} {p.t_in + trs:.6g} {2 * p.a})")
    d.add("Rs s_e s0 50")
    t0, t1, t2, t3 = p.t_s, p.t_s + p.tr, p.t_s + p.width, p.t_s + p.width + p.tr
    for pol, amp in (("p", 2 * p.vp), ("n", -2 * p.vp)):
        d.add(f"Vst{pol} st{pol}_e 0 pwl(0 0 {t0:.6g} 0 {t1:.6g} {amp} {t2:.6g} {amp} {t3:.6g} 0)")
        d.add(f"Rst{pol} st{pol}_e st{pol}{p.n - 1} 50")       # launched at the far end
        d.add(f"Rstt{pol} st{pol}0 0 50")
    for i in range(p.n):
        if i:
            d.trace(f"s{i - 1}", f"s{i}", 0, z0=p.z_sig, td=p.td_sig)
            d.trace(f"stp{i - 1}", f"stp{i}", 0, z0=p.z_st, td=p.td_st)
            d.trace(f"stn{i - 1}", f"stn{i}", 0, z0=p.z_st, td=p.td_st)
        d.add(f"Xd1_{i} a{i} s{i} dpk")
        d.add(f"Xd2_{i} s{i} k{i} dpk")
        if p.r_iso:
            d.add(f"Ria{i} stp{i} ia{i} {p.r_iso}")
            d.add(f"Rik{i} stn{i} ik{i} {p.r_iso}")
        ia, ik = (f"ia{i}", f"ik{i}") if p.r_iso else (f"stp{i}", f"stn{i}")
        d.add(f"Ca{i} a{i} {ia} {p.c}")
        d.add(f"Ck{i} k{i} {ik} {p.c}")
        d.add(f"Rba{i} a{i} vba {p.rb}")
        d.add(f"Rbk{i} k{i} vbk {p.rb}")
    d.add(f"Rt s{p.n - 1} 0 50")
    d.add(f"Vba vba 0 {-p.vb}")
    d.add(f"Vbk vbk 0 {p.vb}")
    tend = p.t_s + p.n * p.td_st + 3e-9
    d.add(".options klu reltol=3e-4 abstol=1e-12 vntol=1e-7")
    d.add(f".tran 1p {tend:.6g} 0 2p")
    for i in range(p.n):
        d.add(f".meas tran o{i} find par('(v(a{i})+v(k{i}))/2') at={tend - 1e-12:.6g}")
        d.add(f".meas tran pk{i} max par('v(a{i})-v(k{i})')")
    d.add(".end")
    return "\n".join(d.lines) + "\n"


def run(p: A) -> tuple[np.ndarray, np.ndarray]:
    with tempfile.NamedTemporaryFile("w", suffix=".cir", delete=False) as fh:
        fh.write(build(p))
        path = fh.name
    try:
        r = subprocess.run(["ngspice", "-b", path], capture_output=True, text=True, timeout=900)
    finally:
        os.unlink(path)
    o = {m.group(1): float(m.group(2)) for m in re.finditer(r"^((?:o|pk)\d+)\s*=\s*([-+0-9.eE]+)", r.stdout, re.M)}
    if len(o) != 2 * p.n:
        raise RuntimeError(r.stdout[-1500:] + r.stderr[-500:])
    return np.array([o[f"o{i}"] for i in range(p.n)]), np.array([o[f"pk{i}"] for i in range(p.n)])


def job(args):
    return run(args)


def characterise(pool, p: A, label: str) -> None:
    span = p.n * (p.td_sig + p.td_st)
    xs = np.arange(-span - 0.3e-9, 0.5e-9, 20e-12)       # step time relative to the strobe launch
    res = pool.map(job, [dataclasses.replace(p, t_in=p.t_s + x) for x in xs])
    v = np.array([r[0] for r in res])                     # [step time, tap]
    pk = res[0][1]
    lo, hi = v[-3:].mean(0), v[:3].mean(0)                # late step: still low; early step: high
    n = (v - lo) / (hi - lo)
    t50 = np.array([w.crossing(-xs[::-1], n[::-1, i], 0.5) for i in range(p.n)])
    tr = np.array([w.crossing(-xs[::-1], n[::-1, i], 0.9) - w.crossing(-xs[::-1], n[::-1, i], 0.1) for i in range(p.n)])
    eff = (hi - lo) / (2 * p.a)
    sp = np.diff(t50)
    print(label)
    print("  tap spacing %.0f ps mean (%.0f..%.0f), nominal %.0f | swing at hold node %.0f..%.0f %% of the signal | recorded edge 10-90 %.0f..%.0f ps"
          % (abs(sp.mean()) * 1e12, np.abs(sp).min() * 1e12, np.abs(sp).max() * 1e12, (p.td_sig + p.td_st) * 1e12,
             eff.min() * 100, eff.max() * 100, tr.min() * 1e12, tr.max() * 1e12))
    print("  per tap, first to last on the signal line: swing %% " + " ".join("%.0f" % (e * 100) for e in eff))
    print("  peak drive across each gate, V:           " + " ".join("%.1f" % x for x in pk))


if __name__ == "__main__":
    with mp.Pool(4) as pool:
        characterise(pool, A(), "16 taps, 0.47 pF, strobe 1.5 V per side")
        characterise(pool, A(c=1e-12, rb=20e3), "16 taps, 1 pF")
        characterise(pool, A(z_sig=60.0, z_st=65.0), "16 taps, 0.47 pF, lines 60 R / 65 R unloaded to offset the tap loading")
        characterise(pool, A(n=8), "8 taps, 0.47 pF")
