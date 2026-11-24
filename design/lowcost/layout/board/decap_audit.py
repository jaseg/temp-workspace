#!/usr/bin/env python3
"""Decoupling audit (TIGHTEN, 24 Nov): for every capacitor with one pad on GND and the other on a supply net, find the
IC pin it decouples (nearest U* pad on that net) and report
  d_cu     pad-edge to pad-edge distance IC pin -> capacitor supply pad (mm)
  crt      courtyard gap IC <-> capacitor (same side only; '-' for opposite sides); 0.0 = touching
  vS       supply via nearest the IC pin: its distance to the pin / to the capacitor supply pad
  vG       GND via nearest the capacitor GND pad (distance), and GND vias within 0.7 mm of a non-EP IC GND pin
Defects:
  D1  capacitor farther from its pin than the courtyards require (same side: crt > 0.3 mm and d_cu > 1.0 mm;
      opposite side: d_cu > 1.5 mm)
  D1 is judged on the primary (nearest) capacitor of each IC / net only; others are marked (2nd)
  D2s (same side only) a supply via sits between pin and capacitor or at the pin: nearest supply via closer to the pin than the
      capacitor pad is (d(via, pin) < d_cu - 0.1) - current reaches the pin before the capacitor
  D2g capacitor GND pad without a GND via within 1.0 mm
Run: python3 decap_audit.py [board.kicad_pcb] [--refs U603,U601] [--all]"""
import sys, math, re
import pcbnew

SUPPLY_RX = re.compile(r"^(/)?(\+|-)\d|^VBUS|^/power/|^/\+|^/-|VCC|VDD|VTAP|_LDO|5V|3V3|1V2|2V5|1V8|VREF|VCCIO")


def mm(v):
    return pcbnew.ToMM(v)


def bbox(p):
    b = p.GetBoundingBox()
    return mm(b.GetLeft()), mm(b.GetTop()), mm(b.GetRight()), mm(b.GetBottom())


def rect_d(a, b):
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return math.hypot(dx, dy)


def pt_rect(p, r):
    dx = max(r[0] - p[0], 0, p[0] - r[2])
    dy = max(r[1] - p[1], 0, p[1] - r[3])
    return math.hypot(dx, dy)


def crt_gap(f1, f2):
    if f1.GetLayer() != f2.GetLayer():
        return None
    lay = pcbnew.F_CrtYd if f1.GetLayer() == pcbnew.F_Cu else pcbnew.B_CrtYd
    a, b = f1.GetCourtyard(lay), f2.GetCourtyard(lay)
    if not a.OutlineCount() or not b.OutlineCount():
        return None
    ba, bb = a.BBox(), b.BBox()
    ra = (mm(ba.GetLeft()), mm(ba.GetTop()), mm(ba.GetRight()), mm(ba.GetBottom()))
    rb = (mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom()))
    return rect_d(ra, rb)


def audit(path, refs=None, show_all=False):
    b = pcbnew.LoadBoard(path)
    for f in b.GetFootprints():
        f.BuildCourtyardCaches()
    vias = [(mm(v.GetPosition().x), mm(v.GetPosition().y), v.GetNetname())
            for v in b.GetTracks() if isinstance(v, pcbnew.PCB_VIA)]
    ics = [f for f in b.GetFootprints() if f.GetReference().startswith("U")]
    rows = []
    for c in b.GetFootprints():
        r = c.GetReference()
        if not r.startswith("C") or len(c.Pads()) != 2:
            continue
        nets = [p.GetNetname() for p in c.Pads()]
        if "GND" not in nets:
            continue
        sn = [n for n in nets if n != "GND"][0]
        if not sn or not SUPPLY_RX.search(sn):
            continue
        cs = [p for p in c.Pads() if p.GetNetname() == sn][0]
        cg = [p for p in c.Pads() if p.GetNetname() == "GND"][0]
        rs, rg = bbox(cs), bbox(cg)
        best = None
        for u in ics:
            for p in u.Pads():
                if p.GetNetname() != sn:
                    continue
                d = rect_d(rs, bbox(p))
                if best is None or d < best[0]:
                    best = (d, u, p)
        if best is None or best[0] > 6.0:
            continue
        d, u, p = best
        if refs and u.GetReference() not in refs:
            continue
        rp = bbox(p)
        pc = ((rp[0] + rp[2]) / 2, (rp[1] + rp[3]) / 2)
        cg_ = crt_gap(u, c)
        sv = [(math.hypot(x - pc[0], y - pc[1]), x, y) for x, y, n in vias if n == sn]
        sv.sort()
        vs = None
        if sv and sv[0][0] < 4.0:
            vs = (round(pt_rect((sv[0][1], sv[0][2]), rp), 2), round(pt_rect((sv[0][1], sv[0][2]), rs), 2))
        gv = [pt_rect((x, y), rg) for x, y, n in vias if n == "GND"]
        vg = round(min(gv), 2) if gv else None
        d1 = (cg_ is not None and cg_ > 0.3 and d > 1.0) or (cg_ is None and d > 1.5)
        d2s = cg_ is not None and vs is not None and vs[0] < d - 0.1     # same side only (B caps need a via)
        d2g = vg is None or vg > 1.0
        rows.append(dict(cap=r, side="F" if c.GetLayer() == pcbnew.F_Cu else "B", ic=u.GetReference(),
                         pin=p.GetNumber(), net=sn, d_cu=round(d, 2), crt=None if cg_ is None else round(cg_, 2),
                         vS=vs, vG=vg, D1=d1, D2s=d2s, D2g=d2g, pos=(round(mm(c.GetPosition().x), 2),
                                                                     round(mm(c.GetPosition().y), 2))))
    # D1 only for the primary capacitor of each IC / net (nearest); bulk / secondary capacitors are reported, not flagged
    prim = {}
    for q in rows:
        k = (q["ic"], q["net"])
        rank = lambda q_: q_["d_cu"] + (0.0 if q_["crt"] is not None else 1.0)     # same-side capacitor preferred
        if k not in prim or rank(q) < rank(prim[k]):
            prim[k] = q
    for q in rows:
        q["prim"] = prim[(q["ic"], q["net"])] is q
        if not q["prim"]:
            q["D1"] = False
    rows.sort(key=lambda q: (q["ic"], q["cap"]))
    return rows


def fmt(q):
    fl = " ".join(k for k in ("D1", "D2s", "D2g") if q[k]) + ("" if q["prim"] else " (2nd)")
    return (f"{q['ic']:6s} {q['pin']:>4s} {q['cap']:6s} {q['side']} {q['net'][:16]:16s} d_cu {q['d_cu']:5.2f} "
            f"crt {'  -  ' if q['crt'] is None else f'{q[chr(99)+chr(114)+chr(116)]:5.2f}'} "
            f"vS(pin/cap) {str(q['vS']):14s} vG {str(q['vG']):5s} {q['pos']} {fl}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "scope-fe.kicad_pcb"
    refs = None
    if "--refs" in sys.argv:
        refs = set(sys.argv[sys.argv.index("--refs") + 1].split(","))
    rows = audit(path, refs)
    bad = [q for q in rows if q["D1"] or q["D2s"] or q["D2g"]]
    for q in (rows if "--all" in sys.argv else bad):
        print(fmt(q))
    print(f"capacitors {len(rows)}; D1 {sum(q['D1'] for q in rows)}; D2s {sum(q['D2s'] for q in rows)}; "
          f"D2g {sum(q['D2g'] for q in rows)}")
