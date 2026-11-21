"""Bias-tee netlists (present and corrected) with the layout parasitics of the fragments.

Each tee is a SPICE subcircuit with pins `tap` (the 50 R line node) and `vcc` (the supply plane / rail).
Parasitics (pF / nH) come from models.LAYOUT_CONST and the generator geometry:
  present sampler  (layout/sampler, FB402/L402 before this change): bead pad centred 0.30 mm off the line axis,
                   0.3 mm track; bead -> 1210 by 0.6 mm x 0.7 mm track; 1210 cold pad -> +3V3 polygon, plane vias
                   1.75 mm left of the inductor, 1 nF / 10 uF 2.0 / 3.5 mm to the right.
  present line     (layout/phase_trigger, L301/L302): 120 nH pad on the line, 0.5 mm x 1.4 mm track to the
                   47 uH (0806 part on a 1008 land), cold pad -> 0.5 mm x 1.6 mm track -> 100 nF / 1 nF.
  present GVA      (schematic only): bead + 2.2 uH LQM21PN, generic compact placement assumed.
  corrected TRF    bead pad on the line axis, bead -> 47 uH 1210 abutting (0.64 mm x 0.3 mm), 1 k across the
                   47 uH (0402 beside it), 100 nF 0.3 mm behind the cold pad, GND via at its pad, plane via pair
                   on the far side of the capacitor.
  corrected GVA    as corrected TRF with 2.2 uH LQM21PN (0805), no damping resistor (the stub shorts the band
                   where the 2.2 uH resonates; see RESULT.md).
"""
from __future__ import annotations

import models as m

K = m.LAYOUT_CONST


def tr(name, a, b, w, l):
    """Short track as one L section with C split to ground (pF/nH from the microstrip formula)."""
    L, C = m.l_mm(w) * l, m.c_mm(w) * l
    return [f"L{name} {a} {b} {L:.4g}n", f"C{name}a {a} 0 {C / 2:.4g}p", f"C{name}b {b} 0 {C / 2:.4g}p"]


def cold_end(tag, node, caps, via_gnd_l, track_l, plane_vias, plane_dist):
    """Decoupling at the cold end: caps [(subckt, distance mm)], each to GND through its via; plane via(s)."""
    out = []
    for i, (sub, dist) in enumerate(caps):
        out += tr(f"{tag}c{i}", node, f"{tag}cp{i}", 0.6, max(dist, 0.05))
        out += [f"X{tag}C{i} {tag}cp{i} {tag}cg{i} {sub}", f"L{tag}vg{i} {tag}cg{i} 0 {via_gnd_l + m.l_mm(0.4) * track_l:.4g}n"]
    out += tr(f"{tag}pl", node, f"{tag}pv", 1.0, plane_dist)
    out += [f"L{tag}pv {tag}pv vcc {K['via_in2'] / plane_vias:.4g}n"]
    return out


def tee(kind: str) -> str:
    v = K["via_in1"]
    L = [f".subckt TEE_{kind} tap vcc"]
    if kind == "present_sampler":
        L += [f"Ctap tap 0 {K['pad0402'] * 0.70 + m.c_mm(0.3) * 0.12:.4g}p",        # off-axis pad + 0.3 mm stub
              f"Ltap tap t1 {m.l_mm(0.3) * 0.3:.4g}n", "Xfb t1 n1 BEAD",
              f"Cn1 n1 0 {K['pad0402']:.4g}p"]
        L += tr("bl", "n1", "n2", 0.6, 0.7) + [f"Cn2 n2 0 {K['pad1210']:.4g}p", "XL n2 n3 L47_1210",
                                                f"Cn3 n3 0 {K['pad1210']:.4g}p"]
        L += cold_end("ce", "n3", [("C1N", 2.0), ("C10U", 3.5)], v, 0.6, 2, 1.75)
    elif kind == "present_line":
        L += [f"Ctap tap 0 {K['pad0402_on_line']:.4g}p", "Xl1 tap n1 LQW120N", f"Cn1 n1 0 {K['pad0402']:.4g}p"]
        L += tr("bl", "n1", "n2", 0.5, 1.4) + [f"Cn2 n2 0 {K['pad1008']:.4g}p", "XL n2 n3 L47_0806",
                                                f"Cn3 n3 0 {K['pad1008']:.4g}p"]
        L += cold_end("ce", "n3", [("C100N", 1.6), ("C1N", 2.5)], v, 0.6, 1, 2.1)
    elif kind == "present_gva":
        L += [f"Ctap tap 0 {K['pad0402_on_line']:.4g}p", "Xfb tap n1 BEAD", f"Cn1 n1 0 {K['pad0402']:.4g}p"]
        L += tr("bl", "n1", "n2", 0.5, 1.0) + [f"Cn2 n2 0 {K['pad0805']:.4g}p", "XL n2 n3 L2U2",
                                                f"Cn3 n3 0 {K['pad0805']:.4g}p"]
        L += cold_end("ce", "n3", [("C1N", 1.0), ("C100N", 2.0), ("C10U", 3.0)], v, 0.6, 1, 2.0)
    elif kind in ("corr_trf", "corr_trf_noR"):
        L += [f"Ctap tap 0 {K['pad0402_on_line']:.4g}p", "Xfb tap n1 BEAD", f"Cn1 n1 0 {K['pad0402']:.4g}p"]
        L += tr("bl", "n1", "n2", 0.64, 0.3) + [f"Cn2 n2 0 {K['pad1210'] + K['pad0402']:.4g}p", "XL n2 n3 L47_1210",
                                                 f"Cn3 n3 0 {K['pad1210'] + K['pad0402']:.4g}p"]
        if kind == "corr_trf":
            L += ["Rd n2 n3 1k", "Cd n2 n3 0.05p"]                                # 0402 1 k, its own 50 fF
        L += cold_end("ce", "n3", [("C100N", 0.3)], v, 0.1, 2, 1.3)
    elif kind == "corr_gva":
        L += [f"Ctap tap 0 {K['pad0402_on_line']:.4g}p", "Xfb tap n1 BEAD", f"Cn1 n1 0 {K['pad0402']:.4g}p"]
        L += tr("bl", "n1", "n2", 0.64, 0.3) + [f"Cn2 n2 0 {K['pad0805']:.4g}p", "XL n2 n3 L2U2",
                                                 f"Cn3 n3 0 {K['pad0805']:.4g}p"]
        L += cold_end("ce", "n3", [("C100N", 0.3)], v, 0.1, 2, 1.3)
    elif kind == "ideal":
        L += ["Rbig tap vcc 1e9"]
    else:
        raise KeyError(kind)
    L += [".ends"]
    return "\n".join(L)


KINDS = ["present_sampler", "present_line", "present_gva", "corr_trf", "corr_trf_noR", "corr_gva", "ideal"]
LABEL = {"present_sampler": "present strobe/sampler: BLM15HD102 + 47 uH 1210",
         "present_line": "present line driver: 120 nH 0402 + 47 uH 0806",
         "present_gva": "present GVA: BLM15HD102 + 2.2 uH LQM21PN",
         "corr_trf": "corrected TRF: BLM15HD102 + (47 uH 1210 || 1 k)",
         "corr_trf_noR": "corrected layout, no 1 k",
         "corr_gva": "corrected GVA: BLM15HD102 + 2.2 uH (compact)",
         "ideal": "no branch"}


def lib(d_bead=1.0):
    return m.library(d_bead) + "\n" + "\n".join(tee(k) for k in KINDS) + "\n"
