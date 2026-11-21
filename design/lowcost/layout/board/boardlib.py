#!/usr/bin/env python3
"""boardlib: shared infrastructure for the scope-fe board (KiCad 7.0.11 pcbnew Python API).

Sections
  1. Netlist     netlist(), net_of(ref, pad), canon(name), comps / pads / nets of export/scope-fe.net
  2. Stack-up    JLC04161H-7628 constants, microstrip(), cpwg(), width_for(), ps_mm(), c_per_mm(),
                 loaded(), solve_tdu(), W50 ... (copied from layout/phase_trigger/gen_phase_trigger.py)
  3. Block       class Block: new 4-layer board with the stack-up, place-from-netlist, pad(), track()
                 (chamfered, no corner > 45 deg), via(), via_pair(), zone(), keepout(), edge_rect(), text(),
                 iface() -> <block>.ifaces.json, save()
  4. Footprints  FP_ALIAS (part -> KiCad library footprint), FP_CUSTOM (builders for parts / pads that are
                 not in /usr/share/kicad/footprints)
  5. check_board(pcb_path, refs=None, rf_widths=None) -> dict of counts, printed report
  6. merge(master, block_pcb_path, dx, dy, rot_deg, flip=False, ...)
  7. render(pcb_path, out_png, layers, crop=None)

Canonical board net name = the netlist name VERBATIM ("/BUF_OUT_S", "/input/VIN", "GND", "Net-(C106-Pad2)").
This is what KiCad's "Update PCB from schematic" would write, so the scripted board stays compatible with
the schematic.  canon() maps short names ("BUF_OUT_S", "VIN", "input/VIN") to the verbatim name when the
mapping is unique; auto-named nets ("Net-(...)") are best reached through net_of(ref, pad).

Coordinates: mm, +x right, +y down, rotation in degrees counter-clockwise (KiCad convention).  A Block keeps
its local origin at pcbnew coordinate ORG = (100, 100) mm and stores it as the board's aux origin, which
merge() uses as the block origin.  kicad-cli 7 has no DRC / ERC: check_board() is the scripted substitute.
"""
import json, math, os, re, subprocess, tempfile
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
LOWCOST = os.path.normpath(os.path.join(HERE, "..", ".."))
NETLIST = os.path.join(LOWCOST, "kicad", "export", "scope-fe.net")
FPLIB = "/usr/share/kicad/footprints"
# footprint search path: library nickname -> directory holding <nickname>.pretty. "scope-fe" is the project
# library written by kicad/gen/gen_footprints.py (kicad/lib/scope-fe.pretty, also in kicad/fp-lib-table).
FP_PATHS = {"scope-fe": os.path.join(LOWCOST, "kicad", "lib")}
SVG2PNG = os.path.join(LOWCOST, "kicad", "gen", "svg2png.js")
ORG = (100.0, 100.0)
mm = pcbnew.FromMM
CU_LAYERS = {"F.Cu": pcbnew.F_Cu, "In1.Cu": pcbnew.In1_Cu, "In2.Cu": pcbnew.In2_Cu, "B.Cu": pcbnew.B_Cu}


def L(layer):
    """layer name or id -> id"""
    if isinstance(layer, int):
        return layer
    ids = dict(CU_LAYERS, **{"F.SilkS": pcbnew.F_SilkS, "B.SilkS": pcbnew.B_SilkS, "F.Fab": pcbnew.F_Fab,
                             "B.Fab": pcbnew.B_Fab, "Edge.Cuts": pcbnew.Edge_Cuts, "F.CrtYd": pcbnew.F_CrtYd,
                             "B.CrtYd": pcbnew.B_CrtYd, "Dwgs.User": pcbnew.Dwgs_User, "Cmts.User": pcbnew.Cmts_User})
    return ids[layer]


# ============================================================================= 1. netlist
def _sexpr(text):
    """minimal s-expression parser -> nested lists of str"""
    tok = re.compile(r'\(|\)|"((?:[^"\\]|\\.)*)"|([^\s()"]+)')
    stack, cur = [], []
    for m in tok.finditer(text):
        s = m.group(0)
        if s == "(":
            stack.append(cur)
            cur = []
        elif s == ")":
            done = cur
            cur = stack.pop()
            cur.append(done)
        else:
            cur.append(m.group(1).replace('\\"', '"') if m.group(1) is not None else m.group(2))
    return cur[0]


def _find(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


class Netlist:
    """comps {ref: {"value", "footprint" (lib:name), "sheet" ("/input/")}},
    pads {(ref, pad): net}, nets {net: [(ref, pad), ...]} (net names verbatim)."""

    def __init__(self, path=NETLIST):
        with open(path) as f:
            root = _sexpr(f.read())
        self.path = path
        self.comps, self.pads, self.nets = {}, {}, {}
        for comps in _find(root, "components"):
            for c in _find(comps, "comp"):
                d = {k[0]: k[1] for k in c[1:] if isinstance(k, list) and len(k) > 1 and isinstance(k[1], str)}
                sp = _find(c, "sheetpath")
                sheet = _find(sp[0], "names")[0][1] if sp else "/"
                self.comps[d["ref"]] = {"value": d.get("value", ""), "footprint": d.get("footprint", ""),
                                        "sheet": sheet}
        for nets in _find(root, "nets"):
            for n in _find(nets, "net"):
                name = _find(n, "name")[0][1]
                nodes = []
                for nd in _find(n, "node"):
                    d = {k[0]: k[1] for k in nd[1:] if isinstance(k, list)}
                    nodes.append((d["ref"], d["pin"]))
                    self.pads[(d["ref"], d["pin"])] = name
                self.nets[name] = nodes
        self._short = {}
        for name in self.nets:
            for alias in {name, name.lstrip("/"), name.rsplit("/", 1)[-1]}:
                self._short.setdefault(alias, set()).add(name)

    def canon(self, name):
        """short or verbatim net name -> verbatim netlist name (KeyError if unknown, ValueError if ambiguous)"""
        if name in self.nets:
            return name
        hit = self._short.get(name) or self._short.get(name.lstrip("/"))
        if not hit:
            raise KeyError(f"net {name!r} is not in {os.path.basename(self.path)}")
        if len(hit) > 1:
            raise ValueError(f"net {name!r} is ambiguous: {sorted(hit)}")
        return next(iter(hit))

    def net_of(self, ref, pad):
        return self.pads.get((ref, str(pad)))

    def refs(self, sheet=None, prefix_digit=None):
        """refs of a sheet ("input", "/input/") and/or of a hundreds group (1 -> 1xx)"""
        out = []
        for r, c in self.comps.items():
            if sheet and c["sheet"].strip("/") != sheet.strip("/"):
                continue
            if prefix_digit is not None:
                m = re.match(r"[A-Z]+(\d)\d\d$", r)
                if not m or int(m.group(1)) != prefix_digit:
                    continue
            out.append(r)
        return sorted(out)


_NL = None


def netlist():
    global _NL
    if _NL is None:
        _NL = Netlist()
    return _NL


def net_of(ref, pad):
    return netlist().net_of(ref, pad)


def canon(name):
    return netlist().canon(name)


# ============================================================================= 2. stack-up / impedance
# JLC04161H-7628 (jlcpcb.com/impedance): L1 35 um / 7628 prepreg 0.2104 mm er 4.4 / L2 15.2 um / core 1.065 mm
# er 4.6 / L3 15.2 um / 7628 0.2104 mm / L4 35 um.  Mask er 3.8, 15 um over the trace, 30 um over laminate.
H, T_CU, ER, ER_MASK, C_MASK_TR, C_MASK_SUB = 0.2104, 0.035, 4.4, 3.8, 0.015, 0.030
C0 = 0.299792458                                   # mm/ps


def microstrip(w, h=H, t=T_CU, er=ER, mask=True):
    """Hammerstad-Jensen microstrip + Hammerstad thickness correction + first-order solder-mask overlay
    (eps_eff += (er_mask - 1)(1 - q)(1 - exp(-1.2 c / h))).  -> (Z0, eps_eff).  Copied verbatim from
    layout/phase_trigger/gen_phase_trigger.py (lands on JLC's 0.36 mm for 50 R)."""
    u = w / h

    def z_air(x):
        f = 6 + (2 * math.pi - 6) * math.exp(-(30.666 / x) ** 0.7528)
        return 60 * math.log(f / x + math.sqrt(1 + 4 / x ** 2))

    def ee0(x):
        a = 1 + math.log((x ** 4 + (x / 52) ** 2) / (x ** 4 + 0.432)) / 49 + math.log(1 + (x / 18.1) ** 3) / 18.7
        b = 0.564 * ((er - 0.9) / (er + 3)) ** 0.053
        return (er + 1) / 2 + (er - 1) / 2 * (1 + 10 / x) ** (-a * b)
    du1 = t / h / math.pi * math.log(1 + 4 * math.e / (t / h * (1 / math.tanh(math.sqrt(6.517 * u))) ** 2))
    dur = 0.5 * (1 + 1 / math.cosh(math.sqrt(er - 1))) * du1
    u1, ur = u + du1, u + dur
    ee = ee0(ur) * (z_air(u1) / z_air(ur)) ** 2
    if mask:
        q = (ee - 1) / (er - 1)
        ee += (ER_MASK - 1) * (1 - q) * (1 - math.exp(-1.2 * (C_MASK_TR + C_MASK_SUB) / 2 / h))
    return z_air(u1) / math.sqrt(ee), ee


def _K(k):
    a, b = 1.0, math.sqrt(1 - k * k)
    for _ in range(30):
        a, b = (a + b) / 2, math.sqrt(a * b)
    return math.pi / (2 * a)


def cpwg(w, g, h=H, er=ER):
    """conductor-backed coplanar waveguide (t = 0, no mask), Wadell -> (Z0, eps_eff)"""
    k = w / (w + 2 * g)
    k3 = math.tanh(math.pi * w / (4 * h)) / math.tanh(math.pi * (w + 2 * g) / (4 * h))
    r1 = _K(k) / _K(math.sqrt(1 - k * k))
    r3 = _K(k3) / _K(math.sqrt(1 - k3 * k3))
    ee = (1 + er * r3 / r1) / (1 + r3 / r1)
    return 60 * math.pi / math.sqrt(ee) / (r1 + r3), ee


def width_for(z, **kw):
    lo, hi = 0.02, 3.0
    for _ in range(60):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if microstrip(m, **kw)[0] > z else (lo, m)
    return (lo + hi) / 2


def ps_mm(w):
    return math.sqrt(microstrip(w)[1]) / C0


def c_per_mm(w):                                    # pF/mm
    z, ee = microstrip(w)
    return math.sqrt(ee) / (C0 * z)


def loaded(tdu, z, cl):
    """section (delay tdu ps, Z0 z) + lumped cl pF -> (loaded delay ps, loaded Z)"""
    td = math.sqrt(tdu * (tdu + z * cl))
    return td, z * tdu / td


def solve_tdu(z, cl, target):
    lo, hi = 0.5, target
    for _ in range(60):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if loaded(m, z, cl)[0] < target else (lo, m)
    return (lo + hi) / 2


def r01(x):
    return round(x / 0.01) * 0.01


W50 = r01(width_for(50.0))                          # 0.36 mm
Z50, EE50 = microstrip(W50)
PS_MM50 = ps_mm(W50)                                # 6.057 ps/mm
GAP_RF = 2 * W50                                    # F.Cu pour gap for 50 R
W73 = r01(width_for(73.0))                          # 0.16 mm (PSTRB sections)
W_LIN = 0.25                                        # PH_LINE sections (phase_trigger computes 0.25-0.26)
W_SIG, W_PWR, W_GND, W_NODE = 0.2, 0.5, 0.4, 0.15
VIA_D, VIA_DRILL = 0.45, 0.2                        # JLC standard 0.45 / 0.2 mm
VIA_PWR_D, VIA_PWR_DRILL = 0.6, 0.3

STACKUP = """    (stackup
      (layer "F.SilkS" (type "Top Silk Screen"))
      (layer "F.Paste" (type "Top Solder Paste"))
      (layer "F.Mask" (type "Top Solder Mask") (thickness 0.015) (epsilon_r 3.8))
      (layer "F.Cu" (type "copper") (thickness 0.035))
      (layer "dielectric 1" (type "prepreg") (thickness 0.2104) (material "7628") (epsilon_r 4.4) (loss_tangent 0.02))
      (layer "In1.Cu" (type "copper") (thickness 0.0152))
      (layer "dielectric 2" (type "core") (thickness 1.065) (material "FR4") (epsilon_r 4.6) (loss_tangent 0.02))
      (layer "In2.Cu" (type "copper") (thickness 0.0152))
      (layer "dielectric 3" (type "prepreg") (thickness 0.2104) (material "7628") (epsilon_r 4.4) (loss_tangent 0.02))
      (layer "B.Cu" (type "copper") (thickness 0.035))
      (layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.015) (epsilon_r 3.8))
      (layer "B.Paste" (type "Bottom Solder Paste"))
      (layer "B.SilkS" (type "Bottom Silk Screen"))
      (copper_finish "ENIG")
      (dielectric_constraints no)
    )
"""


def setup_board(b, org=ORG):
    """4 copper layers, JLC rules (0.1 mm clearance / track, 0.45 / 0.2 mm via), aux origin = org"""
    b.SetCopperLayerCount(4)
    for lay, name, typ in ((pcbnew.F_Cu, "F.Cu", pcbnew.LT_SIGNAL), (pcbnew.In1_Cu, "In1.Cu", pcbnew.LT_POWER),
                           (pcbnew.In2_Cu, "In2.Cu", pcbnew.LT_POWER), (pcbnew.B_Cu, "B.Cu", pcbnew.LT_SIGNAL)):
        b.SetLayerName(lay, name)
        b.SetLayerType(lay, typ)
    ds = b.GetDesignSettings()
    ds.SetBoardThickness(mm(1.6))
    ds.m_MinClearance = mm(0.1)
    ds.m_TrackMinWidth = mm(0.1)
    ds.m_ViasMinSize = mm(0.4)
    ds.m_MinThroughDrill = mm(0.2)
    ds.SetAuxOrigin(pcbnew.VECTOR2I(mm(org[0]), mm(org[1])))
    nc = ds.m_NetSettings.m_DefaultNetClass
    nc.SetClearance(mm(0.1))
    nc.SetTrackWidth(mm(W_SIG))
    nc.SetViaDiameter(mm(VIA_D))
    nc.SetViaDrill(mm(VIA_DRILL))


def write_stackup(path):
    """pcbnew 7 Python cannot build the stack-up; insert it into the saved file"""
    with open(path) as f:
        s = f.read()
    if "(stackup" not in s:
        s = s.replace("  (setup\n", "  (setup\n" + STACKUP, 1)
        with open(path, "w") as f:
            f.write(s)


def save_board(b, path):
    pcbnew.SaveBoard(path, b)
    write_stackup(path)
    for ext in (".kicad_pro", ".kicad_prl"):
        p = path[:-len(".kicad_pcb")] + ext
        if os.path.exists(p):
            os.remove(p)


# ============================================================================= 4. footprint registry
# The netlist names a KiCad standard footprint for every one of its 454 parts (all exist in
# /usr/share/kicad/footprints, checked by selftest()).  FP_ALIAS documents which library footprint the
# fragments used for each special part; FP_CUSTOM holds builders for footprints that are not library parts
# (fragment-defined).  A FP_CUSTOM entry keyed by a netlist "lib:name" REPLACES the library footprint for
# every part with that footprint (the FPID stays the netlist's lib:name, so check_board still matches);
# keyed by "board:<name>" it is only used through Block.custom().
FP_ALIAS = {
    "BUF802_RGT": "Package_DFN_QFN:VQFN-16-1EP_3x3mm_P0.5mm_EP1.68x1.68mm",
    "TMUX136_RSE": "Package_DFN_QFN:Texas_UQFN-10_1.5x2mm_P0.5mm",
    "TRF37D73_DSG": "Package_SON:WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm",
    "TLV3801_DSG": "Package_SON:WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm",
    "BAT15-04W": "Package_TO_SOT_SMD:SOT-323_SC-70",
    "BAT15-03W": "Diode_SMD:D_SOD-323",
    "SMA_EDGE": "Connector_Coaxial:SMA_Samtec_SMA-J-P-X-ST-EM1_EdgeMount",
    "BALUN_DLW21SN": "Inductor_SMD:L_CommonModeChoke_Coilcraft_0805USB",
    "GW1NZ_QN48": "Package_DFN_QFN:QFN-48-1EP_6x6mm_P0.4mm_EP4.3x4.3mm",
    "MS5351M": "Package_SO:MSOP-10_3x3mm_P0.5mm",
    "LQH32C_47uH": "Inductor_SMD:L_1210_3225Metric",
    "BLM15HD": "Inductor_SMD:L_0402_1005Metric",
    "NETTIE": "NetTie:NetTie-2_SMD_Pad0.5mm",
}
RR = pcbnew.PAD_SHAPE_ROUNDRECT
CIRC = pcbnew.PAD_SHAPE_CIRCLE


def build_footprint(board, name, pads, crt=(0, 0), copper=(), lib="board"):
    """pads [(num, dx, dy, sx, sy, shape)], crt (half x, half y) courtyard, copper [(x0, y0, x1, y1, w)]
    F.Cu segments inside the footprint (net ties)"""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    for num, dx, dy, sx, sy, shape in pads:
        pd = pcbnew.PAD(fp)
        pd.SetNumber(num)
        pd.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pd.SetShape(shape)
        if shape == RR:
            pd.SetRoundRectRadiusRatio(0.1)
        pd.SetLayerSet(pd.SMDMask())
        pd.SetSize(pcbnew.VECTOR2I(mm(sx), mm(sy)))
        pd.SetPosition(pcbnew.VECTOR2I(mm(dx), mm(dy)))
        pd.SetPos0(pcbnew.VECTOR2I(mm(dx), mm(dy)))
        fp.Add(pd)
    cx, cy = crt
    if cx > 0:
        pts = [(-cx, -cy), (cx, -cy), (cx, cy), (-cx, cy), (-cx, -cy)]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            s = pcbnew.FP_SHAPE(fp, pcbnew.SHAPE_T_SEGMENT)
            s.SetLayer(pcbnew.F_CrtYd)
            s.SetWidth(mm(0.05))
            s.SetStart0(pcbnew.VECTOR2I(mm(x0), mm(y0)))
            s.SetEnd0(pcbnew.VECTOR2I(mm(x1), mm(y1)))
            s.SetDrawCoord()
            fp.Add(s)
    for x0, y0, x1, y1, w in copper:
        s = pcbnew.FP_SHAPE(fp, pcbnew.SHAPE_T_SEGMENT)
        s.SetLayer(pcbnew.F_Cu)
        s.SetWidth(mm(w))
        s.SetStart0(pcbnew.VECTOR2I(mm(x0), mm(y0)))
        s.SetEnd0(pcbnew.VECTOR2I(mm(x1), mm(y1)))
        s.SetDrawCoord()
        fp.Add(s)
    if copper and hasattr(fp, "AddNetTiePadGroup"):
        fp.AddNetTiePadGroup(", ".join(p[0] for p in pads))
    return fp


FP_CUSTOM = {
    # sampler fragment's balun land (pad map 1/3 | 2/4, i.e. NOT the Coilcraft library map 1/4 | 2/3);
    # use only after the DLW21SN pin map is checked against the Murata drawing
    "board:CMC_0805_balun_fragment": lambda b: build_footprint(
        b, "CMC_0805_balun_fragment",
        [("1", 0.835, -0.435, 0.76, 0.51, RR), ("3", 0.835, 0.435, 0.76, 0.51, RR),
         ("2", -0.835, -0.435, 0.76, 0.51, RR), ("4", -0.835, 0.435, 0.76, 0.51, RR)], (1.47, 0.94)),
    # sampler fragment's stub short: 0.36 mm pad on the stub end, 0.7 mm GND pad, F.Cu bar 0.36 mm
    "board:NetTie_stub_short": lambda b: build_footprint(
        b, "NetTie_stub_short", [("1", 0, -0.5, 0.36, 0.36, CIRC), ("2", 0, 0.4, 0.7, 0.7, CIRC)],
        copper=[(0, -0.5, 0, 0.4, W50)]),
    # interface / test pads used by the fragments (not netlist parts: do not use on the final board)
    "board:IF_pad": lambda b: build_footprint(b, "IF_pad", [("1", 0, 0, 0.6, 0.5, RR)]),
}


def load_footprint(board, fpid):
    if fpid in FP_CUSTOM:
        fp = FP_CUSTOM[fpid](board)
    else:
        lib, name = fpid.split(":", 1)
        base = FP_PATHS.get(lib, FPLIB)
        fp = pcbnew.FootprintLoad(os.path.join(base, lib + ".pretty"), name)
        if fp is None:
            raise KeyError(f"footprint {fpid} not found in {base}")
    lib, name = fpid.split(":", 1)
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


# ============================================================================= 3. block builder
class Block:
    """b = Block("analog"); b.place("U101", x, y, rot); b.track("BUF_OUT_S", W50, [("U101", "10"), (x, y)]);
    b.iface("BUF_OUT_T", x, y, "F.Cu", "E", "rf50"); b.edge_rect(0, 0, w, h); b.save(dirname)"""

    def __init__(self, name, org=ORG):
        self.name, self.org = name, org
        self.nl = netlist()
        self._tmp = tempfile.mkdtemp(prefix=f"block_{name}_")
        self.b = pcbnew.NewBoard(os.path.join(self._tmp, name + ".kicad_pcb"))
        setup_board(self.b, org)
        self.nets, self.fps, self.ifaces, self.routes = {}, {}, [], {}
        self.polys = []                     # (label, points) for the 45-degree check

    # --- coordinates / nets
    def P(self, x, y):
        return pcbnew.VECTOR2I(mm(x + self.org[0]), mm(y + self.org[1]))

    def loc(self, v):
        return (pcbnew.ToMM(v.x) - self.org[0], pcbnew.ToMM(v.y) - self.org[1])

    def net(self, name):
        """netlist net (short names allowed); a net that is not in the netlist raises"""
        name = self.nl.canon(name)
        if name not in self.nets:
            n = pcbnew.NETINFO_ITEM(self.b, name)
            self.b.Add(n)
            self.nets[name] = n
        return self.nets[name]

    # --- parts
    def place(self, ref, x, y, rot=0, side="F"):
        """footprint and nets come from the netlist; side "B" = flipped left-right about (x, y) after rotating"""
        c = self.nl.comps[ref]
        fp = load_footprint(self.b, c["footprint"])
        fp.SetReference(ref)
        fp.SetValue(c["value"])
        fp.SetPosition(self.P(x, y))
        fp.SetOrientationDegrees(rot)
        for pd in fp.Pads():
            n = self.nl.net_of(ref, pd.GetNumber())
            if n is not None:
                pd.SetNet(self.net(n))
        if side == "B":
            fp.Flip(self.P(x, y), True)
        fp.Reference().SetLayer(pcbnew.B_Fab if side == "B" else pcbnew.F_Fab)
        fp.Reference().SetTextSize(pcbnew.VECTOR2I(mm(0.3), mm(0.3)))
        fp.Reference().SetTextThickness(mm(0.05))
        fp.Reference().SetPosition(fp.GetPosition())
        fp.Value().SetVisible(False)
        self.b.Add(fp)
        self.fps[ref] = fp
        return fp

    def tline(self, ref, pts, width=W50, layer="F.Cu", ch=0.45):
        """netlist transmission-line part (TL401..TL403, no library footprint): a custom footprint
        "board:TLine_<ref>" whose F.Cu copper IS the line (chamfered polyline, net-tie group 1, 3), pad 1 at the
        first point, pad 3 at the last (pins 2 / 4 = GND reference are the In1 plane, no pads).  Returns the
        drawn polyline (local mm) and its length."""
        pts = [self.pad(*p) if isinstance(p[0], str) else p for p in pts]
        q = chamfer(pts, ch) if len(pts) > 2 else pts
        x0, y0 = q[0]
        fp = build_footprint(self.b, "TLine_" + ref,
                             [("1", 0, 0, width, width, CIRC), ("3", q[-1][0] - x0, q[-1][1] - y0, width, width, CIRC)],
                             copper=[(a[0] - x0, a[1] - y0, c[0] - x0, c[1] - y0, width) for a, c in zip(q, q[1:])])
        if hasattr(fp, "AddNetTiePadGroup"):
            pass
        for gr in list(fp.GraphicalItems()):
            if gr.GetLayer() == pcbnew.F_Cu and layer != "F.Cu":
                gr.SetLayer(L(layer))
        fp.SetReference(ref)
        fp.SetValue(self.nl.comps[ref]["value"])
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)
        fp.SetPosition(self.P(x0, y0))
        for pd in fp.Pads():
            pd.SetNet(self.net(self.nl.net_of(ref, pd.GetNumber())))
        self.b.Add(fp)
        self.fps[ref] = fp
        self.polys.append((ref, q))
        return q, plen(q)

    def pad(self, ref, num):
        """local (x, y) of a pad; num "@NET" picks the pad on that net"""
        for p in self.fps[ref].Pads():
            if p.GetNumber() == str(num) or (str(num)[0] == "@" and p.GetNetname() == self.nl.canon(num[1:])):
                return self.loc(p.GetPosition())
        raise KeyError((ref, num))

    def pad_obj(self, ref, num):
        return [p for p in self.fps[ref].Pads() if p.GetNumber() == str(num)][0]

    # --- copper
    def track(self, netname, width, pts, layer="F.Cu", name=None, z=None, ch=0.2):
        """polyline (points or (ref, pad)); every corner > 45 deg is cut by a 45-degree chamfer of leg ch;
        raises if a corner sharper than 45 deg remains (no 90-degree corners by construction)"""
        pts = [self.pad(*p) if isinstance(p[0], str) else p for p in pts]
        q = [pts[0]]
        for p in pts[1:]:
            if math.hypot(p[0] - q[-1][0], p[1] - q[-1][1]) > 1e-6:
                q.append(p)
        if len(q) > 2:
            q = chamfer(q, ch)
        for a, b_, c in zip(q, q[1:], q[2:]):
            if turn_deg(a, b_, c) > 45.5:
                raise ValueError(f"{netname}: corner {turn_deg(a, b_, c):.0f} deg at {b_} (chamfer leg too short)")
        n = self.net(netname)
        for (x0, y0), (x1, y1) in zip(q, q[1:]):
            t = pcbnew.PCB_TRACK(self.b)
            t.SetStart(self.P(x0, y0))
            t.SetEnd(self.P(x1, y1))
            t.SetWidth(mm(width))
            t.SetLayer(L(layer))
            t.SetNet(n)
            self.b.Add(t)
        if name:
            r = self.routes.setdefault(name, {"net": n.GetNetname(), "width": width, "z": z, "pts": []})
            r["pts"].append(q)
        self.polys.append((name or netname, q))
        return q

    def route_len(self, name):
        return sum(plen(q) for q in self.routes[name]["pts"])

    def via(self, x, y, netname, dia=VIA_D, drill=VIA_DRILL):
        v = pcbnew.PCB_VIA(self.b)
        v.SetPosition(self.P(x, y))
        v.SetDrill(mm(drill))
        v.SetWidth(mm(dia))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetNet(self.net(netname))
        self.b.Add(v)
        return v

    def via_pair(self, x, y, netname, dx=0.0, dy=0.7, dia=VIA_D, drill=VIA_DRILL):
        """two vias side by side (supply / GND at a decoupling capacitor pad)"""
        return [self.via(x - dx / 2, y - dy / 2, netname, dia, drill), self.via(x + dx / 2, y + dy / 2, netname, dia, drill)]

    def zone(self, netname, layers, pts, clearance=0.2, prio=0, minw=0.2, thermal=False):
        z = pcbnew.ZONE(self.b)
        ls = pcbnew.LSET()
        for l_ in layers:
            ls.AddLayer(L(l_))
        z.SetLayerSet(ls)
        z.SetNet(self.net(netname))
        z.SetLocalClearance(mm(clearance))
        z.SetMinThickness(mm(minw))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL if thermal else pcbnew.ZONE_CONNECTION_FULL)
        z.SetAssignedPriority(prio)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_AREA)
        z.SetMinIslandArea(int(mm(1.0)) * int(mm(1.0)))
        self._outline(z, pts)
        self.b.Add(z)
        return z

    def keepout(self, pts, layers=("F.Cu",), tracks=False, vias=False):
        """rule area: no copper pour (optionally no tracks / vias)"""
        z = pcbnew.ZONE(self.b)
        ls = pcbnew.LSET()
        for l_ in layers:
            ls.AddLayer(L(l_))
        z.SetLayerSet(ls)
        z.SetIsRuleArea(True)
        z.SetDoNotAllowCopperPour(True)
        z.SetDoNotAllowTracks(tracks)
        z.SetDoNotAllowVias(vias)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        self._outline(z, pts)
        self.b.Add(z)
        return z

    def rf_keepout(self, track_pts, width, gap=None, layer="F.Cu"):
        """pour keep-out of gap (default 2 w) around every segment of an RF polyline"""
        g = (2 * width if gap is None else gap) + width / 2
        for (x0, y0), (x1, y1) in zip(track_pts, track_pts[1:]):
            ux, uy = x1 - x0, y1 - y0
            n = math.hypot(ux, uy)
            ux, uy = ux / n * g, uy / n * g
            self.keepout([(x0 - ux - uy, y0 - uy + ux), (x1 + ux - uy, y1 + uy + ux),
                          (x1 + ux + uy, y1 + uy - ux), (x0 - ux + uy, y0 - uy - ux)], (layer,))

    def _outline(self, z, pts):
        ol = z.Outline()
        ol.NewOutline()
        for x, y in pts:
            ol.Append(mm(x + self.org[0]), mm(y + self.org[1]))

    # --- graphics
    def line(self, x0, y0, x1, y1, layer="Edge.Cuts", w=0.1):
        s = pcbnew.PCB_SHAPE(self.b)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(self.P(x0, y0))
        s.SetEnd(self.P(x1, y1))
        s.SetLayer(L(layer))
        s.SetWidth(mm(w))
        self.b.Add(s)
        return s

    def edge_rect(self, x0, y0, x1, y1, layer="Edge.Cuts"):
        for a, c in zip(rect_pts(x0, y0, x1, y1), rect_pts(x0, y0, x1, y1)[1:] + [(x0, y0)]):
            self.line(*a, *c, layer=layer)

    def circle(self, x, y, r, layer="Edge.Cuts", w=0.1):
        s = pcbnew.PCB_SHAPE(self.b)
        s.SetShape(pcbnew.SHAPE_T_CIRCLE)
        s.SetCenter(self.P(x, y))
        s.SetEnd(self.P(x + r, y))
        s.SetLayer(L(layer))
        s.SetWidth(mm(w))
        self.b.Add(s)

    def text(self, s, x, y, size=0.4, layer="F.SilkS", rot=0):
        t = pcbnew.PCB_TEXT(self.b)
        t.SetText(s)
        t.SetPosition(self.P(x, y))
        t.SetLayer(L(layer))
        t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
        t.SetTextThickness(mm(size * 0.15))
        t.SetTextAngleDegrees(rot)
        if layer.startswith("B."):
            t.SetMirrored(True)
        self.b.Add(t)
        return t

    # --- interfaces
    def iface(self, netname, x, y, layer, side, cls="slow", width=None, note=""):
        """record an inter-block connection point: side N/E/S/W of the block, cls rf50 / pair / slow / supply"""
        self.ifaces.append({"net": self.nl.canon(netname), "x": round(x, 4), "y": round(y, 4), "layer": layer,
                            "side": side, "class": cls, "width": width, "note": note})

    def save(self, out_dir=None):
        out_dir = out_dir or os.getcwd()
        path = os.path.join(out_dir, self.name + ".kicad_pcb")
        save_board(self.b, path)
        with open(os.path.join(out_dir, self.name + ".ifaces.json"), "w") as f:
            json.dump({"block": self.name, "origin": "local (0, 0) = pcbnew " + str(self.org),
                       "ifaces": self.ifaces}, f, indent=1)
        return path


# ============================================================================= geometry helpers
def rect_pts(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def plen(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def turn_deg(a, b, c):
    """direction change at b of the polyline a-b-c (0 = straight)"""
    v1, v2 = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
    n = math.hypot(*v1) * math.hypot(*v2)
    if n == 0:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / n))))


def chamfer(pts, c):
    """cut every corner sharper than 45 deg by 45-degree steps: 90 deg -> one 45-degree chamfer, 135 deg ->
    two (leg c, limited by the legs).  Copied from the fragments, extended to > 90 deg."""
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        (xa, ya), (xb, yb), (xc, yc) = out[-1], pts[i], pts[i + 1]
        la, lc = math.hypot(xb - xa, yb - ya), math.hypot(xc - xb, yc - yb)
        if la < 1e-9 or lc < 1e-9:
            continue
        v1 = ((xb - xa) / la, (yb - ya) / la)
        v2 = ((xc - xb) / lc, (yc - yb) / lc)
        ang = math.degrees(math.acos(max(-1, min(1, v1[0] * v2[0] + v1[1] * v2[1]))))
        if ang < 45.5:
            out.append((xb, yb))
            continue
        cc = min(c, la / 2.01 if i > 1 else la * 0.99, lc / 2.01 if i < len(pts) - 2 else lc * 0.99)
        if ang < 91:
            out.append((xb - v1[0] * cc, yb - v1[1] * cc))
            out.append((xb + v2[0] * cc, yb + v2[1] * cc))
        else:                                  # two 45-degree-ish steps through the bisector direction
            bx, by = v2[0] - v1[0], v2[1] - v1[1]
            nb = math.hypot(bx, by)
            bx, by = bx / nb, by / nb
            p1 = (xb - v1[0] * cc, yb - v1[1] * cc)
            p2 = (p1[0] + bx * cc * 0.8, p1[1] + by * cc * 0.8)
            out += [p1, p2, (xb + v2[0] * cc, yb + v2[1] * cc)]
    out.append(pts[-1])
    return out


def courtyard_overlaps(b, min_area=0.005):
    """COURTYARD RULE: same-side footprint courtyards (F.CrtYd / B.CrtYd, BuildCourtyardCaches + GetCourtyard)
    intersected pairwise (BooleanIntersection); pairs with an intersection area > min_area mm2 are returned.
    b: pcbnew.BOARD or path."""
    if isinstance(b, str):
        b = pcbnew.LoadBoard(b)
    cs = []
    for f in b.GetFootprints():
        f.BuildCourtyardCaches()
        for lay in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            ps = f.GetCourtyard(lay)
            if ps.OutlineCount():
                cs.append((f.GetReference(), lay, ps, ps.BBox()))
    hits = []
    for i in range(len(cs)):
        for j in range(i + 1, len(cs)):
            a_, c_ = cs[i], cs[j]
            if a_[1] != c_[1] or not a_[3].Intersects(c_[3]):
                continue
            x_ = pcbnew.SHAPE_POLY_SET(a_[2])
            x_.BooleanIntersection(c_[2], pcbnew.SHAPE_POLY_SET.PM_FAST)
            ar = x_.Area() / 1e12
            if ar > min_area:
                hits.append(f"{a_[0]}/{c_[0]} {'F' if a_[1] == pcbnew.F_CrtYd else 'B'} {ar:.3f} mm2")
    return hits


# ============================================================================= 5. check_board
def _fpid(fp):
    i = fp.GetFPID()
    return f"{i.GetLibNickname()}:{i.GetLibItemName()}"


def check_board(pcb_path, refs=None, rf_widths=None, rf_gap=True, fill=True, clearance=0.1, verbose=10,
                quiet=False):
    """Compare a board / block with export/scope-fe.net and run the scripted checks.
    refs: iterable of netlist refs the board should contain (default: all 454); a callable(ref) also works.
    rf_widths: {net (short names ok): width mm} -> width deviations and (rf_gap) F.Cu pour gap >= 2 w.
    Returns a dict of counts."""
    nl = netlist()
    b = pcbnew.LoadBoard(pcb_path)
    if refs is None:
        want = set(nl.comps)
    elif callable(refs):
        want = {r for r in nl.comps if refs(r)}
    else:
        want = set(refs)
    fps = list(b.GetFootprints())
    have = {}
    dup = []
    for fp in fps:
        r = fp.GetReference()
        if r in have:
            dup.append(r)
        have[r] = fp
    R = {k: [] for k in ("pad_missing", "missing", "extra", "duplicate", "footprint", "footprint_nolib", "value", "pad_net",
                         "pad_net_short", "pad_nonet", "pad_unknown", "unrouted", "clearance", "corner",
                         "pad_axis", "rf_width", "rf_gap", "courtyard")}
    R["duplicate"] = dup
    R["missing"] = sorted(want - set(have))
    R["extra"] = sorted(set(have) - want)
    for r, fp in have.items():
        if r not in want or r not in nl.comps:
            continue
        c = nl.comps[r]
        fid = _fpid(fp)
        if not c["footprint"]:                     # TL401..403: copper-only part, board:TLine_<ref>
            if fid != f"board:TLine_{r}":
                R["footprint"].append(f"{r}: {fid} != board:TLine_{r}")
        elif fid != c["footprint"]:
            if fid.split(":")[0] == "" or fid.split(":")[0].endswith("fragment"):
                if fid.split(":", 1)[1] == c["footprint"].split(":", 1)[1]:
                    R["footprint_nolib"].append(r)
                    fid = c["footprint"]
            if fid != c["footprint"]:
                R["footprint"].append(f"{r}: {fid} != {c['footprint']}")
        if fp.GetValue() != c["value"]:
            R["value"].append(f"{r}: {fp.GetValue()} != {c['value']}")
        bnums = {p.GetNumber() for p in fp.Pads()}
        for (rr, num), nn in nl.pads.items():
            if rr == r and num not in bnums and not (not c["footprint"] and nn == "GND"):
                R["pad_missing"].append(f"{r}.{num} ({nn})")
        for p in fp.Pads():
            num = p.GetNumber()
            if not num or p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                continue
            want_net = nl.net_of(r, num)
            got = p.GetNetname()
            if want_net is None:
                if got:
                    R["pad_unknown"].append(f"{r}.{num} ({got}) not in netlist")
                continue
            if not got:
                R["pad_nonet"].append(f"{r}.{num} (want {want_net})")
            elif got != want_net:
                try:
                    same = nl.canon(got) == want_net
                except (KeyError, ValueError):
                    same = False
                (R["pad_net_short"] if same else R["pad_net"]).append(f"{r}.{num}: {got} != {want_net}")
    # --- connectivity after zone fill
    if fill:
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    b.BuildConnectivity()
    cn = b.GetConnectivity()
    R["unrouted"] = unrouted_nets(b)
    n_unconn = cn.GetUnconnectedCount(False)
    # --- clearance (tracks / vias vs everything, pads vs pads of other parts), grid-bucketed
    CLR = mm(clearance) - 1000
    cu = list(CU_LAYERS.values())
    tracks = list(b.GetTracks())
    pads = [p for fp in fps for p in fp.Pads() if p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH]
    items = [(t, t.GetBoundingBox()) for t in tracks] + [(p, p.GetBoundingBox()) for p in pads]
    G = mm(1.0)
    grid = {}
    for i, (it, bb) in enumerate(items):
        for gx in range((bb.GetX() - G // 4) // G, (bb.GetRight() + G // 4) // G + 1):
            for gy in range((bb.GetY() - G // 4) // G, (bb.GetBottom() + G // 4) // G + 1):
                grid.setdefault((gx, gy), []).append(i)
    seen = set()
    for cell in grid.values():
        for ii, i in enumerate(cell):
            a, ba = items[i]
            for j in cell[ii + 1:]:
                key = (i, j) if i < j else (j, i)
                if key in seen:
                    continue
                seen.add(key)
                c, bc = items[j]
                if a.GetNetCode() == c.GetNetCode() and a.GetNetCode() > 0:
                    continue
                pa, pc = isinstance(a, pcbnew.PAD), isinstance(c, pcbnew.PAD)
                if pa and pc and a.GetParent() is c.GetParent():
                    continue
                if pa and pc and a.GetNetCode() == c.GetNetCode():
                    continue
                if not ba.Inflate(CLR).Intersects(bc):
                    continue
                for lay in cu:
                    if a.IsOnLayer(lay) and c.IsOnLayer(lay) and \
                            a.GetEffectiveShape(lay).Collide(c.GetEffectiveShape(lay), CLR):
                        def who(x):
                            if isinstance(x, pcbnew.PAD):
                                return f"{x.GetParent().GetReference()}.{x.GetNumber()}"
                            return ("via " if isinstance(x, pcbnew.PCB_VIA) else "") + x.GetNetname()
                        pos = a.GetPosition()
                        R["clearance"].append(f"{who(a)} / {who(c)} on {b.GetLayerName(lay)} at "
                                              f"({pcbnew.ToMM(pos.x):.2f}, {pcbnew.ToMM(pos.y):.2f})")
                        break
    # --- corners: degree-2 track joints sharper than 45 deg (joints inside a pad of the net are excused)
    ends = {}
    for t in tracks:
        if isinstance(t, pcbnew.PCB_VIA) or t.GetClass() == "PCB_ARC":
            continue
        s, e = t.GetStart(), t.GetEnd()
        if s == e:
            continue
        for p, o in ((s, e), (e, s)):
            ends.setdefault((t.GetNetCode(), t.GetLayer(), p.x, p.y), []).append((o.x, o.y))
    pad_by_net = {}
    for p in pads:
        pad_by_net.setdefault(p.GetNetCode(), []).append(p)

    def in_pad(net, x, y, lay):
        for p in pad_by_net.get(net, []):
            if p.IsOnLayer(lay) and p.HitTest(pcbnew.VECTOR2I(x, y)):
                return p
        return None
    for (net, lay, x, y), others in ends.items():
        pd = in_pad(net, x, y, lay)
        if pd is not None:
            # pad-axis rule: a track leaving a pad runs along a pad axis (pad orientation 0 / 90 deg)
            for ox, oy in others:
                ang = (math.degrees(math.atan2(oy - y, ox - x)) - pd.GetOrientationDegrees()) % 90
                if min(ang, 90 - ang) > 1.0:
                    R["pad_axis"].append(f"{pd.GetParent().GetReference()}.{pd.GetNumber()} "
                                         f"({pcbnew.ToMM(x):.2f}, {pcbnew.ToMM(y):.2f})")
            continue
        if len(others) != 2:
            continue
        (ax, ay), (cx, cy) = others
        tdeg = turn_deg((ax, ay), (x, y), (cx, cy))
        if tdeg > 45.5:
            R["corner"].append(f"{b.FindNet(net).GetNetname() if hasattr(b, 'FindNet') else net} "
                               f"{tdeg:.0f} deg at ({pcbnew.ToMM(x):.2f}, {pcbnew.ToMM(y):.2f})")
    # --- RF widths and pour gap
    if rf_widths:
        tab = {}
        for k, w in rf_widths.items():
            try:
                tab[nl.canon(k)] = w
            except (KeyError, ValueError):
                tab[k] = w
        rf_tracks = [t for t in tracks if not isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() in tab]
        for t in rf_tracks:
            w = pcbnew.ToMM(t.GetWidth())
            if abs(w - tab[t.GetNetname()]) > 0.005:
                R["rf_width"].append(f"{t.GetNetname()} {w:.3f} != {tab[t.GetNetname()]:.3f} at "
                                     f"({pcbnew.ToMM(t.GetStart().x):.2f}, {pcbnew.ToMM(t.GetStart().y):.2f})")
        if rf_gap:
            pours = [z for z in b.Zones() if not z.GetIsRuleArea() and z.IsOnLayer(pcbnew.F_Cu)]
            for t in rf_tracks:
                if t.GetLayer() != pcbnew.F_Cu:
                    continue
                w = pcbnew.ToMM(t.GetWidth())
                for z in pours:
                    if z.GetNetname() == t.GetNetname():
                        continue
                    fl = z.GetFilledPolysList(pcbnew.F_Cu)
                    s, e = t.GetStart(), t.GetEnd()
                    hit = False
                    for i in range(11):
                        u = i / 10
                        pt = pcbnew.VECTOR2I(int(s.x + u * (e.x - s.x)), int(s.y + u * (e.y - s.y)))
                        if fl.Collide(pt, mm(2.5 * w - 0.02)):
                            hit = True
                            break
                    if hit:
                        R["rf_gap"].append(f"{t.GetNetname()} / pour {z.GetNetname()} at "
                                           f"({pcbnew.ToMM(s.x):.2f}, {pcbnew.ToMM(s.y):.2f})")
                        break
    R["courtyard"] = courtyard_overlaps(b)
    counts = {k: len(v) for k, v in R.items()}
    counts["unconnected_items"] = n_unconn
    counts["footprints"] = len(fps)
    counts["tracks"] = sum(1 for t in tracks if not isinstance(t, pcbnew.PCB_VIA))
    counts["vias"] = sum(1 for t in tracks if isinstance(t, pcbnew.PCB_VIA))
    if not quiet:
        print(f"check_board {os.path.basename(pcb_path)}: {len(fps)} footprints, {counts['tracks']} tracks, "
              f"{counts['vias']} vias; expected refs {len(want)}")
        labels = {"pad_missing": "netlist pads absent on the footprint", "missing": "missing refs", "extra": "extra refs (not expected)", "duplicate": "duplicate refs",
                  "footprint": "footprint mismatch (lib:name)", "footprint_nolib": "footprint name ok, lib nickname missing",
                  "value": "value mismatch", "pad_net": "pad-net mismatch",
                  "pad_net_short": "pad-net differs only by the /sheet/ prefix", "pad_nonet": "pads without net",
                  "pad_unknown": "pads with a net the netlist does not list",
                  "unrouted": "nets with unrouted connections (after fill)", "clearance": f"clearance < {clearance} mm",
                  "corner": "track corners > 45 deg", "pad_axis": "tracks leaving a pad off-axis",
                  "rf_width": "RF width deviations", "rf_gap": "RF pour gap < 2 w",
                  "courtyard": "courtyard overlaps (same side, > 0.005 mm2)"}
        for k, lab in labels.items():
            v = R[k]
            print(f"  {lab:50s} {len(v):5d}" + ("" if not v or not verbose else "   e.g. " + "; ".join(v[:verbose])))
        print(f"  {'unconnected items (pcbnew connectivity)':50s} {n_unconn:5d}")
    counts["details"] = R
    return counts


def unrouted_nets(b):
    """own connectivity (pcbnew 7 does not wrap RN_NET): union-find over pads, tracks, vias and filled zone
    islands of one net touching on a common copper layer -> ["net (n missing links)"]; call after zone fill"""
    items = []
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() > 0:
                items.append(p)
    items += [t for t in b.GetTracks() if t.GetNetCode() > 0]
    for z in b.Zones():
        if z.GetIsRuleArea() or z.GetNetCode() <= 0:
            continue
        for lay in z.GetLayerSet().CuStack():
            fl = z.GetFilledPolysList(lay)
            for i in range(fl.OutlineCount()):
                sub = pcbnew.SHAPE_POLY_SET()
                sub.AddOutline(fl.Outline(i))
                for h in range(fl.HoleCount(i)):
                    sub.AddHole(fl.Hole(i, h))
                items.append(("zone", z.GetNetCode(), lay, sub, sub.BBox()))
    par = list(range(len(items)))

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i

    def info(it):
        if isinstance(it, tuple):
            return it[1], {it[2]}, it[4]
        return it.GetNetCode(), {l_ for l_ in CU_LAYERS.values() if it.IsOnLayer(l_)}, it.GetBoundingBox()
    byn = {}
    for i, it in enumerate(items):
        byn.setdefault(info(it)[0], []).append(i)
    out = []
    for code, idx in byn.items():
        inf = {i: info(items[i]) for i in idx}
        for a_ in range(len(idx)):
            i = idx[a_]
            _, la, ba = inf[i]
            for j in idx[a_ + 1:]:
                _, lc, bc = inf[j]
                common = la & lc
                if not common or not ba.Intersects(bc):
                    continue
                if find(i) == find(j):
                    continue
                A, C = items[i], items[j]
                if isinstance(A, tuple) and isinstance(C, tuple):
                    continue
                for lay in common:
                    if isinstance(A, tuple):
                        hit = C.GetEffectiveShape(lay).Collide(A[3], 0)
                    elif isinstance(C, tuple):
                        hit = A.GetEffectiveShape(lay).Collide(C[3], 0)
                    else:
                        hit = A.GetEffectiveShape(lay).Collide(C.GetEffectiveShape(lay), 0)
                    if hit:
                        par[find(i)] = find(j)
                        break
        roots = {find(i) for i in idx if isinstance(items[i], pcbnew.PAD)}
        if len(roots) > 1:
            out.append(f"{b.FindNet(code).GetNetname()} ({len(roots) - 1})")
    return sorted(out)


# ============================================================================= 6. merge
def _block_origin(bb):
    o = bb.GetDesignSettings().GetAuxOrigin()
    if o.x or o.y:
        return o
    edge = [d for d in bb.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
    if edge:
        box = edge[0].GetBoundingBox()
        for d in edge[1:]:
            box.Merge(d.GetBoundingBox())
        return pcbnew.VECTOR2I(box.GetX(), box.GetY())
    return pcbnew.VECTOR2I(0, 0)


def merge(master, block_pcb_path, dx, dy, rot_deg=0.0, flip=False, skip_edge=True, skip_planes=False,
          origin=None, ref_map=None):
    """Append a block board to master (pcbnew.BOARD).  The block's local origin (its aux origin, else the
    top-left of its Edge.Cuts) is flipped (left-right, optional), rotated by rot_deg (CCW) about itself and
    moved to master-local (dx, dy) (master aux origin + offset).  Nets are mapped by name (created in the
    master if absent).  skip_edge drops the block's Edge.Cuts; skip_planes drops its zones on In1 / In2.
    ref_map: optional {old_ref: new_ref}.  Returns {"footprints", "tracks", "zones", "drawings", "nets"}."""
    bb = pcbnew.LoadBoard(block_pcb_path)
    o = origin if origin is not None else _block_origin(bb)
    mo = master.GetDesignSettings().GetAuxOrigin()
    target = pcbnew.VECTOR2I(mo.x + mm(dx), mo.y + mm(dy))
    shift = pcbnew.VECTOR2I(target.x - o.x, target.y - o.y)
    ang = pcbnew.EDA_ANGLE(rot_deg, pcbnew.DEGREES_T)
    mnets = {}

    def mnet(ni):
        name = ni.GetNetname()
        if not name:
            return None
        if name not in mnets:
            n = master.FindNet(name)
            if n is None:
                n = pcbnew.NETINFO_ITEM(master, name)
                master.Add(n)
            mnets[name] = n
        return mnets[name]

    def xform(it):
        if flip:
            it.Flip(o, True)
        if rot_deg:
            it.Rotate(o, ang)
        it.Move(shift)
    cnt = {"footprints": 0, "tracks": 0, "zones": 0, "drawings": 0}
    for fp in list(bb.GetFootprints()):
        nets = [(p, mnet(p.GetNet())) for p in fp.Pads()]
        bb.Remove(fp)
        xform(fp)
        if ref_map and fp.GetReference() in ref_map:
            fp.SetReference(ref_map[fp.GetReference()])
        master.Add(fp)
        for p, n in nets:
            if n is not None:
                p.SetNet(n)
            else:
                p.SetNetCode(0)
        cnt["footprints"] += 1
    for t in list(bb.GetTracks()):
        n = mnet(t.GetNet())
        bb.Remove(t)
        xform(t)
        master.Add(t)
        if n is not None:
            t.SetNet(n)
        cnt["tracks"] += 1
    for z in list(bb.Zones()):
        if skip_planes and not z.GetIsRuleArea() and (z.IsOnLayer(pcbnew.In1_Cu) or z.IsOnLayer(pcbnew.In2_Cu)):
            continue
        n = None if z.GetIsRuleArea() else mnet(z.GetNet())
        bb.Remove(z)
        xform(z)
        master.Add(z)
        if n is not None:
            z.SetNet(n)
        cnt["zones"] += 1
    for d in list(bb.GetDrawings()):
        if skip_edge and d.GetLayer() == pcbnew.Edge_Cuts:
            continue
        bb.Remove(d)
        xform(d)
        master.Add(d)
        cnt["drawings"] += 1
    cnt["nets"] = len(mnets)
    return cnt


def new_master(w, h, holes=((3, 3), None, None, None), org=ORG):
    """empty 4-layer board with outline w x h at local (0, 0) and 4 M3 holes (MountingHole_3.2mm_M3) 3 mm in"""
    blk = Block("master", org)
    blk.edge_rect(0, 0, w, h)
    for i, (x, y) in enumerate(((3, 3), (w - 3, 3), (3, h - 3), (w - 3, h - 3))):
        fp = pcbnew.FootprintLoad(os.path.join(FPLIB, "MountingHole.pretty"), "MountingHole_3.2mm_M3")
        fp.SetReference(f"H{i + 1}")
        fp.SetPosition(blk.P(x, y))
        blk.b.Add(fp)
    return blk


# ============================================================================= 7. render
def render(pcb_path, out_png, layers=("F.Cu", "F.SilkS", "F.Fab", "Edge.Cuts"), crop=None, mirror=False,
           tmpdir=None):
    """kicad-cli pcb export svg (board area) -> PNG (playwright, kicad/gen/svg2png.js, 3200 px wide).
    crop = (x0, y0, x1, y1) in pcbnew mm: crops the SVG viewBox before rasterising."""
    tmpdir = tmpdir or tempfile.mkdtemp(prefix="render_")
    base = os.path.splitext(os.path.basename(out_png))[0]
    svg = os.path.join(tmpdir, base + ".svg")
    cmd = ["kicad-cli", "pcb", "export", "svg", "--layers", ",".join(layers), "--exclude-drawing-sheet",
           "--page-size-mode", "2", "-o", svg, pcb_path]
    if mirror:
        cmd.insert(4, "--mirror")
    subprocess.run(cmd, check=True, capture_output=True)
    if crop:
        with open(svg) as f:
            s = f.read()
        x0, y0, x1, y1 = crop
        s = re.sub(r'viewBox="[^"]*"', f'viewBox="{x0} {y0} {x1 - x0} {y1 - y0}"', s, 1)
        s = re.sub(r'width="[^"]*mm"', f'width="{x1 - x0}mm"', s, 1)
        s = re.sub(r'height="[^"]*mm"', f'height="{y1 - y0}mm"', s, 1)
        with open(svg, "w") as f:
            f.write(s)
    subprocess.run(["node", SVG2PNG, tmpdir, svg], check=True, capture_output=True)
    png = os.path.join(tmpdir, base + ".png")
    if os.path.abspath(png) != os.path.abspath(out_png):
        os.replace(png, out_png)
    return out_png


# ============================================================================= self-test
def selftest():
    nl = netlist()
    miss = [f for f in sorted({c["footprint"] for c in nl.comps.values() if c["footprint"]})
            if f not in FP_CUSTOM and not os.path.exists(os.path.join(FP_PATHS.get(f.split(":")[0], FPLIB),
                                                                      f.split(":")[0] + ".pretty",
                                                                      f.split(":")[1] + ".kicad_mod"))]
    print(f"netlist: {len(nl.comps)} components, {len(nl.nets)} nets, {len(nl.pads)} pad nodes; "
          f"footprints not found: {miss or 'none'}")
    print(f"50 R: w {W50:.2f} mm, Z0 {Z50:.1f} R, eps_eff {EE50:.2f}, {PS_MM50:.3f} ps/mm; 73 R: {W73:.2f} mm")
    for k in ("BUF_OUT_S", "VIN", "GND", "CMP_P"):
        print(f"  canon({k!r}) = {canon(k)!r}")
    print("  net_of('U101', '10') =", net_of("U101", "10"))


if __name__ == "__main__":
    selftest()
