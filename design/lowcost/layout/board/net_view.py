#!/usr/bin/env python3
"""Review render (TIGHTEN, 24 Nov): one copper side of a board as a net-coloured plot -- filled zones (light), tracks,
pads (solid, labelled ref.pad), vias (circles: GND black ring, supplies coloured), courtyards (thin grey) -- so that
decoupling loops and via positions can be read at a glance.  Zones must be filled in the file (the generators save a
filled copy in their scratch directory).
Run: python3 net_view.py <filled.kicad_pcb> <out.png> <F|B|L3> x0 y0 x1 y1 [--org ox oy]   (crop in local mm, origin org)"""
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Circle
import pcbnew

PAL = {"GND": "#3a7d44", "VBUS": "#e08a00", "/+5V1": "#1f6fd1", "+3V3": "#c2185b", "+1V2": "#7b1fa2",
       "/power/+5V1F": "#0097a7", "+5V": "#5c6bc0", "-5V": "#8d6e63", "+2V5": "#f06292", "-2V5": "#a1887f"}


def col(net):
    if net in PAL:
        return PAL[net]
    if "SW" in net or "-L1" in net or "-L2" in net:
        return "#d32f2f"
    if "FB" in net or "PG" in net:
        return "#9e9e9e"
    return "#607d8b"


def main():
    a = sys.argv
    path, out, side = a[1], a[2], a[3]
    x0, y0, x1, y1 = map(float, a[4:8])
    ox, oy = (float(a[a.index("--org") + 1]), float(a[a.index("--org") + 2])) if "--org" in a else (100.0, 100.0)
    b = pcbnew.LoadBoard(path)
    L = {"F": pcbnew.F_Cu, "B": pcbnew.B_Cu, "L3": pcbnew.In2_Cu}[side]      # L3: inner layer In2 (BOM-2)
    CY = pcbnew.B_CrtYd if side == "B" else pcbnew.F_CrtYd
    mm = lambda v: pcbnew.ToMM(v)
    P = lambda p: (mm(p.x) - ox, mm(p.y) - oy)
    fig, ax = plt.subplots(figsize=(10, 10 * (y1 - y0) / (x1 - x0)), dpi=200)
    zs = [z for z in b.Zones() if not z.GetIsRuleArea() and z.IsOnLayer(L)]
    for z in sorted(zs, key=lambda z_: z_.GetAssignedPriority()):
        fl = z.GetFilledPolysList(L)
        c = col(z.GetNetname())
        for i in range(fl.OutlineCount()):
            o = fl.Outline(i)
            pts = [P(o.CPoint(k)) for k in range(o.PointCount())]
            if len(pts) > 2:
                ax.add_patch(Polygon(pts, closed=True, fc=c, ec=c, alpha=0.35 if z.GetNetname() == "GND" else 0.5,
                                     lw=0.3))
            for h in range(fl.HoleCount(i)):
                o = fl.Hole(i, h)
                pts = [P(o.CPoint(k)) for k in range(o.PointCount())]
                if len(pts) > 2:
                    ax.add_patch(Polygon(pts, closed=True, fc="white", ec="none"))
    for t in b.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            continue
        if t.GetLayer() != L:
            continue
        s, e = P(t.GetStart()), P(t.GetEnd())
        ax.plot([s[0], e[0]], [s[1], e[1]], color=col(t.GetNetname()), lw=mm(t.GetWidth()) * 72 * 10 / (x1 - x0) / 1.0,
                solid_capstyle="round", alpha=0.9)
    for fp in b.GetFootprints():
        fp.BuildCourtyardCaches()
        cy = fp.GetCourtyard(CY)
        for i in range(cy.OutlineCount()):
            o = cy.Outline(i)
            pts = [P(o.CPoint(k)) for k in range(o.PointCount())]
            ax.add_patch(Polygon(pts, closed=True, fill=False, ec="#9e9e9e", lw=0.6, ls="--"))
        for p in fp.Pads():
            if not p.IsOnLayer(L):
                continue
            sp = pcbnew.SHAPE_POLY_SET()
            p.TransformShapeToPolygon(sp, L, 0, 5000)
            for i in range(sp.OutlineCount()):
                o = sp.Outline(i)
                pts = [P(o.CPoint(k)) for k in range(o.PointCount())]
                ax.add_patch(Polygon(pts, closed=True, fc=col(p.GetNetname()), ec="black", lw=0.4, alpha=0.95))
            c = P(p.GetPosition())
            if x0 <= c[0] <= x1 and y0 <= c[1] <= y1 and p.GetNumber():
                ax.text(c[0], c[1], f"{fp.GetReference()}.{p.GetNumber()}", fontsize=4.5, ha="center", va="center",
                        color="white", weight="bold")
    for v in b.GetTracks():
        if not isinstance(v, pcbnew.PCB_VIA):
            continue
        c = P(v.GetPosition())
        n = v.GetNetname()
        ax.add_patch(Circle(c, mm(v.GetWidth()) / 2, fc="white", ec=("black" if n == "GND" else col(n)), lw=1.6))
        ax.add_patch(Circle(c, mm(v.GetDrillValue()) / 2, fc=("black" if n == "GND" else col(n))))
    ax.set_xlim(x0, x1)
    ax.set_ylim(y1, y0)
    ax.set_aspect("equal")
    ax.grid(True, lw=0.2, alpha=0.5)
    ax.set_title(f"{side} side, net view (GND green / black-ring vias)", fontsize=8)
    fig.tight_layout()
    fig.savefig(out)


if __name__ == "__main__":
    main()
