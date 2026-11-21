"""Project footprint library ../lib/scope-fe.pretty (KiCad 7 format, footprint version 20221018).

Würth_WR-WST_debug_490107671612_2x08_P2.54mm_Vertical: Würth WR-WST Redfit IDC direct-to-board footprint
(debug tolerances, MPN 490107671612, 2x08), re-created from the yanartas sensing board library
(libraries/Connector_Wuerth_WR_WST.pretty, KiCad 9/10 format, which KiCad 7 cannot load). Same name, pads
(16 plated holes 1.85 mm / drill 1.5 mm, staggered 1.27 mm, odd pins at x = -1.27, even at x = +1.27, pin 1 at
y = -9.525), two NPTH (2.2 mm at (-1.27, +10.755), 2.6 mm at (+1.27, -10.755)), silkscreen, courtyard and fab
outline. Footprint only: the cable connector plugs into the board, nothing is soldered.

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


def main():
    os.makedirs(LIBDIR, exist_ok=True)
    for name, txt in (wrwst(),):
        fn = os.path.join(LIBDIR, name + ".kicad_mod")
        with open(fn, "w", encoding="utf-8") as f:
            f.write(txt)
        print("footprint:", os.path.relpath(fn, os.path.join(HERE, "..")))


if __name__ == "__main__":
    main()
