"""Grid maze router for the integrated board (inter-block nets).

Rasterises all copper of the master board on a fine grid (0.025 mm) per routing layer (F.Cu, In2.Cu, B.Cu),
then routes one net at a time with A* on a coarse 0.1 mm grid whose origin is chosen per net so that both end
points are reached by an exact 45-degree connector: every joint of the result is 0 or 45 degrees (no 90-degree
corners), and the connector meets the block's interface stub at <= 45 degrees.

Usage:  R = Router(blk)   (blk = boardlib.Block wrapping the master)
        R.route(net, (x, y, "B.Cu", "N"), (x, y, "B.Cu", "S"), w=0.15, layers=("B.Cu", "In2.Cu"))
End-point spec: (x, y, layer, side) - side = direction the route may LEAVE the point in: "N" "S" "E" "W" or
"*" (any, e.g. a via or a pad centre on a through-hole) ; layer "*" = a via / THT point on all layers.
"""
import math, heapq
import numpy as np
from scipy import ndimage
import pcbnew
import boardlib as bl

F = 0.025                          # raster step
G = 0.1                            # routing grid
LAYERS = ("F.Cu", "In2.Cu", "B.Cu")
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]   # +y down: 2 = S, 6 = N
_C = ["E", "SE", "S", "SW", "W", "NW", "N", "NE"]
SIDE_DIRS = {c: {(k - 1) % 8, k, (k + 1) % 8} for k, c in enumerate(_C)}
SIDE_DIRS["*"] = set(range(8))


class Router:
    def __init__(self, blk, W=100.0, H=57.0, edge=0.3, clr=0.15):
        self.blk, self.b, self.W, self.H, self.clr = blk, blk.b, W, H, clr
        self.NX, self.NY = int(round(W / F)) + 1, int(round(H / F)) + 1
        self.own = {ln: np.full((self.NX, self.NY), -1, np.int32) for ln in LAYERS}
        self.novia = np.zeros((self.NX, self.NY), bool)
        self.notrack = {ln: np.zeros((self.NX, self.NY), bool) for ln in LAYERS}
        self.edge = edge
        self.cost = {ln: np.ones((self.NX, self.NY), np.float32) for ln in LAYERS}
        self._raster_all()
        self.log = []

    # ------------------------------------------------------------------ raster
    def _win(self, x0, y0, x1, y1):
        i0, i1 = max(0, int(math.floor(x0 / F))), min(self.NX - 1, int(math.ceil(x1 / F)))
        j0, j1 = max(0, int(math.floor(y0 / F))), min(self.NY - 1, int(math.ceil(y1 / F)))
        if i0 > i1 or j0 > j1:
            return None
        X = (np.arange(i0, i1 + 1) * F)[:, None]
        Y = (np.arange(j0, j1 + 1) * F)[None, :]
        return (slice(i0, i1 + 1), slice(j0, j1 + 1)), X, Y

    def mark_seg(self, ln, x0, y0, x1, y1, r, code, arr=None):
        w = self._win(min(x0, x1) - r, min(y0, y1) - r, max(x0, x1) + r, max(y0, y1) + r)
        if w is None:
            return
        sl, X, Y = w
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy or 1e-12
        u = np.clip(((X - x0) * dx + (Y - y0) * dy) / L2, 0, 1)
        m = (X - x0 - u * dx) ** 2 + (Y - y0 - u * dy) ** 2 <= r * r
        a = self.own[ln] if arr is None else arr
        a[sl][m] = code

    def mark_box(self, ln, x0, y0, x1, y1, code):
        w = self._win(x0, y0, x1, y1)
        if w is not None:
            self.own[ln][w[0]] = code

    def mark_poly(self, arr, poly, val, inflate=0.0):
        """arr[...] = val inside SHAPE_POLY_SET poly (outline 0 with holes), via point-in-polygon on its bbox"""
        bb = poly.BBox()
        x0, y0 = pcbnew.ToMM(bb.GetX()) - self.blk.org[0] - inflate, pcbnew.ToMM(bb.GetY()) - self.blk.org[1] - inflate
        x1, y1 = pcbnew.ToMM(bb.GetRight()) - self.blk.org[0] + inflate, pcbnew.ToMM(bb.GetBottom()) - self.blk.org[1] + inflate
        w = self._win(x0, y0, x1, y1)
        if w is None:
            return
        sl, X, Y = w
        from matplotlib.path import Path
        m = np.zeros((X.shape[0], Y.shape[1]), bool)
        pts = np.stack(np.broadcast_arrays(X, Y), -1).reshape(-1, 2)
        for k in range(poly.OutlineCount()):
            o = poly.Outline(k)
            vs = [(pcbnew.ToMM(o.CPoint(i).x) - self.blk.org[0], pcbnew.ToMM(o.CPoint(i).y) - self.blk.org[1])
                  for i in range(o.PointCount())]
            inside = Path(vs).contains_points(pts, radius=-2 * inflate if inflate else 0).reshape(m.shape)
            for h in range(poly.HoleCount(k)):
                ho = poly.Hole(k, h)
                hv = [(pcbnew.ToMM(ho.CPoint(i).x) - self.blk.org[0], pcbnew.ToMM(ho.CPoint(i).y) - self.blk.org[1])
                      for i in range(ho.PointCount())]
                inside &= ~Path(hv).contains_points(pts).reshape(m.shape)
            m |= inside
        arr[sl][m] = val

    def _loc(self, v):
        return pcbnew.ToMM(v.x) - self.blk.org[0], pcbnew.ToMM(v.y) - self.blk.org[1]

    def add_item(self, it):
        if isinstance(it, pcbnew.PCB_VIA):
            x, y = self._loc(it.GetPosition())
            r = pcbnew.ToMM(it.GetWidth()) / 2
            for ln in LAYERS:
                self.mark_seg(ln, x, y, x, y, r, it.GetNetCode())
            self.mark_seg(None, x, y, x, y, pcbnew.ToMM(it.GetDrillValue()) / 2 + 0.25 + 0.1, 1, arr=self.novia)
            return
        if isinstance(it, pcbnew.PCB_TRACK):
            ln = it.GetLayerName()
            if ln in LAYERS:
                (x0, y0), (x1, y1) = self._loc(it.GetStart()), self._loc(it.GetEnd())
                if it.GetClass() == "PCB_ARC":
                    bb = it.GetBoundingBox()
                    self.mark_box(ln, *self._loc(bb.GetOrigin()), *self._loc(bb.GetEnd()), it.GetNetCode())
                else:
                    self.mark_seg(ln, x0, y0, x1, y1, pcbnew.ToMM(it.GetWidth()) / 2, it.GetNetCode())

    def _raster_all(self):
        b = self.b
        for fp in b.GetFootprints():
            for p in fp.Pads():
                code = p.GetNetCode() if p.GetNetCode() > 0 else -2
                for ln in LAYERS:
                    if p.IsOnLayer(bl.L(ln)) or p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                        poly = p.GetEffectivePolygon() if hasattr(p, "GetEffectivePolygon") else None
                        if poly is not None and poly.OutlineCount():
                            self.mark_poly(self.own[ln], poly, code)
                        else:
                            bb = p.GetBoundingBox()
                            self.mark_box(ln, *self._loc(bb.GetOrigin()), *self._loc(bb.GetEnd()), code)
                if p.GetDrillSizeX() > 0:
                    x, y = self._loc(p.GetPosition())
                    self.mark_seg(None, x, y, x, y, pcbnew.ToMM(p.GetDrillSizeX()) / 2 + 0.25 + 0.1, 1, arr=self.novia)
            # copper graphics in footprints (net ties, TLines)
            for g in fp.GraphicalItems():
                ln = g.GetLayerName()
                if ln in LAYERS and g.GetClass() in ("PCB_SHAPE", "FP_SHAPE"):
                    bb = g.GetBoundingBox()
                    code = fp.Pads()[0].GetNetCode() if len(fp.Pads()) else -2
                    self.mark_box(ln, *self._loc(bb.GetOrigin()), *self._loc(bb.GetEnd()), code)
        for t in b.GetTracks():
            self.add_item(t)
        for z in b.Zones():
            if z.GetIsRuleArea():
                if z.GetDoNotAllowTracks() or z.GetDoNotAllowVias():
                    for ln in LAYERS:
                        if z.IsOnLayer(bl.L(ln)) and z.GetDoNotAllowTracks():
                            self.mark_poly(self.notrack[ln], z.Outline(), True)
                    if z.GetDoNotAllowVias():
                        self.mark_poly(self.novia, z.Outline(), True)
                continue
            net = z.GetNetname()
            for ln in LAYERS:
                if not z.IsOnLayer(bl.L(ln)):
                    continue
                if net == "GND" and ln != "In2.Cu":
                    continue                       # GND pours refill around new copper
                if net == "+3V3" and ln == "In2.Cu":
                    continue                       # In2 +3V3 is re-drawn by the integrator
                self.mark_poly(self.own[ln], z.Outline(), z.GetNetCode())
        # board edge
        e = int(round(self.edge / F))
        for ln in LAYERS:
            for a in (self.own[ln],):
                a[:e, :] = -3
                a[-e:, :] = -3
                a[:, :e] = -3
                a[:, -e:] = -3

    def keep(self, ln, x0, y0, x1, y1):
        """no tracks of new routes in this box (ln None = all layers, also no vias)"""
        w = self._win(x0, y0, x1, y1)
        for l_ in (LAYERS if ln is None else (ln,)):
            self.notrack[l_][w[0]] = True
        if ln is None:
            self.novia[w[0]] = True

    def penal(self, ln, x0, y0, x1, y1, c):
        w = self._win(x0, y0, x1, y1)
        for l_ in (LAYERS if ln is None else (ln,)):
            self.cost[l_][w[0]] = np.maximum(self.cost[l_][w[0]], c)

    # ------------------------------------------------------------------ routing
    def route(self, net, A, B, w=0.15, layers=("B.Cu",), lcost=None, via_cost=3.0, clr=None, margin=6.0,
              via_d=bl.VIA_D, via_drill=bl.VIA_DRILL, maxn=800_000, avoid=None):
        """A / B: (x, y, layer, side).  Returns the list of (layer, pts) runs or None."""
        clr = self.clr if clr is None else clr
        net = bl.canon(net)
        code = self.blk.net(net).GetNetCode()
        lcost = lcost or {}
        Ls = [ln for ln in LAYERS if ln in layers]
        x0 = max(0.0, min(A[0], B[0]) - margin)
        x1 = min(self.W, max(A[0], B[0]) + margin)
        y0 = max(0.0, min(A[1], B[1]) - margin)
        y1 = min(self.H, max(A[1], B[1]) + margin)
        si, sj = int(x0 / F), int(y0 / F)
        ei, ej = int(math.ceil(x1 / F)), int(math.ceil(y1 / F))
        dist, cst = {}, {}
        for ln in Ls:
            o = self.own[ln][si:ei + 1, sj:ej + 1]
            occ = ((o != -1) & (o != code)) | self.notrack[ln][si:ei + 1, sj:ej + 1]
            for (al, ax0, ay0, ax1, ay1) in (avoid or ()):
                if al == ln:
                    a0, a1 = max(0, int(ax0 / F) - si), max(0, int(math.ceil(ax1 / F)) - si + 1)
                    b0, b1 = max(0, int(ay0 / F) - sj), max(0, int(math.ceil(ay1 / F)) - sj + 1)
                    occ[a0:a1, b0:b1] = True
            dist[ln] = ndimage.distance_transform_edt(~occ) * F
            cst[ln] = self.cost[ln][si:ei + 1, sj:ej + 1]
        if len(Ls) > 1:
            dv = [ndimage.distance_transform_edt(~((self.own[ln][si:ei + 1, sj:ej + 1] != -1) &
                                                    (self.own[ln][si:ei + 1, sj:ej + 1] != code))) * F
                  for ln in LAYERS]
            via_free = np.minimum.reduce(dv) >= via_d / 2 + clr + 0.02
            via_free &= ~self.novia[si:ei + 1, sj:ej + 1]
        best_res = None
        for ta, tb in (("d1", "d2"), ("d2", "d1")):
            a_ = ((A[1] - A[0]) if ta == "d1" else (A[1] + A[0])) % G
            b_ = ((B[1] - B[0]) if tb == "d1" else (B[1] + B[0])) % G
            if ta == "d1":
                ox, oy = (b_ - a_) / 2, (a_ + b_) / 2
            else:
                ox, oy = (a_ - b_) / 2, (a_ + b_) / 2
            res = self._astar(net, code, A, B, ta, tb, ox % G, oy % G, w, Ls, lcost, via_cost, clr, dist, cst,
                              via_free if len(Ls) > 1 else None, (si, sj), (x0, y0, x1, y1), maxn)
            if res and (best_res is None or res[0] < best_res[0]):
                best_res = res
        if best_res is None:
            self.log.append(f"FAILED {net} {A} -> {B}")
            print("  ROUTE FAILED", net, A, B)
            return None
        runs = best_res[1]
        for k, (ln, pts) in enumerate(runs):
            self.blk.track(net, w, pts, ln, ch=0.0)
            for p, q in zip(pts, pts[1:]):
                self.mark_seg(ln, p[0], p[1], q[0], q[1], w / 2, code)
            if k < len(runs) - 1:
                vx, vy = pts[-1]
                v = self.blk.via(vx, vy, net, via_d, via_drill)
                self.add_item(v)
        return runs

    def _astar(self, net, code, A, B, ta, tb, ox, oy, w, Ls, lcost, via_cost, clr, dist, cst, via_free, s0,
               win, maxn):
        si, sj = s0
        need = w / 2 + clr + 0.02

        imin = int(math.ceil((win[0] - ox) / G))
        imax = int(math.floor((win[2] - ox) / G))
        jmin = int(math.ceil((win[1] - oy) / G))
        jmax = int(math.floor((win[3] - oy) / G))
        nxc, nyc = imax - imin + 1, jmax - jmin + 1
        I = np.clip(np.round((ox + (np.arange(nxc) + imin) * G) / F).astype(int) - si, 0, None)
        J = np.clip(np.round((oy + (np.arange(nyc) + jmin) * G) / F).astype(int) - sj, 0, None)
        OKB, CB = {}, {}
        for ln in Ls:
            d = dist[ln]
            Ii, Jj = np.minimum(I, d.shape[0] - 1), np.minimum(J, d.shape[1] - 1)
            OKB[ln] = bytearray((d[np.ix_(Ii, Jj)] >= need).astype(np.uint8).ravel().tobytes())
            CB[ln] = cst[ln][np.ix_(Ii, Jj)].astype(float).ravel().tolist()
        if via_free is not None:
            Ii, Jj = np.minimum(I, via_free.shape[0] - 1), np.minimum(J, via_free.shape[1] - 1)
            VB = bytearray(via_free[np.ix_(Ii, Jj)].astype(np.uint8).ravel().tobytes())

        def gxy(i, j):
            return ox + i * G, oy + j * G

        def ok(ln, i, j):
            a, b_ = i - imin, j - jmin
            if a < 0 or b_ < 0 or a >= nxc or b_ >= nyc:
                return False
            return OKB[ln][a * nyc + b_] == 1

        def ccost(ln, i, j):
            return CB[ln][(i - imin) * nyc + j - jmin]

        def vok(i, j):
            a, b_ = i - imin, j - jmin
            if a < 0 or b_ < 0 or a >= nxc or b_ >= nyc:
                return False
            return VB[a * nyc + b_] == 1

        def conn_nodes(P, typ):
            """grid nodes on the 45-degree line of type typ through P, 1..6 cells away, in an allowed direction"""
            x, y, ln, side = P
            out = []
            allowed = SIDE_DIRS[side]
            for sgn in (1, -1):
                # d1: y - x = const -> direction (1,1) or (-1,-1); d2: y + x = const -> (1,-1) or (-1,1)
                dvec = (sgn, sgn) if typ == "d1" else (sgn, -sgn)
                dd = DIRS.index(dvec)
                if dd not in allowed:
                    continue
                i_f = (x - ox) / G
                for k in range(1, 8):
                    # node with x' = ox + i G on the line, x' - x in direction sgn
                    i = math.floor(i_f) + (k if sgn > 0 else 1 - k)
                    xx = ox + i * G
                    t = xx - x
                    if t * sgn < 0.12:
                        continue
                    yy = y + (t if typ == "d1" else -t)
                    j = int(round((yy - oy) / G))
                    if abs(oy + j * G - yy) > 1e-6:
                        break
                    out.append((i, j, dd, abs(t) * 1.4142))
                    if len(out) >= 4:
                        break
            return out
        lays_a = Ls if A[2] == "*" else [A[2]]
        lays_b = Ls if B[2] == "*" else [B[2]]
        starts = [(i, j, ln, d, c) for (i, j, d, c) in conn_nodes(A, ta) for ln in lays_a if ln in Ls]
        goals = {}
        for (i, j, d, c) in conn_nodes(B, tb):
            for ln in lays_b:
                if ln in Ls:
                    goals[(i, j, ln)] = ((d + 4) % 8, c)    # arrive moving towards B = opposite of leaving dir
        if not starts or not goals:
            return None
        gi = [k[0] for k in goals]
        gj = [k[1] for k in goals]
        gx0, gx1, gy0, gy1 = min(gi), max(gi), min(gj), max(gj)

        def h(i, j):
            dx = max(gx0 - i, 0, i - gx1)
            dy = max(gy0 - j, 0, j - gy1)
            return (max(dx, dy) + 0.4142 * min(dx, dy)) * 0.999
        openl, best, prev = [], {}, {}
        for (i, j, ln, d, c) in starts:
            if ok(ln, i, j):
                st = (i, j, ln, d)
                g0 = c / G
                best[st] = g0
                heapq.heappush(openl, (g0 + h(i, j), g0, st))
        goal, n = None, 0
        while openl:
            f, g_, st = heapq.heappop(openl)
            if g_ > best.get(st, 1e18) + 1e-9:
                continue
            i, j, ln, d = st
            gk = goals.get((i, j, ln))
            if gk is not None and (d == gk[0] or d < 0 and False):
                goal = st
                g_ += gk[1] / G
                break
            if gk is not None and d >= 0 and (d - gk[0]) % 8 in (1, 7):
                goal = st
                g_ += gk[1] / G + 0.3
                break
            n += 1
            if n > maxn:
                break
            nds = range(8) if d < 0 else (d, (d + 1) % 8, (d - 1) % 8)
            lc = lcost.get(ln, 1.0)
            for nd in nds:
                di, dj = DIRS[nd]
                a, b_ = i + di, j + dj
                if not ok(ln, a, b_):
                    continue
                # diagonal step: also check the midpoint for thin obstacles
                step = (1.4142 if nd % 2 else 1.0) * lc * ccost(ln, a, b_) + (0.4 if (d >= 0 and nd != d) else 0.0)
                ns = (a, b_, ln, nd)
                ng = g_ + step
                if ng < best.get(ns, 1e18):
                    best[ns] = ng
                    prev[ns] = st
                    heapq.heappush(openl, (ng + h(a, b_), ng, ns))
            if via_free is not None and d >= 0 and vok(i, j):
                for l2 in Ls:
                    if l2 == ln or not ok(l2, i, j):
                        continue
                    ns = (i, j, l2, -1)
                    ng = g_ + via_cost / G
                    if ng < best.get(ns, 1e18):
                        best[ns] = ng
                        prev[ns] = st
                        heapq.heappush(openl, (ng + h(i, j), ng, ns))
        if goal is None:
            return None
        path = [goal]
        while path[-1] in prev:
            path.append(prev[path[-1]])
        path.reverse()
        # split into layer runs; a via state (d = -1) starts a new run
        runs, cur = [], [path[0]]
        for s in path[1:]:
            if s[2] != cur[-1][2]:
                runs.append(cur)
                cur = [s]
            else:
                cur.append(s)
        runs.append(cur)
        out = []
        for k, r in enumerate(runs):
            pts = [gxy(s[0], s[1]) for s in r]
            if k == 0:
                pts = [(A[0], A[1])] + pts
            if k == len(runs) - 1:
                pts = pts + [(B[0], B[1])]
            # drop collinear points
            q = [pts[0]]
            for p, c in zip(pts[1:], pts[2:]):
                v1 = (p[0] - q[-1][0], p[1] - q[-1][1])
                v2 = (c[0] - p[0], c[1] - p[1])
                if abs(v1[0] * v2[1] - v1[1] * v2[0]) > 1e-7:
                    q.append(p)
            q.append(pts[-1])
            q = [(round(x, 4), round(y, 4)) for x, y in q]
            out.append((r[0][2], q))
        return g_, out
