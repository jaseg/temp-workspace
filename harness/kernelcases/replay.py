"""Independent replay of one SolidCraft kernel case (tests/kernel-cases/<area>/<id>) on OCCT,
through FreeCAD's Part module.

  python replay.py <fc_lib> <case_dir> <out.json>

The recipe's app commands are re-implemented here from SolidCraft's documented command semantics
(engine schema, command handlers and doc evaluation, read as reference only). Anything this replay
cannot map faithfully raises Unsupported and the case is reported "unsupported" without grading.
The result JSON holds the measured model (or the error) and is graded by run_cases.py.
"""

import json
import math
import os
import re
import sys
import time
import traceback

sys.path.append(sys.argv[1])
import FreeCAD as App  # noqa: E402
import Part  # noqa: E402
from FreeCAD import Vector as V  # noqa: E402

TOL = 1e-7
SEAM_ANGLE = 0.6131  # SolidCraft starts primitive circles here (radians from the frame's x)


class Unsupported(Exception):
    pass


class EngineRefusal(Exception):
    """A refusal SolidCraft's engine makes before any kernel call (argument checks)."""


class KernelError(Exception):
    pass


def num(v, kind="length"):
    if v is None:
        return None
    if isinstance(v, bool):
        raise Unsupported("boolean where a number was expected")
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    m = re.fullmatch(r"([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*(mm|deg|°)?", s)
    if not m:
        raise Unsupported("expression %r" % s)
    x = float(m.group(1))
    return x


def deg(v):
    return num(v, "angle")


def vec(a):
    if isinstance(a, dict):
        a = [a.get("x", 0), a.get("y", 0), a.get("z", 0)]
    return V(float(num(a[0])), float(num(a[1])), float(num(a[2])) if len(a) > 2 else 0.0)


# ------------------------------------------------------------------------------------------
# Planes (SolidCraft's Plane: origin, x, y; normal x × y)
# ------------------------------------------------------------------------------------------

class Plane:
    def __init__(self, o, x, y):
        x = V(x).normalize()
        n = x.cross(V(y))
        n.normalize()
        y = n.cross(x)
        y.normalize()
        self.o, self.x, self.y, self.n = V(o), x, y, n

    @staticmethod
    def named(name):
        n = name.upper()
        if n in ("XY", "TOP"):
            return Plane(V(0, 0, 0), V(1, 0, 0), V(0, 1, 0))
        if n in ("XZ", "FRONT"):
            return Plane(V(0, 0, 0), V(1, 0, 0), V(0, 0, -1))
        if n in ("YZ", "RIGHT"):
            return Plane(V(0, 0, 0), V(0, 1, 0), V(0, 0, 1))
        raise Unsupported("plane %s" % name)

    @staticmethod
    def from_normal(o, n):
        n = V(n).normalize()
        cand = V(1, 0, 0) if abs(n.z) > 0.9 else V(0, 0, 1).cross(n)
        x = cand - n * cand.dot(n)
        x.normalize()
        return Plane(o, x, n.cross(x))

    def w(self, p):
        return self.o + self.x * float(p[0]) + self.y * float(p[1])

    def dw(self, d):
        return self.x * float(d[0]) + self.y * float(d[1])

    def local(self, p):
        d = V(p) - self.o
        return (d.dot(self.x), d.dot(self.y))

    def height(self, p):
        return (V(p) - self.o).dot(self.n)

    def offset(self, d):
        return Plane(self.o + self.n * d, self.x, self.y)


# ------------------------------------------------------------------------------------------
# Sketches
# ------------------------------------------------------------------------------------------

class Sketch:
    def __init__(self, name, plane):
        self.name = name
        self.plane = plane
        self.curves = []  # (id, kind, data, construction)
        self.points = {}  # "l1.start" -> (x, y)
        self.nline = 0
        self.narc = 0
        self.ncircle = 0
        self._regions = None

    def pt(self, spec):
        if isinstance(spec, str):
            if spec in self.points:
                return self.points[spec]
            if spec == "origin":
                return (0.0, 0.0)
            raise Unsupported("sketch point reference %r" % spec)
        if isinstance(spec, dict):
            if "ref" in spec:
                return self.pt(spec["ref"])
            if "x" in spec:
                return (num(spec["x"]), num(spec["y"]))
            raise Unsupported("point form %r" % spec)
        return (num(spec[0]), num(spec[1]))

    def add_line(self, a, b, cid=None, construction=False):
        self.nline += 1
        cid = cid or "l%d" % self.nline
        self.points[cid + ".start"] = a
        self.points[cid + ".end"] = b
        if math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-12:
            raise Unsupported("zero-length line")
        self.curves.append((cid, "line", (a, b), construction))

    def edge_of(self, kind, data):
        P = self.plane
        if kind == "line":
            a, b = data
            return Part.LineSegment(P.w(a), P.w(b)).toShape()
        if kind == "circle":
            c, r = data
            circ = Part.Circle(P.w(c), P.n, r)
            circ.XAxis = P.x
            return circ.toShape()
        if kind == "arc3":
            a, m, b = data
            return Part.Arc(P.w(a), P.w(m), P.w(b)).toShape()
        if kind == "arc":
            c, r, a0, sw = data
            circ = Part.Circle(P.w(c), P.n, r)
            circ.XAxis = P.x
            if sw > 0:
                return Part.ArcOfCircle(circ, a0, a0 + sw).toShape()
            return Part.ArcOfCircle(circ, a0 + sw, a0).toShape()
        raise Unsupported(kind)

    def edges(self, construction=False):
        return [self.edge_of(k, d) for (i, k, d, c) in self.curves if c == construction]

    def curve_edge(self, cid):
        for (i, k, d, c) in self.curves:
            if i == cid:
                return k, d
        return None, None

    # ---- regions: the minimal faces of the arrangement of the drawn (non-construction) curves
    def simple_regions(self, edges):
        """Regions when the drawn curves are closed loops that neither cross nor touch: each loop
        less the loops directly inside it. None when that does not hold."""
        def key(p):
            return (round(p.x, 7), round(p.y, 7), round(p.z, 7))
        deg = {}
        for e in edges:
            if e.isClosed() and len(e.Vertexes) == 1:
                continue
            for v in (e.Vertexes[0], e.Vertexes[-1]):
                deg[key(v.Point)] = deg.get(key(v.Point), 0) + 1
        if any(d != 2 for d in deg.values()):
            return None
        try:
            groups = Part.sortEdges(edges)
        except Exception:
            return None
        wires = []
        for g in groups:
            w = Part.Wire(g)
            if not w.isClosed():
                return None
            wires.append(w)
        n = len(wires)
        for i in range(n):
            for j in range(i + 1, n):
                bi, bj = wires[i].BoundBox, wires[j].BoundBox
                bi.enlarge(1e-6)
                if bi.intersect(bj) and wires[i].distToShape(wires[j])[0] < 1e-6:
                    return None
        faces = []
        for w in wires:
            f = Part.Face(w)
            if not f.isValid() or f.Area < 1e-12:
                return None
            faces.append(f)
        inside = [[False] * n for _ in range(n)]  # inside[j][i]: loop j lies inside loop i
        for i in range(n):
            for j in range(n):
                if i != j:
                    inside[j][i] = faces[i].isInside(wires[j].Vertexes[0].Point, 1e-9, False)
        out = []
        for i in range(n):
            kids = [j for j in range(n) if inside[j][i] and not any(inside[j][k] and inside[k][i] for k in range(n) if k not in (i, j))]
            f = faces[i]
            if kids:
                f = Part.Face([wires[i]] + [wires[j] for j in kids])
                if not f.isValid():
                    f = faces[i].cut(Part.makeCompound([faces[j] for j in kids])).Faces[0]
            out.append(f)
        return out

    def regions(self):
        if self._regions is not None:
            return self._regions
        import BOPTools.SplitAPI as SA
        edges = self.edges(False)
        quick = self.simple_regions(edges) if edges else None
        if quick:
            quick.sort(key=lambda f: (round(f.CenterOfMass.x, 6), round(f.CenterOfMass.y, 6), round(f.CenterOfMass.z, 6)))
            self._regions = quick
            return quick
        if not edges:
            raise KernelError("%s has no closed profiles" % self.name)
        comp = Part.Compound(edges)
        bb = comp.BoundBox
        L = 10 * (bb.DiagonalLength + 1)
        c = self.plane.w(self.plane.local(bb.Center))
        big = Part.Plane(c, self.plane.n).toShape(-L, L, -L, L)
        frag = SA.booleanFragments([big] + edges, "Standard", 0.0)
        out = []
        for fc in frag.Faces:
            if any((v.Point - c).Length > 0.5 * L for v in fc.OuterWire.Vertexes):
                continue
            if fc.Area < 1e-12:
                continue
            out.append(fc)
        if not out:
            raise KernelError("%s has no closed profiles" % self.name)
        # a stable order (no claim to match SolidCraft's profile numbering)
        out.sort(key=lambda f: (round(f.CenterOfMass.x, 6), round(f.CenterOfMass.y, 6), round(f.CenterOfMass.z, 6)))
        self._regions = out
        return out


def interior_point(face):
    c = face.CenterOfMass
    if face.isInside(c, 1e-9, False):
        return c
    u0, u1, v0, v1 = face.ParameterRange
    best = None
    for i in range(1, 40):
        for j in range(1, 40):
            u = u0 + (u1 - u0) * i / 40.0
            v = v0 + (v1 - v0) * j / 40.0
            p = face.valueAt(u, v)
            if face.isInside(p, 1e-9, False):
                d = face.OuterWire.distToShape(Part.Vertex(p))[0]
                for w in face.Wires[1:]:
                    d = min(d, w.distToShape(Part.Vertex(p))[0])
                if best is None or d > best[0]:
                    best = (d, p)
    if best is None:
        raise KernelError("no interior point")
    return best[1]


def merged(faces):
    """SolidCraft's merge_regions: picked regions that share boundary become one region."""
    if len(faces) == 1:
        return [faces[0]]
    f = faces[0].multiFuse(faces[1:])
    try:
        f = f.removeSplitter()
    except Exception:
        pass
    return list(f.Faces)


def select_profiles(sk, spec, default_even_odd):
    regs = sk.regions()
    if spec is None and default_even_odd:
        holes = any(len(r.Wires) > 1 for r in regs)
        if not holes:
            return merged(regs)
        outers = [Part.Face(r.OuterWire) for r in regs]
        mat = []
        for i, r in enumerate(regs):
            p = interior_point(r)
            depth = sum(1 for j, o in enumerate(outers) if j != i and o.isInside(p, 1e-9, False))
            if depth % 2 == 0:
                mat.append(r)
        return merged(mat)
    if spec is None or (isinstance(spec, str) and spec.lower() == "all"):
        return merged(regs)
    if isinstance(spec, int) and not isinstance(spec, bool):
        spec = [spec]
    if isinstance(spec, list) and all(isinstance(x, int) and not isinstance(x, bool) for x in spec):
        if sorted(spec) == list(range(len(regs))):
            return merged(regs)
        if len(regs) == 1 and spec == [0]:
            return merged(regs)
        raise Unsupported("profiles by index into %d regions (SolidCraft's numbering unknown)" % len(regs))
    if isinstance(spec, list) and all(isinstance(x, dict) and "point" in x for x in spec):
        picked = []
        for x in spec:
            q = sk.plane.w(sk.pt(x["point"]))
            hit = [r for r in regs if r.isInside(q, 1e-7, True)]
            if not hit:
                raise KernelError("profile at %s in %s" % (x["point"], sk.name))
            # innermost: the smallest region containing the point
            r = min(hit, key=lambda f: f.Area)
            if not any(r.isSame(o) for o in picked):
                picked.append(r)
        return merged(picked)
    raise Unsupported("profiles form %r" % (spec,))


# ------------------------------------------------------------------------------------------
# Bodies
# ------------------------------------------------------------------------------------------

def solids(s):
    return list(s.Solids) if s is not None else []


def comp(sol):
    sol = list(sol)
    if len(sol) == 1:
        return sol[0]
    return Part.makeCompound(sol)


def refine(s):
    try:
        r = s.copy().removeSplitter()
        if r.isValid() and abs(r.Volume - s.Volume) <= 1e-6 * max(1.0, abs(s.Volume)) and len(r.Solids) == len(s.Solids):
            return r
    except Exception:
        pass
    return s


class Body:
    def __init__(self, name, shape):
        self.name = name
        self.shape = shape

    @property
    def lumps(self):
        return len(self.shape.Solids)


class Model:
    def __init__(self, log):
        self.bodies = []
        self.sketches = {}
        self.sketch_list = []
        self.active = None
        self.counter = 0
        self.log = log

    # names --------------------------------------------------------------------------------
    def body(self, name):
        for b in self.bodies:
            if b.name == name:
                return b
        return None

    def new_name(self, names, k):
        if k < len(names) and names[k] and self.body(names[k]) is None:
            return names[k]
        if k >= len(names) and names and names[0].strip():
            n = "%s (%d)" % (names[0], k + 1)
            if self.body(n) is None:
                return n
        while True:
            self.counter += 1
            n = "Body%d" % self.counter
            if self.body(n) is None:
                return n

    def size(self):
        sh = [b.shape for b in self.bodies]
        if not sh:
            return 100.0
        return Part.makeCompound(sh).BoundBox.DiagonalLength

    # booleans -------------------------------------------------------------------------------
    def apply(self, op, tools, targets, names, explicit_targets):
        """SolidCraft's apply_traced, with its body bookkeeping."""
        tools = [t for t in tools]
        if op == "new" or (not targets and op == "join"):
            if op in ("cut", "intersect"):
                raise KernelError("there is no body to %s" % op)
            for k, t in enumerate(tools):
                self.bodies.append(Body(self.new_name(names, k), refine(t)))
            return
        if not targets:
            raise KernelError("there is no body to %s" % op)
        if op == "join":
            self.join(tools, targets)
            return
        if op == "intersect":
            tool = tools[0] if len(tools) == 1 else tools[0].multiFuse(tools[1:])
            tools = [tool]
        before = {n: self.body(n).lumps for n in targets}
        remove = []
        for n in targets:
            b = self.body(n)
            acc = b.shape
            for t in tools:
                if not acc.BoundBox.intersect(t.BoundBox) and op == "cut":
                    continue
                acc = acc.cut(t) if op == "cut" else acc.common(t)
                self.log.append("%s %s: %d solids, vol %.6g" % (op, n, len(acc.Solids), sum(s.Volume for s in acc.Solids)))
            if op == "intersect" and not acc.Solids:
                if explicit_targets:
                    raise KernelError("the intersection with %s is empty" % n)
                remove.append(n)
                continue
            if not acc.Solids:
                remove.append(n)
                continue
            b.shape = refine(comp(acc.Solids))
        if op == "intersect" and len(remove) == len(targets):
            raise KernelError("the intersection is empty")
        self.bodies = [b for b in self.bodies if b.name not in remove]
        # a cut that leaves more pieces than the body had splits it into bodies
        out = []
        taken = set(b.name for b in self.bodies)
        for b in self.bodies:
            had = before.get(b.name)
            if had is None or b.lumps <= had:
                out.append(b)
                continue
            pieces = list(b.shape.Solids)
            for k, p in enumerate(pieces):
                if k == 0:
                    nm = b.name
                else:
                    j = k
                    nm = "%s (%d)" % (b.name, j)
                    while nm in taken:
                        j += 1
                        nm = "%s (%d)" % (b.name, j)
                taken.add(nm)
                out.append(Body(nm, p))
        self.bodies = out

    def join(self, tools, targets):
        live = list(targets)
        joined = []
        if len(live) == 1 and len(tools) > 1:
            b = self.body(live[0])
            old = b.shape
            r = b.shape.multiFuse(tools)
            self.log.append("join %s: %d solids" % (b.name, len(r.Solids)))
            b.shape = refine(comp(r.Solids))
            self.separate_touching(b, old)
            return
        for t in tools:
            met = []
            tb = t.BoundBox
            tb.enlarge(1e-5)
            for n in (live if len(live) > 1 else []):
                b = self.body(n)
                if tb.intersect(b.shape.BoundBox) and b.shape.distToShape(t)[0] <= 1e-7:
                    met.append(n)
            keep = (met or live)[0]
            kb = self.body(keep)
            old = kb.shape
            r = kb.shape.fuse(t)
            for n in met[1:]:
                r = r.fuse(self.body(n).shape)
            self.log.append("join %s: %d solids" % (keep, len(r.Solids)))
            kb.shape = refine(comp(r.Solids))
            absorbed = set(met[1:])
            self.bodies = [b for b in self.bodies if b.name not in absorbed]
            live = [n for n in live if n not in absorbed]
            if keep not in joined:
                joined.append(keep)
            self.separate_touching(kb, old)

    def separate_touching(self, b, old):
        sol = list(b.shape.Solids)
        if len(sol) < 2:
            return
        n = len(sol)
        touch = [[] for _ in range(n)]
        for i in range(n):
            bi = sol[i].BoundBox
            bi.enlarge(1e-5)
            for j in range(i + 1, n):
                if bi.intersect(sol[j].BoundBox) and sol[i].distToShape(sol[j])[0] <= 1e-6:
                    touch[i].append(j)
                    touch[j].append(i)
        if not any(touch):
            return
        # anchor: the pieces holding the body's material before the feature
        anchor = []
        for i, s in enumerate(sol):
            try:
                if old is not None and s.common(old).Volume > 1e-9 * max(1.0, s.Volume):
                    anchor.append(i)
            except Exception:
                pass
        if not anchor:
            anchor = [0]
        stays = [not touch[i] for i in range(n)]
        kept = []
        for i in anchor:
            if not any(k in touch[i] for k in kept):
                stays[i] = True
                kept.append(i)
        stay = [sol[i] for i in range(n) if stays[i]]
        go = [sol[i] for i in range(n) if not stays[i]]
        b.shape = comp(stay)
        taken = set(x.name for x in self.bodies)
        k = 1
        for s in go:
            nm = "%s (%d)" % (b.name, k)
            while nm in taken:
                k += 1
                nm = "%s (%d)" % (b.name, k)
            taken.add(nm)
            self.bodies.append(Body(nm, s))
        self.log.append("join kept %d piece(s) touching along an edge or at a point apart" % len(go))

    # picks -------------------------------------------------------------------------------------
    def pick_edge(self, p, body=None):
        p = vec(p)
        vp = Part.Vertex(p)
        cands = []
        for b in self.bodies:
            if body is not None and b.name != body:
                continue
            for e in b.shape.Edges:
                d = e.distToShape(vp)[0]
                cands.append((d, b, e))
        if not cands:
            raise KernelError("no body")
        d0 = min(c[0] for c in cands)
        reach = self.size() * 0.05 + 1e-3
        if d0 > reach:
            raise EngineRefusal("no edge at (%.3f, %.3f, %.3f)" % (p.x, p.y, p.z))
        near = [c for c in cands if c[0] <= d0 + 1e-7]
        if len(near) > 1:
            sharp = [c for c in near if not is_seam_or_smooth(c[1].shape, c[2])]
            if sharp:
                near = sharp
        bodies = set(c[1].name for c in near)
        if len(bodies) > 1 and body is None:
            raise EngineRefusal("the point is on edges of 2 bodies")
        return near[0][1], near[0][2]

    def pick_face(self, p, body=None):
        p = vec(p)
        vp = Part.Vertex(p)
        best = None
        for b in self.bodies:
            if body is not None and b.name != body:
                continue
            for f in b.shape.Faces:
                d = f.distToShape(vp)[0]
                if best is None or d < best[0] - 1e-9:
                    best = (d, b, f)
        if best is None or best[0] > 1e-3 * max(1.0, self.size()):
            raise EngineRefusal("no face at %s" % (list(p),))
        return best[1], best[2]


def adjacent_faces(shape, e):
    return [f for f in shape.ancestorsOfType(e, Part.Face)]


def is_seam_or_smooth(shape, e):
    fs = adjacent_faces(shape, e)
    uniq = []
    for f in fs:
        if not any(f.isSame(g) for g in uniq):
            uniq.append(f)
    if len(uniq) == 1:
        return True  # seam (or a free edge)
    if len(uniq) == 2:
        return face_angle_at(e, uniq[0], uniq[1]) < math.radians(0.5)
    return False


def normal_at(f, p):
    u, v = f.Surface.parameter(p)
    n = f.normalAt(u, v)
    return n


def face_angle_at(e, f1, f2):
    worst = 0.0
    for t in (0.25, 0.5, 0.75):
        p = e.valueAt(e.FirstParameter + t * (e.LastParameter - e.FirstParameter))
        n1, n2 = normal_at(f1, p), normal_at(f2, p)
        c = max(-1.0, min(1.0, n1.dot(n2)))
        worst = max(worst, math.acos(c))
    return worst


def tangent_chain(shape, seeds):
    """SolidCraft's chain: edges continuing a picked edge tangentially (0.5 deg) at a shared
    vertex; seams and smooth edges end it."""
    def tan_at(e, v):
        u = e.FirstParameter if (e.Vertexes[0].Point - v).Length < (e.Vertexes[-1].Point - v).Length else e.LastParameter
        t = e.tangentAt(u)
        return t.normalize() if t.Length > 0 else t
    sel = list(seeds)
    edges = [e for e in shape.Edges if not is_seam_or_smooth(shape, e)]
    changed = True
    while changed:
        changed = False
        for e in edges:
            if any(e.isSame(s) for s in sel):
                continue
            for s in list(sel):
                hit = False
                for va in e.Vertexes:
                    for vb in s.Vertexes:
                        if va.isSame(vb):
                            ta, tb = tan_at(e, va.Point), tan_at(s, vb.Point)
                            if abs(abs(ta.dot(tb)) - 1) < 1 - math.cos(math.radians(0.5)):
                                hit = True
                if hit:
                    sel.append(e)
                    changed = True
                    break
    return sel


# ------------------------------------------------------------------------------------------
# Tools
# ------------------------------------------------------------------------------------------

def circle_face(center, axis, r):
    pl = Plane.from_normal(center, axis)
    circ = Part.Circle(center, pl.n, r)
    x = pl.x * math.cos(SEAM_ANGLE) + pl.y * math.sin(SEAM_ANGLE)
    circ.XAxis = x
    return Part.Face(Part.Wire(circ.toShape()))


def prism(face, n, lo, hi):
    g = face.copy()
    g.translate(n * lo)
    return g.extrude(n * (hi - lo))


def join_collinear(w):
    es = list(w.OrderedEdges)
    out = []
    for e in es:
        if out and isinstance(e.Curve, Part.Line) and isinstance(out[-1].Curve, Part.Line):
            a0, a1 = out[-1].valueAt(out[-1].FirstParameter), out[-1].valueAt(out[-1].LastParameter)
            b0, b1 = e.valueAt(e.FirstParameter), e.valueAt(e.LastParameter)
            da, db = a1 - a0, b1 - b0
            # oriented along the wire: OrderedEdges keeps each edge's own direction
            if da.Length > 0 and db.Length > 0 and da.cross(db).Length < 1e-9 * da.Length * db.Length:
                pts = [a0, a1, b0, b1]
                # the shared point drops out
                share = [(i, j) for i in (0, 1) for j in (2, 3) if (pts[i] - pts[j]).Length < 1e-9]
                if share:
                    i, j = share[0]
                    ends = [pts[1 - i], pts[5 - j]]
                    out[-1] = Part.LineSegment(ends[0], ends[1]).toShape()
                    continue
        out.append(e)
    if len(out) > 2 and isinstance(out[0].Curve, Part.Line) and isinstance(out[-1].Curve, Part.Line):
        a, b = out[-1], out[0]
        da = a.valueAt(a.LastParameter) - a.valueAt(a.FirstParameter)
        db = b.valueAt(b.LastParameter) - b.valueAt(b.FirstParameter)
        if da.cross(db).Length < 1e-9 * da.Length * db.Length:
            pa = [a.valueAt(a.FirstParameter), a.valueAt(a.LastParameter)]
            pb = [b.valueAt(b.FirstParameter), b.valueAt(b.LastParameter)]
            share = [(i, j) for i in (0, 1) for j in (0, 1) if (pa[i] - pb[j]).Length < 1e-9]
            if share:
                i, j = share[0]
                out[0] = Part.LineSegment(pa[1 - i], pb[1 - j]).toShape()
                out.pop()
    return Part.Wire(Part.__sortEdges__(out))


def tapered(face, n, base, sign, length, ang):
    d = length * math.tan(ang)
    f0 = face.copy()
    f0 = Part.Face([join_collinear(w) for w in f0.Wires])  # a side drawn in collinear pieces is one side
    f0.translate(n * base)
    outer = f0.OuterWire
    top_face = Part.Face(outer).makeOffset2D(d, 2, False, False, False)
    if not top_face.Faces:
        raise KernelError("taper offset vanished")
    top = top_face.Faces[0].OuterWire.copy()
    top.translate(n * (sign * length))
    solid = Part.makeLoft([outer, top], True, True)
    for h in f0.Wires[1:]:
        hf = Part.Face(h).makeOffset2D(-d, 2, False, False, False)
        if not hf.Faces:
            continue
        ht = hf.Faces[0].OuterWire.copy()
        ht.translate(n * (sign * length))
        solid = solid.cut(Part.makeLoft([h, ht], True, True))
    if solid.Volume < 0:
        solid.reverse()
    return solid


# ------------------------------------------------------------------------------------------
# Commands
# ------------------------------------------------------------------------------------------

KNOWN = {
    "solid.box": {"length", "width", "height", "corner", "center", "operation", "targets", "body_name", "name"},
    "solid.cylinder": {"radius", "diameter", "height", "base", "axis", "operation", "targets", "body_name", "name"},
    "solid.sphere": {"radius", "diameter", "center", "operation", "targets", "body_name", "name"},
    "solid.cone": {"radius", "top_radius", "height", "base", "axis", "operation", "targets", "body_name", "name"},
    "solid.torus": {"major", "minor", "center", "operation", "targets", "body_name", "name"},
    "solid.combine": {"target", "tools", "operation", "keep_tools", "name"},
    "solid.fillet": {"edges", "radius", "body", "tangent_chain", "corner", "name"},
    "solid.chamfer": {"edges", "distance", "distance2", "flip", "body", "tangent_chain", "name"},
    "solid.shell": {"faces", "thickness", "body", "direction", "name"},
    "sketch.create": {"plane", "offset", "name", "project_edges"},
    "sketch.finish": set(),
    "sketch.line": {"points", "closed", "infer", "connect", "construction", "ids"},
    "sketch.rectangle.two_point": {"p0", "p1"},
    "sketch.rectangle.center": {"center", "corner"},
    "sketch.circle.center": {"center", "radius"},
    "sketch.arc.center_point": {"center", "start", "end", "sweep", "clockwise"},
    "solid.extrude": {"sketch", "through_all", "direction", "operation", "targets", "face", "face_body", "distance",
                      "profiles", "taper", "body_name", "to", "body_names", "start_offset", "from", "name"},
    "solid.revolve": {"axis", "angle", "operation", "direction", "body_name", "sketch", "profiles", "targets", "angle2", "name"},
    "solid.split_body": {"body", "tool", "plane"},
    "inspect.measure": None,
}


def op_of(p, default="new"):
    o = str(p.get("operation", default)).lower().replace("_", "").replace("-", "").replace(" ", "")
    return {"new": "new", "newbody": "new", "join": "join", "cut": "cut", "intersect": "intersect"}.get(o) or (_ for _ in ()).throw(Unsupported("operation %s" % o))


class Runner:
    def __init__(self, log):
        self.m = Model(log)
        self.log = log

    def run(self, cmds):
        for i, c in enumerate(cmds):
            name = c["command"]
            p = c.get("params", {}) or {}
            known = KNOWN.get(name, "missing")
            if known == "missing":
                raise Unsupported("command %s" % name)
            if known is not None:
                extra = set(p) - known
                if extra:
                    raise Unsupported("%s params %s" % (name, sorted(extra)))
            t = time.perf_counter()
            self.step = i + 1
            if os.environ.get("REPLAY_TRACE"):
                print("step", i + 1, name, flush=True)
            getattr(self, "c_" + name.replace(".", "_"))(p)
            self.log.append("step %d %s ok (%.3fs)" % (i + 1, name, time.perf_counter() - t))

    # primitives ---------------------------------------------------------------------------
    def primitive(self, p, shape):
        op = op_of(p)
        names = [p["body_name"]] if p.get("body_name") else []
        tg = p.get("targets")
        if isinstance(tg, str):
            tg = [tg]
        explicit = bool(tg)
        if op != "new":
            if not tg:
                tg = [b.name for b in self.m.bodies]
            for t in tg:
                if self.m.body(t) is None:
                    raise EngineRefusal("`targets` must list existing bodies")
        self.m.apply(op, [shape], tg or [], names, explicit)

    def c_solid_box(self, p):
        l, w, h = num(p["length"]), num(p["width"]), num(p["height"])
        if "corner" in p:
            c = vec(p["corner"])
        elif "center" in p:
            c = vec(p["center"]) - V(l, w, h) * 0.5
        else:
            c = V(0, 0, 0)
        if not (l > 1e-6 and w > 1e-6 and h > 1e-6):
            raise EngineRefusal("box needs a positive size")
        self.primitive(p, Part.makeBox(l, w, h, c))

    def axis_dir(self, a):
        if a is None:
            return V(0, 0, 1)
        if isinstance(a, str):
            return {"X": V(1, 0, 0), "Y": V(0, 1, 0), "Z": V(0, 0, 1)}[a.strip().upper()]
        v = vec(a)
        return v.normalize()

    def c_solid_cylinder(self, p):
        r = num(p["radius"]) if p.get("radius") is not None else num(p["diameter"]) / 2
        h = num(p["height"])
        base = vec(p.get("base", [0, 0, 0]))
        ax = self.axis_dir(p.get("axis"))
        f = circle_face(base, ax, r)
        self.primitive(p, f.extrude(ax * h))

    def c_solid_sphere(self, p):
        r = num(p["radius"]) if p.get("radius") is not None else num(p["diameter"]) / 2
        self.primitive(p, Part.makeSphere(r, vec(p.get("center", [0, 0, 0]))))

    def c_solid_torus(self, p):
        self.primitive(p, Part.makeTorus(num(p["major"]), num(p["minor"]), vec(p.get("center", [0, 0, 0])), V(0, 0, 1)))

    def c_solid_cone(self, p):
        r = num(p["radius"])
        rt = num(p.get("top_radius", 0))
        h = num(p["height"])
        if abs(h) <= 1e-6:
            raise EngineRefusal("height must not be zero")
        base = vec(p.get("base", [0, 0, 0]))
        ax = self.axis_dir(p.get("axis"))
        if h < 0:
            ax = ax * -1
            h = -h
        self.primitive(p, Part.makeCone(r, rt if rt > 1e-6 else 0.0, h, base, ax))

    # combine ---------------------------------------------------------------------------------
    def c_solid_combine(self, p):
        target = p["target"]
        tools = p["tools"] if isinstance(p["tools"], list) else [p["tools"]]
        op = op_of(p, "join")
        if op == "new":
            raise EngineRefusal("operation must be join, cut or intersect")
        if target in tools:
            raise EngineRefusal("a body cannot be combined with itself")
        tb = []
        for t in tools:
            b = self.m.body(t)
            if b is None:
                raise Unsupported("combine tool %s not a body here (piece naming?)" % t)
            tb.append(b.shape.copy())
        if self.m.body(target) is None:
            raise Unsupported("combine target %s not a body here" % target)
        self.m.apply(op, tb, [target], [], True)
        if not p.get("keep_tools"):
            self.m.bodies = [b for b in self.m.bodies if b.name not in tools]

    # blends -----------------------------------------------------------------------------------
    def blend_groups(self, p):
        body = p.get("body")
        if body is not None and self.m.body(body) is None:
            raise EngineRefusal("no body %s" % body)
        groups = {}
        for e in p["edges"]:
            if isinstance(e, dict) and "body" in e and "index" in e:
                raise Unsupported("edge by index")
            pt = e.get("point") if isinstance(e, dict) and "point" in e else e
            b, edge = self.m.pick_edge(pt, body)
            groups.setdefault(b.name, [])
            vs = [v.Point for v in edge.Vertexes]
            self.m.log.append("pick %s -> %s %s %s len %.4g" % (list(pt), b.name, edge.Curve.__class__.__name__,
                              [tuple(round(c, 3) for c in v) for v in vs], edge.Length))
            if not any(edge.isSame(x) for x in groups[b.name]):
                groups[b.name].append(edge)
        return groups

    def on_solid(self, b, edges, fn):
        """Apply fn(solid, edges) to the solid of body b holding the edges."""
        sol = list(b.shape.Solids)
        out = []
        used = False
        for s in sol:
            mine = [e for e in edges if any(e.isSame(x) for x in s.Edges)]
            if mine:
                r = fn(s, mine)
                used = True
                out += list(r.Solids) if r.Solids else []
                if not r.Solids:
                    raise KernelError("blend left no solid")
            else:
                out.append(s)
        if not used:
            raise KernelError("edges not on the body")
        b.shape = comp(out)

    def c_solid_fillet(self, p):
        if p.get("corner") not in (None, "rolling"):
            raise Unsupported("fillet corner %s" % p.get("corner"))
        r = num(p["radius"])
        groups = self.blend_groups(p)
        for name, edges in groups.items():
            b = self.m.body(name)
            if p.get("tangent_chain", True) is False:
                ch = tangent_chain(b.shape, edges)
                if len(ch) > len(edges):
                    raise Unsupported("tangent_chain: false where the chain continues (OCCT's fillet always propagates along tangent edges)")
            v0 = b.shape.Volume
            self.on_solid(b, edges, lambda s, es: s.makeFillet(r, es))
            self.m.log.append("fillet %s: valid %s, dV %.6g" % (name, b.shape.isValid(), b.shape.Volume - v0))
            if abs(b.shape.Volume - v0) < 1e-12 * max(1.0, abs(v0)):
                self.m.log.append("NOOP: fillet returned the body unchanged")

    def c_solid_chamfer(self, p):
        d1 = num(p["distance"])
        d2 = num(p["distance2"]) if p.get("distance2") is not None else None
        flip = bool(p.get("flip", False))
        groups = self.blend_groups(p)
        for name, edges in groups.items():
            b = self.m.body(name)
            if p.get("tangent_chain", True) is False:
                ch = tangent_chain(b.shape, edges)
                if len(ch) > len(edges):
                    raise Unsupported("tangent_chain: false where the chain continues")
            if d2 is None:
                self.on_solid(b, edges, lambda s, es: s.makeChamfer(d1, es))
            else:
                def two(s, es):
                    # FreeCAD's makeChamfer(d1, d2, edges) puts d1 on the first face (in the solid's
                    # face order) holding each edge; SolidCraft puts d1 on the face facing up most
                    # (down with flip). The same faces are put in an order where each edge's d1
                    # face comes first, and all edges are chamfered in one call.
                    up = V(0, 0, -1) if flip else V(0, 0, 1)
                    faces = list(s.Faces)
                    before = []  # (i, j): face i must come before face j
                    for e in es:
                        fs = [i for i, f in enumerate(faces) if any(x.isSame(e) for x in f.Edges)]
                        if len(fs) != 2:
                            raise Unsupported("chamfer edge with %d faces" % len(fs))
                        mid = e.valueAt(0.5 * (e.FirstParameter + e.LastParameter))
                        ups = [normal_at(faces[i], mid).dot(up) for i in fs]
                        if abs(ups[0] - ups[1]) < 1e-9:
                            raise Unsupported("chamfer: neither face faces up more")
                        a, c = (fs[0], fs[1]) if ups[0] > ups[1] else (fs[1], fs[0])
                        before.append((a, c))
                    order, seen, temp = [], set(), set()

                    def visit(i):
                        if i in seen:
                            return
                        if i in temp:
                            raise Unsupported("two-distance chamfer: no face order puts every edge's first face first")
                        temp.add(i)
                        for (a, c) in before:
                            if c == i:
                                visit(a)
                        temp.discard(i)
                        seen.add(i)
                        order.append(i)
                    for i in range(len(faces)):
                        visit(i)
                    if order != list(range(len(faces))):
                        if len(s.Shells) != 1:
                            raise Unsupported("two-distance chamfer on a solid with voids")
                        s2 = Part.Solid(Part.Shell([faces[i] for i in order]))
                        if not s2.isValid() or abs(s2.Volume - s.Volume) > 1e-9 * max(1, abs(s.Volume)):
                            raise Unsupported("two-distance chamfer: reordered solid differs")
                        s = s2
                        es = [x for x in s.Edges if any(x.isSame(e) for e in es)]
                    for e in es:
                        fs = [i for i, f in enumerate(s.Faces) if any(x.isSame(e) for x in f.Edges)]
                        mid = e.valueAt(0.5 * (e.FirstParameter + e.LastParameter))
                        assert normal_at(s.Faces[fs[0]], mid).dot(up) > normal_at(s.Faces[fs[1]], mid).dot(up)
                    return s.makeChamfer(d1, d2, es)
                self.on_solid(b, edges, two)

    def c_solid_shell(self, p):
        t = num(p["thickness"])
        direction = (p.get("direction") or "inside").lower()
        if direction == "both":
            raise Unsupported("shell both")
        faces = p.get("faces")
        body = p.get("body")
        if not faces:
            if body is None:
                if len(self.m.bodies) != 1:
                    raise EngineRefusal("a shell that opens no face needs the body named")
                b = self.m.bodies[0]
            else:
                b = self.m.body(body)
            picked = []
        else:
            picked = []
            b = None
            for q in faces:
                if isinstance(q, str):
                    raise Unsupported("face by name")
                bb, f = self.m.pick_face(q, body)
                if b is None:
                    b = bb
                picked.append(f)
        sol = b.shape.Solids
        if len(sol) != 1:
            raise Unsupported("shell of a multi-lump body")
        s = sol[0]
        if not picked:
            off = -t if direction == "inside" else t
            other = s.makeOffsetShape(off, 1e-7, False, False, 0, 2)
            if direction == "inside":
                r = s.cut(other)
            else:
                r = other.cut(s)
        else:
            r = s.makeThickness(picked, -t if direction == "inside" else t, 1e-7, False, False, 0, 2)
        self.m.log.append("shell: %d solids valid %s, V %.6g -> %.6g" % (len(r.Solids), r.isValid(), s.Volume, r.Volume))
        if abs(r.Volume - s.Volume) < 1e-9 * max(1.0, abs(s.Volume)):
            self.m.log.append("NOOP: shell returned the body unchanged")
        if not r.Solids:
            # makeThickness may return a shell; make a solid of it
            try:
                r = Part.Solid(r.Shells[0])
            except Exception:
                raise KernelError("shell gave no solid")
        b.shape = comp(r.Solids)

    # sketches -----------------------------------------------------------------------------------
    def c_sketch_create(self, p):
        pl = p.get("plane", "XY")
        if isinstance(pl, str):
            P = Plane.named(pl)
        elif isinstance(pl, dict) and "face" in pl:
            if set(pl) - {"face"}:
                raise Unsupported("face plane keys %s" % sorted(pl))
            b, f = self.m.pick_face(pl["face"])
            if f.Surface.__class__.__name__ != "Plane":
                raise EngineRefusal("not a planar face")
            q = vec(pl["face"])
            n = normal_at(f, q)
            c = f.CenterOfMass
            P = Plane.from_normal(n * c.dot(n), n)
            P.face_body = b.name
        elif isinstance(pl, dict) and "x_dir" in pl:
            if set(pl) - {"origin", "x_dir", "y_dir"}:
                raise Unsupported("plane keys %s" % sorted(pl))
            P = Plane(vec(pl.get("origin", [0, 0, 0])), vec(pl["x_dir"]), vec(pl["y_dir"]))
        else:
            raise Unsupported("plane %r" % (pl,))
        if p.get("offset") is not None:
            fb = getattr(P, "face_body", None)
            P = P.offset(num(p["offset"]))
            if fb:
                P.face_body = fb
        name = p.get("name") or "Sketch%d" % (len(self.m.sketch_list) + 1)
        sk = Sketch(name, P)
        self.m.sketches[name] = sk
        self.m.sketch_list.append(sk)
        self.m.active = sk

    def sk(self):
        if self.m.active is None:
            raise Unsupported("no active sketch")
        return self.m.active

    def c_sketch_finish(self, p):
        self.m.active = None

    def c_sketch_line(self, p):
        sk = self.sk()
        pts = [sk.pt(q) for q in p["points"]]
        ids = p.get("ids") or []
        segs = list(zip(pts, pts[1:]))
        if p.get("closed"):
            segs.append((pts[-1], pts[0]))
        for k, (a, b) in enumerate(segs):
            sk.add_line(a, b, ids[k] if k < len(ids) else None, bool(p.get("construction")))

    def c_sketch_rectangle_two_point(self, p):
        sk = self.sk()
        a, b = sk.pt(p["p0"]), sk.pt(p["p1"])
        self._rect(sk, a, b)

    def c_sketch_rectangle_center(self, p):
        sk = self.sk()
        c, k = sk.pt(p["center"]), sk.pt(p["corner"])
        a = (2 * c[0] - k[0], 2 * c[1] - k[1])
        self._rect(sk, a, k)

    def _rect(self, sk, a, b):
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        q = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        for i in range(4):
            sk.add_line(q[i], q[(i + 1) % 4])

    def c_sketch_circle_center(self, p):
        sk = self.sk()
        sk.ncircle += 1
        sk.curves.append(("c%d" % sk.ncircle, "circle", (sk.pt(p["center"]), num(p["radius"])), False))

    def c_sketch_arc_center_point(self, p):
        sk = self.sk()
        c, s = sk.pt(p["center"]), sk.pt(p["start"])
        r = math.hypot(s[0] - c[0], s[1] - c[1])
        a0 = math.atan2(s[1] - c[1], s[0] - c[0])
        if p.get("sweep") is not None:
            sw = math.radians(num(p["sweep"]))
        else:
            e = sk.pt(p["end"])
            a1 = math.atan2(e[1] - c[1], e[0] - c[0])
            if p.get("clockwise"):
                sw = -((a0 - a1) % (2 * math.pi))
            else:
                sw = (a1 - a0) % (2 * math.pi)
        sk.narc += 1
        cid = "a%d" % sk.narc
        endp = (c[0] + r * math.cos(a0 + sw), c[1] + r * math.sin(a0 + sw))
        if p.get("sweep") is None and isinstance(p.get("end"), (str, dict)):
            # an end given as an existing point shares that point
            e = sk.pt(p["end"])
            if math.hypot(e[0] - endp[0], e[1] - endp[1]) < 1e-3:
                endp = e
        sk.points[cid + ".start"] = s
        sk.points[cid + ".end"] = endp
        mid = (c[0] + r * math.cos(a0 + sw / 2), c[1] + r * math.sin(a0 + sw / 2))
        sk.curves.append((cid, "arc3", (s, mid, endp), False))

    def sketch_ref(self, p):
        if p.get("sketch") is not None:
            s = p["sketch"]
            if s not in self.m.sketches:
                raise Unsupported("sketch by id %r" % s)
            return self.m.sketches[s]
        if self.m.active is not None:
            return self.m.active
        if not self.m.sketch_list:
            raise EngineRefusal("no sketch")
        return self.m.sketch_list[-1]

    # extrude / revolve --------------------------------------------------------------------------
    def face_height(self, q, P):
        """height of the From/To object along the sketch normal: the face at the point (one square
        to the sketch normal preferred, as SolidCraft's object_face takes the normal as a hint),
        or the point itself."""
        qv = vec(q)
        vp = Part.Vertex(qv)
        at = []
        for b in self.m.bodies:
            for f in b.shape.Faces:
                if f.distToShape(vp)[0] <= 1e-6:
                    at.append(f)
        if not at:
            return P.height(qv)
        square = [f for f in at if f.Surface.__class__.__name__ == "Plane" and abs(abs(normal_at(f, qv).dot(P.n)) - 1) < 1e-9]
        if square:
            return P.height(qv)
        raise Unsupported("from/to a face not square to the extrude (curved or slanted)")

    def c_solid_extrude(self, p):
        names = []
        if p.get("body_name"):
            names.append(p["body_name"])
        names += list(p.get("body_names") or [])
        op = op_of(p)
        face_body = None
        if p.get("face") is not None:
            b, f = self.m.pick_face(p["face"], p.get("face_body"))
            if f.Surface.__class__.__name__ != "Plane":
                raise EngineRefusal("not a planar face")
            n = normal_at(f, vec(p["face"]))
            P = Plane.from_normal(f.CenterOfMass, n)
            regions = [Part.Face(f.Wires) if len(f.Wires) > 1 else Part.Face(f.OuterWire)]
            regions = [f.copy()]
            face_body = b.name
        else:
            sk = self.sketch_ref(p)
            P = sk.plane
            regions = select_profiles(sk, p.get("profiles"), True)
            face_body = getattr(P, "face_body", None)
        n = P.n
        direction = (p.get("direction") or "positive").lower()
        direction = {"one_side": "positive", "reverse": "negative", "flip": "negative"}.get(direction, direction)
        frm = self.face_height(p["from"], P) if p.get("from") is not None else 0.0
        so = num(p.get("start_offset", 0))
        targets = p.get("targets")
        if isinstance(targets, str):
            targets = [targets]
        explicit = bool(targets)
        if op == "join" and not targets:
            targets = [face_body] if face_body else [b.name for b in self.m.bodies]
        elif op in ("cut", "intersect") and not targets:
            targets = [b.name for b in self.m.bodies]
        if p.get("to") is not None:
            h = self.face_height(p["to"], P)
            d = h - (frm + so)
            if abs(d) < 1e-9:
                raise EngineRefusal("the To object is where the extrude starts")
            direction = "positive"
        elif p.get("through_all"):
            far = 0.0
            ts = [b for b in self.m.bodies if not targets or b.name in targets]
            if not ts:
                raise EngineRefusal("through all needs a body to cut")
            for b in ts:
                bb = b.shape.BoundBox
                for i in range(8):
                    q = V(bb.XMax if i & 1 else bb.XMin, bb.YMax if i & 2 else bb.YMin, bb.ZMax if i & 4 else bb.ZMin)
                    far = max(far, abs(P.height(q)))
            d = far * 1.02 + 1.0
        else:
            d = num(p["distance"])
        tools = []
        if p.get("taper") is not None and abs(deg(p["taper"])) > 0:
            if direction == "symmetric":
                raise EngineRefusal("not supported yet: taper with two-sided or symmetric extents")
            ang = math.radians(deg(p["taper"]))
            sign = -1.0 if (p.get("to") is None and direction == "negative") else 1.0
            ln, sign = (-d, -sign) if d < 0 else (d, sign)
            base = frm + so
            for r in regions:
                tools.append(tapered(r, n, base, sign, ln, ang))
        else:
            if direction == "positive":
                a, bnd = 0.0, d
            elif direction == "negative":
                a, bnd = -d, 0.0
            elif direction == "symmetric":
                half = d if p.get("through_all") else d / 2
                a, bnd = -half, half
            else:
                raise Unsupported("direction %s" % direction)
            lo, hi = min(a, bnd), max(a, bnd)
            off = frm + so
            for r in regions:
                tools.append(prism(r, n, lo + off, hi + off))
        for t in tools:
            if not t.isValid():
                self.m.log.append("extrude tool invalid")
        self.m.apply(op, tools, targets or [], names, explicit)

    def c_solid_revolve(self, p):
        sk = self.sketch_ref(p)
        P = sk.plane
        regions = select_profiles(sk, p.get("profiles"), False)
        ax = p["axis"]
        if isinstance(ax, dict):
            if set(ax) - {"origin", "dir"}:
                raise Unsupported("axis form %r" % ax)
            o3, d3 = vec(ax.get("origin", [0, 0, 0])), vec(ax["dir"])
            if abs(d3.normalize().dot(P.n)) > 1e-9 or abs(P.height(o3)) > 1e-9:
                raise EngineRefusal("the axis does not lie in the sketch plane")
            o2 = P.local(o3)
            d2 = (d3.dot(P.x), d3.dot(P.y))
        elif ax in ("X", "Y", "Z"):
            d3 = {"X": V(1, 0, 0), "Y": V(0, 1, 0), "Z": V(0, 0, 1)}[ax]
            if abs(d3.dot(P.n)) > 1e-9 or abs(P.height(V(0, 0, 0))) > 1e-9:
                raise EngineRefusal("the %s axis does not lie in the sketch plane" % ax)
            o2 = P.local(V(0, 0, 0))
            d2 = (d3.dot(P.x), d3.dot(P.y))
        elif ax in ("x", "y"):
            o2 = (0.0, 0.0)
            d2 = (1.0, 0.0) if ax == "x" else (0.0, 1.0)
        else:
            k, data = sk.curve_edge(ax)
            if k != "line":
                raise Unsupported("revolve axis %r" % ax)
            a, b = data
            o2, d2 = a, (b[0] - a[0], b[1] - a[1])
        angle = deg(p.get("angle", "360 deg"))
        angle2 = deg(p["angle2"]) if p.get("angle2") is not None else None
        sym = str(p.get("direction", "")).lower() == "symmetric"
        if angle2 is not None:
            start, sweep = -angle2, angle + angle2
        elif sym:
            start, sweep = -angle / 2.0, angle
        else:
            start, sweep = 0.0, angle
        if not (abs(sweep) > 1e-9 and abs(sweep) <= 360 + 1e-9):
            raise EngineRefusal("the revolve angle must be more than 0 and at most 360")
        o = P.w(o2)
        axis = P.dw(d2)
        axis.normalize()
        tools = []
        for r in regions:
            c = r.CenterOfMass
            radial = (c - o) - axis * (c - o).dot(axis)
            A = axis * -1 if axis.cross(radial).dot(P.n) < 0 else V(axis)
            if abs(sweep) >= 360 - 1e-9:
                t = r.revolve(o, A, 360)
            else:
                t = r.revolve(o, A, sweep)
            if abs(start) > 1e-12:
                t.rotate(o, A, start)
            tools.append(t)
        op = op_of(p)
        names = [p["body_name"]] if p.get("body_name") else []
        targets = p.get("targets")
        explicit = bool(targets)
        fb = getattr(P, "face_body", None)
        if op == "join" and not targets:
            targets = [fb] if fb else [b.name for b in self.m.bodies]
        elif op in ("cut", "intersect") and not targets:
            targets = [b.name for b in self.m.bodies]
        self.m.apply(op, tools, targets or [], names, explicit)

    def c_solid_split_body(self, p):
        b = self.m.body(p["body"])
        if b is None:
            raise EngineRefusal("no body %s" % p["body"])
        import BOPTools.SplitAPI as SA
        L = 10 * self.m.size() + 1000
        if p.get("tool"):
            tb = self.m.body(p["tool"]["body"])
            _, f = self.m.pick_face(p["tool"]["point"], tb.name)
            if f.Surface.__class__.__name__ != "Plane":
                raise Unsupported("split by a curved face")
            q = vec(p["tool"]["point"])
            n = normal_at(f, q)
            tool = Part.Plane(q, n).toShape(-L, L, -L, L)
        else:
            pl = p["plane"]
            if isinstance(pl, str):
                P = Plane.named(pl)
                o, n = P.o, P.n
            elif isinstance(pl, dict) and "normal" in pl:
                o, n = vec(pl.get("origin", [0, 0, 0])), vec(pl["normal"])
            else:
                raise Unsupported("split plane %r" % (pl,))
            tool = Part.Plane(o, n).toShape(-L, L, -L, L)
        r = SA.slice(b.shape, [tool], "Split")
        parts = list(r.Solids)
        self.m.log.append("split: %d pieces valid %s" % (len(parts), r.isValid()))
        if len(parts) < 2:
            raise KernelError("the tool does not split the body")
        b.shape = parts[0]
        for k, s in enumerate(parts[1:]):
            nm = "%s (%d)" % (b.name, k + 1)
            while self.m.body(nm):
                nm += "'"
            self.m.bodies.append(Body(nm, s))
        self.split_names = True

    def c_inspect_measure(self, p):
        pass


def measure(m):
    sh = [b.shape for b in m.bodies]
    sol = [s for x in sh for s in x.Solids]
    vol = sum(s.Volume for s in sol)
    area = sum(s.Area for s in sol)
    com = V(0, 0, 0)
    for s in sol:
        com += s.CenterOfMass * s.Volume
    com = com * (1.0 / vol) if vol else com
    res = {
        "body_count": len(m.bodies),
        "body_names": [b.name for b in m.bodies],
        "solids": len(sol),
        "shells": sum(len(s.Shells) for s in sol),
        "volume_mm3": vol,
        "area_mm2": area,
        "faces": sum(len(x.Faces) for x in sh),
        "edges": sum(len(x.Edges) for x in sh),
        "center_of_mass": [com.x, com.y, com.z],
        "valid": all(x.isValid() for x in sh) and all(len(x.Solids) > 0 for x in sh),
        "invalid_bodies": [b.name for b in m.bodies if not b.shape.isValid()],
    }
    if sh:
        bb = Part.makeCompound(sh).optimalBoundingBox()
        res["bbox"] = {"min": [bb.XMin, bb.YMin, bb.ZMin], "max": [bb.XMax, bb.YMax, bb.ZMax]}
    return res


def load_recipe(case):
    r = json.load(open(os.path.join(case, "recipe.json")))
    if "commands" not in r:
        raise Unsupported("oracle recipe format")
    cmds = list(r["commands"])
    if "base" in r:
        base = os.path.normpath(os.path.join(case, r["base"]))
        cmds = load_recipe(base) + cmds
    return cmds


def main():
    case, out = sys.argv[2], sys.argv[3]
    res = {"case": case, "occt": Part.OCC_VERSION}
    log = []
    t0 = time.perf_counter()
    rn = None
    try:
        cmds = load_recipe(case)
        rn = Runner(log)
        rn.run(cmds)
        res["outcome"] = "ok"
        res.update(measure(rn.m))
    except Unsupported as e:
        res["outcome"] = "unsupported"
        res["why"] = str(e)
    except EngineRefusal as e:
        res["outcome"] = "engine_refusal"
        res["error"] = str(e)
        res["step"] = getattr(rn, "step", None)
    except Exception as e:  # OCCT (Part.OCCError, ...) or a replay-side failure
        res["outcome"] = "error"
        res["error"] = "%s: %s" % (type(e).__name__, e)
        res["step"] = getattr(rn, "step", None)
        res["trace"] = traceback.format_exc()[-2000:]
    res["wall_s"] = time.perf_counter() - t0
    res["log"] = log[-60:]
    with open(out, "w") as fh:
        json.dump(res, fh, indent=1)


if __name__ == "__main__":
    main()
