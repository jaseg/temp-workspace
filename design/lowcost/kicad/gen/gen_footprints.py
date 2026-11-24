"""Project footprint library ../lib/scope-fe.pretty (KiCad 7 format, footprint version 20221018).

Würth_WR-WST_debug_490107671612_2x08_P2.54mm_Vertical: Würth WR-WST Redfit IDC direct-to-board footprint
(debug tolerances, MPN 490107671612, 2x08), re-created from the yanartas sensing board library
(libraries/Connector_Wuerth_WR_WST.pretty, KiCad 9/10 format, which KiCad 7 cannot load). Same name, pads
(16 plated holes 1.85 mm / drill 1.5 mm, staggered 1.27 mm, odd pins at x = -1.27, even at x = +1.27, pin 1 at
y = -9.525), two NPTH (2.2 mm at (-1.27, +10.755), 2.6 mm at (+1.27, -10.755)), silkscreen, courtyard and fab
outline. Footprint only: the cable connector plugs into the board, nothing is soldered.

Texas_DLA0010A_VSON-HR-10_2x3mm_P0.5mm: TPS63802DLAR (U603). TI SLVSEU9D, DLA0010A example board layout
(4223750/D): pins 1-5 at x = -0.9 (0.6 x 0.25 mm), pins 10, 9, 7, 6 at x = +0.75 (0.9 x 0.25 mm), pin 8 (GND)
at x = +0.55 (1.3 x 0.25 mm), all on a 0.5 mm pitch, pin 1 / 10 at y = -1.0; no exposed pad. Non-solder-mask
defined (mask = pad + 0.05 mm per side); paste = pad (0.1 mm stencil, pin 8 about 83 % in the TI example).

L_XR0420_4.4x4.2mm: XR XR0420-R47M 0.47 uH (L601). Xiangru datasheet section 4 recommended land: gap a = 2.2,
overall b = 5.2, pad height c = 2.5 mm -> two 1.5 x 2.5 mm pads at x = +/-1.85; body 4.4 x 4.2 mm.

Usage: python3 gen_footprints.py   (gen_all.py runs it)."""
import os
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
LIBDIR = os.path.normpath(os.path.join(HERE, "..", "lib", "scope-fe.pretty"))
_NS = uuid.UUID("5c09e5f0-7d1b-4b52-9a51-0f3c2a1e0002")

WRWST = "Würth_WR-WST_debug_490107671612_2x08_P2.54mm_Vertical"
FONT = "(effects (font (size 1 1) (thickness 0.15)))"


def _n(v):
    v = round(v, 4)
    return f"{v:g}" if v != 0 else "0"


def wrwst():
    name = WRWST
    ts = (lambda k: str(uuid.uuid5(_NS, name + "/" + k)))
    out = [f'(footprint "{name}" (version 20221018) (generator pcbnew)',
           '  (layer "F.Cu")',
           '  (descr "Würth WR-WST series direct-to-board connector footprint, debug application tolerances, '
           'MPN 490107671612 https://www.we-online.com/components/products/datasheet/490107671612.pdf '
           '(re-created in KiCad 7 format from the yanartas sensing board library)")',
           '  (tags "connector Würth WR-WST_debug vertical")',
           '  (attr through_hole)',
           f'  (fp_text reference "REF**" (at 0 -15.16) (layer "F.SilkS")\n    {FONT}\n    (tstamp {ts("ref")})\n  )',
           f'  (fp_text value "{name}" (at 0 15.16) (layer "F.Fab")\n    {FONT}\n    (tstamp {ts("val")})\n  )',
           f'  (fp_text user "${{REFERENCE}}" (at 0 1.5) (layer "F.Fab")\n    {FONT}\n    (tstamp {ts("user")})\n  )']
    silk = [(-3.24, -14.395, -1.74, -14.395), (-3.24, -12.895, -3.24, -14.395), (-2.8, -12.875, -1.3, -12.125),
            (-2.8, 10.975, -2.4, 10.975), (-2.4, 10.975, -2.4, 12.475), (-2.4, 12.475, -2.8, 12.475),
            (-1.3, -12.125, -2.8, -11.375), (2.4, -12.875, 2.4, -11.375), (2.4, -11.375, 2.8, -11.375),
            (2.8, -12.875, 2.4, -12.875)]
    fab = [(-2.8, -10.275, -1.3, -9.525), (-1.3, -9.525, -2.8, -8.775)]
    k = 0
    for layer, w, lines in (("F.SilkS", 0.12, silk), ("F.Fab", 0.1, fab)):
        for x0, y0, x1, y1 in lines:
            k += 1
            out.append(f'  (fp_line (start {_n(x0)} {_n(y0)}) (end {_n(x1)} {_n(y1)})\n'
                       f'    (stroke (width {_n(w)}) (type solid)) (layer "{layer}") (tstamp {ts(f"l{k}")}))')
    for layer, w, (x0, y0, x1, y1) in (("F.SilkS", 0.12, (-2.8, -13.955, 2.8, 13.955)),
                                       ("F.CrtYd", 0.05, (-3.3, -14.455, 3.3, 14.455)),
                                       ("F.Fab", 0.1, (-2.8, -13.955, 2.8, 13.955))):
        out.append(f'  (fp_rect (start {_n(x0)} {_n(y0)}) (end {_n(x1)} {_n(y1)})\n'
                   f'    (stroke (width {_n(w)}) (type solid)) (fill none) (layer "{layer}") (tstamp {ts("r" + layer)}))')
    for i, (x, y, d) in enumerate(((-1.27, 10.755, 2.2), (1.27, -10.755, 2.6))):
        out.append(f'  (pad "" np_thru_hole circle (at {_n(x)} {_n(y)}) (size {_n(d)} {_n(d)}) (drill {_n(d)}) '
                   f'(layers "*.Cu" "*.Mask") (tstamp {ts(f"npth{i}")}))')
    for p in range(1, 17):
        x = -1.27 if p % 2 else 1.27
        y = -9.525 + (p - 1) * 1.27
        out.append(f'  (pad "{p}" thru_hole circle (at {_n(x)} {_n(y)}) (size 1.85 1.85) (drill 1.5) '
                   f'(layers "*.Cu" "*.Mask") (tstamp {ts(f"p{p}")}))')
    out.append(")")
    return name, "\n".join(out) + "\n"


def _hdr(name, descr, tags, attr="smd"):
    ts = (lambda k: str(uuid.uuid5(_NS, name + "/" + k)))
    out = [f'(footprint "{name}" (version 20221018) (generator pcbnew)', '  (layer "F.Cu")',
           f'  (descr "{descr}")', f'  (tags "{tags}")', f'  (attr {attr})']
    return out, ts


def _txt(out, ts, yref, name):
    out.append(f'  (fp_text reference "REF**" (at 0 {_n(-yref)}) (layer "F.SilkS")\n    {FONT}\n    (tstamp {ts("ref")})\n  )')
    out.append(f'  (fp_text value "{name}" (at 0 {_n(yref)}) (layer "F.Fab")\n    {FONT}\n    (tstamp {ts("val")})\n  )')
    out.append(f'  (fp_text user "${{REFERENCE}}" (at 0 0) (layer "F.Fab")\n'
               f'    (effects (font (size 0.5 0.5) (thickness 0.08)))\n    (tstamp {ts("user")})\n  )')


def _rect(out, ts, layer, w, x0, y0, x1, y1, key):
    out.append(f'  (fp_rect (start {_n(x0)} {_n(y0)}) (end {_n(x1)} {_n(y1)})\n'
               f'    (stroke (width {_n(w)}) (type solid)) (fill none) (layer "{layer}") (tstamp {ts(key)}))')


def _line(out, ts, layer, w, x0, y0, x1, y1, key):
    out.append(f'  (fp_line (start {_n(x0)} {_n(y0)}) (end {_n(x1)} {_n(y1)})\n'
               f'    (stroke (width {_n(w)}) (type solid)) (layer "{layer}") (tstamp {ts(key)}))')


def _pad(out, ts, num, x, y, w, h, rr=0.2, mask=0.05):
    out.append(f'  (pad "{num}" smd roundrect (at {_n(x)} {_n(y)}) (size {_n(w)} {_n(h)}) '
               f'(layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio {_n(rr)}) '
               f'(solder_mask_margin {_n(mask)}) (tstamp {ts("p" + str(num))}))')


DLA = "Texas_DLA0010A_VSON-HR-10_2x3mm_P0.5mm"
XR0420 = "L_XR0420_4.4x4.2mm"


def dla0010a():
    """TPS63802 DLA (VSON-HR-10, 2 x 3 mm), TI land pattern 4223750/D (see module docstring)."""
    name = DLA
    out, ts = _hdr(name, "TI DLA0010A VSON-HR-10 2x3 mm 0.5 mm pitch, no exposed pad (TPS63802), land pattern per "
                         "SLVSEU9D 4223750/D https://www.ti.com/lit/ds/symlink/tps63802.pdf", "VSON-HR DLA TPS63802")
    _txt(out, ts, 2.4, name)
    _rect(out, ts, "F.Fab", 0.1, -1.0, -1.5, 1.0, 1.5, "fab")
    _line(out, ts, "F.Fab", 0.1, -1.0, -1.0, -0.5, -1.5, "fab1")
    _line(out, ts, "F.SilkS", 0.12, -0.45, -1.62, 1.06, -1.62, "s1")
    _line(out, ts, "F.SilkS", 0.12, -1.06, 1.62, 1.06, 1.62, "s2")
    _line(out, ts, "F.SilkS", 0.12, -1.45, -1.62, -1.2, -1.62, "s3")
    _rect(out, ts, "F.CrtYd", 0.05, -1.5, -1.8, 1.5, 1.8, "crt")
    for i, num in enumerate((1, 2, 3, 4, 5)):
        _pad(out, ts, num, -0.9, -1.0 + 0.5 * i, 0.6, 0.25)
    for num, y in ((10, -1.0), (9, -0.5), (7, 0.5), (6, 1.0)):
        _pad(out, ts, num, 0.75, y, 0.9, 0.25)
    _pad(out, ts, 8, 0.55, 0.0, 1.3, 0.25)
    out.append(")")
    return name, "\n".join(out) + "\n"


def xr0420():
    """XR0420 molded power inductor 4.4 x 4.2 mm, Xiangru recommended land (see module docstring)."""
    name = XR0420
    out, ts = _hdr(name, "XR XR0420 molded power inductor 4.4x4.2x2.0 mm, land 2x 1.5x2.5 mm, gap 2.2 mm "
                         "(Xiangru datasheet, LCSC C5307593)", "inductor XR0420")
    _txt(out, ts, 3.2, name)
    _rect(out, ts, "F.Fab", 0.1, -2.2, -2.1, 2.2, 2.1, "fab")
    _line(out, ts, "F.SilkS", 0.12, -0.9, -2.22, 0.9, -2.22, "s1")
    _line(out, ts, "F.SilkS", 0.12, -0.9, 2.22, 0.9, 2.22, "s2")
    _rect(out, ts, "F.CrtYd", 0.05, -2.85, -2.5, 2.85, 2.5, "crt")
    for num, x in ((1, -1.85), (2, 1.85)):
        _pad(out, ts, num, x, 0.0, 1.5, 2.5, rr=0.1, mask=0.0)
    out.append(")")
    return name, "\n".join(out) + "\n"


def main():
    os.makedirs(LIBDIR, exist_ok=True)
    for name, txt in (wrwst(), dla0010a(), xr0420()):
        fn = os.path.join(LIBDIR, name + ".kicad_mod")
        with open(fn, "w", encoding="utf-8") as f:
            f.write(txt)
        print("footprint:", os.path.relpath(fn, os.path.join(HERE, "..")))


if __name__ == "__main__":
    main()
