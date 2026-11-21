"""Input stage of the low-cost sampling front end: SMA -> K1 50R termination -> 5:1 divider
(separate HF capacitive divider into BUF802 IN, 900k/100k resistive alpha divider into the servo)
-> BUF802 composite loop (CL mode, In_Aux) with an integrating OPA197/TP2272 servo -> 49.9R
back-termination -> splitter (modelled as 50R || 0.3 pF).

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
    mode50=True,      # K1 closed (50R) or open (1 Mohm)
    Rs=50.0,          # source resistance
    Lrelay=2e-9,      # K1 both poles in parallel, each 100R + ~4 nH (assumed; HFD3 RF data not available)
    Copen=0.5e-12,    # K1 open-contact capacitance (assumed)
    Ltune=0.0,        # series inductor in the termination leg (constant-R compensation)
    Ctop=1.5e-12, Cbot=3.3e-12, Cin=2.4e-12, Rg=10.0,
    Cp=18e-12,        # C0G at the alpha tap: tap RC (90k x 26 pF) = Rpar x Cint -> differential integrator
    G0=0.983,          # BUF802 unloaded main-path gain -> 0.971 into 101R
    Ga=0.26, fbuf=3.1e9, faux=800e6,
    gbw=10e6, sr=20e6,  # OPA197 (TP2272: 7e6, 20e6)
    Rf1=10e3, Rf2=20.1e3, Rofs=33e3, Rmid=49.9e3, Cint=470e-12, Raux=1e3, Caux=100e-12,
    vofs=1.65, vclh=1.5, vcll=-1.5,
    pad=0.07e-12, esl=0.4e-9,
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
    L += trace("s2", "vin", 6, tag="tin")
    # termination: 49.9R at the input node, Ltune, relay contact to ground
    L += [f"R50 vin rt1 49.9", "C50p vin rt1 0.06p", "L50 rt1 rt 0.15n",
          f"Ltun rt rt2 {q['Ltune']:.3g}", "Ctun rt2 0 0.05p", "Crp rt2 0 0.3p"]
    if q["mode50"]:
        L += [f"Lk rt2 rk {q['Lrelay']:.3g}", "Rk rk 0 0.1"]
    else:
        L += [f"Ck rt2 0 {q['Copen']:.3g}"]
    L += ["Cvin vin 0 0.15p"]  # node pad + via to the divider parts
    # HF capacitive divider -> BUF802 IN
    L += cap("top", "vin", "ga", q["Ctop"], q["esl"]) + ["Cst vin ga 0.03p", f"Cpga ga 0 {q['pad']}"]
    L += cap("bot", "ga", "0", q["Cbot"], q["esl"])
    L += [f"Rg ga gp {q['Rg']}", f"Cpgp gp 0 {q['pad']}", "Lin gp gd 0.5n", f"Cin gd 0 {q['Cin']:.4g}",
          "Rb1 gp gb 4.99Meg", "Cb1 gp gb 0.06p", "Rb2 gb inb 4.99Meg", "Cb2 gb inb 0.06p", "Cpgb gb 0 0.05p",
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
    L += ["R1a vin n1 300k", "C1a1 vin n1 0.06p", "R1b n1 n2 300k", "C1b n2 n1 0.06p",
          "R1c n2 tap 300k", "C1c n2 tap 0.06p", "Cpn1 n1 0 0.05p", "Cpn2 n2 0 0.05p",
          "R2 tap 0 100k", "C2 tap 0 0.06p", "Cptap tap 0 0.2p"]
    L += [f"Ccp tap 0 {q['Cp']:.4g}"]
    # servo: OPA+ = tap, OPA- = fb (integrator), OPA out -> Raux -> In_Aux (Caux)
    L += ["Xop tap fb opo opamp", f"Rf1 outp fb {q['Rf1']}", f"Rf2 fb 0 {q['Rf2']:.6g}",
          f"Rofs vofs fb {q['Rofs']}", f"Rmid vmid fb {q['Rmid']}", f"Cint opo fb {q['Cint']:.4g}",
          f"Vofs vofs 0 {q['vofs']}", "Vmid vmid 0 -2.5",
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


if __name__ == "__main__":
    R = {}
    # --- 1. trim: find Rf2 so that LF gain (1 Hz) equals HF gain (10 MHz) at the BUF802 pin
    a0 = ac({}, "ac_trim")
    hf = np.interp(10e6, a0["f"], np.abs(a0["outp"] / a0["vin"]))  # gain from the input node
    lf = np.abs(a0["outp"][0] / a0["vin"][0])
    # LF gain = 0.1*Rf1*(1/Rf1+1/Rf2+2/33k); solve for Rf2
    s = hf / 0.1 / 10e3 - 1 / 10e3 - 1 / 33e3 - 1 / 49.9e3
    rf2 = 1 / s
    R["trim"] = dict(hf_gain_pin=hf, lf_gain_pin_untrimmed=lf, Rf2_trimmed=rf2)
    print("trim", R["trim"])
    base = dict(Rf2=rf2)

    # --- 2. AC cases
    cases = {
        "OPA197, trimmed, 50R": dict(base),
        "TP2272 (7 MHz), same trim": dict(base, gbw=7e6),
        "Cin +0.3 pF, not re-trimmed": dict(base, Cin=2.7e-12),
        "Cin -0.3 pF, not re-trimmed": dict(base, Cin=2.1e-12),
        "OPA197, 1 Mohm mode (50R source)": dict(base, mode50=False),
    }
    acr = {k: ac(v, f"ac{i}") for i, (k, v) in enumerate(cases.items())}
    # Ltune / relay sensitivity (S11 and BW)
    lt = {}
    for i, (lr, ltn) in enumerate([(1.5e-9, 0), (2e-9, 0), (3e-9, 0), (4e-9, 0)]):
        a = ac(dict(base, Lrelay=lr, Ltune=ltn), f"lt{i}")
        lt[f"Lrelay {lr*1e9:.1f} nH, Ltune {ltn*1e9:.1f} nH"] = a
    fig, ax = plt.subplots(2, 2, figsize=(13, 9))
    for k, a in acr.items():
        g = np.abs(a["bout"]); gn = g / np.interp(10e6, a["f"], g)
        ax[0, 0].semilogx(a["f"], 20 * np.log10(gn), label=k)
        m = a["f"] < 1e8
        ax[0, 1].semilogx(a["f"][m], 100 * (gn[m] - 1), label=k)
        R.setdefault("ac", {})[k] = dict(f3db_GHz=f3db(a["f"], a["bout"]) / 1e9,
                                        lf_err_pct=float(100 * (gn[0] - 1)),
                                        max_dev_1Hz_100MHz_pct=float(100 * np.max(np.abs(gn[m] - 1))),
                                        gain_10MHz_bout=float(np.interp(10e6, a["f"], g)),
                                        peak_dB=float(20 * np.log10(np.max(gn))))
    ax[0, 0].set_ylim(-9, 3); ax[0, 0].set_xlim(1e6, 1e10); ax[0, 0].axhline(-3, color="0.6", lw=0.7)
    ax[0, 0].set_title("Gain at splitter input, normalised to 10 MHz"); ax[0, 0].set_ylabel("dB")
    ax[0, 1].set_title("Crossover flatness 1 Hz-100 MHz"); ax[0, 1].set_ylabel("gain error, %")
    ax[0, 1].set_ylim(-6, 6)
    for k, a in lt.items():
        zin = a["s1"] / a["i"]; s11 = (zin - 50) / (zin + 50)
        ax[1, 0].semilogx(a["f"], 20 * np.log10(np.abs(s11)), label=k)
        g = np.abs(a["bout"]); gn = g / np.interp(10e6, a["f"], g)
        ax[1, 1].semilogx(a["f"], 20 * np.log10(gn), label=k)
        m = (a["f"] > 1e8) & (a["f"] < 2e9)
        R.setdefault("relay", {})[k] = dict(S11_worst_to_2GHz_dB=float(20 * np.log10(np.max(np.abs(s11[m])))),
                                           f3db_GHz=f3db(a["f"], a["bout"]) / 1e9,
                                           peak_dB=float(20 * np.log10(np.max(gn))))
    ax[1, 0].set_xlim(1e8, 1e10); ax[1, 0].set_ylim(-40, 0); ax[1, 0].set_title("S11 at the SMA, 50R mode"); ax[1, 0].set_ylabel("dB")
    ax[1, 1].set_xlim(1e8, 1e10); ax[1, 1].set_ylim(-9, 3); ax[1, 1].set_title("Gain vs relay / tuning inductance"); ax[1, 1].set_ylabel("dB")
    for a_ in ax.flat:
        a_.grid(True, which="both", alpha=0.3); a_.legend(fontsize=8); a_.set_xlabel("Hz")
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "input_ac.png"), dpi=100)

    # --- 3. LF step (crossover) and HF step
    fig, ax = plt.subplots(1, 3, figsize=(15, 5))
    src_lf = "Vs src 0 dc 0 pulse(0 1 20u 10n 10n 1 2)"
    for k, p in [("OPA197 trimmed", base), ("TP2272", dict(base, gbw=7e6)),
                 ("Cin +0.3 pF untrimmed", dict(base, Cin=2.7e-12)), ("1 Mohm mode", dict(base, mode50=False))]:
        d = tran(p, "tlf", src_lf, 300e-6, 20e-9, 50e-9)
        t, v = d[:, 0], d[:, 1]
        vf = v[-1]
        ax[0].plot(t * 1e6, v / vf, label=k)
        m = t > 25e-6
        R.setdefault("lfstep", {})[k] = dict(final=float(vf), max_dev_pct=float(100 * np.max(np.abs(v[m] / vf - 1))))
    ax[0].set_ylim(0.9, 1.1); ax[0].set_title("1 V step, 0-300 us (servo/HF crossover)"); ax[0].set_xlabel("us")
    ax[0].set_ylabel("V(splitter) / final")
    src_hf = "Vs src 0 dc 0 pulse(0 1 0.2n 20p 20p 1u 2u)"
    for k, p in [("50R mode", base), ("1 Mohm mode, 50R source", dict(base, mode50=False)),
                 ("50R, Lrelay 4 nH (one pole only)", dict(base, Lrelay=4e-9))]:
        d = tran(p, "thf", src_hf, 3e-9, 1e-12, 2e-12)
        t, vb, vg = d[:, 0], d[:, 1], d[:, 3]
        ax[1].plot(t * 1e9, vb / vb[-1], label=k + " (splitter)")
        ax[1].plot(t * 1e9, vg / vg[-1], "--", label=k + " (BUF802 die)")
        R.setdefault("hfstep", {})[k] = dict(tr_out_ps=rise(t, vb) * 1e12, tr_gate_ps=rise(t, vg) * 1e12,
                                            overshoot_pct=float(100 * (vb.max() / vb[-1] - 1)))
    ax[1].set_title("20 ps step: passive part (dashed) and output"); ax[1].set_xlabel("ns"); ax[1].set_xlim(0, 2)
    # offset sweep check: VOFS 0 and 3.3 V, input 0
    offs = {}
    for v in (0.0, 1.65, 3.3):
        d = tran(dict(base, vofs=v), "tof", "Vs src 0 dc 0", 1e-6, 10e-9, 20e-9)
        offs[v] = float(d[-1, 2])
    R["offset_outp_vs_VOFS"] = offs
    # overload: 20 V, 10 us pulse in 1 Mohm mode, recovery
    d = tran(dict(base, mode50=False), "tov", "Vs src 0 dc 0 pulse(0 20 10u 1n 1n 10u 1)", 80e-6, 20e-9, 50e-9,
             vecs=("v(bout)", "v(outp)", "v(gd)", "v(aux)", "v(opo)"))
    t = d[:, 0]
    ax[2].plot(t * 1e6, d[:, 2], label="BUF802 OUT")
    ax[2].plot(t * 1e6, d[:, 3], label="BUF802 IN (die)")
    ax[2].plot(t * 1e6, d[:, 5], label="servo out")
    ax[2].set_ylim(-6, 6); ax[2].set_title("+20 V, 10 us overload (1 Mohm mode)"); ax[2].set_xlabel("us")
    rec = t[(t > 20e-6) & (np.abs(d[:, 2] - d[-1, 2]) > 0.01)]
    R["overload_recovery_to_10mV_us"] = float((rec.max() - 20e-6) * 1e6) if len(rec) else 0.0
    R["overload_gate_peak_V"] = float(d[:, 3].max())
    for a_ in ax:
        a_.grid(True, alpha=0.3); a_.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "input_steps.png"), dpi=100)

    # --- 4. noise referred to the input, 2 GHz (analytic from AC transfer)
    a = acr["OPA197, trimmed, 50R"]
    f = a["f"]; A = np.abs(a["outp"] / a["vin"]); Ag = np.abs(a["gd"])
    kT4 = 4 * 1.38e-23 * 300
    en_buf = 2.3e-9 * np.sqrt(1 + 18e3 / f)
    Hbuf = A / np.maximum(Ag, 1e-30)            # gate -> outp (includes loop suppression at LF)
    flp = 0.26 / (2 * np.pi * NOM["Rf1"] * NOM["Cint"])
    sup = (f / flp) / np.sqrt(1 + (f / flp) ** 2)  # loop suppresses BUF802 noise below f_loop
    n_buf = en_buf * 0.971 * np.abs(np.sqrt(1 / (1 + (f / 3.1e9) ** 4))) * sup
    n_alpha = np.sqrt(kT4 * 90e3) * 2.0 / np.sqrt(1 + (f / flp) ** 2) / np.sqrt(1 + (f / 68e3) ** 2)
    n_opa = 5.5e-9 * 2.0 / np.sqrt(1 + (f / flp) ** 2)
    n_bt = np.sqrt(kT4 * 25) * np.ones_like(f)   # back-termination || splitter, at the splitter node, /0.5 to outp
    m = (f >= 10) & (f <= 2e9)
    integ = lambda n: float(np.sqrt(np.trapezoid(n[m] ** 2, f[m])))
    gmid = float(np.interp(10e6, f, A))
    R["noise_input_referred_uVrms_2GHz"] = {k: integ(v) / gmid * 1e6 for k, v in
                                           dict(BUF802=n_buf, alpha_network=n_alpha, servo=n_opa, back_term_and_splitter=n_bt * A / np.interp(10e6, f, np.abs(a["bout"] / a["vin"]))).items()}
    R["noise_input_referred_uVrms_2GHz"]["total"] = float(np.sqrt(sum(v ** 2 for v in R["noise_input_referred_uVrms_2GHz"].values())))
    R["input_C_pF_at_10MHz_1M_mode"] = None
    a1 = acr["OPA197, 1 Mohm mode (50R source)"]
    zin = a1["s1"] / a1["i"]
    i10 = np.argmin(np.abs(a1["f"] - 10e6))
    R["input_C_pF_at_10MHz_1M_mode"] = float(-1 / (2 * np.pi * a1["f"][i10] * np.imag(1 / (1 / zin[i10]))) * 1e12) if False else \
        float(np.imag(1 / zin[i10]) / (2 * np.pi * a1["f"][i10]) * 1e12)
    i1 = np.argmin(np.abs(a1["f"] - 1))
    R["input_R_Mohm_at_1Hz"] = float(np.real(zin[i1]) / 1e6)
    json.dump(R, open(os.path.join(HERE, "results.json"), "w"), indent=1, default=float)
    print(json.dumps(R, indent=1, default=float))
