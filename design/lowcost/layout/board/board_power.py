#!/usr/bin/env python3
"""Board-level supply distribution for the six-layer scope-fe board (TOPOLOGY.md sections 8 / 9 / 10).

24 Nov 2026 rewrite for the new power tree (TPS62A01A x2, TPS63802, LM27762 x2; docs/research/power-tree.md):

  L4 (In3)  +3V3 only: one solid plane (board_finish.planes), plus the FPGA block's +1V2 island, which is joined to
            the U602 output via by a short L4 finger along the power block's west edge (apply_l4_1v2).
  L3 (In2)  the minor rails as wide TRACKS: /+5V1 (GVA-84+ chokes, 0.34 A), +5V, -5V, +2V5, -2V5, VTAP_P / VTAP_N.
  L6 (B)    only where a rail cannot stay planar on L3 (grid router, cost x3 + via cost), VBUS to J501 pin 1.

Every rail is routed by one grid router (0.1 mm grid, octilinear, scipy Dijkstra on L3 + L6 with vias between):
the tree grows from the regulator output via in the power block; each still-unconnected copper island of the rail
(block vias / tracks / zones) is joined to the tree by the shortest path at the widest width that fits (widths per
rail, widest first; a width is taken if its path is at most 25 % + 3 mm longer than the narrowest one).  Obstacles:
all copper of other nets (tracks, vias, pads, filled zones; GND pours excluded), rule areas, board edge, holes; slow
bias lines keep 0.3 mm, ADC_IN 0.5 mm, and L3 power copper keeps 0.6 mm from every L3 cut-out (node windows, pad cuts).
A guide polyline per rail (cost x1 within 2.5 mm, x2 elsewhere) keeps the planar order of TOPOLOGY.md section 10.
widen() then fattens every rail segment to the widest width (<= WMAX) its clearance allows.

API used by gen_board.py:  apply(board, m) -> report;  widen(board, m) -> {net: mm widened};  verify(board) -> dict;
table(res) -> str.
"""
import math

import numpy as np
import pcbnew
from matplotlib.path import Path as MPath
from scipy import ndimage, sparse
from scipy.sparse import csgraph

import boardlib as bl

G = 0.1                                   # grid (mm)
BW, BH = 100.0, 57.0
NX, NY = int(round(BW / G)) + 1, int(round(BH / G)) + 1
OX, OY = bl.ORG
CLR = 0.18                                # rail copper to foreign copper (Power netclass 0.15)
MARG = 0.75 * G                           # rasterisation margin
EDGE = 0.5                                # copper to board edge
VIA_D, VIA_DRILL = bl.VIA_D, bl.VIA_DRILL
L6_FACTOR = 3.0                           # step cost on L6 relative to L3
VIA_COST = 4.0                            # mm-equivalent per layer change
CLR_TIGHT = 0.15                          # fallback clearance where nothing fits at CLR (= Power netclass)
CUT_MARGIN = 0.6                          # L3 power copper to L3 cut-outs (node windows, pad cuts)
EXTRA = {"/ADC_IN": 0.35, "/VBIAS_A": 0.15, "/VBIAS_K": 0.15, "/VOFS": 0.15, "/VNEG_REF": 0.15, "/DAC_TRIG": 0.15,
         "/VTAP_TH": 0.15, "/ADC_REF_MID": 0.15, "/TRIG_SEL": 0.15}     # extra clearance (slow lines 0.3, ADC_IN 0.5)
# REPAIR (24 Nov, recheck RF2-6): fast / clock nets get 0.15 mm extra (rail edge >= 0.33 mm from them on L3 / L6)
import re as _re
_FAST = _re.compile(r"^/(TAP\d+|COARSE|FPGA_CLK|MCU_CLK|SPI_\w+|ADC_TRIG|S_STROBE_\w|PH_STROBE_\w|USB_D\w|"
                    r"trigger_phase/CMP_\w+|trigger_phase/PH_\w+)$")


def _xtra(n):
    return EXTRA.get(n, 0.15 if _FAST.match(n or "") else 0.0)
LAY = {"In2.Cu": pcbnew.In2_Cu, "B.Cu": pcbnew.B_Cu}
LNAMES = ("In2.Cu", "B.Cu")

# rails in routing order: net, widths (widest first), widen limit, guide polyline (board mm) or None
RAILS = [
    ("/+5V1", (1.2, 1.0, 0.8, 0.6, 0.5, 0.4), 1.5,
     [(86.3, 21.3), (86.3, 26.6), (33.0, 26.6), (24.0, 26.6), (21.0, 29.0), (21.0, 46.0), (23.4, 47.6)]),
    ("+5V", (0.8, 0.6, 0.5, 0.4, 0.3), 1.0,
     [(83.05, 8.77), (83.05, 19.4), (75.9, 19.4), (75.9, 8.7), (73.2, 8.7), (73.2, 1.0), (8.0, 1.0), (7.6, 7.2),
      (1.4, 7.2), (1.4, 19.0), (11.0, 19.9)]),
    ("-5V", (0.8, 0.6, 0.5, 0.4, 0.3), 1.0,
     [(74.45, 14.0), (56.0, 14.0), (14.0, 13.5), (9.0, 14.0), (2.5, 17.2)]),
    ("-2V5", (0.8, 0.6, 0.5, 0.4, 0.3), 1.0, None),
    ("+2V5", (0.8, 0.6, 0.5, 0.4, 0.3), 1.0, None),
    ("VBUS", (0.6, 0.5, 0.4, 0.3), 0.8, None),
]
STRIPS = [("/VTAP_P", [(90.6, 45.85), (90.6, 41.34), (29.0, 41.34), (97.5, 41.34)]),     # tap-row rails (12.5 mA
           ("/VTAP_N", [(92.45, 45.85), (92.45, 33.66), (29.0, 33.66), (97.5, 33.66)])]    # each), guided along the rows
SLOW_RESERVED = []                               # (kept for gen_board compatibility; slow lines are drawn first now)


# ============================================================================ raster helpers
def _ij(x, y):
    return int(round(x / G)), int(round(y / G))


def _win(x0, y0, x1, y1):
    i0, j0 = max(0, int(math.floor(x0 / G))), max(0, int(math.floor(y0 / G)))
    i1, j1 = min(NX - 1, int(math.ceil(x1 / G))), min(NY - 1, int(math.ceil(y1 / G)))
    return i0, j0, i1, j1


_GX, _GY = np.meshgrid(np.arange(NX) * G, np.arange(NY) * G, indexing="ij")


def draw_seg(m, a, b, r):
    i0, j0, i1, j1 = _win(min(a[0], b[0]) - r, min(a[1], b[1]) - r, max(a[0], b[0]) + r, max(a[1], b[1]) + r)
    if i0 > i1 or j0 > j1:
        return
    X, Y = _GX[i0:i1 + 1, j0:j1 + 1], _GY[i0:i1 + 1, j0:j1 + 1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        d2 = (X - a[0]) ** 2 + (Y - a[1]) ** 2
    else:
        t = np.clip(((X - a[0]) * dx + (Y - a[1]) * dy) / L2, 0, 1)
        d2 = (X - a[0] - t * dx) ** 2 + (Y - a[1] - t * dy) ** 2
    m[i0:i1 + 1, j0:j1 + 1] |= d2 <= r * r


def draw_rect(m, x0, y0, x1, y1):
    i0, j0, i1, j1 = _win(x0, y0, x1, y1)
    if i0 <= i1 and j0 <= j1:
        m[i0:i1 + 1, j0:j1 + 1] = True


def draw_poly(m, pts, grow=0.0):
    if len(pts) < 3:
        return
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    i0, j0, i1, j1 = _win(min(xs) - grow, min(ys) - grow, max(xs) + grow, max(ys) + grow)
    if i0 > i1 or j0 > j1:
        return
    X, Y = _GX[i0:i1 + 1, j0:j1 + 1], _GY[i0:i1 + 1, j0:j1 + 1]
    inside = MPath(pts).contains_points(np.c_[X.ravel(), Y.ravel()]).reshape(X.shape)
    m[i0:i1 + 1, j0:j1 + 1] |= inside
    if grow > 0:
        for a, b in zip(pts, pts[1:] + pts[:1]):
            draw_seg(m, a, b, grow)


def _loc(v):
    return pcbnew.ToMM(v.x) - OX, pcbnew.ToMM(v.y) - OY


def _poly_list(sps):
    out = []
    for k in range(sps.OutlineCount()):
        c = sps.COutline(k)
        out.append([_loc(c.CPoint(i)) for i in range(c.PointCount())])
    return out


def _pad_shape(p):
    bb = p.GetBoundingBox()
    x0, y0 = _loc(pcbnew.VECTOR2I(bb.GetX(), bb.GetY()))
    return x0, y0, x0 + pcbnew.ToMM(bb.GetWidth()), y0 + pcbnew.ToMM(bb.GetHeight())


# ============================================================================ board model
class Model:
    """rasterised copper per layer for one net's routing; rebuilt per net (cheap: < 1 s)"""

    def __init__(self, board):
        self.b = board

    def masks(self, net):
        """obstacle masks {layer: bool} for net (foreign copper + extra clearance), via-forbidden mask, own copper
        per layer {layer: bool} (L3 / L6, without SMD pads), own via / THT cells"""
        b = self.b
        obs = {ln: np.zeros((NX, NY), bool) for ln in LNAMES + ("F.Cu",)}
        novia = np.zeros((NX, NY), bool)
        own = {ln: np.zeros((NX, NY), bool) for ln in LNAMES}
        own_pad = {ln: np.zeros((NX, NY), bool) for ln in LNAMES}
        self.cutzone = np.zeros((NX, NY), bool)
        lid = {pcbnew.F_Cu: "F.Cu", pcbnew.In2_Cu: "In2.Cu", pcbnew.B_Cu: "B.Cu"}
        for t in b.GetTracks():
            n = t.GetNetname()
            if t.GetClass() == "PCB_VIA":
                c = _loc(t.GetPosition())
                r = pcbnew.ToMM(t.GetWidth()) / 2
                if n == net:
                    for ln in LNAMES:
                        draw_seg(own[ln], c, c, r)
                    ring = np.zeros((NX, NY), bool)
                    draw_seg(ring, c, c, 0.5)
                    core = np.zeros((NX, NY), bool)
                    draw_seg(core, c, c, 0.15)
                    novia |= ring & ~core           # hole-to-hole: a new via either reuses this one or keeps 0.5 mm
                else:
                    for ln in obs:
                        draw_seg(obs[ln], c, c, r + _xtra(n))
                continue
            ln = lid.get(t.GetLayer())
            if ln is None:
                continue
            a, e = _loc(t.GetStart()), _loc(t.GetEnd())
            r = pcbnew.ToMM(t.GetWidth()) / 2
            if n == net and ln in own:
                draw_seg(own[ln], a, e, max(r, 0.5 * G))
            elif n != net:
                draw_seg(obs[ln], a, e, r + _xtra(n))
        for fp in b.GetFootprints():
            for gi in fp.GraphicalItems():           # copper drawn in footprints (TL401-TL403 lines, net ties)
                if gi.GetClass() not in ("PCB_SHAPE", "FP_SHAPE", "MGRAPHIC"):
                    continue
                ln = lid.get(gi.GetLayer())
                if ln is None:
                    continue
                wv = pcbnew.ToMM(gi.GetWidth()) / 2
                try:
                    if gi.GetShape() == pcbnew.SHAPE_T_POLY:
                        for pl in _poly_list(gi.GetPolyShape()):
                            draw_poly(obs[ln], pl, wv)
                        continue
                except Exception:
                    pass
                draw_seg(obs[ln], _loc(gi.GetStart()), _loc(gi.GetEnd()), max(wv, 0.05))
            for p in fp.Pads():
                n = p.GetNetname()
                x0, y0, x1, y1 = _pad_shape(p)
                tht = p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)
                for L_, ln in lid.items():
                    if not (tht or p.IsOnLayer(L_)):
                        continue
                    if n == net and n and ln in own:
                        if tht:
                            draw_rect(own[ln], x0, y0, x1, y1)
                        else:                       # own SMD pad, shrunk by the clearance: paths may pass, not cross
                            sh = CLR + MARG
                            draw_rect(own_pad[ln], x0 + sh, y0 + sh, x1 - sh, y1 - sh)
                    elif n != net or not n:
                        draw_rect(obs[ln], x0, y0, x1, y1)
        for z in b.Zones():
            if z.GetIsRuleArea():
                for ln, L_ in (("In2.Cu", pcbnew.In2_Cu), ("B.Cu", pcbnew.B_Cu)):
                    if z.IsOnLayer(L_) and z.GetDoNotAllowTracks():
                        for pl in _poly_list(z.Outline()):
                            draw_poly(obs[ln], pl, 0.0)
                            if ln == "In2.Cu":
                                draw_poly(self.cutzone, pl, CUT_MARGIN + 0.5)
                if z.GetDoNotAllowVias() or z.GetDoNotAllowTracks():
                    for pl in _poly_list(z.Outline()):
                        draw_poly(novia, pl, 0.3)
                continue
            n = z.GetNetname()
            for ln, L_ in (("F.Cu", pcbnew.F_Cu), ("In2.Cu", pcbnew.In2_Cu), ("B.Cu", pcbnew.B_Cu)):
                if not z.IsOnLayer(L_):
                    continue
                if n == "GND" and ln != "F.Cu":
                    continue                    # GND pours yield
                if n == "GND":
                    continue
                for pl in _poly_list(z.GetFilledPolysList(L_)):
                    if n == net and ln in own:
                        draw_poly(own[ln], pl)
                    elif n != net:
                        draw_poly(obs[ln], pl)
            if n != net and z.IsOnLayer(pcbnew.In3_Cu) and n != "+3V3":
                for pl in _poly_list(z.GetFilledPolysList(pcbnew.In3_Cu)):
                    draw_poly(novia, pl, 0.3)     # no rail via through another L4 island (+1V2)
        edge = (_GX < EDGE) | (_GX > BW - EDGE) | (_GY < EDGE) | (_GY > BH - EDGE)
        for ln in obs:
            obs[ln] |= edge
        return obs, novia, own, own_pad

    def dist(self, obs):
        return {ln: ndimage.distance_transform_edt(~m) * G for ln, m in obs.items()}


# ============================================================================ own-net islands
def islands(board, net, own=None, own_pad=None):
    """the rail's copper islands: union-find over its pads, tracks, vias and filled zone pieces touching on a common
    copper layer (as boardlib.unrouted_nets).  Each island: cells {layer: mask} usable as path ends on L3 / L6
    (vias, THT pads, L3 / L6 tracks and zones), pads {layer: mask} (SMD pads on L3 / L6), names, items"""
    CU = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.In4_Cu, pcbnew.B_Cu]
    items = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == net:
                items.append(p)
    items += [t for t in board.GetTracks() if t.GetNetname() == net]
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetname() != net:
            continue
        for lay in z.GetLayerSet().CuStack():
            fl = z.GetFilledPolysList(lay)
            for i in range(fl.OutlineCount()):
                sub = pcbnew.SHAPE_POLY_SET()
                sub.AddOutline(fl.Outline(i))
                for h in range(fl.HoleCount(i)):
                    sub.AddHole(fl.Hole(i, h))
                items.append(("zone", lay, sub, sub.BBox()))
    par = list(range(len(items)))

    def f(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i

    def info(it):
        if isinstance(it, tuple):
            return {it[1]}, it[3]
        return {l_ for l_ in CU if it.IsOnLayer(l_)}, it.GetBoundingBox()
    inf = [info(it) for it in items]
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            common = inf[i][0] & inf[j][0]
            if not common or not inf[i][1].Intersects(inf[j][1]) or f(i) == f(j):
                continue
            A, C = items[i], items[j]
            if isinstance(A, tuple) and isinstance(C, tuple):
                continue
            for lay in common:
                if isinstance(A, tuple):
                    hit = C.GetEffectiveShape(lay).Collide(A[2], 0)
                elif isinstance(C, tuple):
                    hit = A.GetEffectiveShape(lay).Collide(C[2], 0)
                else:
                    hit = A.GetEffectiveShape(lay).Collide(C.GetEffectiveShape(lay), 0)
                if hit:
                    par[f(i)] = f(j)
                    break
    groups = {}
    for k in range(len(items)):
        groups.setdefault(f(k), []).append(items[k])
    out = []
    for g in groups.values():
        cells = {ln: np.zeros((NX, NY), bool) for ln in LNAMES}
        pads = {ln: np.zeros((NX, NY), bool) for ln in LNAMES}
        names = []
        for it in g:
            if isinstance(it, tuple):
                ln = {pcbnew.In2_Cu: "In2.Cu", pcbnew.B_Cu: "B.Cu"}.get(it[1])
                if ln:
                    for pl in _poly_list(it[2]):
                        draw_poly(cells[ln], pl)
                continue
            cls = it.GetClass()
            if cls == "PCB_VIA":
                c = _loc(it.GetPosition())
                for ln in LNAMES:
                    draw_seg(cells[ln], c, c, 0.12)
                names.append("via(%.2f,%.2f)" % c)
            elif cls in ("PCB_TRACK", "PCB_ARC"):
                ln = it.GetLayerName()
                if ln in cells:
                    draw_seg(cells[ln], _loc(it.GetStart()), _loc(it.GetEnd()), 0.5 * G)
            elif cls == "PAD":
                x0, y0, x1, y1 = _pad_shape(it)
                tht = it.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
                names.append(f"{it.GetParent().GetReference()}.{it.GetNumber()}")
                for ln, L_ in LAY.items():
                    if tht:
                        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                        draw_seg(cells[ln], (cx, cy), (cx, cy), 0.12)
                    elif it.IsOnLayer(L_):
                        draw_rect(pads[ln], x0 + 0.05, y0 + 0.05, x1 - 0.05, y1 - 0.05)
        vias = np.zeros((NX, NY), bool)
        for it in g:
            if not isinstance(it, tuple) and it.GetClass() == "PCB_VIA":
                c = _loc(it.GetPosition())
                draw_seg(vias, c, c, 0.12)
        out.append(dict(cells=cells, pads=pads, vias=vias, names=names,
                        items=[it for it in g if not isinstance(it, tuple)]))
    return out


# ============================================================================ router
def _guide_cost(guide):
    if not guide:
        return None
    m = np.zeros((NX, NY), bool)
    for a, b in zip(guide, guide[1:]):
        draw_seg(m, a, b, 2.5)
    return np.where(m, 1.0, 2.0)


def route_once(dist, novia, src, dst, w, gcost, win, clr=None):
    """Dijkstra on the two layers inside win; src / dst {layer: bool mask}; returns [(layer, [(x, y)...])] runs or
    None.  A cell is free for width w if its distance to foreign copper >= w/2 + CLR + MARG."""
    i0, j0, i1, j1 = win
    sx, sy = i1 - i0 + 1, j1 - j0 + 1
    N = sx * sy
    clr = CLR if clr is None else clr
    need = w / 2 + clr + MARG
    free = [dist[ln][i0:i1 + 1, j0:j1 + 1] >= need for ln in LNAMES]
    vneed = VIA_D / 2 + clr + MARG
    viaok = ((dist["In2.Cu"][i0:i1 + 1, j0:j1 + 1] >= vneed) & (dist["B.Cu"][i0:i1 + 1, j0:j1 + 1] >= vneed) &
             (dist["F.Cu"][i0:i1 + 1, j0:j1 + 1] >= vneed) & ~novia[i0:i1 + 1, j0:j1 + 1])
    S = [src[ln][i0:i1 + 1, j0:j1 + 1] & free[k] for k, ln in enumerate(LNAMES)]
    T = [dst[ln][i0:i1 + 1, j0:j1 + 1] & free[k] for k, ln in enumerate(LNAMES)]
    if not any(s.any() for s in S) or not any(t.any() for t in T):
        return None
    gc = np.ones((sx, sy)) if gcost is None else gcost[i0:i1 + 1, j0:j1 + 1]
    rows, cols, wts = [], [], []
    ids = np.arange(N).reshape(sx, sy)
    for k, fac in ((0, 1.0), (1, L6_FACTOR)):
        fr = free[k]
        for di, dj in ((1, 0), (0, 1), (1, 1), (1, -1)):
            a_sl = (slice(max(0, -di), sx - max(0, di)), slice(max(0, -dj), sy - max(0, dj)))
            b_sl = (slice(max(0, di), sx - max(0, -di) if di < 0 else sx), slice(max(0, dj), sy if dj >= 0 else sy + dj))
            b_sl = (slice(max(0, di), sx + min(0, di)), slice(max(0, dj), sy + min(0, dj)))
            ok = fr[a_sl] & fr[b_sl]
            ia, ib = ids[a_sl][ok] + k * N, ids[b_sl][ok] + k * N
            step = G * (1.4142 if di and dj else 1.0) * fac
            wv = step * 0.5 * (gc[a_sl][ok] + gc[b_sl][ok])
            rows += [ia, ib]
            cols += [ib, ia]
            wts += [wv, wv]
    vok = viaok & free[0] & free[1]
    iv = ids[vok]
    rows += [iv, iv + N]
    cols += [iv + N, iv]
    wts += [np.full(iv.size, VIA_COST), np.full(iv.size, VIA_COST)]
    sup = 2 * N
    s_ids = np.concatenate([ids[S[0]], ids[S[1]] + N])
    rows.append(np.full(s_ids.size, sup))
    cols.append(s_ids)
    wts.append(np.full(s_ids.size, 1e-6))
    gr = sparse.csr_matrix((np.concatenate(wts), (np.concatenate(rows), np.concatenate(cols))), shape=(2 * N + 1, 2 * N + 1))
    d, pred = csgraph.dijkstra(gr, directed=True, indices=sup, return_predecessors=True)
    t_ids = np.concatenate([ids[T[0]], ids[T[1]] + N])
    dt = d[t_ids]
    if not np.isfinite(dt).any():
        return None
    cur = int(t_ids[np.argmin(dt)])
    path = []
    while cur != sup and cur >= 0:
        path.append(cur)
        cur = int(pred[cur])
    path.reverse()
    runs = []
    for nid in path:
        k, c = divmod(nid, N)
        ci, cj = divmod(c, sy)
        p = (round((ci + i0) * G, 3), round((cj + j0) * G, 3))
        if not runs or runs[-1][0] != LNAMES[k]:
            runs.append((LNAMES[k], [p]))
        else:
            runs[-1][1].append(p)
    free_full = {ln: dist[ln] >= need for ln in LNAMES}
    return [(ln, simplify(free_full[ln], pts)) for ln, pts in runs], float(dt.min())


def _los(free, a, b):
    """octilinear segment a-b fully on free cells"""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if not (abs(dx) < 1e-6 or abs(dy) < 1e-6 or abs(abs(dx) - abs(dy)) < 1e-6):
        return False
    n = int(round(max(abs(dx), abs(dy)) / G))
    for k in range(n + 1):
        i, j = _ij(a[0] + dx * k / max(n, 1), a[1] + dy * k / max(n, 1))
        if not free[i, j]:
            return False
    return True


def simplify(free, pts):
    if len(pts) < 3:
        return pts
    q = [pts[0]]
    k = 0
    while k < len(pts) - 1:
        best = k + 1
        lo = min(len(pts) - 1, k + 400)
        for j in range(lo, k + 1, -1):
            if _los(free, pts[k], pts[j]):
                best = j
                break
        q.append(pts[best])
        k = best
    # drop collinear
    r = [q[0]]
    for a, b, c in zip(q, q[1:], q[2:]):
        v1, v2 = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
        if abs(v1[0] * v2[1] - v1[1] * v2[0]) > 1e-9:
            r.append(b)
    r.append(q[-1])
    return r


# ============================================================================ the rail loop
def _union(m):
    return {ln: m[ln].copy() for ln in LNAMES}


def route_rail(board, m, model, net, widths, guide, report, use_l6=True):
    added = []
    skip = set()
    for rnd in range(60):
        obs, novia, own, own_pad = model.masks(net)
        for ln in LNAMES:
            obs[ln] |= own_pad[ln]               # paths never run over the rail's own SMD pads (pad-axis rule)
        dist = model.dist(obs)
        gcost = _guide_cost(guide)
        if not net.startswith("/VTAP"):
            gcost = np.where(model.cutzone, 4.0, 1.0) * (1.0 if gcost is None else gcost)   # soft keep-off of cut-outs
        if not use_l6:
            dist["B.Cu"] = np.zeros_like(dist["B.Cu"])
        isl = islands(board, net)
        if len(isl) <= 1:
            break
        isl_all = isl
        # the tree = the island holding the regulator output (the one with the most items inside the power block)
        def score(g):
            return sum(1 for it in g["items"] if it.GetClass() in ("PCB_VIA", "PAD") and _loc(it.GetPosition())[0] > 74.0
                       and _loc(it.GetPosition())[1] < 22.6)
        isl.sort(key=lambda g: (-score(g), -len(g["items"])))
        tree = isl[0]
        padzone = {ln: ndimage.binary_dilation(np.logical_or.reduce([g["pads"][ln] for g in isl]), iterations=2)
                   & ~np.logical_or.reduce([g["vias"] for g in isl]) for ln in LNAMES}
        src = {ln: tree["cells"][ln] & ~padzone[ln] for ln in LNAMES}
        isl = [tree] + [g for g in isl[1:] if tuple(sorted(g["names"])) not in skip]
        if len(isl) <= 1:
            break
        # nearest remaining island
        tcen = np.argwhere(src["In2.Cu"] | src["B.Cu"])
        best = None
        for g in isl[1:]:
            c = np.argwhere(g["cells"]["In2.Cu"] | g["cells"]["B.Cu"])
            if c.size == 0:
                report.setdefault("no_landing", {}).setdefault(net, [])
                if g["names"][:4] not in report["no_landing"][net]:
                    report["no_landing"][net].append(g["names"][:4])
                continue
            cc = c[len(c) // 2]
            d = np.min(np.abs(tcen - cc).sum(axis=1)) if tcen.size else 0
            if best is None or d < best[0]:
                best = (d, g, cc)
        if best is None:
            report.setdefault("no_landing", {})[net] = [g["names"][:4] for g in isl[1:]]
            break
        _, g, cc = best
        dst = {ln: g["cells"][ln] & ~padzone[ln] for ln in LNAMES}
        # window: the target plus the nearest tree cells, with margin; full board on failure
        near = tcen[np.argmin(np.abs(tcen - cc).sum(axis=1))]
        res = None
        for margin in (12.0, 200.0):
            win = _win(min(near[0], cc[0]) * G - margin, min(near[1], cc[1]) * G - margin,
                       max(near[0], cc[0]) * G + margin, max(near[1], cc[1]) * G + margin)
            cands = []
            for w in widths:
                r = route_once(dist, novia, src, dst, w, gcost, win)
                if r is not None:
                    cands.append((w, r))
            if not cands:                            # tight spot: 0.3 mm at the Power class clearance 0.15 + margin
                for w in (0.4, 0.3):
                    r = route_once(dist, novia, src, dst, w, gcost, win, clr=CLR_TIGHT)
                    if r is not None:
                        cands.append((w, r))
                        report.setdefault("tight", []).append((net, w))
                        break
            if cands:
                lmin = min(c[1][1] for c in cands)
                for w, r in cands:                  # widest whose cost is within 25 % + 3 mm of the cheapest
                    if r[1] <= 1.6 * lmin + 8.0:
                        res = (w, r[0])
                        break
                break
        if res is None:
            report.setdefault("failed", {}).setdefault(net, []).append(g["names"][:4])
            skip.add(tuple(sorted(g["names"])))
            continue
        w, runs = res
        ln_e, pts_e = runs[-1]
        for it in g["items"]:
            if it.GetClass() == "PAD" and it.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and len(pts_e) >= 2:
                x0, y0, x1, y1 = _pad_shape(it)
                e = pts_e[-1]
                if x0 <= e[0] <= x1 and y0 <= e[1] <= y1:
                    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                    while len(pts_e) > 2 and x0 - 0.6 <= pts_e[-2][0] <= x1 + 0.6 and y0 - 0.6 <= pts_e[-2][1] <= y1 + 0.6:
                        del pts_e[-2]
                    q = pts_e[-2]
                    if abs(q[0] - cx) >= abs(q[1] - cy):       # approach along x from outside the pad
                        sx_ = 1 if q[0] > cx else -1
                        p1 = (round(cx + sx_ * ((x1 - x0) / 2 + 0.3), 3), cy)
                    else:
                        sy_ = 1 if q[1] > cy else -1
                        p1 = (cx, round(cy + sy_ * ((y1 - y0) / 2 + 0.3), 3))
                    pts_e[-1:] = [p1, (cx, cy)]
                    pts_e[:] = [p_ for k_, p_ in enumerate(pts_e) if k_ == 0 or p_ != pts_e[k_ - 1]]
        for k, (ln, pts) in enumerate(runs):
            if len(pts) >= 2:
                m.track(net, w, pts, ln, ch=0.15)
                added.append((ln, pts, w))
            if k < len(runs) - 1 and not any(
                    v.GetClass() == "PCB_VIA" and v.GetNetname() == net and
                    math.hypot(_loc(v.GetPosition())[0] - pts[-1][0], _loc(v.GetPosition())[1] - pts[-1][1]) < 0.2
                    for v in board.GetTracks()):
                m.via(pts[-1][0], pts[-1][1], net)
                report.setdefault("vias", {}).setdefault(net, 0)
                report["vias"][net] += 1
        zs = [z for z in board.Zones() if z.GetNetname() == net and not z.GetIsRuleArea()]
        if zs:
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    report.setdefault("added", {})[net] = added
    return added


def apply_l4_1v2(board, m, report):
    """+1V2: L4 finger from the U602 output via (75.0, 7.9) along the power block's west edge to the FPGA block's
    +1V2 L4 island (its east strip y 14.3-16.6 ends at x 74)"""
    pts = [(74.35, 7.35), (75.65, 7.35), (75.65, 8.45), (74.95, 9.15), (74.95, 13.0), (74.2, 13.75), (74.2, 15.2),
           (73.2, 15.2), (73.2, 13.4), (73.95, 12.65), (73.95, 8.45)]
    z = m.zone("+1V2", ("In3.Cu",), pts, clearance=0.25, prio=5, minw=0.25)
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    m.track("+1V2", 0.6, [(73.55, 13.9), (73.55, 14.9)], "In3.Cu")   # explicit tie into the fpga block's island
    report["+1V2"] = "L4 finger (74.0-75.6, 7.35-14.3) to the fpga +1V2 island"
    return z


def _via_layers(board, v):
    """copper layers on which via v is connected (tracks ending in it, pads / filled zones of its net under it)"""
    net = v.GetNetname()
    c = v.GetPosition()
    r = v.GetWidth() / 2
    lays = set()
    pc = _loc(c)
    for t in board.GetTracks():
        if t.GetClass() == "PCB_TRACK" and t.GetNetname() == net:
            if _pt_seg(pc, _loc(t.GetStart()), _loc(t.GetEnd())) <= pcbnew.ToMM(r + t.GetWidth() / 2) - 0.01:
                lays.add(t.GetLayer())
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == net and p.HitTest(c):
                lays |= {l_ for l_ in (pcbnew.F_Cu, pcbnew.B_Cu) if p.IsOnLayer(l_)}
    for z in board.Zones():
        if not z.GetIsRuleArea() and z.GetNetname() == net:
            for l_ in z.GetLayerSet().CuStack():
                if z.GetFilledPolysList(l_).Contains(c):
                    lays.add(l_)
    return lays


def _pt_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0 if L2 < 1e-12 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def fix_dangling(board, m, nets):
    """rail vias connected on one layer only (DRC via_dangling): joined on L3 to a sibling via within 1.2 mm that is
    connected on L3, or removed when they only join tracks on that one layer"""
    out = []
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    vias = [v for v in board.GetTracks() if v.GetClass() == "PCB_VIA" and v.GetNetname() in nets]
    for v in vias:
        L = _via_layers(board, v)
        if len(L) >= 2:
            continue
        p = _loc(v.GetPosition())
        sib = [u for u in vias if u is not v and u.GetNetname() == v.GetNetname() and
               math.hypot(_loc(u.GetPosition())[0] - p[0], _loc(u.GetPosition())[1] - p[1]) < 1.2 and
               pcbnew.In2_Cu in _via_layers(board, u)]
        if sib:
            q = _loc(sib[0].GetPosition())
            m.track(v.GetNetname(), 0.4, [p, q], "In2.Cu", ch=0.0001)
            out.append(("L3 tie", v.GetNetname(), p, q))
            continue
        trs = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetNetname() == v.GetNetname()
               and min(math.hypot(*np.subtract(_loc(t.GetStart()), p)), math.hypot(*np.subtract(_loc(t.GetEnd()), p))) < 0.2]
        thru = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetNetname() == v.GetNetname()
                and _pt_seg(p, _loc(t.GetStart()), _loc(t.GetEnd())) < 0.2 and t not in trs]
        ntr = len(trs)
        if len(L) == 1 and (ntr >= 2 or (thru and ntr == 0)):
            board.Remove(v)
            out.append(("removed", v.GetNetname(), p))
        elif len(L) == 1 and ntr == 1:
            # a stub: the via and its one track go if the track's far end is joined to something else
            t = trs[0]
            a_, b_ = _loc(t.GetStart()), _loc(t.GetEnd())
            far = b_ if math.hypot(a_[0] - p[0], a_[1] - p[1]) < math.hypot(b_[0] - p[0], b_[1] - p[1]) else a_
            others = [u for u in board.GetTracks() if u is not t and u is not v and u.GetNetname() == v.GetNetname()
                      and (u.GetClass() == "PCB_VIA" and math.hypot(*np.subtract(_loc(u.GetPosition()), far)) < 0.25
                           or u.GetClass() == "PCB_TRACK" and _pt_seg(far, _loc(u.GetStart()), _loc(u.GetEnd())) < 0.05)]
            pads = [pd for fp in board.GetFootprints() for pd in fp.Pads() if pd.GetNetname() == v.GetNetname() and
                    pd.HitTest(pcbnew.VECTOR2I(pcbnew.FromMM(far[0] + OX), pcbnew.FromMM(far[1] + OY)))]
            if others or pads:
                board.Remove(t)
                board.Remove(v)
                out.append(("stub removed", v.GetNetname(), p))
            else:
                out.append(("left", v.GetNetname(), p, len(L), ntr))
        else:
            out.append(("left", v.GetNetname(), p, len(L), ntr))
    return out


def prune_tracks(board, nets):
    """remove rail tracks on L3 / L6 with an end that touches nothing of their net (router leftovers), and tiny
    (< 0.25 mm) chamfer remnants whose both ends lie inside other copper of the net (DRC track_dangling)"""
    gone = []
    for _ in range(5):                           # tiny spurs: < 0.25 mm with one end shared by nothing (KiCad
        hit = False                              # counts only end-to-end / via / pad anchors as connections)
        for t in list(board.GetTracks()):
            if t.GetClass() != "PCB_TRACK" or t.GetNetname() not in nets or t.GetLayerName() not in LNAMES:
                continue
            a, e = _loc(t.GetStart()), _loc(t.GetEnd())
            if math.hypot(e[0] - a[0], e[1] - a[1]) >= 0.25:
                continue

            def anchored(pt):
                for u in board.GetTracks():
                    if u is t or u.GetNetname() != t.GetNetname():
                        continue
                    if u.GetClass() == "PCB_VIA":
                        if math.hypot(*np.subtract(_loc(u.GetPosition()), pt)) <= pcbnew.ToMM(u.GetWidth()) / 2:
                            return True
                    elif u.GetLayer() == t.GetLayer() and (
                            math.hypot(*np.subtract(_loc(u.GetStart()), pt)) < 0.01 or
                            math.hypot(*np.subtract(_loc(u.GetEnd()), pt)) < 0.01):
                        return True
                P_ = pcbnew.VECTOR2I(pcbnew.FromMM(pt[0] + OX), pcbnew.FromMM(pt[1] + OY))
                return any(pd.GetNetname() == t.GetNetname() and pd.IsOnLayer(t.GetLayer()) and pd.HitTest(P_)
                           for fp in board.GetFootprints() for pd in fp.Pads())
            if not (anchored(a) and anchored(e)):
                gone.append((t.GetNetname(), t.GetLayerName(), a, e, "tiny spur"))
                board.Remove(t)
                hit = True
        if not hit:
            break
    for _ in range(10):
        hit = False
        for t in list(board.GetTracks()):
            if t.GetClass() != "PCB_TRACK" or t.GetNetname() not in nets or t.GetLayerName() not in LNAMES:
                continue
            net = t.GetNetname()
            for e in (t.GetStart(), t.GetEnd()):
                pe = _loc(e)
                ok = False
                for u in board.GetTracks():
                    if u is t or u.GetNetname() != net:
                        continue
                    if u.GetClass() == "PCB_VIA":
                        ok = math.hypot(*np.subtract(_loc(u.GetPosition()), pe)) <= pcbnew.ToMM(u.GetWidth()) / 2
                    elif u.GetLayer() == t.GetLayer():
                        ok = _pt_seg(pe, _loc(u.GetStart()), _loc(u.GetEnd())) <= pcbnew.ToMM(u.GetWidth()) / 2 + 0.005
                    if ok:
                        break
                if not ok:
                    for fp in board.GetFootprints():
                        for pd in fp.Pads():
                            if pd.GetNetname() == net and pd.IsOnLayer(t.GetLayer()) and pd.HitTest(e):
                                ok = True
                if not ok:
                    for z in board.Zones():
                        if not z.GetIsRuleArea() and z.GetNetname() == net and z.IsOnLayer(t.GetLayer()) and \
                                z.GetFilledPolysList(t.GetLayer()).Contains(e):
                            ok = True
                if not ok:
                    gone.append((net, t.GetLayerName(), _loc(t.GetStart()), _loc(t.GetEnd())))
                    board.Remove(t)
                    hit = True
                    break
        if not hit:
            break
    return gone


def _proj(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0 if L2 < 1e-12 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return (a[0] + t * dx, a[1] + t * dy)


def snap_ends(board, nets):
    """a rail track end that is no anchor (no other track end, via or pad there) but lies inside another track of its
    net (a T-join onto the track body) is moved onto that track's centre line, so KiCad sees the T-junction"""
    P = lambda q: pcbnew.VECTOR2I(pcbnew.FromMM(q[0] + OX), pcbnew.FromMM(q[1] + OY))
    out = []
    trs = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetNetname() in nets]
    vias = [v for v in board.GetTracks() if v.GetClass() == "PCB_VIA" and v.GetNetname() in nets]
    for t in trs:
        for k, e in ((0, _loc(t.GetStart())), (1, _loc(t.GetEnd()))):
            same = [u for u in trs if u is not t and u.GetNetname() == t.GetNetname() and u.GetLayer() == t.GetLayer()]
            if any(math.hypot(*np.subtract(_loc(u.GetStart()), e)) < 0.005 or
                   math.hypot(*np.subtract(_loc(u.GetEnd()), e)) < 0.005 for u in same):
                continue
            if any(v.GetNetname() == t.GetNetname() and math.hypot(*np.subtract(_loc(v.GetPosition()), e)) < 0.005
                   for v in vias):
                continue
            if any(pd.GetNetname() == t.GetNetname() and pd.IsOnLayer(t.GetLayer()) and pd.HitTest(P(e))
                   for fp in board.GetFootprints() for pd in fp.Pads()):
                continue
            if any(v.GetNetname() == t.GetNetname() and
                   math.hypot(*np.subtract(_loc(v.GetPosition()), e)) < pcbnew.ToMM(v.GetWidth()) / 2 for v in vias):
                continue                         # inside a via: connected as it is
            hosts = [u for u in same if _pt_seg(e, _loc(u.GetStart()), _loc(u.GetEnd())) <
                     pcbnew.ToMM(u.GetWidth()) / 2]
            if not hosts:
                continue
            q = _proj(e, _loc(hosts[0].GetStart()), _loc(hosts[0].GetEnd()))
            (t.SetStart if k == 0 else t.SetEnd)(P(q))
            out.append((t.GetNetname(), tuple(round(v, 3) for v in e), tuple(round(v, 3) for v in q)))
    return out


def fix_corners(board, nets, c=0.15):
    """degree-2 joints of rail tracks sharper than 45 deg (where two routes meet): a 45-degree chamfer of leg c"""
    from collections import defaultdict
    P = lambda q: pcbnew.VECTOR2I(pcbnew.FromMM(q[0] + OX), pcbnew.FromMM(q[1] + OY))
    out = []
    for _ in range(3):
        ends = defaultdict(list)
        for t in board.GetTracks():
            if t.GetClass() == "PCB_TRACK" and t.GetNetname() in nets:
                for k, e in ((0, t.GetStart()), (1, t.GetEnd())):
                    ends[(t.GetNetname(), t.GetLayer(), e.x, e.y)].append((t, k))
        done = 0
        for (net, lay, x, y), lst in ends.items():
            if len(lst) != 2:
                continue
            (t1, k1), (t2, k2) = lst
            j = _loc(pcbnew.VECTOR2I(x, y))
            if any(pd.GetNetname() == net and pd.IsOnLayer(lay) and pd.HitTest(pcbnew.VECTOR2I(x, y))
                   for fp in board.GetFootprints() for pd in fp.Pads()):
                continue                         # joints inside a pad are the pad's business
            o1 = _loc(t1.GetEnd() if k1 == 0 else t1.GetStart())
            o2 = _loc(t2.GetEnd() if k2 == 0 else t2.GetStart())
            l1, l2 = math.hypot(o1[0] - j[0], o1[1] - j[1]), math.hypot(o2[0] - j[0], o2[1] - j[1])
            if l1 < 1e-6 or l2 < 1e-6:
                continue
            v1 = ((j[0] - o1[0]) / l1, (j[1] - o1[1]) / l1)
            v2 = ((o2[0] - j[0]) / l2, (o2[1] - j[1]) / l2)
            ang = math.degrees(math.acos(max(-1, min(1, v1[0] * v2[0] + v1[1] * v2[1]))))
            if ang <= 45.5:
                continue
            cc = min(c, l1 / 2.01, l2 / 2.01)
            a_ = (j[0] - v1[0] * cc, j[1] - v1[1] * cc)
            b_ = (j[0] + v2[0] * cc, j[1] + v2[1] * cc)
            (t1.SetStart if k1 == 0 else t1.SetEnd)(P(a_))
            (t2.SetStart if k2 == 0 else t2.SetEnd)(P(b_))
            nt = pcbnew.PCB_TRACK(board)
            nt.SetStart(P(a_))
            nt.SetEnd(P(b_))
            nt.SetWidth(min(t1.GetWidth(), t2.GetWidth()))
            nt.SetLayer(lay)
            nt.SetNet(t1.GetNet())
            board.Add(nt)
            out.append((net, tuple(round(v, 2) for v in j), round(ang)))
            done += 1
        if not done:
            break
    return out


def apply(board, m):
    """route every rail; returns a report dict"""
    report = {}
    apply_l4_1v2(board, m, report)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    model = Model(board)
    for net, widths, wmax, guide in RAILS:
        route_rail(board, m, model, net, widths, guide, report)
    for net, guide in STRIPS:
        route_rail(board, m, model, net, (0.6, 0.5, 0.4, 0.3), guide, report)
    report["dangling"] = fix_dangling(board, m, [r[0] for r in RAILS] + [r[0] for r in STRIPS])
    report["dangling"] += fix_dangling(board, m, [r[0] for r in RAILS] + [r[0] for r in STRIPS])
    report["pruned"] = prune_tracks(board, [r[0] for r in RAILS] + [r[0] for r in STRIPS])
    rails_ = [r[0] for r in RAILS] + [r[0] for r in STRIPS]
    report["snapped"] = []
    for _ in range(3):                           # snap T-joins onto the host centre line, drop zero-length remnants
        report["snapped"] += snap_ends(board, rails_)
        for t in list(board.GetTracks()):
            if t.GetClass() == "PCB_TRACK" and t.GetNetname() in rails_ and t.GetLength() < pcbnew.FromMM(0.005):
                board.Remove(t)
    report["corners"] = fix_corners(board, [r[0] for r in RAILS] + [r[0] for r in STRIPS])
    return report


# ============================================================================ widen
_FOREIGN = {}
POWER_CLASS = ("+3V3", "+5V", "-5V", "+2V5", "-2V5", "+1V2", "VBUS", "/+5V1")   # board_finish.write_pro Power netclass


def _seg_seg(p1, p2, q1, q2):
    """minimum distance between two segments (mm)"""
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    d1, d2 = cross(q1, q2, p1), cross(q1, q2, p2)
    d3, d4 = cross(p1, p2, q1), cross(p1, p2, q2)
    if d1 * d2 < 0 and d3 * d4 < 0:
        return 0.0
    return min(_pt_seg(p1, q1, q2), _pt_seg(p2, q1, q2), _pt_seg(q1, p1, p2), _pt_seg(q2, p1, p2))


def _foreign(t, a, e):
    """edge distances (centre line of t to the copper edge) of foreign vias / same-layer tracks near t"""
    b = t.GetBoard()
    if id(b) not in _FOREIGN:
        _FOREIGN.clear()
        _FOREIGN[id(b)] = [(x.GetNetname(), x.GetLayer(), x.GetClass() == "PCB_VIA", _loc(x.GetStart()), _loc(x.GetEnd()),
                            pcbnew.ToMM(x.GetWidth()) / 2) for x in b.GetTracks()]
    x0, x1 = min(a[0], e[0]) - 2.5, max(a[0], e[0]) + 2.5
    y0, y1 = min(a[1], e[1]) - 2.5, max(a[1], e[1]) + 2.5
    out = []
    for net, lay, isv, s_, e_, r in _FOREIGN[id(b)]:
        if net == t.GetNetname() or not (x0 < s_[0] < x1 and y0 < s_[1] < y1):
            continue
        if not isv and lay != t.GetLayer():
            continue
        out.append((_seg_seg(a, e, s_, e_) - r, net))
    return out


def widen(board, m, nets=None, step=0.1):
    """fatten every L3 / L6 rail segment to the widest width (<= the rail's WMAX) that keeps CLR to foreign copper"""
    wmax = {n: wm for n, _, wm, _ in RAILS}
    wmax.update({n: 0.8 for n, _ in STRIPS})
    nets = nets or list(wmax)
    model = Model(board)
    out = {}
    for net in nets:
        obs, novia, own, own_pad = model.masks(net)
        dist = model.dist(obs)
        tot = 0.0
        for t in board.GetTracks():
            if t.GetClass() != "PCB_TRACK" or t.GetNetname() != net or t.GetLayerName() not in LNAMES:
                continue
            a, e = _loc(t.GetStart()), _loc(t.GetEnd())
            L = math.hypot(e[0] - a[0], e[1] - a[1])
            n = max(1, int(L / (G / 2)))
            dmin = min(dist[t.GetLayerName()][_ij(a[0] + (e[0] - a[0]) * k / n, a[1] + (e[1] - a[1]) * k / n)]
                       for k in range(n + 1))
            w0 = pcbnew.ToMM(t.GetWidth())
            wfit = math.floor(((dmin - CLR - MARG) * 2) / step + 1e-6) * step
            # REPAIR (24 Nov): exact check against foreign vias / same-layer tracks (the raster missed a /+5V1
            # interface via next to a +2V5 T-join that snap_ends had moved after routing)
            wex = min([math.floor(((q - (0.155 if (net in POWER_CLASS or fn in POWER_CLASS) else 0.105)) * 2) / 0.05
                                  + 1e-6) * 0.05 for q, fn in _foreign(t, a, e)] + [9.0])
            wfit = min(wfit, wex)
            if w0 > wex + 1e-6 and wex >= 0.3:   # routed too wide for an exact neighbour: shrink (netclass gap + 5 um)
                t.SetWidth(pcbnew.FromMM(round(wex, 3)))
                out.setdefault("shrunk", []).append((net, tuple(round(v, 2) for v in a), round(w0, 2), round(wex, 2)))
                continue
            wnew = min(wmax[net], wfit)
            if wnew > w0 + 1e-6:
                t.SetWidth(pcbnew.FromMM(round(wnew, 3)))
                tot += L
        out[net] = round(tot, 1)
    return out


# ============================================================================ verify / report
def verify(board):
    board.BuildConnectivity()
    res = {"unconnected": board.GetConnectivity().GetUnconnectedCount(True)}
    per = {}
    for net, *_ in RAILS + [(n, None, None, None) for n, _ in STRIPS]:
        segs = [(t.GetLayerName(), pcbnew.ToMM(t.GetWidth()),
                 math.hypot(*(np.subtract(_loc(t.GetEnd()), _loc(t.GetStart())))), t)
                for t in board.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetNetname() == net and
                t.GetLayerName() in LNAMES]
        if not segs:
            per[net] = None
            continue
        wmin = min(s[1] for s in segs)
        narrow = [s for s in segs if abs(s[1] - wmin) < 1e-6]
        hist = {}
        for ln, w, L, _ in segs:
            hist.setdefault((ln, round(w, 2)), 0.0)
            hist[(ln, round(w, 2))] += L
        t = narrow[0][3]
        per[net] = dict(total={ln: round(sum(L for l2, _, L, _ in segs if l2 == ln), 1) for ln in LNAMES},
                        wmin=round(wmin, 2), at_wmin=round(sum(s[2] for s in narrow), 1),
                        where=tuple(round(v, 1) for v in _loc(t.GetStart())),
                        hist={f"{k[0][:3]} {k[1]}": round(v, 1) for k, v in sorted(hist.items())},
                        vias=sum(1 for v in board.GetTracks() if v.GetClass() == "PCB_VIA" and v.GetNetname() == net))
    res["rails"] = per
    return res


def table(res):
    lines = [f"unconnected (pcbnew): {res['unconnected']}",
             "rail | L3 mm | L6 mm | narrowest | mm at narrowest | e.g. at | vias | width histogram"]
    for net, r in res["rails"].items():
        if r is None:
            lines.append(f"{net} | - |")
            continue
        lines.append(f"{net} | {r['total']['In2.Cu']} | {r['total']['B.Cu']} | {r['wmin']} | {r['at_wmin']} | "
                     f"{r['where']} | {r['vias']} | {r['hist']}")
    return "\n".join(lines)
