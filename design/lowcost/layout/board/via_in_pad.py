#!/usr/bin/env python3
"""Via-in-pad check (rule 12 of RULES.md): the board is ordered as a standard JLCPCB six-layer board with ordinary
TENTED vias (no plugged / capped / resin-filled vias).  So no via may lie inside or touch a soldered SMD pad on either
side: neither its copper nor its solder-mask opening nor its paste opening.

For every (through) via and every soldered SMD pad on F or B:
  e_hole = distance from the via HOLE edge to the nearest point of (pad copper U mask opening U paste opening)
           (negative = the hole lies inside it)
  e_cu   = distance from the via COPPER (annular ring) edge to the mask opening (tent web between them)
  FAIL   e_hole < HOLE_MIN (0.15 mm) or e_cu < 0 (via copper inside the mask opening: not tented)
  NEAR   HOLE_MIN <= e_hole < HOLE_TARGET (0.2 mm): legal, listed
A pad is 'soldered' when it is SMD copper with paste on its side, or when a paste-only aperture of the same footprint
overlaps it (exposed pads with windowed paste).  Exposed SMD pads WITHOUT paste (test points) are reported separately
(not soldered: a tented via beside them is harmless) and do not fail the check.  Net-tie / copper-only pads (no mask,
no paste) are not pads in this sense and are listed only as a cross-check that they have neither opening.

EP_ALLOW: exposed thermal pads where the datasheet asks for thermal / ground vias IN the pad (decision recorded in
README.md): vias inside them are allowed only with drill <= 0.2 mm and are counted separately (tented on the far side).

Run: python3 via_in_pad.py [board.kicad_pcb] [-v]    (exit status 1 when FAIL > 0)"""
import sys, math
import pcbnew

HOLE_MIN, HOLE_TARGET = 0.15, 0.20
# (ref, pad) -> reason.  Decisions per part in README.md ('Vias out of pads'); every other exposed pad (TLV3801
# U302, LM27762 U604 / U605, TPS63802 U603, TMUX136 U301 has none) is joined by copper to vias outside the package.
_TRF = "TRF37D73 DSG: TI layout guideline asks for ground vias in the thermal pad (RF ground + heat)"
EP_ALLOW = {("U101", "17"): "BUF802 RGT: datasheet layout example has thermal vias in the pad (0.4 W, 3 GHz ground)",
            ("U303", "9"): _TRF, ("U401", "9"): _TRF, ("U402", "9"): _TRF, ("U403", "9"): _TRF,
            ("U405", "9"): _TRF,
            ("U404", "2"): "GVA-84+ SOT-89 tab: Mini-Circuits mounting layout has plated holes in the GND tab",
            ("U406", "2"): "GVA-84+ SOT-89 tab: Mini-Circuits mounting layout has plated holes in the GND tab",
            ("U501", "49"): "GW1NZ QN48: the exposed pad is the only GND of the die; Gowin asks for vias in it"}


def mm(v):
    return pcbnew.ToMM(v)


def polys(item_poly):
    """SHAPE_POLY_SET -> list of outlines [(x, y) ...] in mm"""
    out = []
    for i in range(item_poly.OutlineCount()):
        ol = item_poly.Outline(i)
        out.append([(mm(ol.CPoint(k).x), mm(ol.CPoint(k).y)) for k in range(ol.PointCount())])
    return out


def seg_d(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def inside(p, ol):
    x, y = p; c = False
    n = len(ol)
    for i in range(n):
        (x1, y1), (x2, y2) = ol[i], ol[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def sdist(p, outlines):
    """signed distance point -> union of outlines (negative inside)"""
    best, ins = 1e9, False
    for ol in outlines:
        if len(ol) < 2:
            continue
        ins = ins or inside(p, ol)
        for i in range(len(ol)):
            best = min(best, seg_d(p, ol[i], ol[(i + 1) % len(ol)]))
    return -best if ins else best


def shape(pad, layer, clearance=0):
    ps = pcbnew.SHAPE_POLY_SET()
    pad.TransformShapeToPolygon(ps, layer, int(clearance), pcbnew.FromMM(0.002))
    return polys(ps)


def bbox_mm(o):
    xs = [x for ol in o for x, _ in ol]; ys = [y for ol in o for _, y in ol]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def pad_sets(b):
    """soldered pads, exposed unsoldered pads, copper-only pads: list of dict(ref, pad, net, side, cu, mask, paste)"""
    sold, expo, bare = [], [], []
    for f in b.GetFootprints():
        aper = []                                            # paste-only apertures (no copper)
        for p in f.Pads():
            ls = p.GetLayerSet()
            if not ls.Contains(pcbnew.F_Cu) and not ls.Contains(pcbnew.B_Cu):
                for pl, cl in ((pcbnew.F_Paste, pcbnew.F_Cu), (pcbnew.B_Paste, pcbnew.B_Cu)):
                    if ls.Contains(pl):
                        aper.append((cl, shape(p, pl)))
        for p in f.Pads():
            if p.GetAttribute() not in (pcbnew.PAD_ATTRIB_SMD, pcbnew.PAD_ATTRIB_CONN):
                continue
            ls = p.GetLayerSet()
            for cu, mk, pa in ((pcbnew.F_Cu, pcbnew.F_Mask, pcbnew.F_Paste), (pcbnew.B_Cu, pcbnew.B_Mask, pcbnew.B_Paste)):
                if not ls.Contains(cu):
                    continue
                c = shape(p, cu)
                m = shape(p, mk, p.GetSolderMaskExpansion()) if ls.Contains(mk) else []
                pst = shape(p, pa) if ls.Contains(pa) else []
                bb = bbox_mm(c)
                ap = [o for cl, o in aper if cl == cu and bbox_mm(o) and bb and not (
                    bbox_mm(o)[0] > bb[2] or bbox_mm(o)[2] < bb[0] or bbox_mm(o)[1] > bb[3] or bbox_mm(o)[3] < bb[1])]
                for o in ap:
                    pst = pst + o
                d = dict(ref=f.GetReference(), pad=p.GetNumber(), net=p.GetNetname(), side="F" if cu == pcbnew.F_Cu else "B",
                         cu=c, mask=m, paste=pst, bb=bb)
                if m and pst:
                    sold.append(d)
                elif m:
                    expo.append(d)
                else:
                    bare.append(d)
    return sold, expo, bare


def check(path_or_board, verbose=False):
    b = pcbnew.LoadBoard(path_or_board) if isinstance(path_or_board, str) else path_or_board
    sold, expo, bare = pad_sets(b)
    vias = [v for v in b.GetTracks() if isinstance(v, pcbnew.PCB_VIA)]
    res = dict(fail=[], near=[], ep_allowed=[], exposed_tp=[], bare_with_opening=[], vias=len(vias), pads=len(sold))
    for d in bare:                                           # copper-only pads must have no openings at all
        if d["mask"] or d["paste"]:
            res["bare_with_opening"].append((d["ref"], d["pad"]))
    for v in vias:
        x, y = mm(v.GetPosition().x), mm(v.GetPosition().y)
        rh, rc = mm(v.GetDrillValue()) / 2, mm(v.GetWidth()) / 2
        for group, key in ((sold, "s"), (expo, "e")):
            for d in group:
                bb = d["bb"]
                if bb is None or x < bb[0] - 1.0 or x > bb[2] + 1.0 or y < bb[1] - 1.0 or y > bb[3] + 1.0:
                    continue
                allo = d["cu"] + d["mask"] + d["paste"]
                e_hole = sdist((x, y), allo) - rh
                e_cu = sdist((x, y), d["mask"]) - rc if d["mask"] else 9.0
                if e_hole >= HOLE_TARGET and e_cu >= 0:
                    continue
                row = (d["ref"], d["pad"], d["side"], d["net"], v.GetNetname(), round(x - 100, 3), round(y - 100, 3),
                       round(mm(v.GetDrillValue()), 2), round(e_hole, 3), round(e_cu, 3))
                if key == "e":
                    if e_hole < HOLE_MIN:
                        res["exposed_tp"].append(row)
                    continue
                if (d["ref"], d["pad"]) in EP_ALLOW and e_hole < HOLE_MIN:
                    # allowed only if small (drill <= 0.2) and the whole via (annular ring) lies inside the copper,
                    # i.e. not half in / half out of the exposed pad
                    ok = rh * 2 <= 0.2001 and sdist((x, y), d["cu"]) <= -rc + 1e-3
                    (res["ep_allowed"] if ok else res["fail"]).append(row)
                elif e_hole < HOLE_MIN or e_cu < 0:
                    res["fail"].append(row)
                else:
                    res["near"].append(row)
    return res


def report(res, verbose=False):
    print(f"via-in-pad: {res['vias']} vias x {res['pads']} soldered pads: FAIL {len(res['fail'])}, "
          f"near ({HOLE_MIN}-{HOLE_TARGET} mm) {len(res['near'])}, EP-allowed {len(res['ep_allowed'])}, "
          f"beside unsoldered exposed pads {len(res['exposed_tp'])}, copper-only pads with an opening "
          f"{len(res['bare_with_opening'])}")
    for r in res["fail"][: (10 ** 6 if verbose else 60)]:
        print("   FAIL  %s.%s %s pad %s  via %s (%.3f, %.3f) drill %.2f  hole edge %.3f  tent web %.3f" % r)
    if verbose:
        for r in res["near"]:
            print("   near  %s.%s %s pad %s  via %s (%.3f, %.3f) drill %.2f  hole edge %.3f  tent web %.3f" % r)
        for r in res["exposed_tp"]:
            print("   tp    %s.%s %s pad %s  via %s (%.3f, %.3f) drill %.2f  hole edge %.3f  tent web %.3f" % r)
    if verbose:
        for r in res["ep_allowed"]:
            print("   EP    %s.%s %s pad %s  via %s (%.3f, %.3f) drill %.2f  hole edge %.3f  tent web %.3f" % r)
    for r in res["bare_with_opening"]:
        print("   copper-only pad with a mask / paste opening:", r)


if __name__ == "__main__":
    path = next((a for a in sys.argv[1:] if not a.startswith("-")), "scope-fe.kicad_pcb")
    r = check(path)
    report(r, "-v" in sys.argv)
    sys.exit(1 if r["fail"] or r["bare_with_opening"] else 0)
