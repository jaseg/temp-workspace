"""Sampler bridge with the strobe arms STRB_A / STRB_K between balun T401 and C201 / C202 (validation RF-1/2/3).

Deck = sim/sampler/bridge.py (final circuit: 24.9 R rails, 47 pF C0G coupling, 1 k bias feeds at +/-1 V, 10 R
input leg from the BUF802 model, unequal splitter, 2.2 pF hold + TPH2501 Cin) with these changes:
  * strobe = simulated 2xTRF chain output (strobe_wave.json, 4.30 V step into 50 R, 152 ps), Thevenin 2V/50 R,
    1.37 mm to the tap, shorted stub 80 + 5 ps (RF-2), BAT15 clamp at the tap (D401), 1.6 mm tap -> T401.1
  * balun T401 as in sim/scope_sampler.py (1 uH CM, 0.3 nH leakage, 2 k loss, 0.3 pF per output)
  * arms: 50 R lines, 5.925 ps/mm (6-layer L1, 0.16 mm); R204 1 k inline on A at 1.45 mm from T401.2 and on a
    0.765 mm stub (+30 fF pad) off K at 3.8 mm from T401.4 (as built); optional coupled pair, damping
  * rail node 0.15 pF each (C201.2 / R202 / R205 copper), rail tracks R202/R203 -> diodes 2.565 mm
  * hold node + 268 fF layout copper (THEORY-6)
  * 2.5 ns tail: once the diodes are off the hold-node charge is conserved, so the settled value follows from
    v(ls), v(inv) at any later time (same correction as sim/sampler).
python3 arms.py [case-index ...]   -> results.json
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
import amp  # noqa: E402  (local copy of sim/sampler/amp.py)

PS_MM = 5.925e-12
C_HOLD, C_PAD, C_CM, C_DIFF, C_CU = 2.2e-12, 0.2e-12, 1.0e-12, 2.7e-12, 0.268e-12
WAVE = json.load(open(os.path.join(HERE, "strobe_wave.json")))


@dataclasses.dataclass
class P:
    arm_mm: float = 16.747      # each arm, T401 pad -> C201 / C202 pad
    clip_mm: float = 1.6        # CLIP line, stub tap -> T401.1 (single-ended 50 R)
    stub_td: float = 85e-12     # TL401 80 ps + 5 ps shorted end (RF-2)
    r204: float = 1e3
    r204_pos: str = "asbuilt"   # "asbuilt" | "sym" (both pads inline at the balun end) | "bridge" (at C201/C202)
    coupled: bool = False       # edge-coupled pair, Zodd 50 R, Zeven ~56 R (kL 0.08, Cm/Cs 0.03)
    r_ser_bal: float = 0.0      # series R per arm at the balun end (back termination)
    r_sh_end: float = 0.0       # extra shunt R across the arms at the bridge end (0 = none)
    c_sh_end: str = ""          # series C with r_sh_end ("" = DC path; R204 position unchanged)
    scale: float = 1.0          # strobe amplitude factor
    v_rev: float = 2.0
    in_step: float = 0.2
    t_strobe: float = 1.5e-9
    t_in: float = 1.5e-9
    t_tail: float = 2.5e-9
    v_ls: float = 0.0
    in_bw: float = 10e9         # first-order input edge (35 ps) for the aperture runs
    src: str = "clean"          # "clean": 1.2 R source, no lead L (aperture); "buf802": sim/sampler model (kick-out)


def strobe_pwl(p: P) -> str:
    t = np.array(WAVE["t"]) + p.t_strobe
    v = np.array(WAVE["v"]) * 2 * p.scale
    k = t > 0.05e-9
    pts = [(0.0, 0.0)] + list(zip(t[k], v[k]))
    return " ".join(f"{a:.5g} {b:.5g}" for a, b in pts)


def line(d: f.Deck, a: str, b: str, td: float, z0: float = 50.0) -> None:
    if td > 0:
        d.trace(a, b, 0, z0=z0, td=td)
    else:
        d.add(f"R{a}_{b} {a} {b} 1m")


def coupled(d: f.Deck, a1, b1, a2, b2, td, z_odd=50.0, kl=0.08, kc=0.03, sec=3e-12):
    """symmetric edge-coupled pair as an LC ladder; td = odd-mode delay"""
    n = max(1, math.ceil(td / sec))
    lodd, codd = z_odd * td / n, td / z_odd / n
    ls_, cs = lodd / (1 - kl), codd / (1 + 2 * kc)
    cm = kc * cs
    i = d.uid()
    pa, pb = a1, a2
    for k in range(n):
        na = b1 if k == n - 1 else f"cp{i}a{k}"
        nb = b2 if k == n - 1 else f"cp{i}b{k}"
        w = 0.5 if k == 0 else 1.0
        d.add(f"Cca{i}_{k} {pa} 0 {cs * w:.5g}")
        d.add(f"Ccb{i}_{k} {pb} 0 {cs * w:.5g}")
        d.add(f"Ccm{i}_{k} {pa} {pb} {cm * w:.5g}")
        d.add(f"Lca{i}_{k} {pa} {na} {ls_:.5g}")
        d.add(f"Lcb{i}_{k} {pb} {nb} {ls_:.5g}")
        d.add(f"Kc{i}_{k} Lca{i}_{k} Lcb{i}_{k} {kl}")
        pa, pb = na, nb
    d.add(f"Cca{i}_e {b1} 0 {cs / 2:.5g}")
    d.add(f"Ccb{i}_e {b2} 0 {cs / 2:.5g}")
    d.add(f"Ccm{i}_e {b1} {b2} {cm / 2:.5g}")


def build(p: P) -> str:
    d = f.Deck()
    d.add("* sampler bridge with strobe arms")
    d.add(f.MODELS)
    d.add(amp.SUBCKT)
    d.add(f"Vdrv drv_e 0 pwl({strobe_pwl(p)})")
    d.add("Rdrv drv_e drv 50")
    d.add("Cdrv drv 0 0.3p")
    line(d, "drv", "tap", 1.37 * PS_MM)
    line(d, "tap", "stub_end", p.stub_td)
    d.add("Rstub stub_end 0 0.05")
    d.add("Xclamp 0 tap dpk")                    # D401 BAT15-03W, K to the tap, A to GND
    line(d, "tap", "bal_in", p.clip_mm * PS_MM)
    l_cm, l_leak = 1e-6, 0.3e-9
    d.add(f"Lb1 bal_in bal_a {l_cm}")
    d.add(f"Lb2 0 bal_b {l_cm}")
    d.add(f"Kb Lb1 Lb2 {1 - l_leak / (2 * l_cm):.9f}")
    d.add("Rcm1 bal_in bal_a 2k")
    d.add("Rcm2 0 bal_b 2k")
    d.add("Cpara bal_a 0 0.3p")
    d.add("Cparb bal_b 0 0.3p")
    # back termination at the balun end
    if p.r_ser_bal:
        d.add(f"Rsba bal_a a0 {p.r_ser_bal}")
        d.add(f"Rsbb bal_b k0 {p.r_ser_bal}")
    else:
        d.add("Rsba bal_a a0 1m")
        d.add("Rsbb bal_b k0 1m")
    L = p.arm_mm
    if p.coupled:
        coupled(d, "a0", "sa", "k0", "sk", L * PS_MM)
        d.add(f"R204 a0 k0 {p.r204}")
    elif p.r204_pos == "asbuilt" and L > 3.9:
        line(d, "a0", "a1", 1.45 * PS_MM)
        line(d, "a1", "sa", (L - 1.45) * PS_MM)
        line(d, "k0", "k1", 3.8 * PS_MM)
        line(d, "k1", "sk", (L - 3.8) * PS_MM)
        line(d, "k1", "k1s", 0.765 * PS_MM)
        d.add("Cr204p k1s 0 30f")
        d.add(f"R204 a1 k1s {p.r204}")
    else:
        line(d, "a0", "sa", L * PS_MM)
        line(d, "k0", "sk", L * PS_MM)
        if p.r204_pos == "bridge":
            d.add(f"R204 sa sk {p.r204}")
        else:
            d.add(f"R204 a0 k0 {p.r204}")
    if p.r_sh_end:
        if p.c_sh_end:
            d.add(f"Rshe sa she {p.r_sh_end}")
            d.add(f"Cshe she sk {p.c_sh_end}")
        else:
            d.add(f"Rshe sa sk {p.r_sh_end}")
    for n, s in (("a", "sa"), ("b", "sk")):
        d.cap0402(f"cblk{n}", s, f"rail_{n}", "47p")
        d.add(f"Crn{n} rail_{n} 0 0.15p")
    d.add(f"Vba vba 0 {-p.v_rev / 2}")
    d.add(f"Vbk vbk 0 {p.v_rev / 2}")
    d.add("Rba rail_a vba 1k")
    d.add("Rbk rail_b vbk 1k")
    d.add("Vsa rail_a ra_x 0")
    d.add("Vsk kk_x rail_b 0")
    d.add("Ra ra_x ka0 24.9")
    d.add("Rk kk0 kk_x 24.9")
    line(d, "ka0", "ka", 2.565 * PS_MM)
    line(d, "kk", "kk0", 2.565 * PS_MM)
    for side in ("ls", "hs"):
        d.add(f"Xda_{side} ka {side} dpk")
        d.add(f"Xdk_{side} {side} kk dpk")
    a, b = -p.in_step / 2, p.in_step / 2
    if p.in_bw:
        d.add(f"Vin in_e0 0 pwl(0 {a} {p.t_in:.6g} {a} {p.t_in + 1e-12:.6g} {b})")
        d.add("Rbw in_e0 in_f 1k")
        d.add(f"Cbw in_f 0 {1 / (2 * math.pi * p.in_bw * 1e3):.5g}")
        d.add("Ebw in_e 0 in_f 0 1")
    else:
        d.add(f"Vin in_e 0 pwl(0 {a} {p.t_in:.6g} {a} {p.t_in + 1e-12:.6g} {b})")
    d.add("Rbo in_e bo_x 1.2")
    d.add("Lbo bo_x buf %s" % ("0.5n" if p.src == "buf802" else "1p"))
    d.add("Cbuf buf 0 0.3p")
    d.add("Rs buf s1 10")
    d.trace("s1", "hs", 0, td=3.12 * PS_MM)
    d.add("Rt buf t1 49.9")
    d.trace("t1", "trig", 30.0)
    d.add("Ctrig trig 0 2.5p")
    d.add(f"Ch ls 0 {C_HOLD}")
    d.add(f"Cpad ls 0 {C_PAD}")
    d.add(f"Ccu ls 0 {C_CU}")
    d.add(f"Ccmp ls 0 {C_CM}")
    d.add(f"Cdif ls inv {C_DIFF}")
    d.add(f"Ccmn inv 0 {C_CM + C_PAD}")
    d.add("Xu1 ls inv out vp vn tph2501")
    d.add("Vp vp 0 2.5")
    d.add("Vn vn 0 -2.5")
    d.add("Rf out inv 1k")
    d.add("Rg inv 0 499")
    d.add("Rl out 0 2k")
    d.add(f".ic v(ls)={p.v_ls:.9g}")
    tend = p.t_strobe + p.t_tail
    ts = p.t_strobe - 0.3e-9
    t2 = p.t_strobe + 0.35e-9          # main conduction is over by then (lumped case)
    d.add(".options klu reltol=3e-4 abstol=1e-12 vntol=1e-7")
    d.add(f".tran 1p {tend + 5e-12:.6g} 0 2p")
    d.add(f".meas tran end_ls find v(ls) at={tend:.6g}")
    d.add(f".meas tran end_inv find v(inv) at={tend:.6g}")
    d.add(f".meas tran pk_drive max par('v(ka)-v(kk)') from={ts:.6g}")
    d.add(f".meas tran t_pk when par('v(ka)-v(kk)')=0 rise=1 from={ts:.6g}")
    d.add(f".meas tran pk_late max par('v(ka)-v(kk)') from={t2:.6g}")
    d.add(f".meas tran rev_pk min par('v(ka)-v(kk)') from={ts:.6g}")
    d.add(f".meas tran pk_rail max par('v(sa)-v(sk)') from={ts:.6g}")
    d.add(f".meas tran kick_hs pp v(hs) from={ts:.6g}")
    d.add(f".meas tran kick_buf pp v(buf) from={ts:.6g}")
    d.add(f".meas tran kick_trig pp v(trig) from={ts:.6g}")
    d.add(f".meas tran qa integ i(vsa) from={ts:.6g} to={tend:.6g}")
    d.add(".end")
    return "\n".join(d.lines) + "\n"


KEYS = ("end_ls", "end_inv", "pk_drive", "pk_late", "rev_pk", "pk_rail", "kick_hs", "kick_buf", "kick_trig", "qa")


def run(p: P, wave: list[str] | None = None) -> dict:
    err = ""
    text = build(p)
    if wave:
        text = text.replace(".end\n", ".control\nrun\nset wr_singlescale\nwrdata %s " % wave[0] + " ".join(wave[1:]) + "\n.endc\n.end\n")
    for tmax in ("2p", "1.5p", "1p", "3p"):
        with tempfile.NamedTemporaryFile("w", suffix=".cir", delete=False) as fh:
            fh.write(text.replace(" 0 2p\n", f" 0 {tmax}\n"))
            path = fh.name
        try:
            r = subprocess.run(["ngspice", "-b", path], capture_output=True, text=True, timeout=900)
        finally:
            os.unlink(path)
        out = {m.group(1): float(m.group(2)) for m in re.finditer(
            r"^(%s)\s*=\s*([-+0-9.eE]+)" % "|".join(KEYS), r.stdout, re.M)}
        if len(out) == len(KEYS):
            cg = C_HOLD + C_PAD + C_CU + C_CM
            out["settled"] = out["end_ls"] + C_DIFF * (out["end_ls"] - out["end_inv"]) / cg
            return out
        err = r.stdout[-1500:] + r.stderr[-1500:]
    raise RuntimeError(err)


def efficiency(pool, p: P, v0=-0.05, dv=0.02):
    q = dataclasses.replace(p, t_in=p.t_strobe + p.t_tail + 1e-9)
    r0, r1 = pool.map(run, [dataclasses.replace(q, v_ls=v0), dataclasses.replace(q, v_ls=v0 + dv)])
    d0, d1 = r0["settled"] - v0, r1["settled"] - v0 - dv
    eff = -(d1 - d0) / dv
    return eff, v0 + d0 / eff, r0


XS = np.round(np.concatenate([np.arange(-1.2e-9, -0.42e-9, 0.04e-9), np.arange(-0.42e-9, 0.1e-9, 0.01e-9),
                              [0.2e-9, 0.4e-9, 0.6e-9]]), 13)


def step_response(pool, p: P, xs=XS) -> dict:
    eff, v_lo, _ = efficiency(pool, p)
    quiet = run(dataclasses.replace(p, src="buf802", in_bw=0.0, t_in=p.t_strobe + p.t_tail + 1e-9, v_ls=v_lo))
    runs = pool.map(run, [dataclasses.replace(p, t_in=p.t_strobe - x, v_ls=v_lo) for x in xs])
    v = np.array([v_lo + (r["settled"] - v_lo) / eff for r in runs])
    hi = v[-2:].mean()
    n = (v - v_lo) / (hi - v_lo)
    import wave as w  # sim/wave.py
    xs = np.array(xs)
    gain = (hi - v_lo) / p.in_step
    i50 = int(np.flatnonzero(n >= 0.5)[0])
    x10 = w.crossing(xs, n, 0.1)
    m = xs >= x10 - 0.03e-9            # main edge only
    tr = w.crossing(xs[m], n[m], 0.9) - w.crossing(xs[m], n[m], 0.1)
    pre = xs < x10 - 0.06e-9           # region where a second (later) sampling instant would show
    return dict(params=dataclasses.asdict(p), x=xs.tolist(), n=n.tolist(), eff=eff, gain=gain,
                ped=v_lo + gain * p.in_step / 2, tr=tr, x50=float(xs[i50]), overshoot=float(n.max() - 1),
                early=float(n[pre].max()), early_min=float(n[pre].min()), quiet=quiet)


SYS = dict(src="buf802", in_bw=2e9)          # input through the BUF802 model behind a 2 GHz first-order edge
CASES = [
    ("lumped (no arms, old deck geometry)", P(arm_mm=0.0, r204_pos="sym")),
    ("as built: 16.75 mm arms, R204 as built", P()),
    ("as built, stub 80 ps (RF-2 fixed)", P(stub_td=80e-12)),
    ("16.75 mm, R204 symmetric at balun", P(r204_pos="sym")),
    ("16.75 mm coupled pair (Zodd 50, Zeven 56)", P(coupled=True)),
    ("16.75 mm, R204 1 k at bridge end", P(r204_pos="bridge")),
    ("16.75 mm, + 200 R across bridge end", P(r_sh_end=200.0)),
    ("16.75 mm, + 100 R + 10 pF across bridge end", P(r_sh_end=100.0, c_sh_end="10p")),
    ("16.75 mm, 12 R series per arm at balun", P(r_ser_bal=12.0)),
    ("16.75 mm, 25 R series per arm at balun", P(r_ser_bal=25.0)),
    ("4 mm arms, T401 moved, tap/stub stay (CLIP 14.35 mm)", P(arm_mm=4.0, clip_mm=14.35, r204_pos="sym")),
    ("4 mm arms, T401 + tap + stub at the bridge", P(arm_mm=4.0, r204_pos="sym")),
    ("8 mm arms (tap moved along)", P(arm_mm=8.0, r204_pos="sym")),
    ("12 mm arms (tap moved along)", P(arm_mm=12.0, r204_pos="sym")),
    ("as built, bias +/-1.3 V", P(v_rev=2.6)),
    ("as built, bias +/-1.5 V", P(v_rev=3.0)),
    ("as built, strobe -25 %", P(scale=0.75)),
    ("as built, strobe +10 %", P(scale=1.1)),
    ("lumped, strobe -25 %", P(arm_mm=0.0, r204_pos="sym", scale=0.75)),
    ("4 mm + tap at bridge, strobe -25 %", P(arm_mm=4.0, r204_pos="sym", scale=0.75)),
    ("as built, bias +/-1.3 V, strobe -25 %", P(v_rev=2.6, scale=0.75)),
    ("system: lumped, BUF802 2 GHz", P(arm_mm=0.0, r204_pos="sym", **SYS)),
    ("system: as built, BUF802 2 GHz", P(**SYS)),
    ("system: as built, bias +/-1.3 V, BUF802 2 GHz", P(v_rev=2.6, **SYS)),
    ("REC: as built + R204 sym + stub 80 ps + bias +/-1.3 V", P(r204_pos="sym", stub_td=80e-12, v_rev=2.6)),
    ("REC, strobe -25 %", P(r204_pos="sym", stub_td=80e-12, v_rev=2.6, scale=0.75)),
    ("REC, strobe +10 %", P(r204_pos="sym", stub_td=80e-12, v_rev=2.6, scale=1.1)),
    ("REC, bias +/-1.46 V", P(r204_pos="sym", stub_td=80e-12, v_rev=2.92)),
    ("system: REC, BUF802 2 GHz", P(r204_pos="sym", stub_td=80e-12, v_rev=2.6, **SYS)),
    ("system: 4 mm + tap at bridge, stub 80 ps, BUF802 2 GHz", P(arm_mm=4.0, r204_pos="sym", stub_td=80e-12, **SYS)),
    ("4 mm + tap at bridge, stub 80 ps, bias +/-1.15 V", P(arm_mm=4.0, r204_pos="sym", stub_td=80e-12, v_rev=2.3)),
    ("system: 4 mm + tap at bridge, stub 80 ps, bias +/-1.15 V", P(arm_mm=4.0, r204_pos="sym", stub_td=80e-12, v_rev=2.3, **SYS)),
]

if __name__ == "__main__":
    sel = [int(a) for a in sys.argv[1:]]
    path = os.path.join(HERE, "results.json")
    res = json.load(open(path)) if os.path.exists(path) else {}
    with mp.Pool(4) as pool:
        for i, (label, p) in enumerate(CASES):
            if sel and i not in sel:
                continue
            r = step_response(pool, p)
            res[label] = r
            q = r["quiet"]
            print(f"{i:2d} {label:44s} tr {r['tr']*1e12:4.0f} ps ov {r['overshoot']*100:3.0f} % early {r['early']*100:+4.1f}/{r['early_min']*100:+4.1f} % "
                  f"gain {r['gain']:.3f} eff {r['eff']*100:4.1f} % ped {r['ped']*1e3:+5.1f} mV drive {q['pk_drive']:.2f} late {q['pk_late']:+.2f} "
                  f"rev {q['rev_pk']:.2f} kick hs/buf/trig {q['kick_hs']*1e3:.0f}/{q['kick_buf']*1e3:.0f}/{q['kick_trig']*1e3:.1f} mV", flush=True)
            json.dump(res, open(path, "w"), indent=1)
