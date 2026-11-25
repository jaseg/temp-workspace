"""BOM-2 input-stage study (no trimmer): fixed 1 % servo network + firmware correction of the LF/HF doublet,
Ctop 1.5 pF 50 V +/-0.05 pF (single, existing footprint; the 2 x 3.3 pF series pair is an AC-only alternative),
Cint 1 nF C0G with the servo resistors scaled to JLC basic values (4.7k / 22k / 10k / 15k).
Deck: input_stage_bom2.py (copy of sim/input/input_stage.py). Run: python3 bom2_input.py  (about 2-4 min)
Writes results.json, bom2_ac.png, bom2_steps.png next to this file."""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import input_stage_bom2 as ist  # noqa: E402
RB1 = float(os.environ.get("RB1", "1e6"))     # R105 (gate side), as built 1 M 0402
RB2 = float(os.environ.get("RB2", "10e6"))    # R106 (In_Bias side), as built 10 M 0603 (SPEC 35)

# as built (24 Nov 2026): Ctop 1.5p, Rf1 10k, Rf2 22k + RV101, Rofs 24.9k, Rmid 33k, Cint 470p, VNEG_REF -1.933 V
OLD = dict(ctop_mode="single", Ctop=1.5e-12, Rf1=10e3, Rf2=33.9e3, Rofs=24.9e3, Rmid=33e3, Cint=470e-12,
           vmid=-1.933, vofs=1.45)
# proposed: C101 1.5p 50 V +/-0.05 pF, R118 4.7k, R120 22k (no RV101), R119 10k, R123 15k, C106 1n C0G
NEW = dict(ctop_mode="single", Ctop=1.5e-12, Rf1=4.7e3, Rf2=22e3, Rofs=10e3, Rmid=15e3, Cint=1e-9,
           vmid=-1.933, vofs=1.289, Rb1=RB1, Rb2=RB2)   # R105 1 M / R106 10 M as built (SPEC 35); RB1=RB2=4.99e6: the study
# alternative: C101 as 2 x 3.3p in series on a shared-pad footprint (one line less), Rf2 15k re-centres LF = HF
PAIR = dict(NEW, ctop_mode="pair", Ct1=3.3e-12, Ct2=3.3e-12, Lmid=0.1e-9, Cmid=0.06e-12, Rf2=15e3)
R = {}
rng = np.random.default_rng(1)


def gains(a):
    g = np.abs(a["outp"] / a["vin"])
    return float(g[0]), float(np.interp(10e6, a["f"], g)), g


def lf_gain(p):
    q = dict(ist.NOM); q.update(p)
    alpha = q["R2"] / (q["R1a"] + q["R1b"] + q["R1c"] + q["R2"])
    return alpha * q["Rf1"] * (1 / q["Rf1"] + 1 / q["Rf2"] + 1 / q["Rofs"] + 1 / q["Rmid"])


def trim_old(base):
    """the RV101 trim of the as-built network: Rf2 for LF = HF (what the trimmer does)"""
    a = ist.ac(base, "trim")
    _, hf, _ = gains(a)
    q = dict(ist.NOM); q.update(base)
    alpha = q["R2"] / (q["R1a"] + q["R1b"] + q["R1c"] + q["R2"])
    s = hf / alpha / q["Rf1"] - 1 / q["Rf1"] - 1 / q["Rofs"] - 1 / q["Rmid"]
    return 1 / s


def mc_draw(base, i, tol_top=0.1e-12):
    """one board: uniform within the part tolerances (worst-case-like spread)"""
    u = lambda tol: 1 + tol * (2 * rng.random() - 1)
    p = dict(base)
    if p["ctop_mode"] == "pair":
        p["Ct1"] = 3.3e-12 + 0.1e-12 * (2 * rng.random() - 1)       # GJM1555C1H3R3BB01D +/-0.1 pF
        p["Ct2"] = 3.3e-12 + 0.1e-12 * (2 * rng.random() - 1)
        p["Cmid"] = 0.10e-12 * u(0.3)
    else:
        p["Ctop"] = 1.5e-12 + tol_top * (2 * rng.random() - 1)     # old CBR04C159B1GAC 0.1 / new GJM..WB01D 0.05 pF
    p["Cbot"] = 3.3e-12 + 0.1e-12 * (2 * rng.random() - 1)
    p["Cin"] = 2.4e-12 + 0.3e-12 * (2 * rng.random() - 1)           # BUF802 typ only; +/-0.3 pF assumed
    p["pad"] = 0.07e-12 * u(0.4)
    p["G0"] = 0.983 * u(0.01)
    p["Ga"] = 0.26 * u(0.2)
    for k in ("R1a", "R1b", "R1c", "R2"):
        p[k] = ist.NOM[k] * u(0.01)
    for k in ("Rf1", "Rf2", "Rofs", "Rmid"):
        p[k] = base[k] * u(0.01)
    p["Cint"] = base["Cint"] * u(0.05)
    p["Cp"] = 18e-12 * u(0.05)
    return p


def doublet_step(t, a, eps, tau):
    return a * ((1 + eps) - eps * np.exp(-np.clip(t, 0, None) / tau))


def corr_resp(f, eps, tau):
    """firmware correction C(s) = (1+eps)(s+wp)/(s+wz), wz = wp(1+eps): output referred to the LF gain"""
    s = 2j * np.pi * f
    wp = 1 / tau
    return (1 + eps) * (s + wp) / (s + wp * (1 + eps))


def corr_iir(y, fs, eps, tau):
    """same correction on the real-time ADC stream: x = (1+eps) y - eps LPz(y), LPz unity-gain pole wz"""
    wz = (1 + eps) / tau
    k = 1 - np.exp(-wz / fs)
    lp = np.empty_like(y)
    acc = y[0]
    for i, v in enumerate(y):
        acc += k * (v - acc)
        lp[i] = acc
    return (1 + eps) * y - eps * lp


if __name__ == "__main__":
    # ---------------------------------------------------------------- 1. nominal: old (trimmed / untrimmed), new
    rf2_trim = trim_old(OLD)
    R["old_Rf2_trimmed_ohm"] = rf2_trim
    nets = {"as built, RV101 trimmed": dict(OLD, Rf2=rf2_trim), "as built, RV101 at nominal (33.9k)": OLD,
            "proposed (1.5p 50V, 4.7k/22k/10k/15k, 1n)": NEW,
            "proposed, no terminator": dict(NEW, term="none"),
            "alternative 2x3.3p series, Rf2 15k": PAIR, "alternative 2x3.3p, no terminator": dict(PAIR, term="none"), "as built, no terminator": dict(OLD, Rf2=rf2_trim, term="none")}
    acs = {k: ist.ac(v, f"nom{i}") for i, (k, v) in enumerate(nets.items())}
    fig, ax = plt.subplots(1, 3, figsize=(17, 5))
    for k, a in acs.items():
        lf, hf, g = gains(a)
        gb = np.abs(a["bout"]); gn = gb / np.interp(10e6, a["f"], gb)
        m = a["f"] < 1e8
        zin = a["s1"] / a["i"]; s11 = (zin - 50) / (zin + 50)
        R.setdefault("nominal", {})[k] = dict(
            lf_gain=lf, hf_gain_10MHz=hf, eps_pct=100 * (lf / hf - 1), lf_gain_formula=lf_gain(nets[k]),
            f3db_out_GHz=ist.f3db(a["f"], a["bout"]) / 1e9, f3db_die_GHz=ist.f3db(a["f"], a["gd"]) / 1e9,
            peak_out_dB=float(20 * np.log10(gn.max())),
            S11_dB={f"{fx/1e9:g} GHz": float(20 * np.log10(abs(np.interp(fx, a["f"], np.abs(s11))))) for fx in (1e9, 2e9)},
            Cin_board_pF_10MHz=float(np.imag(1 / zin[np.argmin(abs(a["f"] - 10e6))]) / (2 * np.pi * 10e6) * 1e12))
        ax[0].semilogx(a["f"], 20 * np.log10(gn), label=k)
    ax[0].set_xlim(1e7, 1e10); ax[0].set_ylim(-9, 3); ax[0].set_title("gain at splitter, norm. 10 MHz"); ax[0].set_ylabel("dB")
    print(json.dumps(R["nominal"], indent=1))

    # ---------------------------------------------------------------- 2. HF step (rise, overshoot), new vs old
    src_hf = "Vs src 0 dc 0 pulse(0 1 0.2n 20p 20p 1u 2u)"
    for k in ("as built, RV101 trimmed", "proposed (1.5p 50V, 4.7k/22k/10k/15k, 1n)", "proposed, no terminator", "alternative 2x3.3p series, Rf2 15k", "as built, no terminator"):
        d = ist.tran(nets[k], "thf", src_hf, 3e-9, 1e-12, 2e-12)
        t, vb, vg = d[:, 0], d[:, 1], d[:, 3]
        R.setdefault("hfstep", {})[k] = dict(tr_out_ps=ist.rise(t, vb) * 1e12, overshoot_out_pct=float(100 * (vb.max() / vb[-1] - 1)),
                                            tr_die_ps=ist.rise(t, vg) * 1e12)
    print(json.dumps(R["hfstep"], indent=1))

    # ---------------------------------------------------------------- 3. offset range (VOFS DAC) and overload, new network
    for v in (0.2, 1.289, 2.7):
        d = ist.tran(dict(NEW, vofs=v), "tof", "Vs src 0 dc 0", 1e-6, 10e-9, 20e-9)
        R.setdefault("new_offset_outp_vs_VOFS", {})[str(v)] = float(d[-1, 2])
    for k, p in (("old", dict(OLD, Rf2=rf2_trim)), ("new", NEW)):
        d = ist.tran(dict(p, term="none"), "tov", "Vs src 0 dc 0 pulse(0 20 10u 1n 1n 10u 1)", 80e-6, 20e-9, 50e-9)
        t = d[:, 0]
        rec = t[(t > 20e-6) & (np.abs(d[:, 2] - d[-1, 2]) > 0.01)]
        R.setdefault("overload_recovery_to_10mV_us", {})[k] = float((rec.max() - 20e-6) * 1e6) if len(rec) else 0.0
    print(R["new_offset_outp_vs_VOFS"], R["overload_recovery_to_10mV_us"])

    # ---------------------------------------------------------------- 4. Monte Carlo: LF/HF mismatch without a trimmer
    NMC = int(os.environ.get("NMC", "60"))
    mc = {}
    for tag, base, tt in (("old fixed (RV101 replaced by its nominal)", OLD, 0.1e-12), ("proposed", NEW, 0.05e-12)):
        rows = []
        for i in range(NMC):
            p = mc_draw(base, i, tt)
            a = ist.ac(p, f"mc{tag[:3]}{i}")
            lf, hf, g = gains(a)
            gn = g / hf
            m = (a["f"] > 1) & (a["f"] < 1e7)
            g2 = float(20 * np.log10(np.interp(2e9, a["f"], np.abs(a["bout"])) / np.interp(10e6, a["f"], np.abs(a["bout"]))))
            half = 1 + (lf / hf - 1) / 2       # doublet corner: halfway between LF and HF gain
            fc = float(a["f"][m][np.argmin(np.abs(gn[m] - half))])
            rows.append(dict(p=p, eps=lf / hf - 1, fc=fc, f=a["f"], g=g, hf=hf, lf=lf, g2=g2))
        e = np.array([r["eps"] for r in rows]) * 100
        fcs = np.array([r["fc"] for r in rows])
        mc[tag] = rows
        g2s = np.array([r["g2"] for r in rows])
        R.setdefault("mc", {})[tag] = dict(n=NMC, gain_2GHz_dB=[float(g2s.min()), float(g2s.max())], eps_pct_min=float(e.min()), eps_pct_max=float(e.max()), eps_pct_std=float(e.std()),
                                          doublet_fc_kHz=[float(fcs.min() / 1e3), float(np.median(fcs) / 1e3), float(fcs.max() / 1e3)],
                                          tau_us=[float(1e6 / (2 * np.pi * fcs.max())), float(1e6 / (2 * np.pi * np.median(fcs))),
                                                  float(1e6 / (2 * np.pi * fcs.min()))])
        print(tag, R["mc"][tag], flush=True)
        ax[1].hist(e, bins=20, alpha=0.5, label=tag)
    ax[1].set_title(f"LF/HF gain mismatch, {NMC} boards (uniform tolerances)"); ax[1].set_xlabel("eps = G_LF/G_HF - 1, %")

    # ---------------------------------------------------------------- 5. firmware calibration + correction
    # calibration: 1 kHz square (any generator, 50 R source, no terminator), 64 edges averaged, 3 MS/s stream;
    # model = HF gain + two first-order LF terms (the servo response overshoots slightly: one exponential is not enough)
    rows = sorted(mc["proposed"], key=lambda r: abs(r["eps"]))
    picks = [rows[-1], rows[-2], rows[len(rows) // 2], rows[0]]
    fs = 3.0e6
    src_lf = "Vs src 0 dc 0 pulse(0 1 20u 10n 10n 500u 1m)"
    fig2, ax2 = plt.subplots(1, 2, figsize=(14, 5))
    res5 = []

    # BOM-2 repair (25 Nov 2026): the free two-term fit is ill-conditioned and fails with the as-built bias resistors
    # (a third time constant). Fixed basis instead: six first-order terms at fixed time constants 2-300 us, amplitudes
    # by linear least squares with a small ridge; correction C(s) = (1 + sum e_k) / (1 + sum e_k / (1 + s tau_k)).
    TAUS = np.geomspace(2e-6, 300e-6, 6)
    LAM = 1e-4
    EPS_MIN = 0.01          # apply the correction only when the fitted |LF/HF - 1| exceeds 1 %

    def corrk(f, ek):
        s_ = 2j * np.pi * f
        h = 1 + sum(ek[k] / (1 + s_ * TAUS[k]) for k in range(len(TAUS)))
        return (1 + np.sum(ek)) / h

    for j, r in enumerate(picks):
        d = ist.tran(dict(r["p"], term="none"), f"tcal{j}", src_lf, 520e-6, 20e-9, 50e-9)
        t, v, vin = d[:, 0], d[:, 2], d[:, 4]
        ts = np.arange(0, 520e-6, 1 / fs)
        ys = np.interp(ts, t, v) - np.interp(19e-6, t, v)
        noise = 2e-3 * 0.2 / 8                       # 2 mV rms per raw sample at the input, x0.2, /sqrt(64)
        yn = ys + rng.normal(0, noise, ys.size)
        m = ts > 20.4e-6
        tt = ts[m] - 20e-6
        A = np.column_stack([np.ones_like(tt)] + [1 - np.exp(-tt / tk) for tk in TAUS])
        reg = LAM * np.eye(A.shape[1]) * len(tt); reg[0, 0] = 0
        c = np.linalg.solve(A.T @ A + reg, A.T @ yn[m])
        a_hf, ek = c[0], c[1:] / c[0]
        eps_fit = float(np.sum(ek))
        applied = abs(eps_fit) > EPS_MIN
        corr2 = (lambda f, *_: corrk(f, ek)) if applied else (lambda f, *_: np.ones_like(f, dtype=complex))
        e1 = t1 = e2 = t2 = 0.0
        hc = r["g"] * np.abs(corr2(r["f"], e1, t1, e2, t2)) / r["lf"]
        mm = (r["f"] >= 1) & (r["f"] <= 1e8)
        unc = r["g"] / r["lf"]
        # time domain on the noise-free stream: apply the same correction as an FFT filter (periodic 1 kHz square)
        x = ys[(ts >= 20e-6) & (ts < 520e-6)]
        n = len(x)
        ff = np.fft.rfftfreq(2 * n, 1 / fs)
        per = np.r_[x, x[-1] - x + x[0]]             # one full period of the square wave from the half-period record
        yc = np.fft.irfft(np.fft.rfft(per) * corr2(ff, e1, t1, e2, t2), 2 * n)[:n]
        fin = r["lf"] * 1.0
        tsx = np.arange(n) / fs
        mt = tsx > 1e-6
        res5.append(dict(eps_true_pct=100 * r["eps"], fit=dict(a=float(a_hf), eps_fit_pct=100 * eps_fit, e_k_pct=[float(100 * x) for x in ek],
                                                                 tau_k_us=[float(x * 1e6) for x in TAUS], applied=bool(applied)),
                         flat_uncorr_pct=float(100 * np.max(np.abs(unc[mm] - 1))),
                         flat_corr_pct=float(100 * np.max(np.abs(hc[mm] - 1))),
                         step_dev_uncorr_pct=float(100 * np.max(np.abs(x[mt] / fin - 1))),
                         step_dev_corr_pct=float(100 * np.max(np.abs(yc[mt] / fin - 1)))))
        print(res5[-1], flush=True)
        ax2[0].plot(tsx * 1e6, x / fin, label=f"eps {100*r['eps']:+.1f} %, raw")
        ax2[0].plot(tsx * 1e6, yc / fin, "--", label=f"eps {100*r['eps']:+.1f} %, corrected")
        ax2[1].semilogx(r["f"][mm], 100 * (unc[mm] - 1), label=f"eps {100*r['eps']:+.1f} %, raw")
        ax2[1].semilogx(r["f"][mm], 100 * (hc[mm] - 1), "--", label=f"eps {100*r['eps']:+.1f} %, corrected")
        if j == 0:
            ax[2].semilogx(r["f"][mm], 100 * (unc[mm] - 1), label="worst board, raw")
            ax[2].semilogx(r["f"][mm], 100 * (hc[mm] - 1), label="worst board, corrected")
    R["correction"] = res5
    # trimmed as-built reference flatness
    a = acs["as built, RV101 trimmed"]; lf, hf, g = gains(a); mm = (a["f"] >= 1) & (a["f"] <= 1e8)
    R["trimmed_reference_flat_pct"] = float(100 * np.max(np.abs(g[mm] / lf - 1)))
    ax[2].semilogx(a["f"][mm], 100 * (g[mm] / lf - 1), label="as built, RV101 trimmed")
    ax[2].set_title("flatness 1 Hz-100 MHz (to the LF gain)"); ax[2].set_ylabel("%"); ax[2].set_ylim(-10, 10)
    ax2[0].set_xscale("log"); ax2[0].set_ylim(0.88, 1.12); ax2[0].set_title("1 V step (no terminator) at BUF802 OUT / LF gain"); ax2[0].set_xlabel("us")
    ax2[1].set_title("flatness / LF gain, raw and corrected"); ax2[1].set_ylabel("%"); ax2[1].set_ylim(-10, 10)
    for a_ in list(ax) + list(ax2):
        a_.grid(True, which="both", alpha=0.3); a_.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "bom2_ac.png"), dpi=90)
    fig2.tight_layout(); fig2.savefig(os.path.join(HERE, "bom2_steps.png"), dpi=90)
    json.dump(R, open(os.path.join(HERE, "results.json"), "w"), indent=1, default=float)
    print(json.dumps({k: R[k] for k in ("correction", "trimmed_reference_flat_pct")}, indent=1))
