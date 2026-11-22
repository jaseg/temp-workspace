"""GND stitching for the scope-fe board (gen_board.py step 5).

stitch(B, m, rf_tracks, sig_vias) places through GND vias (0.45 / 0.2) only where a raster of ALL copper on all six
layers (tracks, vias, pads of every net incl. GND pads: no via-in-pad), all rule areas (node windows, RF pour gaps,
keep-outs), the mounting-hole keep-outs and the board edge leaves room:
  1. a ground via beside every inter-block signal via (sig_vias: [(x, y)]), tried on a ring 0.75-1.1 mm away,
  2. fences along the L1 RF lines (rf_tracks: [((x0, y0), (x1, y1), w)]) at 1.5 mm pitch, 2 w + 0.35 mm off the edge,
  3. a 2.5 mm grid elsewhere.
Returns counts per class.  No via lands on stub copper (TL401-403 are footprints: their copper is in the raster).
"""
import math
import numpy as np
import pcbnew

G = 0.05                       # raster (mm)
VR = 0.225                     # via radius
CLR = 0.2                      # copper clearance used for stitching (> the 0.1 rule)
HOLES = ((3, 3), (97, 3), (3, 54), (97, 54))
W, H = 100.0, 57.0
ORG = 100.0


def _mm(v):
    return pcbnew.ToMM(v) - ORG


def build_mask(B):
    nx, ny = int(W / G) + 1, int(H / G) + 1
    occ = np.zeros((nx, ny), bool)
    xs = np.arange(nx) * G
    ys = np.arange(ny) * G

    def disk(x, y, r):
        i0, i1 = max(0, int((x - r) / G)), min(nx - 1, int((x + r) / G) + 1)
        j0, j1 = max(0, int((y - r) / G)), min(ny - 1, int((y + r) / G) + 1)
        if i0 > i1 or j0 > j1:
            return
        X, Y = np.meshgrid(xs[i0:i1 + 1], ys[j0:j1 + 1], indexing="ij")
        occ[i0:i1 + 1, j0:j1 + 1] |= (X - x) ** 2 + (Y - y) ** 2 <= r * r

    def seg(x0, y0, x1, y1, r):
        L = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(L / (G * 2)))
        for k in range(n + 1):
            disk(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n, r)

    pad_r = VR + CLR
    for t in B.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            p = t.GetPosition()
            disk(_mm(p.x), _mm(p.y), pcbnew.ToMM(t.GetWidth()) / 2 + pad_r + 0.05)   # also hole-to-hole
        else:
            if t.GetNetname() == "GND":
                continue
            a, b = t.GetStart(), t.GetEnd()
            seg(_mm(a.x), _mm(a.y), _mm(b.x), _mm(b.y), pcbnew.ToMM(t.GetWidth()) / 2 + pad_r)
    for f in B.GetFootprints():
        for p in f.Pads():
            bb = p.GetBoundingBox()
            x0, y0, x1, y1 = _mm(bb.GetX()), _mm(bb.GetY()), _mm(bb.GetRight()), _mm(bb.GetBottom())
            i0, i1 = max(0, int((x0 - pad_r) / G)), min(nx - 1, int((x1 + pad_r) / G) + 1)
            j0, j1 = max(0, int((y0 - pad_r) / G)), min(ny - 1, int((y1 + pad_r) / G) + 1)
            occ[i0:i1 + 1, j0:j1 + 1] = True
        for gi in f.GraphicalItems():                    # net-tie / stub copper drawn as footprint graphics
            if gi.GetLayer() in (pcbnew.F_Cu, pcbnew.B_Cu):
                bb = gi.GetBoundingBox()
                i0, i1 = max(0, int((_mm(bb.GetX()) - pad_r) / G)), min(nx - 1, int((_mm(bb.GetRight()) + pad_r) / G) + 1)
                j0, j1 = max(0, int((_mm(bb.GetY()) - pad_r) / G)), min(ny - 1, int((_mm(bb.GetBottom()) + pad_r) / G) + 1)
                occ[i0:i1 + 1, j0:j1 + 1] = True
    from matplotlib.path import Path as MPath
    from scipy import ndimage
    rule = np.zeros_like(occ)
    for z in B.Zones():
        if not z.GetIsRuleArea():
            continue
        ol = z.Outline()
        for oi in range(ol.OutlineCount()):
            c = ol.COutline(oi)
            pts = [(_mm(c.CPoint(k).x), _mm(c.CPoint(k).y)) for k in range(c.PointCount())]
            if len(pts) < 3:
                continue
            xa, ya = np.array(pts).T
            i0, i1 = max(0, int(xa.min() / G)), min(nx - 1, int(xa.max() / G) + 1)
            j0, j1 = max(0, int(ya.min() / G)), min(ny - 1, int(ya.max() / G) + 1)
            if i0 > i1 or j0 > j1:
                continue
            X, Y = np.meshgrid(xs[i0:i1 + 1], ys[j0:j1 + 1], indexing="ij")
            inside = MPath(pts).contains_points(np.c_[X.ravel(), Y.ravel()]).reshape(X.shape)
            rule[i0:i1 + 1, j0:j1 + 1] |= inside
    occ |= ndimage.binary_dilation(rule, iterations=int((VR + 0.05) / G) + 1)
    for hx, hy in HOLES:
        disk(hx, hy, 3.85)
    e = int(0.8 / G)
    occ[:e, :] = occ[-e:, :] = True
    occ[:, :e] = occ[:, -e:] = True
    return occ


def stitch(B, m, rf_tracks, sig_vias):
    occ = build_mask(B)
    cnt = {"beside signal vias": 0, "RF fences": 0, "grid": 0, "signal vias without a ground via": 0}

    def ok(x, y):
        i, j = int(round(x / G)), int(round(y / G))
        return 0 <= i < occ.shape[0] and 0 <= j < occ.shape[1] and not occ[i, j]

    def place(x, y):
        m.via(round(x, 3), round(y, 3), "GND")
        r = VR * 2 + CLR + 0.05
        i, j, k = int(round(x / G)), int(round(y / G)), int(r / G) + 1
        occ[max(0, i - k):i + k + 1, max(0, j - k):j + k + 1] = True

    for sx, sy in sig_vias:
        done = False
        for rad in (0.75, 0.9, 1.1):
            for a in range(0, 360, 30):
                x, y = sx + rad * math.cos(math.radians(a)), sy + rad * math.sin(math.radians(a))
                if ok(x, y):
                    place(x, y)
                    done = True
                    break
            if done:
                break
        cnt["beside signal vias" if done else "signal vias without a ground via"] += 1
    for (x0, y0), (x1, y1), w in rf_tracks:
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 0.4:
            continue
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        off = w / 2 + 2 * w + 0.35
        k = 0.0
        while k <= L:
            for s in (1, -1):
                x, y = x0 + ux * k - uy * off * s, y0 + uy * k + ux * off * s
                if ok(x, y):
                    place(x, y)
                    cnt["RF fences"] += 1
            k += 1.5
    for x in np.arange(1.25, W, 2.5):
        for y in np.arange(1.25, H, 2.5):
            for dx, dy in ((0, 0), (0.4, 0), (0, 0.4), (-0.4, 0), (0, -0.4), (0.4, 0.4), (-0.4, -0.4)):
                if ok(x + dx, y + dy):
                    place(x + dx, y + dy)
                    cnt["grid"] += 1
                    break
    return cnt
