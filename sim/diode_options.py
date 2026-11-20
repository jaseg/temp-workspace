"""How much diode capacitance and series resistance the tap gates tolerate
(see ../docs/scope-frontend.md, cheaper diodes for the tapped sampler).

Each candidate is a generic Schottky model: junction capacitance, series resistance,
package capacitance and lead inductance. Run for one gate (tap_gate) and for the
16-tap array with 220 R isolation and +/-3 V strobe (tap_array).

  python3 diode_options.py
"""
import dataclasses
import multiprocessing as mp
import os
import re
import subprocess
import tempfile

import numpy as np

import frontend as f
import tap_array as ta
import tap_gate as tg
import wave as w

BASE = f.MODELS


def models(cj, rs, cp, lb=0.7e-9, bv=4.2, is_=74e-9):
    m = BASE
    m = re.sub(r"\.model bat15 d\([^)]*\)", f".model bat15 d(is={is_} n=1.07 rs={rs} xti=1.5 eg=0.59 cjo={cj} m=0.138 vj=0.224 fc=0.5 tt=3p bv={bv} ibv=100u)", m)
    m = m.replace("Lb a a1 0.7n", f"Lb a a1 {lb}").replace("Cp a k 0.16p", f"Cp a k {cp}")
    return m


# name, price per diode at 100 pieces, model parameters
DIODES = [
    ("BAT15-04R / -04W (reference)", "0.10-0.14", dict(cj=0.1385e-12, rs=5.0, cp=0.16e-12)),
    ("NSR201MX: 0.15 pF, 14 R, 2 V", "0.19", dict(cj=0.10e-12, rs=14.0, cp=0.05e-12, lb=0.3e-9, bv=2.0)),
    ("JDH2S02SL: 0.25 pF, 10 V", "0.19", dict(cj=0.17e-12, rs=8.0, cp=0.08e-12, lb=0.3e-9, bv=10.0)),
    ("0.5 pF class", "-", dict(cj=0.35e-12, rs=8.0, cp=0.15e-12, bv=10.0)),
    ("1 pF class (BAT68, RB886, MMDL301)", "0.04-0.26", dict(cj=0.85e-12, rs=10.0, cp=0.15e-12, bv=8.0)),
    ("2 pF class (BAS70, 1N5711 types)", "0.02", dict(cj=1.8e-12, rs=25.0, cp=0.2e-12, bv=70.0)),
    ("10 pF class (BAT54)", "0.01", dict(cj=9.8e-12, rs=5.0, cp=0.2e-12, bv=30.0)),
]


def reverse_peak(g: tg.G) -> float:
    """Largest reverse voltage on either diode of a two-diode gate over one strobe, worst signal level."""
    worst = 0.0
    for a in (-g.a, g.a):
        deck = tg.build(dataclasses.replace(g, a=abs(a), t_in=(1 if a < 0 else 0.5e-9)))
        deck = deck.replace(".end\n", ".meas tran r1 max par('v(s)-v(a)')\n.meas tran r2 max par('v(k)-v(s)')\n.end\n")
        with tempfile.NamedTemporaryFile("w", suffix=".cir", delete=False) as fh:
            fh.write(deck)
            path = fh.name
        r = subprocess.run(["ngspice", "-b", path], capture_output=True, text=True, timeout=300)
        os.unlink(path)
        for m in re.finditer(r"^r[12]\s*=\s*([-+0-9.eE]+)", r.stdout, re.M):
            worst = max(worst, float(m.group(1)))
    return worst


if __name__ == "__main__":
    print("%-38s %9s | one gate: swing aperture | 16-tap array: swing min..max, spacing, slowest tap edge | reverse V" % ("diode", "$/diode"))
    for name, price, kw in DIODES:
        f.MODELS = models(**kw)
        with mp.Pool(4) as pool:
            g = tg.characterise(pool, tg.G(c=0.47e-12, rb=43e3))
            p = ta.A(vp=3.0, vb=0.5, r_iso=220.0, t_s=4e-9)   # late strobe so that early steps stay at positive time
            span = p.n * (p.td_sig + p.td_st)
            xs = np.arange(-2.2 * span - 0.3e-9, 0.5e-9, 25e-12)
            res = pool.map(ta.job, [dataclasses.replace(p, t_in=p.t_s + x) for x in xs])
        v = np.array([r[0] for r in res])
        lo, hi = v[-3:].mean(0), v[:3].mean(0)
        n = (v - lo) / (hi - lo)
        t50 = np.array([w.crossing(-xs[::-1], n[::-1, i], 0.5) for i in range(p.n)])
        tr = np.array([w.crossing(-xs[::-1], n[::-1, i], 0.9) - w.crossing(-xs[::-1], n[::-1, i], 0.1) for i in range(p.n)])
        eff = (hi - lo) / (2 * p.a)
        mid = slice(1, p.n - 1)
        rv = reverse_peak(tg.G(c=0.47e-12, rb=43e3, vp=3.0, a=0.5))
        print("%-38s %9s |   %3.0f %%   %3.0f ps      |   %3.0f..%3.0f %%,  %3.0f ps (nominal 70),  %3.0f ps            | %.1f V" % (
            name, price, g["eff"] * 100, g["tr"] * 1e12, eff[mid].min() * 100, eff[mid].max() * 100,
            abs(np.nanmean(np.diff(t50)[mid])) * 1e12 if np.isfinite(np.diff(t50)[mid]).any() else float("nan"),
            np.nanmax(tr[mid]) * 1e12, rv), flush=True)
