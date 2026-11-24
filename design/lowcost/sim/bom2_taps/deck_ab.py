"""As-built 16-tap phase array (six-layer board, layout/board/blocks/phase/README.md) for the BOM-2 tap-capacitor study.
Reuses sim/phase_array/deck.py (imported, not edited) for the strobe chain, LVDS/TRF/pad signal chain and models;
build_ab() is a modified copy of deck.build():
  * strobe lines: 62 R, 26.25 ps per 4.514 mm section (unloaded), strobe-side cap pad 0.110 pF over L2 at each gate,
    43 R end terminations (R378 / R379), 80 ps launch stub
  * signal line PH_LINE: 62 R, 56.46 ps per 9.707 mm cell (unloaded), BAT15 pad-3 excess 0.095 pF per tap, 49.9 R end
  * gate: coupling ("hold") capacitor cc from PSTRB_A/K to each hold node (0.47 pF in the original deck; DNP = the
    empty 0402 pad pair, about 0.03 pF), hold-node capacitance to ground c_node (as-built copper estimate 0.40 pF:
    1 k node pad and 0.95 mm of 0.15 mm track over solid L2, rest over the L5-referenced cut-out)
  * comparator node: 2 x 1 k, Cin 3 pF (COS3502, assumed as before)
"""
from __future__ import annotations

import dataclasses
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "phase_array"))
import deck as D  # noqa: E402  (also puts sim/phase and sim/strobe on the path)

N = D.N


@dataclasses.dataclass
class AB(D.A):
    stub_td: float = 80e-12
    z_s: float = 62.0
    td_s: float = 26.25e-12
    pad_s: float = 0.110e-12
    r_term_s: float = 43.0
    z_sig: float = 62.0
    td_sig_u: float = 56.46e-12
    pad_sig: float = 0.095e-12
    cc: float = 0.47e-12
    c_node: float = 0.40e-12


def build_ab(p: AB, t_peak0: float) -> str:
    f, c, ld = D.f, D.c, D.ld
    d = f.Deck()
    d.add("* 16-tap co-propagating array, as built (six layers)")
    d.add(f.MODELS)
    if p.signal:
        t_edge = t_peak0 + p.x - 0.126e-9
        pwl = (f"0 0 0.1n 0 {0.1e-9 + c.T_EDGE:.6g} {-c.I_LVDS} {t_edge - c.T_EDGE / 2:.6g} {-c.I_LVDS} "
               f"{t_edge + c.T_EDGE / 2:.6g} {c.I_LVDS}")
    else:
        pwl = f"0 0 0.1n 0 {0.1e-9 + c.T_EDGE:.6g} {-c.I_LVDS}"
    c.lvds(d, pwl)
    ld.chain(d, "s0")
    for i in range(N):
        d.add(f"Cps{i} s{i} 0 {p.pad_sig:.4g}")
        if i:
            d.trace(f"s{i - 1}", f"s{i}", 0, z0=p.z_sig, td=p.td_sig_u, sec=3e-12)
    d.add(f"Rts s{N - 1} 0 49.9")
    for ln, sign in (("pa", 1), ("pk", -1)):
        d.add(f"V{ln} {ln}_e 0 pwl({D.strobe_pwl(p, sign)})")
        d.add(f"R{ln}s {ln}_e {ln}0 50")
        d.trace(f"{ln}0", f"{ln}stub", 0, td=p.stub_td, sec=3e-12)
        d.add(f"R{ln}stub {ln}stub 0 0.05")
        for i in range(N):
            d.add(f"Cp{ln}{i} {ln}{i} 0 {p.pad_s:.4g}")
            if i:
                d.trace(f"{ln}{i - 1}", f"{ln}{i}", 0, z0=p.z_s, td=p.td_s, sec=3e-12)
        d.add(f"R{ln}t {ln}{N - 1} 0 {p.r_term_s}")
    d.add("Vva va 0 -2.5\nVvk vk 0 2.5")
    for i in range(N):
        if p.gates:
            d.add(f"Xd1_{i} a{i} s{i} dpk\nXd2_{i} s{i} k{i} dpk")
        d.add(f"Ca{i} a{i} pa{i} {p.cc:.4g}\nCk{i} k{i} pk{i} {p.cc:.4g}")
        d.add(f"Cna{i} a{i} 0 {p.c_node:.4g}\nCnk{i} k{i} 0 {p.c_node:.4g}")
        d.add(f"Rba{i} a{i} va 2.2k\nRbk{i} k{i} vk 2.2k")
        d.add(f"Roa{i} a{i} o{i} 1k\nRok{i} k{i} o{i} 1k\nCo{i} o{i} 0 {p.cin}")
    d.add(".options klu reltol=3e-4 abstol=1e-12 vntol=1e-7")
    d.add(f".tran 1p {D.T_ST + p.tstop:.6g} 0 3p")
    d.add(".end")
    return "\n".join(d.lines) + "\n"


def sim_ab(p: AB, t_peak0: float, vecs):
    a = D.c.waves(build_ab(p, t_peak0), vecs, tmax_list=(None, 2e-12, 5e-12), timeout=1500)
    return a[:, 0], {v: a[:, j + 1] for j, v in enumerate(vecs)}
