"""Main sampler, strobe-level deck (ngspice, 1 ps steps, ~3.5 ns per run).

BUF802 -> splitter -> 4-diode bridge (2x BAT15-04W, sim/frontend.py model with package)
-> hold node 2.2 pF + TPH2501 input (1 pF CM on each input, 2.7 pF differential, pads)
-> TPH2501 G=+5 (behavioural two-pole model, see amp.py).
Strobe: a step with a 120 ps 10-90 % erf edge minus the same step 130 ps later (what a
shorted clip stub makes), amplitude given as the step into a matched 50 R load, then a 1:1
balun (floating rails) as in sim/scope_sampler.py.

  python3 bridge.py        # writes bridge.json in this directory
"""
from __future__ import annotations

import dataclasses
import json
import math
import multiprocessing as mp
import os
import re
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "sim"))
import frontend as f  # noqa: E402
import amp  # noqa: E402

C_HOLD, C_PAD, C_CM, C_DIFF = 2.2e-12, 0.2e-12, 1.0e-12, 2.7e-12


@dataclasses.dataclass
class P:
    v_strobe: float = 3.0       # step into matched 50 R before clipping
    tr: float = 120e-12         # 10-90 %
    width: float = 130e-12      # delay between the step and its clipped copy (50 % width)
    split: str = "unequal"      # "unequal": BUF802 pin -10R-> bridge, -49.9R-> trigger line (hi-Z end)
                                # "star": BUF802 -50R- 3x16.7R splitter, trigger leg terminated 50R
    r_series: float = 25.0
    v_rev: float = 2.0          # VBIAS_K - VBIAS_A
    v_cm_rail: float = 0.0      # DC shift of both rails (self-bias / bootstrap tests)
    r_bias: float = 2e3
    c_couple: str = "1n"
    c_par_a: float = 0.3e-12
    c_par_b: float = 0.3e-12
    amp_cin: bool = True        # include the TPH2501 input capacitances
    in_step: float = 0.2
    t_strobe: float = 1.5e-9
    t_in: float = 1.5e-9
    t_tail: float = 60e-9       # amp settles (tau 6.6 ns); charge-conservation correction for the rest
    v_ls: float = 0.0
    in_bw: float = 0.0          # first-order input bandwidth (BUF802 stand-in), 0 = 1 ps step


def strobe_pwl(p: P) -> str:
    s = p.tr / 2.563                       # erf edge: 10-90 % = 2.563 sigma
    t = np.arange(0, p.t_strobe + p.width + 6 * s, 5e-12)
    phi = lambda x: 0.5 * (1 + np.vectorize(math.erf)(x / math.sqrt(2)))
    v = 2 * p.v_strobe * (phi((t - p.t_strobe) / s) - phi((t - p.t_strobe - p.width) / s))
    v[t < p.t_strobe - 6 * s] = 0
    return " ".join(f"{a:.4g} {b:.5g}" for a, b in zip(t, v))


def build(p: P) -> str:
    d = f.Deck()
    d.add("* lowcost main sampler")
    d.add(f.MODELS)
    d.add(amp.SUBCKT)
    d.add(f"Vdrv drv_e 0 pwl({strobe_pwl(p)})")
    d.add("Rdrv drv_e drv 50")
    d.trace("drv", "bal_in", 3.0)
    l_cm, l_leak = 1e-6, 0.3e-9
    k = 1 - l_leak / (2 * l_cm)
    d.add(f"Lb1 bal_in bal_a {l_cm}")
    d.add(f"Lb2 0 bal_b {l_cm}")
    d.add(f"Kb Lb1 Lb2 {k:.9f}")
    d.add("Rcm1 bal_in bal_a 2k")
    d.add("Rcm2 0 bal_b 2k")
    d.add("Rterm bal_a bal_b 1k")
    d.add(f"Cpara bal_a 0 {p.c_par_a}")
    d.add(f"Cparb bal_b 0 {p.c_par_b}")
    for n in ("a", "b"):
        d.cap0402(f"cblk{n}", f"bal_{n}", f"rail_{n}", p.c_couple)
    d.add(f"Vba vba 0 {p.v_cm_rail - p.v_rev / 2}")
    d.add(f"Vbk vbk 0 {p.v_cm_rail + p.v_rev / 2}")
    d.add(f"Rba rail_a vba {p.r_bias}")
    d.add(f"Rbk rail_b vbk {p.r_bias}")
    d.add("Vsa rail_a ra_x 0")
    d.add("Vsk kk_x rail_b 0")
    d.add(f"Ra ra_x ka {p.r_series}")
    d.add(f"Rk kk kk_x {p.r_series}")
    for side in ("ls", "hs"):
        d.add(f"Xda_{side} ka {side} dpk")
        d.add(f"Xdk_{side} {side} kk dpk")
    # input: BUF802 emf (1 ps step), 1.2 ohm + 0.5 nH output
    a, b = -p.in_step / 2, p.in_step / 2
    if p.in_bw:
        d.add(f"Vin in_e0 0 pwl(0 {a} {p.t_in:.6g} {a} {p.t_in + 1e-12:.6g} {b})")
        d.add("Rbw in_e0 in_f 1k")
        d.add(f"Cbw in_f 0 {1 / (2 * math.pi * p.in_bw * 1e3):.5g}")
        d.add("Ebw in_e 0 in_f 0 1")
    else:
        d.add(f"Vin in_e 0 pwl(0 {a} {p.t_in:.6g} {a} {p.t_in + 1e-12:.6g} {b})")
    d.add("Rbo in_e bo_x 1.2")
    d.add("Lbo bo_x buf 0.5n")
    d.add("Cbuf buf 0 0.3p")
    if p.split == "unequal":
        d.add("Rs buf s1 10")
        d.trace("s1", "hs", 3.0)
        d.add("Rt buf t1 49.9")
        d.trace("t1", "trig", 30.0)
        d.add("Ctrig trig 0 2.5p")          # TMUX136 + TLV3801 input, unterminated end
    else:
        d.add("R50 buf bo 50")
        d.add("Rst bo star 16.7")
        d.add("Rsa star s1 16.7")
        d.trace("s1", "hs", 3.0)
        d.add("Rtr star t1 16.7")
        d.trace("t1", "trig", 30.0)
        d.add("Rtt trig 0 50")
        d.add("Ctrig trig 0 2.5p")
    d.add(f"Ch ls 0 {C_HOLD}")
    d.add(f"Cpad ls 0 {C_PAD}")
    if p.amp_cin:
        d.add(f"Ccmp ls 0 {C_CM}")
        d.add(f"Cdif ls inv {C_DIFF}")
        d.add(f"Ccmn inv 0 {C_CM + C_PAD}")
    else:
        d.add("Cdif ls inv 1f")
        d.add("Ccmn inv 0 0.2p")
    d.add("Xu1 ls inv out vp vn tph2501")
    d.add("Vp vp 0 2.5")
    d.add("Vn vn 0 -2.5")
    d.add("Rf out inv 1k")
    d.add("Rg inv 0 499")       # G = +3.0 (see RESULT.md: +5 would overrange the level shifter)
    d.add("Rl out 0 2k")
    d.add(f".ic v(ls)={p.v_ls:.9g}")   # amp finds its own DC state
    tend = p.t_strobe + p.t_tail
    ts = p.t_strobe - 0.1e-9
    d.add(".options klu reltol=3e-4 abstol=1e-12 vntol=1e-7")
    d.add(f".tran 1p {tend + 5e-12:.6g} 0 2p")
    d.add(f".meas tran end_ls find v(ls) at={tend:.6g}")
    d.add(f".meas tran end_inv find v(inv) at={tend:.6g}")
    d.add(f".meas tran pk_drive max par('v(ka)-v(kk)') from={ts:.6g}")
    d.add(f".meas tran kick_hs pp v(hs) from={ts:.6g}")
    d.add(f".meas tran kick_buf pp v(buf) from={ts:.6g}")
    d.add(f".meas tran kick_trig pp v(trig) from={ts:.6g}")
    d.add(f".meas tran qa integ i(vsa) from={ts:.6g} to={tend:.6g}")
    d.add(f".meas tran qk integ i(vsk) from={ts:.6g} to={tend:.6g}")
    d.add(".end")
    return "\n".join(d.lines) + "\n"


KEYS = ("end_ls", "end_inv", "pk_drive", "kick_hs", "kick_buf", "kick_trig", "qa", "qk")


def run(p: P) -> dict[str, float]:
    err = ""
    for tmax in ("2p", "1.5p", "1p", "3p"):
        with tempfile.NamedTemporaryFile("w", suffix=".cir", delete=False) as fh:
            fh.write(build(p).replace(" 0 2p\n", f" 0 {tmax}\n"))
            path = fh.name
        try:
            r = subprocess.run(["ngspice", "-b", path], capture_output=True, text=True, timeout=600)
        finally:
            os.unlink(path)
        out = {m.group(1): float(m.group(2)) for m in re.finditer(
            r"^(%s)\s*=\s*([-+0-9.eE]+)" % "|".join(KEYS), r.stdout, re.M)}
        if len(out) == len(KEYS):
            # charge on the hold node is conserved once the diodes are off: when the amp has
            # settled (inv -> ls) the differential Cin charge moves onto the hold capacitance
            c_g = C_HOLD + C_PAD + (C_CM if p.amp_cin else 0)
            c_d = C_DIFF if p.amp_cin else 1e-15
            out["settled"] = out["end_ls"] + c_d * (out["end_ls"] - out["end_inv"]) / c_g
            return out
        err = r.stdout[-1500:] + r.stderr[-1500:]
    raise RuntimeError(err)


def _run(p):
    return run(p)


def efficiency(pool, p: P, v0: float = 0.0, dv: float = 0.02) -> tuple[float, float]:
    """(efficiency, steady-state held value) with the input held at its 'low' level."""
    q = dataclasses.replace(p, t_in=p.t_strobe + p.t_tail + 1e-9)   # input never moves
    r0, r1 = pool.map(_run, [dataclasses.replace(q, v_ls=v0), dataclasses.replace(q, v_ls=v0 + dv)])
    d0, d1 = r0["settled"] - v0, r1["settled"] - v0 - dv
    eff = -(d1 - d0) / dv
    return eff, v0 + d0 / eff, r0


def step_response(pool, p: P, xs) -> dict:
    eff, v_lo, quiet = efficiency(pool, p, v0=-0.05)
    runs = pool.map(_run, [dataclasses.replace(p, t_in=p.t_strobe - x, v_ls=v_lo) for x in xs]
                    + [dataclasses.replace(p, t_in=p.t_strobe + 1e-9, v_ls=v_lo)])
    # feed-through of an input step that comes after the strobe (diodes off), per volt
    ft = (runs.pop()["settled"] - (v_lo + 0 * eff)) / p.in_step
    v = np.array([v_lo + (r["settled"] - (ft * p.in_step if x < 0 else 0) - v_lo) / eff for r, x in zip(runs, xs)])
    hi = v[-2:].mean()
    n = (v - v_lo) / (hi - v_lo)
    from wave import crossing  # sim/wave.py
    tr = crossing(np.array(xs), n, 0.9) - crossing(np.array(xs), n, 0.1)
    return dict(params=dataclasses.asdict(p), x=list(map(float, xs)), v=v.tolist(), n=n.tolist(), eff=eff,
                gain=(hi - v_lo) / p.in_step, v_lo=v_lo, tr_10_90=tr, overshoot=float(n.max() - 1),
                quiet=quiet, feedthrough=ft)


XS = np.round(np.concatenate([[-0.4e-9, -0.2e-9], np.arange(-0.12e-9, 0.30e-9, 0.02e-9),
                              [0.4e-9, 0.6e-9, 0.9e-9, 1.2e-9]]), 13)

CASES = [
    ("3 V strobe, unequal split (10 R)", P()),
    ("2 V strobe, unequal split (10 R)", P(v_strobe=2.0)),
    ("3 V strobe, 3x16.7 R splitter (50 R)", P(split="star")),
    ("2 V strobe, 3x16.7 R splitter (50 R)", P(v_strobe=2.0, split="star")),
    ("2 V strobe, bias 1.2 V, unequal split", P(v_strobe=2.0, v_rev=1.2)),
    ("3 V strobe, unequal, 47 pF / 1 k bias feed (final)", P(c_couple="47p", r_bias=1e3)),
    ("final, input step through 2 GHz 1st-order (175 ps)", P(c_couple="47p", r_bias=1e3, in_bw=2e9)),
]
if os.environ.get("ONLY_LAST"):
    CASES = CASES[-1:]

SENS = [
    ("3 V, no amp Cin (earlier deck)", P(amp_cin=False)),
    ("3 V, coupling 47 pF, bias 1 k", P(c_couple="47p", r_bias=1e3)),
    ("3 V, rail C mismatch 0.3/0.45 pF", P(c_par_b=0.45e-12)),
    ("3 V, bias 2.4 V", P(v_rev=2.4)),
    ("3 V, bias 1.6 V", P(v_rev=1.6)),
    ("2 V, bias 1.2 V", P(v_strobe=2.0, v_rev=1.2)),
    ("3 V, edge 150 ps", P(tr=150e-12)),
    ("3 V, width 160 ps", P(width=160e-12)),
    ("3 V, rails both +0.1 V (hold-node 0.1 V bootstrap)", P(v_cm_rail=0.1)),
]


def quick(pool, p: P) -> dict:
    """efficiency, gain from two input levels, rectified charge, kick-out."""
    eff, v_lo, quiet = efficiency(pool, p, v0=-0.05)
    r_hi = pool.map(_run, [dataclasses.replace(p, t_in=p.t_strobe - 1.2e-9, v_ls=v_lo)])[0]
    v_hi = v_lo + (r_hi["settled"] - v_lo) / eff
    return dict(params=dataclasses.asdict(p), eff=eff, gain=(v_hi - v_lo) / p.in_step, v_lo=v_lo, quiet=quiet)


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    path = os.path.join(HERE, "bridge.json")
    res = json.load(open(path)) if os.path.exists(path) else {}
    with mp.Pool(3) as pool:
        if which in ("all", "step"):
            for label, p in CASES:
                r = step_response(pool, p, XS)
                res[label] = r
                q = r["quiet"]
                print(f"{label:44s} ft {r['feedthrough']*100:.2f} % tr {r['tr_10_90']*1e12:5.0f} ps ov {r['overshoot']*100:4.0f} % gain {r['gain']:.3f} "
                      f"eff {r['eff']*100:4.1f} % vlo {r['v_lo']*1e3:6.1f} mV drive {q['pk_drive']:.2f} "
                      f"kick hs/buf/trig {q['kick_hs']*1e3:.1f}/{q['kick_buf']*1e3:.2f}/{q['kick_trig']*1e3:.2f} mVpp "
                      f"qa {q['qa']*1e12:.3f} qk {q['qk']*1e12:.3f} pC", flush=True)
                json.dump(res, open(path, "w"), indent=1)
        if which in ("all", "sens"):
            for label, p in SENS:
                r = quick(pool, p)
                res[label] = r
                q = r["quiet"]
                print(f"{label:44s} gain {r['gain']:.3f} eff {r['eff']*100:4.1f} % vlo {r['v_lo']*1e3:6.1f} mV "
                      f"drive {q['pk_drive']:.2f} kick hs/buf/trig {q['kick_hs']*1e3:.1f}/{q['kick_buf']*1e3:.2f}/"
                      f"{q['kick_trig']*1e3:.2f} qa {q['qa']*1e12:.3f} qk {q['qk']*1e12:.3f} pC", flush=True)
                json.dump(res, open(path, "w"), indent=1)
