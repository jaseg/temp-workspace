"""Component and layout-parasitic models for the bias tees (ngspice subcircuits).

Vendor data (Murata S-parameter libraries, series-through S2P, 0 mA DC, read from DATA_DIR):
  BLM15HD102SN1 (1 MHz - 3 GHz), LQW15ANR12J00 (50 MHz - 20 GHz; fitted 50 MHz - 1.75 GHz only: the file shows a
  second (series) resonance near 2.5 GHz that the one-section model does not reproduce). Each is fitted here to a Foster ladder
  Rdc + sum_k (R_k || L_k || C_k) with an overall parallel C, error printed by `python3 models.py`.
  Above 3 GHz the bead model is an extrapolation of that fit (its parallel C dominates there).
Datasheet-built (no vendor S-parameters published for the LQH/LQM power inductors):
  L || Cpar || Rp with series DCR; Cpar from the self-resonant frequency, Rp from Q (see PARTS).
DC bias: Murata's S2P files are small-signal at 0 mA. Bead impedance under DC current is reduced with an
  assumed factor d (all section impedances x d): 0.85 at 55 mA, 0.65 at 108-130 mA (assumption, not vendor data).
Layout parasitics: microstrip formula of the layout generators (Hammerstad-Jensen + thickness + mask term) on
  JLC04161H-7628 (L1 over In1 GND at 0.2104 mm, er 4.4); vias by the usual 0.2 h (ln(4h/d) + 1) nH formula.
"""
from __future__ import annotations

import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("BIASTEE_DATA",
                          "/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/biastee/dl")
S2P = {"BLM15HD102SN1": "sp_fb/blm15-s/BLM15HD102SN1.s2p",
       "LQW15ANR12J00": "sp_ind/lqw15an-00-s/LQW15ANR12J00.s2p"}

# ------------------------------------------------------------------------------------------- stack-up
H, T_CU, ER, ER_MASK = 0.2104, 0.035, 4.4, 3.8
C0 = 0.299792458                   # mm/ps
E0 = 8.854e-15                     # F/mm


def microstrip(w, h=H, t=T_CU, er=ER):
    """Same formula as layout/*/gen_*.py: returns (Z0, eps_eff)."""
    u = w / h

    def z_air(x):
        f = 6 + (2 * math.pi - 6) * math.exp(-(30.666 / x) ** 0.7528)
        return 60 * math.log(f / x + math.sqrt(1 + 4 / x ** 2))

    def ee0(x):
        a = 1 + math.log((x ** 4 + (x / 52) ** 2) / (x ** 4 + 0.432)) / 49 + math.log(1 + (x / 18.1) ** 3) / 18.7
        b = 0.564 * ((er - 0.9) / (er + 3)) ** 0.053
        return (er + 1) / 2 + (er - 1) / 2 * (1 + 10 / x) ** (-a * b)
    du1 = t / h / math.pi * math.log(1 + 4 * math.e / (t / h * (1 / math.tanh(math.sqrt(6.517 * u))) ** 2))
    dur = 0.5 * (1 + 1 / math.cosh(math.sqrt(er - 1))) * du1
    u1, ur = u + du1, u + dur
    ee = ee0(ur) * (z_air(u1) / z_air(ur)) ** 2
    q = (ee - 1) / (er - 1)
    ee += (ER_MASK - 1) * (1 - q) * (1 - math.exp(-1.2 * 0.0225 / h))
    return z_air(u1) / math.sqrt(ee), ee


def c_mm(w):
    """Capacitance per mm (pF/mm) of a microstrip of width w (pads are treated as short wide lines)."""
    z, ee = microstrip(w)
    return math.sqrt(ee) / (C0 * z)


def l_mm(w):
    """Inductance per mm (nH/mm)."""
    z, ee = microstrip(w)
    return z * math.sqrt(ee) / C0 * 1e-3


def pad_c(wx, ly):
    """Pad of width wx (across) and length ly over In1: pF."""
    return c_mm(wx) * ly


def via_l(h_mm, d_mm=0.3):
    """Via barrel inductance, nH (h: height to the reference/plane)."""
    return 0.2 * h_mm * (math.log(4 * h_mm / d_mm) + 1)


W50 = 0.36
H_IN2 = H + 0.0152 + 1.065                      # F.Cu to In2 (+3V3 plane)
LAYOUT_CONST = dict(c50=c_mm(W50), l50=l_mm(W50), via_in1=via_l(H), via_in2=via_l(H_IN2),
                    pad0402_on_line=pad_c(0.64, 0.59) - c_mm(W50) * 0.59,     # 0402 pad replacing 0.59 mm of line
                    pad0402=pad_c(0.64, 0.59), pad1210=pad_c(2.65, 1.25), pad0806=pad_c(1.0, 0.85),
                    pad1008=pad_c(2.2, 1.25), pad0805=pad_c(1.2, 0.875))


# ------------------------------------------------------------------------------------------- vendor fits
def load_s2p(name):
    rows = [l.split() for l in open(os.path.join(DATA_DIR, S2P[name])) if l.strip() and l[0] not in "!#"]
    a = np.array([[float(x) for x in r[:9]] for r in rows])
    s21 = a[:, 3] + 1j * a[:, 4]
    return a[:, 0], 2 * 50 * (1 - s21) / s21          # series element in a 50 R fixture


def foster(p, f, nsec):
    """Rdc + sum (R||L||C) sections, all in parallel with Cp. p = log10 of [Rdc, Cp, (R, L, C) * nsec]."""
    q = 10 ** np.asarray(p)
    w = 2j * np.pi * f
    z = q[0] + 0 * w
    for k in range(nsec):
        r, l, c = q[2 + 3 * k: 5 + 3 * k]
        z = z + 1 / (1 / r + 1 / (w * l) + w * c)
    return 1 / (1 / z + w * q[1])


FITS = {}


def fit(name, nsec, fmin, fmax, p0):
    if name in FITS:
        return FITS[name]
    from scipy.optimize import least_squares
    f, z = load_s2p(name)
    m = (f >= fmin) & (f <= fmax)
    f, z = f[m], z[m]

    def res(p):
        e = (foster(p, f, nsec) - z) / np.abs(z)
        return np.concatenate([e.real, e.imag])
    r = least_squares(res, np.log10(p0), method="lm", max_nfev=20000)
    err = np.abs(foster(r.x, f, nsec) - z) / np.abs(z)
    FITS[name] = (r.x, nsec, float(err.max()), float(np.sqrt(np.mean(err ** 2))))
    return FITS[name]


def bead_fit():
    return fit("BLM15HD102SN1", 3, 1e6, 3e9,
               [0.9, 0.05e-12, 300, 1.5e-6, 1e-12, 1500, 0.4e-6, 0.1e-12, 800, 0.1e-6, 0.03e-12])


def lqw_fit():
    return fit("LQW15ANR12J00", 1, 50e6, 1.75e9, [2.8, 1e-15, 7e3, 118e-9, 0.083e-12])


def sub_foster(subname, p, nsec, d=1.0):
    """SPICE subcircuit (pins a b) of a fitted Foster ladder; section impedances scaled by d (DC-bias derate)."""
    q = 10 ** np.asarray(p)
    out = [f".subckt {subname} a b", f"Rdc a n0 {q[0]:.5g}"]
    for k in range(nsec):
        r, l, c = q[2 + 3 * k: 5 + 3 * k]
        nb = "b" if k == nsec - 1 else f"n{k + 1}"
        out += [f"R{k} n{k} {nb} {r * d:.5g}", f"L{k} n{k} {nb} {l * d:.5g}", f"C{k} n{k} {nb} {c / d:.5g}"]
    out += [f"Cp a b {q[1]:.5g}", ".ends"]
    return "\n".join(out)


# ------------------------------------------------------------------------------------------- datasheet parts
# name: (L, DCR typ, DCR max, SRF, Rp, rated mA, source)
PARTS = {
    "LQH32CN470K23L": (47e-6, 1.3, 1.69, 18e6, 15e3, 170,
                       "Murata: 47 uH +/-10 %, Itemp 170 mA, DCR 1.3 R +/-30 % (max 1.69), SRF min 15 MHz (18 MHz used)"),
    "LQH2MCN470K02L": (47e-6, 5.1, 6.63, 20e6, 15e3, 120,
                       "Murata: 0806 (not 1008), 47 uH, Itemp 120 mA, DCR 5.1 R +/-30 % (max 6.63), SRF min 18 MHz"),
    "LQM21PN2R2MGHL": (2.2e-6, 0.125, 0.16, 40e6, 1.5e3, 450,
                       "LCSC C341781: 2.2 uH +/-20 %, 1.3 A, Isat 450 mA, DCR 125 mR, SRF 40 MHz"),
}


def sub_ind(subname, part, dcr="typ"):
    L, rt, rm, srf, rp, _i, _s = PARTS[part]
    c = 1 / (L * (2 * math.pi * srf) ** 2)
    return "\n".join([f".subckt {subname} a b", f"Rs a x {rt if dcr == 'typ' else rm:.4g}", f"L1 x b {L:.4g}",
                      f"Cp a b {c:.4g}", f"Rp a b {rp:.4g}", ".ends"])


def sub_cap(subname, c, esl=0.45e-9, esr=0.03):
    return "\n".join([f".subckt {subname} a b", f"C1 a x {c:.4g}", f"L1 x y {esl:.4g}", f"R1 y b {esr:.4g}", ".ends"])


def library(d_bead=1.0):
    pb, nb, _, _ = bead_fit()
    pl, nl, _, _ = lqw_fit()
    return "\n".join([sub_foster("BEAD", pb, nb, d_bead), sub_foster("LQW120N", pl, nl),
                      sub_ind("L47_1210", "LQH32CN470K23L"), sub_ind("L47_0806", "LQH2MCN470K02L"),
                      sub_ind("L2U2", "LQM21PN2R2MGHL"),
                      sub_cap("C100N", 100e-9), sub_cap("C1N", 1e-9, 0.35e-9, 0.1), sub_cap("C10U", 10e-6, 0.6e-9, 0.005)])


if __name__ == "__main__":
    for nm, fn in (("BLM15HD102SN1", bead_fit), ("LQW15ANR12J00", lqw_fit)):
        p, n, emax, erms = fn()
        print(f"{nm}: {n} sections, fit error max {emax * 100:.1f} %, rms {erms * 100:.1f} %; params {np.round(10 ** p, 15)}")
    for k, v in LAYOUT_CONST.items():
        print(f"{k:16s} {v:.4f}")
    print(library())
