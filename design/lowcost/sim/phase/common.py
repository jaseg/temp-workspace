"""Shared pieces for the phase-recovery decks: behavioural TLV3801 LVDS output, TRF37D73 gain
block, 12 dB pad, tapped 50 R line with BAT15-04W gates, ngspice runner with retry.

Behavioural (no vendor model used):
  TLV3801 output  differential current source +/-3.5 mA (350 mV into 100 R), 20-80 % = 135 ps
                  (linear ramp 0-100 % = 225 ps), 0.5 pF per pin, CM 1.2 V through 10 k.
  TRF37D73        50 R || 0.2 pF in, gain 13.0 (22.3 dB) with one 3.3 GHz pole, tanh limiter
                  +/-2.3 V into 50 R (OP1dB 16.5 dBm), second 3.3 GHz pole, 50 R || 0.3 pF out.
                  Flat to DC behind the external parts: the datasheet only covers 1 MHz-6 GHz.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../sim"))
import frontend as f  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TRF_G, TRF_VSAT, TRF_FP = 13.0, 2.3, 3.3e9
I_LVDS = 3.5e-3
T_EDGE = 135e-12 / 0.6          # 0-100 % of a linear ramp with 135 ps 20-80 %


def lvds(d: f.Deck, pwl: str) -> None:
    """TLV3801 output pins cmp_p / cmp_n; pwl gives the steering current (A, +3.5 mA = high)."""
    d.add(f"Ilv cmp_n cmp_p pwl({pwl})")
    d.add("Rcmp cmp_p vocm 10k\nRcmn cmp_n vocm 10k\nVocm vocm 0 1.2")
    d.add("Cpp cmp_p 0 0.5p\nCpn cmp_n 0 0.5p")


def trf(d: f.Deck, name: str, inp: str, out: str) -> None:
    tau = 1 / (2 * np.pi * TRF_FP)
    d.add(f"R{name}i {inp} 0 50\nC{name}i {inp} 0 0.2p")
    d.add(f"E{name}1 {name}x1 0 {inp} 0 {TRF_G}\nR{name}1 {name}x1 {name}x2 1k\nC{name}1 {name}x2 0 {tau / 1e3:.4g}")
    d.add(f"B{name}l {name}x3 0 v={TRF_VSAT}*tanh(v({name}x2)/{TRF_VSAT})")
    d.add(f"R{name}2 {name}x3 {name}x4 1k\nC{name}2 {name}x4 0 {tau / 1e3:.4g}")
    d.add(f"E{name}o {name}x5 0 {name}x4 0 2\nR{name}o {name}x5 {out} 50\nC{name}o {out} 0 0.3p")


def pad12(d: f.Deck, a: str, b: str) -> None:
    """12 dB pi pad, E24 values 82 / 91 / 82 R."""
    d.add(f"Rpd1 {a} 0 82\nRpd2 {a} {b} 91\nRpd3 {b} 0 82")


def run(deck: str, names: list[str], tmax_list=(None,), timeout=900) -> dict[str, float]:
    """Run a batch deck; .meas names must appear in `names`. Retries with other tmax values."""
    last = ""
    for tm in tmax_list:
        dk = deck if tm is None else re.sub(r"(\.tran \S+ \S+ \S+) \S+", rf"\1 {tm}", deck)
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "d.cir")
            open(p, "w").write(dk)
            r = subprocess.run(["ngspice", "-b", p], capture_output=True, text=True, timeout=timeout, cwd=td)
        o = {m.group(1).lower(): float(m.group(2)) for m in re.finditer(r"^(\w+)\s*=\s*([-+0-9.eE]+)", r.stdout, re.M)}
        if all(n.lower() in o for n in names):
            return o
        last = r.stdout[-1200:] + r.stderr[-600:]
    raise RuntimeError(last)


def waves(deck: str, vecs: list[str], tmax_list=(None,), timeout=900) -> np.ndarray:
    """Run with wrdata of `vecs`; returns array [t, v1, v2, ...]."""
    last = ""
    for tm in tmax_list:
        dk = deck if tm is None else re.sub(r"(\.tran \S+ \S+ \S+) \S+", rf"\1 {tm}", deck)
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "w.txt")
            dk = dk.replace(".end\n", f".control\nset wr_singlescale\nrun\nwrdata {out} {' '.join(vecs)}\n.endc\n.end\n")
            p = os.path.join(td, "d.cir")
            open(p, "w").write(dk)
            r = subprocess.run(["ngspice", "-b", p], capture_output=True, text=True, timeout=timeout, cwd=td)
            if os.path.exists(out) and os.path.getsize(out) > 100:
                return np.loadtxt(out)
        last = r.stdout[-1200:] + r.stderr[-600:]
    raise RuntimeError(last)
