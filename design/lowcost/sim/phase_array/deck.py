"""Full 16-tap phase-strobe array deck (SPEC decision 4, co-propagating geometry).

Strobe: PH_STROBE_P/N -> TRF37D73 -> 10 dB pad -> GVA-84+ (behavioural, strobe/chain.py, "nominal"),
50 % duty square wave: the chain output step is taken from chain.edge() into 50 R and replayed as a
50 R Thevenin source (2 x v(out)); the falling FPGA edge (half period later) is the mirrored step.
At the launch point a shorted stub (50 ps one-way) differentiates it; PSTRB_A gets the positive,
PSTRB_K the negative (complementary chain) pulse. Each strobe line: 16 x (trace z_s / td_s + gate
hold cap), 50 R end. Optional BAT15 (dpk) shunt clamp at each launch point against the
wrong-polarity pulse.
Signal: TLV3801 LVDS -> 1 uF -> TRF37D73 -> 1 uF -> 12 dB pad (phase/line_drive.chain), launched at
the same end as the strobes, 16 taps with trace sections chosen so the line is 50 R / td_sig per tap
with a 0.37 pF gate, 50 R end.
Gate i: BAT15-04W (a_i -> s_i -> k_i), 0.47 pF a_i-PSTRB_A_i and k_i-PSTRB_K_i, 2.2 k to -/+2.5 V,
1 k + 1 k to the comparator node o_i, Cin to ground.
"""
from __future__ import annotations

import dataclasses
import functools
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "phase"))
sys.path.insert(0, os.path.join(HERE, "..", "strobe"))
import common as c  # noqa: E402  (phase/common.py: lvds, trf, pad12, waves)
import frontend as f  # noqa: E402
import line_drive as ld  # noqa: E402

N = 16
T_ST = 1.3e-9          # FPGA strobe edge
T_HALF = 10e-9         # 50 MHz, 50 % duty


@dataclasses.dataclass
class A:
    x: float = 0.0             # signal-edge 50 % time at tap 0 minus strobe peak time at tap 0
    scale: float = 1.0         # launch amplitude factor (chain step x scale)
    stub_td: float = 50e-12
    z_s: float = 73.0          # strobe trace between gates
    td_s: float = 24e-12
    td_sig: float = 70e-12     # loaded signal-line delay per tap (counter-propagation: changes sign below)
    counter: bool = False      # strobes launched at tap 15 instead of tap 0
    cin: float = 3e-12
    duty: float = 0.5          # time of the reverse edge = duty x 20 ns
    reverse: bool = False
    clamp: bool = False
    gates: bool = True
    tstop: float = 4.5e-9      # after T_ST
    signal: bool = True


@functools.lru_cache(maxsize=None)
def strobe_step():
    import chain
    r = chain.edge(chain.CHAINS["TRF+GVA"], tr=600e-12, duty=0.5, split="nominal", t0=1e-9, tstop=3e-9)
    t, v = r["t"], r["v(out)"]
    lo, hi = np.median(v[t < 0.9e-9]), np.median(v[t > 2.5e-9])
    k = (t > 0.8e-9) & (t < 2.6e-9)
    tt, vv = t[k] - 1e-9, v[k] - lo            # step starts ~0 at tt=0
    idx = np.unique(np.r_[0, np.searchsorted(tt, np.arange(tt[0], tt[-1], 4e-12)), len(tt) - 1])
    return tt[idx], vv[idx], hi - lo


def strobe_pwl(p: A, sign: float) -> str:
    tt, vv, step = strobe_step()
    pts = [(0.0, 0.0)]
    pts += [(T_ST + a, 2 * p.scale * b) for a, b in zip(tt, vv)]
    if p.reverse:
        tr = T_ST + p.duty * 2 * T_HALF
        pts += [(tr + a, 2 * p.scale * (step - b)) for a, b in zip(tt, vv)]
    pts = [(a, b - p.scale * step) for a, b in pts]        # zero-mean (stub shorts DC anyway)
    pts[0] = (0.0, pts[1][1])
    return " ".join(f"{a:.6g} {sign * b:.5g}" for a, b in pts)


T_PEAK0 = None   # strobe peak time at tap 0, measured once (see calib())


def build(p: A, t_peak0: float) -> str:
    d = f.Deck()
    d.add("* 16-tap co-propagating array")
    d.add(f.MODELS)
    # ---- signal source: LVDS starts balanced, goes low at 0.1 ns, edge up at the requested time
    if p.signal:
        t_edge = t_peak0 + p.x - 0.126e-9         # LVDS 50 % -> line 50 % at tap 0 (126 ps, calibrated in run.py)
        pwl = f"0 0 0.1n 0 {0.1e-9 + c.T_EDGE:.6g} {-c.I_LVDS} {t_edge - c.T_EDGE / 2:.6g} {-c.I_LVDS} {t_edge + c.T_EDGE / 2:.6g} {c.I_LVDS}"
    else:
        pwl = f"0 0 0.1n 0 {0.1e-9 + c.T_EDGE:.6g} {-c.I_LVDS}"
    c.lvds(d, pwl)
    ld.chain(d, "s0")
    c_tap = 0.37e-12
    c_tr = p.td_sig / 50 - c_tap
    l_tr = p.td_sig * 50
    zu, tdu = np.sqrt(l_tr / c_tr), np.sqrt(l_tr * c_tr)
    for i in range(1, N):
        d.trace(f"s{i - 1}", f"s{i}", 0, z0=zu, td=tdu, sec=3e-12)
    d.add(f"Rts s{N - 1} 0 50")
    # ---- strobe lines
    first = N - 1 if p.counter else 0
    order = list(range(N - 1, -1, -1)) if p.counter else list(range(N))
    for ln, sign in (("pa", 1), ("pk", -1)):
        d.add(f"V{ln} {ln}_e 0 pwl({strobe_pwl(p, sign)})")
        d.add(f"R{ln}s {ln}_e {ln}{first} 50")
        d.trace(f"{ln}{first}", f"{ln}stub", 0, td=p.stub_td, sec=3e-12)
        d.add(f"R{ln}stub {ln}stub 0 0.05")
        if p.clamp:
            d.add(f"Xcl{ln} 0 {ln}{first} dpk" if sign > 0 else f"Xcl{ln} {ln}{first} 0 dpk")
        for a_, b_ in zip(order[:-1], order[1:]):
            d.trace(f"{ln}{a_}", f"{ln}{b_}", 0, z0=p.z_s, td=p.td_s, sec=3e-12)
        d.add(f"R{ln}t {ln}{order[-1]} 0 50")
    # ---- gates and readout
    d.add("Vva va 0 -2.5\nVvk vk 0 2.5")
    for i in range(N):
        if p.gates:
            d.add(f"Xd1_{i} a{i} s{i} dpk\nXd2_{i} s{i} k{i} dpk")
        d.add(f"Ca{i} a{i} pa{i} 0.47p\nCk{i} k{i} pk{i} 0.47p")
        d.add(f"Rba{i} a{i} va 2.2k\nRbk{i} k{i} vk 2.2k")
        d.add(f"Roa{i} a{i} o{i} 1k\nRok{i} k{i} o{i} 1k\nCo{i} o{i} 0 {p.cin}")
    d.add(".options klu reltol=3e-4 abstol=1e-12 vntol=1e-7")
    d.add(f".tran 1p {T_ST + p.tstop:.6g} 0 3p")
    d.add(".end")
    return "\n".join(d.lines) + "\n"


VEC_ALL = ([f"v(o{i})" for i in range(N)] + [f"v(pa{i})" for i in (0, 8, 15)] + [f"v(pk{i})" for i in (0, 8, 15)]
           + [f"v(s{i})" for i in (0, 8, 15)] + [f"v(s{i},a{i})" for i in (0, 8, 15)] + [f"v(k{i},s{i})" for i in (0, 8, 15)])


def sim(p: A, t_peak0: float, vecs=VEC_ALL):
    a = c.waves(build(p, t_peak0), vecs, tmax_list=(None, 2e-12, 5e-12), timeout=1500)
    return a[:, 0], {v: a[:, j + 1] for j, v in enumerate(vecs)}
