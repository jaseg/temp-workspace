"""Trigger source switch without the TMUX136: two four-diode bridges (2 x BAT15-04W each) on the
TLV3801 IN+ node, steered by one 3.3 V GPIO (TRIG_SEL) through a PNP / NPN pair on +2V5 / -2V5.

Circuit (node names as in the deck):
  BUF802 EMF e1 -> 49.9 R -> 50 R line 150 ps -> X1 (BUF_OUT_T end)      bridge 1 (SIG): X1 <-> Y
  EXT source e2 -> 50 R -> 50 R line 200 ps -> X2, 49.9 R X2 -> GND      bridge 2 (EXT): X2 <-> Y
  Bridge k: Da T->X, Dc X->B (package 1: pin 1 = T, pin 3 = X, pin 2 = B),
            Db T->Y, Dd Y->B (package 2: pin 1 = T, pin 3 = Y, pin 2 = B).
  Bridge 1: T1 -Rf- S,  B1 -Rf- SB.   Bridge 2: T2 -Rf- SB,  B2 -Rf- S.
  Q1 PNP (SS8550): E +2V5, B <- 10k <- TRIG_SEL, C = S, R2 S -> -2V5.
  Q2 NPN (MMBT3904): E -2V5, B <- R3 <- S, R4 B -> -2V5, C = SB, R5 SB -> +2V5.
  TRIG_SEL low (reset: 2.0k pull-down on the MCU side): S = +2.4 V, SB = -2.4 V -> bridge 1 on (SIG).
  TRIG_SEL high: S, SB soft -> bridge 2 on (EXT), its current through R5 / R2.
  Y: TLV3801 IN+, 1 pF (datasheet C_IC) + 0.2 pF pad, IB 1 uA.

Reference "TMUX136" deck: 5.7 R, 1.6 pF Con split over both sides, 1.6 pF Coff on the off input and
0.265 pF off coupling (fitted to the datasheet -34 dB at 240 MHz into 50 R).

Models: BAT15 chip model + SOT-323 share (sim/frontend.py dpk: 0.7 nH, 0.16 pF per diode);
MMBT3904 standard SPICE model; SS8550 approximated by a 2N3906-type model with 15 pF Cjc.
Writes RESULT.json; RESULT.md quotes it.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

MODELS = r"""
.model bat15 d(is=74n n=1.07 rs=5.0 xti=1.5 eg=0.59 cjo=138.5f m=0.138 vj=0.224 fc=0.5 tt=3p bv=4.2 ibv=100u)
.subckt dpk a k
Lb a a1 0.7n
D1 a1 k bat15
R1 a1 k 15meg
Cp a k 0.16p
.ends
* BAT15 with a mismatched saturation current (package-to-package spread)
.model bat15m d(is=81.4n n=1.07 rs=5.0 xti=1.5 eg=0.59 cjo=138.5f m=0.138 vj=0.224 fc=0.5 tt=3p bv=4.2 ibv=100u)
.subckt dpkm a k
Lb a a1 0.7n
D1 a1 k bat15m
R1 a1 k 15meg
Cp a k 0.16p
.ends
.model q3904 npn(is=6.734f xti=3 eg=1.11 vaf=74.03 bf=416.4 ne=1.259 ise=6.734f ikf=66.78m xtb=1.5 br=.7371
+ nc=2 isc=0 ikr=0 rc=1 cjc=3.638p mjc=.3085 vjc=.75 fc=.5 cje=4.493p mje=.2593 vje=.75 tr=239.5n tf=301.2p
+ itf=.4 vtf=4 xtf=2 rb=10)
.model q8550 pnp(is=1.41f xti=3 eg=1.11 vaf=18.7 bf=180.7 ne=1.5 ise=0 ikf=300m xtb=1.5 br=4.977 nc=2 isc=0
+ ikr=0 rc=2.5 cjc=15p mjc=.5776 vjc=.75 fc=.5 cje=20p mje=.3677 vje=.75 tr=33.42n tf=179.3p itf=.4 vtf=4
+ xtf=6 rb=10)
"""


def deck(kind: str, sel: float, p: dict, analysis: str, src1: str = "dc 0", src2: str = "dc 0",
         extra: str = "", temp: float = 27.0) -> str:
    L = ["* trig switch", MODELS, f".temp {temp}",
         "Vp vp 0 2.52", "Vn vn 0 -2.44",
         f"Ve1 e1 0 {src1}", "Rs1 e1 l1 49.9", "T1 l1 0 x1 0 z0=50 td=150p", "Cx1 x1 0 0.2p",
         f"Ve2 e2 0 {src2}", "Rs2 e2 l2 50", "T2 l2 0 x2 0 z0=50 td=200p", "Rt2 x2 0 49.9", "Cx2 x2 0 0.2p",
         "Cy y 0 1.2p", "Iby y 0 1u"]
    if kind == "bridge":
        dm = p.get("mismatch", False)
        L += ["X1a t1 x1 dpk", "X1c x1 b1 dpk", f"X1b t1 y {'dpkm' if dm else 'dpk'}", f"X1d y b1 {'dpkm' if dm else 'dpk'}",
              "X2a t2 x2 dpk", "X2c x2 b2 dpk", "X2b t2 y dpk", "X2d y b2 dpk",
              "Ct1 t1 0 0.1p", "Cb1 b1 0 0.1p", "Ct2 t2 0 0.1p", "Cb2 b2 0 0.1p",
              f"Rf1t t1 s {p['rf']}", f"Rf1b b1 sb {p['rf']}", f"Rf2t t2 sb {p.get('rf2', p['rf'])}", f"Rf2b b2 s {p.get('rf2', p['rf'])}",
              f"Vsel gp 0 {sel}", "R1 gp q1b 10k", "Q1 sq q1b q1e q8550", "Lq1e q1e vp 1n", "Lq1c sq s 1n",
              f"R2 s vn {p['r2']}",
              f"R3 s q2b {p['r3']}", f"R4 q2b vn {p['r4']}", "Q2 sbq q2b q2e q3904", "Lq2e q2e vn 1n",
              "Lq2c sbq sb 1n", f"R5 sb vp {p['r5']}",
              "Cq1b q1b 0 0.5p", "Cq2b q2b 0 0.5p", ".options method=gear"]
    else:   # TMUX136 reference, sel 0 = A (x1), sel 1 = B (x2)
        on, off = ("x1", "x2") if sel < 1.6 else ("x2", "x1")
        L += [f"Ron {on} y 5.7", f"Con1 {on} 0 0.8p", "Con2 y 0 0.8p", f"Coff {off} 0 1.6p", f"Ciso {off} y 0.265p"]
    L += [extra, analysis, ".end"]
    return "\n".join(L) + "\n"


def run(dk: str, vecs: list[str]) -> np.ndarray:
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "w.txt")
        dk = dk.replace(".end\n", f".control\nset wr_singlescale\nset wr_vecnames\nrun\nwrdata {out} {' '.join(vecs)}\n.endc\n.end\n")
        open(os.path.join(td, "d.cir"), "w").write(dk)
        r = subprocess.run(["ngspice", "-b", "d.cir"], capture_output=True, text=True, timeout=600, cwd=td)
        if not os.path.exists(out):
            raise RuntimeError(r.stdout[-1500:] + r.stderr[-800:])
        return np.loadtxt(out, skiprows=1)


def op(kind, sel, p, temp=27.0, v1=0.0, v2=0.0):
    nodes = ["v(y)", "v(x1)", "v(x2)"] + (["v(s)", "v(sb)", "v(t1)", "v(b1)", "v(t2)", "v(b2)", "i(vp)", "i(vn)"]
                                          if kind == "bridge" else [])
    a = run(deck(kind, sel, p, ".op", f"dc {v1}", f"dc {v2}", temp=temp), nodes)
    a = np.atleast_2d(a)[0]
    return dict(zip([n.replace("v(", "").replace(")", "") for n in nodes], a[1:1 + len(nodes)]))


def ac(kind, sel, p, drive):
    s1, s2 = ("dc 0 ac 1", "dc 0") if drive == 1 else ("dc 0", "dc 0 ac 1")
    a = run(deck(kind, sel, p, ".ac dec 60 10meg 4g", s1, s2), ["v(y)", "v(x1)", "v(x2)"])
    f = a[:, 0]
    cplx = lambda k: a[:, 1 + 2 * k] + 1j * a[:, 2 + 2 * k]
    return f, cplx(0), cplx(1), cplx(2)


def at(f, h, fx):
    return float(20 * np.log10(np.abs(np.interp(fx, f, np.abs(h)))))


def bw3(f, h):
    g = 20 * np.log10(np.abs(h)); g0 = g[0]
    i = np.where(g < g0 - 3)[0]
    return float(f[i[0]]) if len(i) else float(f[-1])


def main():
    P = {"A": dict(rf="1k", r2="1k", r3="10k", r4="3.3k", r5="1k"),
         "C": dict(rf="1k", rf2="100", r2="1k", r3="10k", r4="3.3k", r5="1k"),
         "B": dict(rf="2.2k", r2="2.2k", r3="10k", r4="3.3k", r5="2.2k")}
    R = {}
    for name, p in P.items():
        r = {}
        for sel, lab in ((0.0, "sig"), (3.3, "ext")):
            o = op("bridge", sel, p)
            r[f"op_{lab}"] = {k: round(v, 4) for k, v in o.items()}
        # insertion / isolation, gain referred to the unloaded source (EMF for SIG, EMF/2 for EXT)
        f, y, x1, x2 = ac("bridge", 0.0, p, 1)
        r["sig_on"] = {"dB_100M": at(f, y, 1e8), "dB_1G": at(f, y, 1e9), "dB_2G": at(f, y, 2e9),
                       "dB_3G": at(f, y, 3e9), "bw3": bw3(f, y), "x1_load_dB_10M": at(f, x1, 1e7)}
        f, y, x1, x2 = ac("bridge", 0.0, p, 2)
        r["ext_off_in_sig"] = {k: at(f, 2 * y, v) for k, v in (("100M", 1e8), ("240M", 2.4e8), ("1G", 1e9), ("2G", 2e9))}
        f, y, x1, x2 = ac("bridge", 3.3, p, 2)
        r["ext_on"] = {"dB_100M": at(f, 2 * y, 1e8), "dB_1G": at(f, 2 * y, 1e9), "dB_2G": at(f, 2 * y, 2e9),
                       "dB_3G": at(f, 2 * y, 3e9), "bw3": bw3(f, 2 * y)}
        f, y, x1, x2 = ac("bridge", 3.3, p, 1)
        r["sig_off_in_ext"] = {k: at(f, y, v) for k, v in (("100M", 1e8), ("240M", 2.4e8), ("1G", 1e9), ("2G", 2e9))}
        r["sig_load_in_ext_dB_10M"] = at(f, x1, 1e7)
        # DC transfer, offset, drift, linearity (SIG on): sweep the BUF802 EMF
        dcr = {}
        for T in (0.0, 27.0, 70.0):
            a = run(deck("bridge", 0.0, p, ".dc Ve1 -0.4 0.4 0.05", temp=T), ["v(y)"])
            v, yy = a[:, 0], a[:, 1]
            g = np.polyfit(v, yy, 1)
            dcr[str(T)] = {"offset_mV_at0": float(1e3 * np.interp(0, v, yy)), "gain": float(g[0]),
                           "nonlin_mVpp": float(1e3 * np.ptp(yy - np.polyval(g, v)))}
        r["dc_sig"] = dcr
        dce = {}
        for T in (0.0, 27.0, 70.0):
            a = run(deck("bridge", 3.3, p, ".dc Ve2 -2.0 2.0 0.1", temp=T), ["v(y)", "v(x2)"])
            x, yy = a[:, 2], a[:, 1]
            m = np.abs(x) <= 0.31
            g = np.polyfit(x[m], yy[m], 1)
            dce[str(T)] = {"offset_mV_at0": float(1e3 * np.interp(0, x, yy)), "gain": float(g[0]),
                           "y_at_x2_+0.9": float(np.interp(0.9, x, yy)), "y_at_x2_-0.9": float(np.interp(-0.9, x, yy))}
        r["dc_ext"] = dce
        # mismatch: 10 % Is between the two packages of bridge 1
        pm = dict(p, mismatch=True)
        dm = {}
        for T in (0.0, 70.0):
            a = run(deck("bridge", 0.0, pm, ".dc Ve1 -0.1 0.1 0.1", temp=T), ["v(y)"])
            dm[str(T)] = float(1e3 * a[1, 1])
        r["mismatch10pct_offset_mV"] = dm
        # overload: SIG at the BUF802 clamp (+/-1.5 V) while EXT is selected, EXT idle
        ov = {}
        for v1 in (-1.5, -0.5, 0.5, 1.5):
            ov[str(v1)] = round(1e3 * op("bridge", 3.3, p, v1=v1)["y"], 2)
        r["ext_mode_y_mV_vs_sig_dc"] = ov
        ov2 = {}
        for v2 in (-2.0, -1.0, 1.0, 2.0):        # EMF; X2 = EMF/2
            ov2[str(v2 / 2)] = round(1e3 * op("bridge", 0.0, p, v2=v2)["y"], 2)
        r["sig_mode_y_mV_vs_ext_dc_at_x2"] = ov2
        # EXT input return loss: line removed, 50 R source straight onto X2
        dk = deck("bridge", 3.3, p, ".ac dec 30 10meg 3g", "dc 0", "dc 0 ac 1").replace(
            "T2 l2 0 x2 0 z0=50 td=200p", "Rl2 l2 x2 0.001")
        a = run(dk, ["v(x2)", "v(l2)"])
        f = a[:, 0]; vx = a[:, 1] + 1j * a[:, 2]
        zin = 50 * vx / (1 - vx)
        rl = 20 * np.log10(np.abs((zin - 50) / (zin + 50)))
        r["ext_return_loss_dB"] = {k: float(np.interp(v, f, rl)) for k, v in (("100M", 1e8), ("1G", 1e9), ("2G", 2e9), ("3G", 3e9))}
        dk = deck("bridge", 0.0, p, ".ac dec 30 10meg 3g", "dc 0", "dc 0 ac 1").replace(
            "T2 l2 0 x2 0 z0=50 td=200p", "Rl2 l2 x2 0.001")
        a = run(dk, ["v(x2)", "v(l2)"])
        f = a[:, 0]; vx = a[:, 1] + 1j * a[:, 2]
        zin = 50 * vx / (1 - vx)
        rl = 20 * np.log10(np.abs((zin - 50) / (zin + 50)))
        r["ext_return_loss_sigmode_dB"] = {k: float(np.interp(v, f, rl)) for k, v in (("100M", 1e8), ("1G", 1e9), ("2G", 2e9))}
        # kick-back: 50 fC in 50 ps into Y (TLV3801 input charge at its own switching; value assumed)
        kb = {}
        for sel, lab in ((0.0, "sig"), (3.3, "ext")):
            ex = "Ikb 0 y pwl(1n 0 1.025n 1m 1.05n 0)"
            a = run(deck("bridge", sel, p, ".tran 2p 6n 0 2p", extra=ex), ["v(y)"])
            t, yy = a[:, 0], a[:, 1]
            base = np.interp(0.9e-9, t, yy)
            dv = yy - base
            ipk = np.argmax(np.abs(dv))
            settle = t[np.where(np.abs(dv) > 0.1 * abs(dv[ipk]))[0][-1]] - 1e-9
            kb[lab] = {"peak_mV": float(1e3 * dv[ipk]), "t10pct_ps": float(1e12 * settle)}
        r["kickback_50fC"] = kb
        # switching time SIG -> EXT and back: Y with SIG at +0.2 V DC, EXT at -0.2 V at X2
        ex = ""
        a = run(deck("bridge", 0.0, p, ".tran 2n 12u 0 2n", src1="dc 0.2", src2="dc -0.4",
                     extra="").replace("Vsel gp 0 0.0", "Vsel gp 0 pwl(1u 0 1.01u 3.3 6u 3.3 6.01u 0)").replace(
                     "T1 l1 0 x1 0 z0=50 td=150p", "Rl1 l1 x1 0.001").replace("T2 l2 0 x2 0 z0=50 td=200p", "Rl2 l2 x2 0.001"),
                ["v(y)"])
        t, yy = a[:, 0], a[:, 1]
        def settle(t0, t1):
            fin = np.interp(t1, t, yy)
            idx = np.where((t > t0) & (t < t1) & (np.abs(yy - fin) > 0.002))[0]
            return float(1e9 * (t[idx[-1]] - t0)) if len(idx) else 0.0
        r["switch_ns_to_2mV"] = {"sig_to_ext": settle(1e-6, 5.9e-6), "ext_to_sig": settle(6e-6, 11.9e-6)}
        r["switch_y_end"] = [float(np.interp(5.9e-6, t, yy)), float(np.interp(11.9e-6, t, yy))]
        r["switch_y_peak_after_ext_to_sig"] = float(yy[t > 6e-6].max())
        R[name] = r
    # TMUX136 reference
    t = {}
    f, y, x1, x2 = ac("tmux", 0.0, {}, 1)
    t["sig_on"] = {"dB_100M": at(f, y, 1e8), "dB_1G": at(f, y, 1e9), "dB_2G": at(f, y, 2e9), "dB_3G": at(f, y, 3e9), "bw3": bw3(f, y)}
    f, y, x1, x2 = ac("tmux", 0.0, {}, 2)
    t["ext_off_in_sig"] = {k: at(f, 2 * y, v) for k, v in (("100M", 1e8), ("240M", 2.4e8), ("1G", 1e9), ("2G", 2e9))}
    f, y, x1, x2 = ac("tmux", 3.3, {}, 2)
    t["ext_on"] = {"dB_100M": at(f, 2 * y, 1e8), "dB_1G": at(f, 2 * y, 1e9), "dB_2G": at(f, 2 * y, 2e9), "bw3": bw3(f, 2 * y)}
    f, y, x1, x2 = ac("tmux", 3.3, {}, 1)
    t["sig_off_in_ext"] = {k: at(f, y, v) for k, v in (("100M", 1e8), ("240M", 2.4e8), ("1G", 1e9), ("2G", 2e9))}
    kb = {}
    for sel, lab in ((0.0, "sig"), (3.3, "ext")):
        a = run(deck("tmux", sel, {}, ".tran 2p 6n 0 2p", extra="Ikb 0 y pwl(1n 0 1.025n 1m 1.05n 0)"), ["v(y)"])
        tt, yy = a[:, 0], a[:, 1]
        dv = yy - np.interp(0.9e-9, tt, yy)
        ipk = np.argmax(np.abs(dv))
        kb[lab] = {"peak_mV": float(1e3 * dv[ipk]),
                   "t10pct_ps": float(1e12 * (tt[np.where(np.abs(dv) > 0.1 * abs(dv[ipk]))[0][-1]] - 1e-9))}
    t["kickback_50fC"] = kb
    R["TMUX136_ref"] = t
    json.dump(R, open(os.path.join(HERE, "RESULT.json"), "w"), indent=1)
    print(json.dumps(R, indent=1))


if __name__ == "__main__":
    main()
