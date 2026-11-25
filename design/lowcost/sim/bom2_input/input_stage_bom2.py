"""COPY of sim/input/input_stage.py (library part only, main removed) for the BOM-2 study, with:
  * Ctop as one part (ctop_mode "single", as before) or two capacitors in series (ctop_mode "pair":
    Ct1 -- mid node (Cmid to ground, extra 0.93 mm of 0.3 mm track) -- Ct2), each with its ESL
  * vectors v(opo) and v(aux) available, tolerance hooks Rtol_* for the alpha string
Original docstring:
Input stage of the low-cost sampling front end: SMA -> short 50R line -> 5:1 divider
(separate HF capacitive divider into BUF802 IN, 900k/100k resistive alpha divider into the servo)
-> BUF802 composite loop (CL mode, In_Aux) with an integrating OPA197/TP2272 servo -> 49.9R
back-termination -> splitter (modelled as 50R || 0.3 pF).

Termination (SPEC decision 10, 21 Nov 2026): no switchable on-board termination. term="ext" puts an ideal
external 50R feed-through terminator at the SMA (source side of the connector), term="none" leaves the
input at 1 Mohm || ~3 pF. term="relay" keeps the superseded K1 HFD3 model (49.9R + relay) for reference.

All active parts are BEHAVIOURAL (no vendor models were used):
  BUF802: main path G*V(IN) with two real poles (3.1 GHz -3 dB), aux path Ga*(V(In_Aux)-Va0) with an
          800 MHz pole, Ga = 0.26 (datasheet 'at crossover'), In_Bias -> 100k -> internal source
          (datasheet RHF), Cin 2.4 pF behind 0.5 nH, Zout 1.2R + 0.3 nH, output clamp to CLH/CLL,
          input clamp diodes to CLH and VS-.
  Op amp: gm-C single pole (GBW), slew limit (tanh), second pole at 3*GBW, Ccm 6.4 pF, Cdiff 1.6 pF
          (OPA197 datasheet; TP2272 Cin unknown, same values assumed), output limited to the rails.
Run: python3 input_stage.py   (writes PNGs and results.json next to this file)
"""
import json, os, subprocess, tempfile
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
PS_PER_MM = 6.05e-12
TMP = tempfile.mkdtemp(prefix="inp_", dir=os.environ.get("SCR", "/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad"))

NOM = dict(
    term="ext",       # "ext": ideal external 50R feed-through at the SMA; "none": 1 Mohm; "relay": old K1
    line_mm=3.0,      # SMA pad -> divider node (VIN), 50R microstrip; short without the relay
    mode50=True,      # term="relay" only (superseded): K1 closed (50R) or open (1 Mohm)
    Rs=50.0,          # source resistance
    Lrelay=2e-9,      # term="relay" only: K1 both poles in parallel, each 100R + ~4 nH (assumed)
    Copen=0.5e-12,    # term="relay" only: K1 open-contact capacitance (assumed)
    Ltune=0.0,        # term="relay" only: series inductor in the termination leg
    Ctop=1.5e-12, Cbot=3.3e-12, Cin=2.4e-12, Rg=10.0,
    Rb=4.99e6,        # R105 / R106 (IN -> In_Bias), each; BOM-2 as built: 1 M
    Cp=18e-12,        # C0G at the alpha tap: tap RC (90k x 26 pF) = Rpar x Cint -> differential integrator
    G0=0.983,          # BUF802 unloaded main-path gain -> 0.971 into 101R
    Ga=0.26, fbuf=3.1e9, faux=800e6,
    gbw=10e6, sr=20e6,  # OPA197 (TP2272: 7e6, 20e6)
    # 21 Nov 2026: VOFS = raw STM32 DAC1_OUT2 (0.2..2.7 V, VREF+ 2.9 V) through Rofs 24.9k, mid-scale
    # cancelled by Rmid 34.0k from VNEG_REF = -0.680 x VREF+ = -1.973 V (U701 TLV9001, mcu_if).
    # (Original network: Rofs 33k from a 0..3.3 V DAC, Rmid 49.9k from -2V5.)
    Rf1=10e3, Rf2=33.9e3, Rofs=24.9e3, Rmid=33.0e3, vmid=-1.933, Cint=470e-12, Raux=1e3, Caux=100e-12,
    vofs=1.45, vclh=1.5, vcll=-1.5,
    pad=0.07e-12, esl=0.4e-9,
    ctop_mode="single", Ct1=3.3e-12, Ct2=3.3e-12, Cmid=0.10e-12, Lmid=0.3e-9,
    R1a=300e3, R1b=300e3, R1c=300e3, R2=100e3,
)


def cap(name, a, b, val, esl):
    return [f"C{name} {a} {name}_x {val:.4g}", f"L{name} {name}_x {name}_y {esl:.3g}",
            f"R{name}esr {name}_y {b} 0.05", f"R{name}dc {a} {b} 1e12"]


def trace(a, b, mm, z0=50.0, sec=3e-12, tag="t"):
    td = mm * PS_PER_MM
    n = max(1, int(np.ceil(td / sec)))
    l, c = td * z0 / n, td / z0 / n
    out, prev = [], a
    for k in range(n):
        nxt = b if k == n - 1 else f"{tag}_{k}"
        out += [f"C{tag}{k} {prev} 0 {c/2 if k == 0 else c:.4g}", f"L{tag}{k} {prev} {nxt} {l:.4g}"]
        prev = nxt
    out.append(f"C{tag}e {b} 0 {c/2:.4g}")
    return out


def deck(p, analysis, src):
    q = dict(NOM); q.update(p)
    two_pi = 2 * np.pi
    fpole = q["fbuf"] / 0.6436          # two equal poles -> -3 dB at fbuf
    gm = two_pi * q["gbw"] * 10e-12
    il = q["sr"] * 10e-12
    L = ["* input stage", ".options klu reltol=1e-4 abstol=1e-13 vntol=1e-7 itl4=200",
         ".model dcl d(is=1e-14 n=1 rs=1 cjo=0.05p)",
         ".subckt opamp inp inn out",
         "Ccm1 inp 0 6.4p", "Ccm2 inn 0 6.4p", "Cdif inp inn 1.6p",
         f"Bgm 0 n1 I={il:.4g}*tanh((V(inp)-V(inn))*{gm/il:.5g})",
         "Cc n1 0 10p", f"Rc n1 0 {1e6/gm:.4g}",
         "E2 n2a 0 n1 0 1", "R2p n2a n2 1k", f"C2p n2 0 {1/(two_pi*1e3*3*q['gbw']):.4g}",
         "Bo o0 0 V=min(max(V(n2),-4.85),4.85)", "Ro o0 out 20", ".ends",
         src,
         f"Rs src s1 {q['Rs']}", "Lsma s1 s2 0.2n", "Csma s2 0 0.25p"]
    if q["term"] == "ext":            # ideal feed-through terminator on the SMA, outside the board
        L += ["Rext s1 0 50"]
    L += trace("s2", "vin", 6 if q["term"] == "relay" else q["line_mm"], tag="tin")
    if q["term"] == "relay":          # superseded: 49.9R at the input node, Ltune, relay contact to ground
        L += [f"R50 vin rt1 49.9", "C50p vin rt1 0.06p", "L50 rt1 rt 0.15n",
              f"Ltun rt rt2 {q['Ltune']:.3g}", "Ctun rt2 0 0.05p", "Crp rt2 0 0.3p"]
        if q["mode50"]:
            L += [f"Lk rt2 rk {q['Lrelay']:.3g}", "Rk rk 0 0.1"]
        else:
            L += [f"Ck rt2 0 {q['Copen']:.3g}"]
    L += ["Cvin vin 0 0.15p"]  # node pad + via to the divider parts
    # HF capacitive divider -> BUF802 IN
    if q["ctop_mode"] == "pair":       # two series 0402 C0G: VIN -- Ct1 -- cm -- Lmid -- cm2 -- Ct2 -- GA
        L += cap("top1", "vin", "cm", q["Ct1"], q["esl"]) + ["Cst1 vin cm 0.03p", f"Ccm cm 0 {q['Cmid']/2:.4g}",
              f"Lcm cm cm2 {q['Lmid']:.3g}", f"Ccm2 cm2 0 {q['Cmid']/2:.4g}", "Rcmleak cm 0 1e11"]
        L += cap("top2", "cm2", "ga", q["Ct2"], q["esl"]) + ["Cst2 cm2 ga 0.03p", f"Cpga ga 0 {q['pad']}"]
    else:
        L += cap("top", "vin", "ga", q["Ctop"], q["esl"]) + ["Cst vin ga 0.03p", f"Cpga ga 0 {q['pad']}"]
    L += cap("bot", "ga", "0", q["Cbot"], q["esl"])
    L += [f"Rg ga gp {q['Rg']}", f"Cpgp gp 0 {q['pad']}", "Lin gp gd 0.5n", f"Cin gd 0 {q['Cin']:.4g}",
          f"Rb1 gp gb {q.get('Rb1', q['Rb']):.4g}", "Cb1 gp gb 0.06p", f"Rb2 gb inb {q.get('Rb2', q['Rb']):.4g}", "Cb2 gb inb 0.06p", "Cpgb gb 0 0.05p",
          "Rhf inb s 100k",
          f"Vclh clh 0 {q['vclh']}", f"Vcll cll 0 {q['vcll']}", "Vneg vneg 0 -5",
          "Dh gd clh dcl", "Dl vneg gd dcl",
          # main path, two poles
          f"Em m1 0 gd 0 {q['G0']}", "Rm1 m1 m2 100", f"Cm1 m2 0 {1/(two_pi*100*fpole):.4g}",
          "Em2 m3 0 m2 0 1", "Rm2 m3 m 100", f"Cm2 m 0 {1/(two_pi*100*fpole):.4g}",
          # aux path
          "Caxp aux 0 1p", "Iaux aux 0 44u",
          f"Ba a1 0 V={q['Ga']}*(V(aux)+2)", "Ra a1 a 100", f"Ca a 0 {1/(two_pi*100*q['faux']):.4g}",
          "Bs s 0 V=min(max(V(m)+V(a),V(cll)),V(clh))",
          "Rout s op 1.2", "Lout op outp 0.3n", "Cpo outp 0 0.1p",
          # back-termination and splitter input
          "Rbt outp bo1 49.9", "Lbt bo1 bo 0.3n"]
    L += trace("bo", "bout", 5, tag="tout")
    L += ["Rspl bout 0 50", "Cspl bout 0 0.3p"]
    # alpha network 3 x 300k + 100k, 0402, 60 fF across each, pads 50 fF
    L += [f"R1a vin n1 {q['R1a']:.6g}", "C1a1 vin n1 0.06p", f"R1b n1 n2 {q['R1b']:.6g}", "C1b n2 n1 0.06p",
          f"R1c n2 tap {q['R1c']:.6g}", "C1c n2 tap 0.06p", "Cpn1 n1 0 0.05p", "Cpn2 n2 0 0.05p",
          f"R2 tap 0 {q['R2']:.6g}", "C2 tap 0 0.06p", "Cptap tap 0 0.2p"]
    L += [f"Ccp tap 0 {q['Cp']:.4g}"]
    # servo: OPA+ = tap, OPA- = fb (integrator), OPA out -> Raux -> In_Aux (Caux)
    L += ["Xop tap fb opo opamp", f"Rf1 outp fb {q['Rf1']}", f"Rf2 fb 0 {q['Rf2']:.6g}",
          f"Rofs vofs fb {q['Rofs']}", f"Rmid vmid fb {q['Rmid']}", f"Cint opo fb {q['Cint']:.4g}",
          f"Vofs vofs 0 {q['vofs']}", f"Vmid vmid 0 {q['vmid']}",
          f"Raux opo aux {q['Raux']}", f"Cauxe aux 0 {q['Caux']:.4g}"]
    L += [analysis, ".end"]
    return "\n".join(L)


def run(p, analysis, src, vecs, name):
    cir = os.path.join(TMP, name + ".cir")
    out = os.path.join(TMP, name + ".txt")
    body = deck(p, analysis, src)
    ctl = f".control\nset filetype=ascii\nset wr_singlescale\nset wr_vecnames\nrun\nwrdata {out} {' '.join(vecs)}\n.endc\n"
    open(cir, "w").write(body.replace(".end", ctl + ".end", 1) if False else body[:-4] + ctl + ".end\n")
    r = subprocess.run(["ngspice", "-b", cir], capture_output=True, text=True, timeout=600)
    if not os.path.exists(out):
        raise RuntimeError(r.stdout[-2000:] + r.stderr[-2000:])
    d = np.loadtxt(out, skiprows=1)
    os.remove(out)
    return d


def ac(p, name):
    vecs = ["vm(bout)", "vp(bout)", "vm(outp)", "vm(gd)", "vm(vin)", "vr(s1)", "vi(s1)", "ir(Vs)", "ii(Vs)"]
    d = run(p, ".ac dec 60 1 10g", "Vs src 0 dc 0 ac 1", ["v(bout)", "v(outp)", "v(gd)", "v(vin)", "v(s1)", "i(Vs)"], name)
    f = d[:, 0]
    c = lambda k: d[:, 1 + 2 * k] + 1j * d[:, 2 + 2 * k]
    return dict(f=f, bout=c(0), outp=c(1), gd=c(2), vin=c(3), s1=c(4), i=-c(5))


def tran(p, name, src, tstop, tstep, tmax, vecs=("v(bout)", "v(outp)", "v(gd)", "v(vin)", "v(opo)")):
    for tm in (tmax, tmax / 3, tmax * 3):
        try:
            d = run(p, f".tran {tstep:.3g} {tstop:.3g} 0 {tm:.3g}", src, list(vecs), name)
            return d
        except RuntimeError as e:
            err = e
    raise err


def rise(t, v):
    v0, v1 = v[0], v[-1]
    lo, hi = v0 + 0.1 * (v1 - v0), v0 + 0.9 * (v1 - v0)
    return t[np.argmax(v >= hi)] - t[np.argmax(v >= lo)]


def f3db(f, h, fref=10e6):
    a = np.abs(h) / np.abs(np.interp(fref, f, np.abs(h)))
    i = np.where((f > fref) & (a < 10 ** (-3 / 20)))[0]
    return f[i[0]] if len(i) else np.nan


