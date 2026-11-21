"""Strobe driver chains: FPGA LVCMOS33 edge -> saturating gain blocks -> shorted-stub differentiator.

Behavioural models only (no vendor SPICE models were used):
  gain block = 50 R input || 0.2 pF -> linear filter part A -> tanh limiter (open-circuit swing
  +/-2*Vsat, i.e. +/-Vsat into 50 R) -> linear filter part B -> 50 R source -> 0.3 pF.
  Filters fitted to the datasheet gain tables:
    TRF37D73  22.3 dB, two poles at 3.3 GHz        (22/19.5/18/15.5/13/10 dB at 0.4/2/3/4/5/6 GHz)
    GVA-84+   24.1 dB, poles 1.1 and 6.5 GHz, zero 3.75 GHz (24.1/21.7/18.4/16/14.6/12.5/10.5 dB)
  Vsat (square-wave level into 50 R): TRF 2.3 V (OP1dB 16.5 dBm = 2.1 V pk sine), GVA 3.6 V
  (OP1dB 20.6, Psat 22.3 dBm).  'split' = which filter sections sit before the limiter:
    nominal     TRF: 1 pole before, 1 after.   GVA: pole 1.1 GHz + zero before, 6.5 GHz pole after
    pessimistic every section after the limiter (the stage cannot slew faster than its small-signal response)
  FPGA pin: Thevenin 3.3 V ramp (10-90 = tr), 40 R, 3 pF.
Edge runs are DC coupled with a zero-mean source (large coupling caps, given duty cycle);
the AC-coupling / choke check is a separate long run (baseline()).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "sim"))
import frontend as f  # noqa: E402

BLOCKS = {
    "TRF": dict(a=10 ** (22.3 / 20), vs=2.3, pre={"nominal": [("p", 3.3e9)], "pess": []},
                post={"nominal": [("p", 3.3e9)], "pess": [("p", 3.3e9), ("p", 3.3e9)]}),
    "GVA": dict(a=10 ** (24.1 / 20), vs=3.6, pre={"nominal": [("p", 1.1e9), ("z", 3.75e9)], "pess": []},
                post={"nominal": [("p", 6.5e9)], "pess": [("p", 1.1e9), ("z", 3.75e9), ("p", 6.5e9)]}),
}


def pad(d: f.Deck, name: str, a: str, b: str, db: float) -> None:
    """50 R pi attenuator."""
    k = 10 ** (db / 20)
    rsh = 50 * (k + 1) / (k - 1)
    rse = 50 * (k * k - 1) / (2 * k)
    d.add(f"R{name}a {a} 0 {rsh:.4g}")
    d.add(f"R{name}s {a} {b} {rse:.4g}")
    d.add(f"R{name}b {b} 0 {rsh:.4g}")


def filt(d: f.Deck, tag: str, x: str, secs) -> str:
    for i, (kind, fc) in enumerate(secs):
        y = f"{tag}f{i}"
        d.add(f"E{tag}b{i} {y}i 0 {x} 0 1")
        if kind == "p":
            d.add(f"R{tag}{i} {y}i {y} 1k")
            d.add(f"C{tag}{i} {y} 0 {1 / (2 * np.pi * fc * 1e3):.5g}")
        else:      # zero: (1+s/wz) via R || C into a 1k load, normalised with a far pole at 20*fz
            r2 = 1e3 / 19
            d.add(f"R{tag}{i} {y}i {y} {r2 * 19:.4g}")
            d.add(f"C{tag}{i} {y}i {y} {1 / (2 * np.pi * fc * r2 * 19):.5g}")
            d.add(f"R{tag}{i}l {y} 0 {r2:.4g}")
            d.add(f"E{tag}g{i} {y}g 0 {y} 0 20")
            y = f"{y}g"
        x = y
    d.add(f"E{tag}out {tag}buf 0 {x} 0 1")
    return f"{tag}buf"


def stage(d: f.Deck, tag: str, kind: str, inp: str, out: str, split: str) -> None:
    b = BLOCKS[kind]
    d.add(f"R{tag}in {inp} 0 50")
    d.add(f"C{tag}in {inp} 0 0.2p")
    x = filt(d, tag + "A", inp, b["pre"][split])
    d.add(f"B{tag}lim {tag}l 0 V={2 * b['vs']}*tanh({b['a']:.4g}*v({x})/{b['vs']})")
    y = filt(d, tag + "B", f"{tag}l", b["post"][split])
    d.add(f"R{tag}o {y} {out} 50")
    d.add(f"C{tag}o {out} 0 0.3p")


def chain(d: f.Deck, stages, src: str, out: str, split: str, r_fpga: float = 47.0) -> None:
    """stages: list of (kind, pad_dB_in_front); the first pad is replaced by r_fpga series."""
    d.add(f"Rfs {src} c0 {r_fpga}")
    node = "c0"
    for i, (kind, db) in enumerate(stages):
        if i and db:
            pad(d, f"p{i}", node, f"s{i}in", db)
            node_in = f"s{i}in"
        else:
            node_in = node
        o = out if i == len(stages) - 1 else f"s{i}o"
        stage(d, f"S{i}", kind, node_in, o, split)
        node = o


def fpga(d: f.Deck, tr: float, duty: float, t0: float, rising: bool = True) -> None:
    """Zero-mean Thevenin source (AC-coupled steady state for the given duty cycle)."""
    lo, hi = -3.3 * duty, 3.3 * (1 - duty)
    a, b = (lo, hi) if rising else (hi, lo)
    d.add(f"Vf fe 0 pwl(0 {a} {t0:.6g} {a} {t0 + tr / 0.8:.6g} {b})")
    d.add("Rfo fe fp 40")
    d.add("Cfp fp 0 3p")


def run_deck(text: str, vecs: list[str], tstop: float) -> dict[str, np.ndarray]:
    for tmax in ("2p", "1.5p", "3p"):
        with tempfile.TemporaryDirectory() as td:
            cir, dat = os.path.join(td, "a.cir"), os.path.join(td, "a.dat")
            body = text + ".options klu reltol=3e-4 abstol=1e-12 vntol=1e-7\n" + \
                f".tran 1p {tstop:.6g} 0 {tmax}\n.control\nrun\nset wr_singlescale\nwrdata {dat} {' '.join(vecs)}\n.endc\n.end\n"
            with open(cir, "w") as fh:
                fh.write(body)
            r = subprocess.run(["ngspice", "-b", cir], capture_output=True, text=True, timeout=300)
            if os.path.exists(dat):
                a = np.loadtxt(dat)
                if a.ndim == 2 and a[-1, 0] > tstop * 0.99:
                    out = {"t": a[:, 0]}
                    for i, v in enumerate(vecs):
                        out[v] = a[:, 1 + i]
                    return out
    raise RuntimeError(r.stdout[-1500:] + r.stderr[-800:])


def edge(stages, tr=450e-12, duty=0.5, split="nominal", load="50", stub_td=0.0, t0=1e-9, tstop=4e-9):
    """Chain output into 50 R (load='50'), or into a shorted stub + 50 R line (phase-strobe launch)."""
    d = f.Deck()
    d.add("* strobe chain")
    fpga(d, tr, duty, t0)
    chain(d, stages, "fp", "out", split)
    if stub_td:
        d.trace("out", "stend", 0, td=stub_td)
        d.add("Rstub stend 0 0.05")
    d.add("Rload out 0 50")
    return run_deck("\n".join(d.lines) + "\n", ["v(out)", "v(c0)"], tstop)


def t1090(t, v):
    lo, hi = np.median(v[t < t[0] + 0.5e-9]), v.max() if v.max() > -v.min() else v.min()
    hi = np.median(v[-200:])
    n = (v - lo) / (hi - lo)
    def cr(x):
        i = np.flatnonzero(n >= x)[0]
        return t[i - 1] + (x - n[i - 1]) / (n[i] - n[i - 1]) * (t[i] - t[i - 1])
    return cr(0.1), cr(0.5), cr(0.9), lo, hi


CHAINS = {
    "2xTRF": [("TRF", 0), ("TRF", 12)],
    "3xTRF": [("TRF", 0), ("TRF", 12), ("TRF", 12)],
    "TRF+GVA": [("TRF", 0), ("GVA", 10)],
    "2xTRF+GVA": [("TRF", 0), ("TRF", 12), ("GVA", 10)],
}

if __name__ == "__main__":
    import json
    res = {}
    for name, st in CHAINS.items():
        for split in ("nominal", "pess"):
            for tr in (300e-12, 600e-12):
                for duty in (0.5, 1 / 64):
                    r = edge(st, tr=tr, duty=duty, split=split)
                    a, m, b, lo, hi = t1090(r["t"], r["v(out)"])
                    key = f"{name}|{split}|{tr * 1e12:.0f}|{duty:.3f}"
                    res[key] = dict(tr=(b - a) * 1e12, t50=m * 1e12, lo=lo, hi=hi, step=hi - lo)
                    print("%-10s %-8s fpga %3.0f ps duty %.3f: edge %4.0f ps, t50 %4.0f ps, %+.2f -> %+.2f V (step %.2f V)" % (
                        name, split, tr * 1e12, duty, (b - a) * 1e12, m * 1e12, lo, hi, hi - lo), flush=True)
    with open(os.path.join(HERE, "chain_edges.json"), "w") as fh:
        json.dump(res, fh, indent=1)
