"""schlib: a small generator for KiCad 7 (.kicad_sch, format 20230121) hierarchical schematics.

README
======
Project layout (design/lowcost/kicad/):
    gen/schlib.py           this library
    gen/gen_<sheet>.py      one generator per sheet, writes ../<sheet>.kicad_sch
    gen/gen_all.py          runs every generator, then the exports
    scope-fe.kicad_sch      root sheet (gen_root.py), scope-fe.kicad_pro

Coordinates are schematic millimetres, Y pointing DOWN (as in KiCad). Keep everything on the
1.27 mm grid (use g(n) = n*1.27 or multiples of 2.54); library pins then land on grid too.

Minimal sub-sheet generator:

    import sys, os; sys.path.insert(0, os.path.dirname(__file__))
    from schlib import Sheet, g
    sh = Sheet("sampler", title="Sampler", ref_base=200)     # refs R201, C201, U201 ...
    r = sh.add("Device:R", "R", "1k", (g(40), g(30)), rot=90,       # horizontal resistor
               fp="Resistor_SMD:R_0402_1005Metric", lcsc="C11702")
    c = sh.add("Device:C", "C", "2.2p", (g(50), g(36)), fp="Capacitor_SMD:C_0402_1005Metric")
    sh.wire(r["2"], c["1"])                # orthogonal: horizontal first, then vertical ("hv")
    sh.wire(r["2"], c["1"], via="vh")      # vertical first; via="hvh"/"vhv" with mid=<x or y>
    sh.path([p0, p1, p2])                  # explicit polyline (points or pins)
    sh.gnd(c["2"])                         # GND symbol 2.54 mm below the pin, wired
    sh.power("+3V3", r["1"], dy=-2.54)     # power symbol above the pin (any power:<name>)
    sh.hlabel("BUF_OUT_S", r["1"], "input", side="left")   # hierarchical label at a pin/point
    sh.label("HOLD", c["1"])               # local net label (net name for netlist/PCB)
    sh.nc(u["7"])                          # no-connect flag
    sh.text("Note: ...", (g(10), g(150)))
    u = sh.add("Amplifier_Operational:OPA197xDBV", "U", "OPA197", (x, y), unit=1, mirror="x")
    pw = sh.add("Amplifier_Operational:LMV358", "U", "TP2272", (x, y), unit=3)  # power unit: pass ref="U203" to share a ref
    sh.save()                              # writes ../sampler.kicad_sch, prints check() warnings

Pins: sym["<number>"] -> (x, y) of the pin's connection point; sym.pin_by_name("VIN").
Symbol fields: ref (prefix -> auto number from ref_base, or full "R201"), value, fp=footprint,
lcsc="Cxxxx" (field "LCSC"), mpn=..., fields={"Price":"0.43 USD", ...}, dnp=True.
Rotation rot in {0,90,180,270} (counter-clockwise as in KiCad), mirror in {None,"x","y"}.
Custom symbols (parts not in the KiCad libraries): ic_symbol("GW1NZ-LV1QN48", left=[(num,name,type),...],
right=[...], top=[...], bottom=[...]) returns a lib id "scope-fe:<name>" usable in add(); pin type is
one of input/output/bidirectional/passive/power_in/power_out/no_connect. A pin entry None leaves a gap.

Junctions are added automatically wherever three or more wire ends/pins meet or a wire end/pin
lands on the middle of another wire. check() (run by save()) warns about dangling wire ends,
unconnected pins (not marked nc) and pins sitting on a wire's middle.

Hierarchy: every sub-sheet file is placed once in the root (gen_root.py). Symbol instance paths are
"/<ROOT_UUID>/<sheet uuid>", both derived deterministically from the sheet name (sheet_uuid(name)),
so annotation survives opening in KiCad and re-generation keeps UUIDs stable. Use a distinct
ref_base per sheet (input 100, sampler 200, trigger_phase 300, strobe 400, fpga_clock 500,
power 600, mcu_if 700, root 900); power symbols get #PWR<ref_base+n>.

Validation: nets(root_file) runs `kicad-cli sch export netlist` and returns {net: {(ref,pin),...}};
assert_net(nets, "NAME", {("R201","1"), ...}) checks membership. export_pdf/export_svg wrap kicad-cli.
"""
from __future__ import annotations

import math
import os
import re
import subprocess
import uuid as _uuid

PROJECT = "scope-fe"
KICAD_SYMDIR = "/usr/share/kicad/symbols"
KICAD_FPDIR = "/usr/share/kicad/footprints"
OUTDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_NS = _uuid.UUID("5c09e5f0-7d1b-4b52-9a51-0f3c2a1e0001")
ROOT_UUID = str(_uuid.uuid5(_NS, PROJECT + "/root"))
FONT = ["effects", ["font", ["size", "1.27", "1.27"]]]


def g(n: float) -> float:
    """n grid units of 1.27 mm."""
    return round(n * 1.27, 4)


def sheet_uuid(name: str) -> str:
    """UUID of the sheet symbol for sub-sheet <name> in the root sheet."""
    return str(_uuid.uuid5(_NS, PROJECT + "/sheet/" + name))


# ----------------------------------------------------------------------------- s-expressions
class Q(str):
    """A quoted string atom."""


def parse_sexpr(text: str):
    tok = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)
    stack, cur, pos = [], [], 0
    n = len(text)
    while pos < n:
        m = tok.match(text, pos)
        if not m:
            if text[pos:].strip() == "":
                break
            raise ValueError("parse error at %d" % pos)
        pos = m.end()
        if m.group(1):
            stack.append(cur)
            cur = []
        elif m.group(2):
            done = cur
            cur = stack.pop()
            cur.append(done)
        elif m.group(3) is not None:
            cur.append(Q(m.group(3).replace('\\"', '"').replace("\\\\", "\\").replace("\\n", "\n")))
        else:
            cur.append(m.group(4))
    return cur[0] if len(cur) == 1 else cur


def fmt(x) -> str:
    if isinstance(x, Q):
        return '"' + x.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    if isinstance(x, list):
        return "(" + " ".join(fmt(i) for i in x) + ")"
    if isinstance(x, float):
        return f"{round(x, 4):g}"
    return str(x)


def find(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def num(v: float) -> str:
    v = round(v, 4)
    return f"{v:g}" if v != 0 else "0"


# ----------------------------------------------------------------------------- symbol library
_libcache: dict[str, dict] = {}
CUSTOM: dict[str, list] = {}      # lib_id -> sexpr of custom symbols (scope-fe:...)


def _load_lib(lib: str) -> dict:
    if lib not in _libcache:
        path = os.path.join(KICAD_SYMDIR, lib + ".kicad_sym")
        tree = parse_sexpr(open(path, encoding="utf-8").read())
        _libcache[lib] = {s[1]: s for s in find(tree, "symbol")}
    return _libcache[lib]


def _rename_units(node, old: str, new: str):
    for c in find(node, "symbol"):
        if c[1].startswith(old + "_"):
            c[1] = Q(new + c[1][len(old):])


def lib_symbol(lib_id: str) -> list:
    """Flattened library symbol, top-level name = lib_id, ready for lib_symbols."""
    if lib_id in CUSTOM:
        return CUSTOM[lib_id]
    lib, name = lib_id.split(":", 1)
    syms = _load_lib(lib)
    if name not in syms:
        raise KeyError(f"symbol {lib_id} not found")
    import copy
    s = copy.deepcopy(syms[name])
    ext = find(s, "extends")
    if ext:
        parent = copy.deepcopy(lib_symbol(lib + ":" + ext[0][1]))
        _rename_units(parent, ext[0][1], name)
        child_props = {p[1]: p for p in find(s, "property")}
        out = [parent[0], Q(lib_id)]
        for c in parent[2:]:
            if isinstance(c, list) and c and c[0] == "property" and c[1] in child_props:
                out.append(child_props.pop(c[1]))
            else:
                out.append(c)
        # insert remaining child properties before sub-symbols
        idx = next((i for i, c in enumerate(out) if isinstance(c, list) and c[0] == "symbol"), len(out))
        out[idx:idx] = list(child_props.values())
        return out
    s[1] = Q(lib_id)
    return s


class PinDef:
    def __init__(self, number, name, typ, x, y, ang, unit, hidden):
        self.number, self.name, self.type = number, name, typ
        self.x, self.y, self.ang, self.unit, self.hidden = x, y, ang, unit, hidden


def lib_pins(sym: list) -> list[PinDef]:
    pins = []
    base = sym[1].split(":")[-1]
    for sub in find(sym, "symbol"):
        m = re.match(re.escape(base) + r"_(\d+)_(\d+)$", sub[1])
        unit, style = (int(m.group(1)), int(m.group(2))) if m else (0, 1)
        if style > 1:
            continue
        for p in find(sub, "pin"):
            at = find(p, "at")[0]
            nm = find(p, "name")[0][1]
            nb = find(p, "number")[0][1]
            hidden = "hide" in p
            pins.append(PinDef(str(nb), str(nm), p[1], float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0,
                               unit, hidden))
    return pins


def ic_symbol(name: str, left=(), right=(), top=(), bottom=(), width: float = None, ref: str = "U",
              footprint: str = "", datasheet: str = "", description: str = "", pin_len: float = 2.54) -> str:
    """Create a box symbol 'scope-fe:<name>'. Pin lists: (number, name, type) or None for a gap.
    Pins are on 2.54 mm pitch; returns the lib_id."""
    P = 2.54
    nl, nr = len(left), len(right)
    nt, nb = len(top), len(bottom)
    h = max(nl, nr, 1) * P + P
    if width is None:
        longest = max([len(p[1]) for p in list(left) + list(right) if p] + [4])
        width = max(math.ceil((longest * 2 * 1.0 + 4) / P) * P, (max(nt, nb) + 1) * P)
    w = width
    hw = round(w / 2 / P) * P
    hh = math.ceil(h / 2 / P) * P
    body = [["rectangle", ["start", num(-hw), num(hh)], ["end", num(hw), num(-hh)],
             ["stroke", ["width", "0.254"], ["type", "default"]], ["fill", ["type", "background"]]]]
    pins = []

    def mk(p, x, y, ang):
        if p is None:
            return
        nb_, nm, typ = p
        pins.append(["pin", typ, "line", ["at", num(x), num(y), str(ang)], ["length", num(pin_len)],
                     ["name", Q(nm), FONT], ["number", Q(str(nb_)), FONT]])

    y0 = hh - P
    for i, p in enumerate(left):
        mk(p, -hw - pin_len, y0 - i * P, 0)
    for i, p in enumerate(right):
        mk(p, hw + pin_len, y0 - i * P, 180)
    x0 = -(nt - 1) * P / 2
    x0 = round(x0 / P) * P
    for i, p in enumerate(top):
        mk(p, x0 + i * P, hh + pin_len, 270)
    x0 = round(-(nb - 1) * P / 2 / P) * P
    for i, p in enumerate(bottom):
        mk(p, x0 + i * P, -hh - pin_len, 90)
    hid = ["effects", ["font", ["size", "1.27", "1.27"]], "hide"]
    sym = ["symbol", Q(PROJECT + ":" + name), ["in_bom", "yes"], ["on_board", "yes"],
           ["property", Q("Reference"), Q(ref), ["at", num(-hw), num(hh + 1.27), "0"],
            ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left", "bottom"]]],
           ["property", Q("Value"), Q(name), ["at", num(-hw), num(-hh - 1.27), "0"],
            ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left", "top"]]],
           ["property", Q("Footprint"), Q(footprint), ["at", "0", "0", "0"], hid],
           ["property", Q("Datasheet"), Q(datasheet), ["at", "0", "0", "0"], hid],
           ["property", Q("ki_description"), Q(description), ["at", "0", "0", "0"], hid],
           ["symbol", Q(name + "_0_1")] + body,
           ["symbol", Q(name + "_1_1")] + pins]
    CUSTOM[PROJECT + ":" + name] = sym
    return PROJECT + ":" + name


def write_custom_lib(path: str):
    """Write all custom symbols to a .kicad_sym library (for the project sym-lib-table)."""
    out = ["(kicad_symbol_lib (version 20220914) (generator schlib)"]
    for lid, s in sorted(CUSTOM.items()):
        import copy
        s2 = copy.deepcopy(s)
        s2[1] = Q(lid.split(":", 1)[1])
        out.append("  " + fmt(s2))
    out.append(")")
    open(path, "w").write("\n".join(out) + "\n")


def footprint_exists(fp: str) -> bool:
    if not fp or ":" not in fp:
        return False
    lib, name = fp.split(":", 1)
    return os.path.exists(os.path.join(KICAD_FPDIR, lib + ".pretty", name + ".kicad_mod"))


# ----------------------------------------------------------------------------- geometry
def xform(lx: float, ly: float, rot: int, mirror) -> tuple[float, float]:
    """Library offset (Y up) -> schematic offset (Y down) for a symbol at angle rot with mirror."""
    sx, sy = lx, -ly
    a = math.radians(rot)
    c, s = round(math.cos(a)), round(math.sin(a))
    rx, ry = sx * c + sy * s, -sx * s + sy * c
    if mirror == "x":
        ry = -ry
    elif mirror == "y":
        rx = -rx
    return rx, ry


def _pt(p):
    return (round(float(p[0]), 3), round(float(p[1]), 3))


class Symbol:
    def __init__(self, sheet, lib_id, ref, value, at, rot, mirror, unit, fp, lcsc, mpn, fields, dnp, power=False):
        self.sheet, self.lib_id, self.ref, self.value = sheet, lib_id, ref, value
        self.at, self.rot, self.mirror, self.unit = _pt(at), rot, mirror, unit
        self.fp, self.fields, self.dnp, self.power = fp, dict(fields or {}), dnp, power
        if lcsc:
            self.fields["LCSC"] = lcsc
        if mpn:
            self.fields["MPN"] = mpn
        self.uuid = sheet.uid("sym")
        self.lib = lib_symbol(lib_id)
        self.pins = [p for p in lib_pins(self.lib) if p.unit in (0, unit)]

    def pin(self, number: str) -> tuple[float, float]:
        for p in self.pins:
            if p.number == str(number):
                dx, dy = xform(p.x, p.y, self.rot, self.mirror)
                return _pt((self.at[0] + dx, self.at[1] + dy))
        raise KeyError(f"{self.ref}: no pin {number} in unit {self.unit} of {self.lib_id}: "
                       f"{[p.number for p in self.pins]}")

    __getitem__ = pin

    def pin_dir(self, number: str) -> tuple[float, float]:
        """Unit vector pointing away from the body at pin <number> (schematic coordinates)."""
        for p in self.pins:
            if p.number == str(number):
                a = math.radians(p.ang)
                dx, dy = xform(-round(math.cos(a)), -round(math.sin(a)), self.rot, self.mirror)
                return (round(dx), round(dy))
        raise KeyError(number)

    def pin_by_name(self, name: str):
        for p in self.pins:
            if p.name == name:
                return self.pin(p.number)
        raise KeyError(f"{self.ref}: no pin named {name}: {[p.name for p in self.pins]}")

    def sexpr(self, path: str) -> str:
        X, Y = self.at
        head = ["symbol", ["lib_id", Q(self.lib_id)], ["at", num(X), num(Y), str(self.rot)]]
        if self.mirror:
            head.append(["mirror", self.mirror])
        head += [["unit", str(self.unit)], ["in_bom", "no" if self.power else "yes"], ["on_board", "yes"],
                 ["dnp", "yes" if self.dnp else "no"], ["uuid", self.uuid]]
        props = {p[1]: p for p in find(self.lib, "property")}
        vals = {"Reference": self.ref, "Value": self.value,
                "Footprint": self.fp if self.fp is not None else (props.get("Footprint", [0, 0, ""])[2]),
                "Datasheet": props.get("Datasheet", [0, 0, ""])[2]}
        out = []
        for key in ["Reference", "Value", "Footprint", "Datasheet"]:
            lp = props.get(key)
            if lp is not None:
                at = find(lp, "at")[0]
                dx, dy = xform(float(at[1]), float(at[2]), self.rot, self.mirror)
                eff = find(lp, "effects")
                eff = eff[0] if eff else FONT
                ang = at[3] if len(at) > 3 else "0"
            else:
                dx, dy, eff, ang = 0, 0, ["effects", ["font", ["size", "1.27", "1.27"]], "hide"], "0"
            if key in ("Footprint", "Datasheet") and "hide" not in eff:
                eff = eff + ["hide"]
            out.append(["property", Q(key), Q(vals[key] or ""), ["at", num(X + dx), num(Y + dy), ang], eff])
        for k, v in self.fields.items():
            out.append(["property", Q(k), Q(str(v)), ["at", num(X), num(Y), "0"],
                        ["effects", ["font", ["size", "1.27", "1.27"]], "hide"]])
        pins = [["pin", Q(p.number), ["uuid", self.sheet.uid("pin")]] for p in self.pins]
        inst = ["instances", ["project", Q(PROJECT), ["path", Q(path), ["reference", Q(self.ref)],
                                                      ["unit", str(self.unit)]]]]
        return "  " + fmt(head + out + pins + [inst])


class Sheet:
    """One .kicad_sch file. name=None -> root sheet (scope-fe.kicad_sch)."""

    def __init__(self, name: str | None, title: str = "", ref_base: int = 0, paper: str = "A3",
                 rev: str = "draft", comments: list[str] = ()):
        self.name, self.title, self.ref_base, self.paper = name, title, ref_base, paper
        self.rev, self.comments = rev, list(comments)
        self.file = (PROJECT if name is None else name) + ".kicad_sch"
        self.symbols: list[Symbol] = []
        self.wires: list[tuple] = []
        self.items: list[str] = []      # labels, text, nc, sheets (already formatted)
        self.junctions: list[tuple] = []
        self.ncs: list[tuple] = []
        self.label_pts: list[tuple] = []
        self.sheets: list[dict] = []
        self._n = 0
        self._refn: dict[str, int] = {}
        self._pwr = 0

    # ids
    def uid(self, kind="x") -> str:
        self._n += 1
        return str(_uuid.uuid5(_NS, f"{PROJECT}/{self.name}/{kind}/{self._n}"))

    def inst_path(self) -> str:
        return "/" + ROOT_UUID if self.name is None else "/" + ROOT_UUID + "/" + sheet_uuid(self.name)

    def next_ref(self, prefix: str) -> str:
        n = self._refn.get(prefix, 0) + 1
        self._refn[prefix] = n
        return f"{prefix}{self.ref_base + n}"

    # parts
    def add(self, lib_id: str, ref: str, value: str, at, rot: int = 0, mirror=None, unit: int = 1,
            fp: str | None = None, lcsc: str = "", mpn: str = "", fields: dict | None = None,
            dnp: bool = False) -> Symbol:
        if not re.search(r"\d", ref):
            ref = self.next_ref(ref)
        if fp and not footprint_exists(fp):
            print(f"WARNING [{self.file}] {ref}: footprint {fp} not found in KiCad libraries")
        s = Symbol(self, lib_id, ref, value, at, rot, mirror, unit, fp, lcsc, mpn, fields, dnp)
        self.symbols.append(s)
        return s

    def power(self, name: str, at, dy: float = 0.0, rot: int = 0, wire: bool = True) -> Symbol:
        """Place power:<name> with its pin at (at.x, at.y+dy); wires from 'at' if dy != 0."""
        self._pwr += 1
        p = _pt((at[0], at[1] + dy))
        s = Symbol(self, "power:" + name, f"#PWR{self.ref_base + self._pwr:04d}", name, p, rot, None, 1,
                   "", "", "", None, False, power=True)
        # shift so that the pin sits on p
        px, py = s.pin(s.pins[0].number)
        s.at = _pt((s.at[0] + p[0] - px, s.at[1] + p[1] - py))
        self.symbols.append(s)
        if wire and dy:
            self.wire(at, p)
        return s

    def gnd(self, at, dy: float = 2.54, name: str = "GND") -> Symbol:
        return self.power(name, at, dy=dy)

    def supply(self, name: str, at, dy: float = -2.54) -> Symbol:
        return self.power(name, at, dy=dy)

    # wires
    def wire(self, a, b, via: str = "hv", mid: float | None = None):
        a, b = _pt(a), _pt(b)
        if a == b:
            return
        if a[0] == b[0] or a[1] == b[1]:
            pts = [a, b]
        elif via == "hv":
            pts = [a, (b[0], a[1]), b]
        elif via == "vh":
            pts = [a, (a[0], b[1]), b]
        elif via == "hvh":
            m = mid if mid is not None else round((a[0] + b[0]) / 2 / 1.27) * 1.27
            pts = [a, (m, a[1]), (m, b[1]), b]
        elif via == "vhv":
            m = mid if mid is not None else round((a[1] + b[1]) / 2 / 1.27) * 1.27
            pts = [a, (a[0], m), (b[0], m), b]
        else:
            raise ValueError(via)
        self.path(pts)

    connect = wire

    def path(self, pts):
        pts = [_pt(p) for p in pts]
        for p, q in zip(pts, pts[1:]):
            if p != q:
                if p[0] != q[0] and p[1] != q[1]:
                    print(f"NOTE [{self.file}] diagonal wire {p}->{q}")
                self.wires.append((p, q))

    def stub(self, sym: Symbol, pin: str, net: str | None = None, length: float = 2.54, kind: str = "label",
             shape: str = "passive"):
        """Short wire out of a pin, ending in: kind="label" (local label <net>), "hlabel" (hierarchical
        label, shape), "power" (power:<net> symbol), "gnd" (GND symbol), "nc" (no wire, NC flag).
        Returns the end point."""
        p = sym.pin(pin)
        if kind == "nc":
            self.nc(p)
            return p
        d = sym.pin_dir(pin)
        e = _pt((p[0] + d[0] * length, p[1] + d[1] * length))
        if kind in ("power", "gnd"):
            name = net or "GND"
            if d[1] != 0 or kind == "gnd" or name.startswith("-") or name == "GND":
                # vertical stub: put the symbol beyond the end, pointing away from the pin
                if d[1] == 0:
                    self.wire(p, e)
                    self.power(name, e, dy=(2.54 if (name == "GND" or name.startswith("-")) else -2.54))
                else:
                    self.power(name, p, dy=d[1] * length)
            else:
                self.wire(p, e)
                self.power(name, e, dy=-2.54)
            return e
        self.wire(p, e)
        left = d[0] < 0
        if kind == "hlabel":
            self.hlabel(net, e, shape, side="left" if left else "right")
        else:
            self.label(net, e, rot=180 if left else 0)
        return e

    def junction(self, at):
        self.junctions.append(_pt(at))

    def nc(self, at):
        at = _pt(at)
        self.ncs.append(at)
        self.items.append(fmt(["no_connect", ["at", num(at[0]), num(at[1])], ["uuid", self.uid("nc")]]))

    def label(self, name: str, at, rot: int = 0, size: float = 1.27):
        at = _pt(at)
        self.label_pts.append(at)
        just = ["justify", "right", "bottom"] if rot in (180, 270) else ["justify", "left", "bottom"]
        self.items.append(fmt(["label", Q(name), ["at", num(at[0]), num(at[1]), str(rot)], ["fields_autoplaced"],
                               ["effects", ["font", ["size", num(size), num(size)]], just],
                               ["uuid", self.uid("lbl")]]))

    def hlabel(self, name: str, at, shape: str = "passive", side: str = "right"):
        """Hierarchical label at 'at'. side = where the text goes relative to the point ('right'/'left')."""
        at = _pt(at)
        self.label_pts.append(at)
        rot, just = (0, "left") if side == "right" else (180, "right")
        self.items.append(fmt(["hierarchical_label", Q(name), ["shape", shape],
                               ["at", num(at[0]), num(at[1]), str(rot)], ["fields_autoplaced"],
                               ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", just]],
                               ["uuid", self.uid("hl")]]))

    def glabel(self, name: str, at, shape: str = "passive", side: str = "right"):
        at = _pt(at)
        self.label_pts.append(at)
        rot, just = (0, "left") if side == "right" else (180, "right")
        self.items.append(fmt(["global_label", Q(name), ["shape", shape],
                               ["at", num(at[0]), num(at[1]), str(rot)], ["fields_autoplaced"],
                               ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", just]],
                               ["uuid", self.uid("gl")]]))

    def text(self, s: str, at, size: float = 1.27):
        self.items.append(fmt(["text", Q(s), ["at", num(at[0]), num(at[1]), "0"],
                               ["effects", ["font", ["size", num(size), num(size)]], ["justify", "left", "top"]],
                               ["uuid", self.uid("txt")]]))

    def rect(self, a, b):
        self.items.append(fmt(["rectangle", ["start", num(a[0]), num(a[1])], ["end", num(b[0]), num(b[1])],
                               ["stroke", ["width", "0.2"], ["type", "dash"]], ["fill", ["type", "none"]],
                               ["uuid", self.uid("rect")]]))

    # hierarchy (root only)
    def sheet(self, name: str, at, size, pins_left=(), pins_right=(), page: int = 2):
        """Place sub-sheet <name>.kicad_sch. pins_*: list of (net, shape) or None for a gap.
        Returns dict net -> pin connection point."""
        x, y = at
        w, h = size
        su = sheet_uuid(name)
        conn = {}
        pins = []
        for side, lst in (("L", pins_left), ("R", pins_right)):
            for i, p in enumerate(lst):
                if p is None:
                    continue
                net, shape = p
                py = y + 2.54 * (i + 1)
                px = x if side == "L" else x + w
                conn[net] = _pt((px, py))
                pins.append(["pin", Q(net), shape, ["at", num(px), num(py), "180" if side == "L" else "0"],
                             ["effects", ["font", ["size", "1.27", "1.27"]],
                              ["justify", "left" if side == "L" else "right"]],
                             ["uuid", self.uid("spin")]])
        s = ["sheet", ["at", num(x), num(y)], ["size", num(w), num(h)], ["fields_autoplaced"],
             ["stroke", ["width", "0.1524"], ["type", "solid"]], ["fill", ["color", "0", "0", "0", "0.0000"]],
             ["uuid", su],
             ["property", Q("Sheetname"), Q(name), ["at", num(x), num(y - 0.7116), "0"],
              ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left", "bottom"]]],
             ["property", Q("Sheetfile"), Q(name + ".kicad_sch"), ["at", num(x), num(y + h + 0.5884), "0"],
              ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left", "top"]]]] + pins + \
            [["instances", ["project", Q(PROJECT), ["path", Q("/" + ROOT_UUID), ["page", Q(str(page))]]]]]
        self.items.append(fmt(s))
        self.sheets.append(dict(name=name, conn=conn))
        self.label_pts.extend(conn.values())
        return conn

    # checks
    def _points(self):
        ends: dict = {}
        for a, b in self.wires:
            for p in (a, b):
                ends[p] = ends.get(p, 0) + 1
        pins = {}
        for s in self.symbols:
            for p in s.pins:
                if p.hidden and p.type == "power_in" and s.power is False:
                    continue
                pins.setdefault(s.pin(p.number), []).append((s, p))
        return ends, pins

    @staticmethod
    def _on_mid(p, a, b):
        if a[0] == b[0] == p[0]:
            return min(a[1], b[1]) < p[1] < max(a[1], b[1])
        if a[1] == b[1] == p[1]:
            return min(a[0], b[0]) < p[0] < max(a[0], b[0])
        return False

    def auto_junctions(self):
        ends, pins = self._points()
        cand = set(ends) | set(pins)
        js = set(self.junctions)
        for p in cand:
            deg = ends.get(p, 0) + len(pins.get(p, []))
            mid = sum(1 for a, b in self.wires if self._on_mid(p, a, b))
            if deg + 2 * mid >= 3:
                js.add(p)
        self.junctions = sorted(js)

    def check(self) -> list[str]:
        ends, pins = self._points()
        warn = []
        lbl = set(self.label_pts) | set(self.ncs)
        for p, n in ends.items():
            if n == 1 and p not in pins and p not in lbl and not any(self._on_mid(p, a, b) for a, b in self.wires):
                warn.append(f"dangling wire end at {p}")
        for p, lst in pins.items():
            touched = p in ends or p in lbl or len(lst) > 1 or any(self._on_mid(p, a, b) for a, b in self.wires)
            for s, pd in lst:
                if not touched and not s.power and pd.type != "no_connect":
                    warn.append(f"unconnected pin {s.ref}.{pd.number} ({pd.name}) at {p}")
        return warn

    # output
    def render(self) -> str:
        self.auto_junctions()
        libs = {}
        for s in self.symbols:
            libs.setdefault(s.lib_id, s.lib)
        tb = ["title_block", ["title", Q(self.title or (self.name or PROJECT))], ["date", Q("2026-11-21")],
              ["rev", Q(self.rev)], ["company", Q("scope-fe low-cost sampling front end")]]
        for i, c in enumerate(self.comments[:9]):
            tb.append(["comment", str(i + 1), Q(c)])
        own_uuid = ROOT_UUID if self.name is None else str(_uuid.uuid5(_NS, PROJECT + "/file/" + self.name))
        out = ["(kicad_sch (version 20230121) (generator eeschema)", f"  (uuid {own_uuid})",
               f'  (paper "{self.paper}")', "  " + fmt(tb), "  (lib_symbols"]
        for lid in sorted(libs):
            out.append("    " + fmt(libs[lid]))
        out.append("  )")
        for j in self.junctions:
            out.append("  " + fmt(["junction", ["at", num(j[0]), num(j[1])], ["diameter", "0"],
                                   ["color", "0", "0", "0", "0"], ["uuid", self.uid("j")]]))
        for a, b in self.wires:
            out.append("  " + fmt(["wire", ["pts", ["xy", num(a[0]), num(a[1])], ["xy", num(b[0]), num(b[1])]],
                                   ["stroke", ["width", "0"], ["type", "default"]], ["uuid", self.uid("w")]]))
        out += ["  " + i for i in self.items]
        path = self.inst_path()
        out += [s.sexpr(path) for s in self.symbols]
        if self.name is None:
            out.append('  (sheet_instances (path "/" (page "1")))')
        out.append(")")
        return "\n".join(out) + "\n"

    def save(self, outdir: str = OUTDIR, quiet: bool = False) -> str:
        fn = os.path.join(outdir, self.file)
        txt = self.render()
        open(fn, "w", encoding="utf-8").write(txt)
        w = self.check()
        if not quiet:
            print(f"{self.file}: {len(self.symbols)} symbols, {len(self.wires)} wires, {len(w)} warnings")
            for x in w:
                print(f"  WARN {x}")
        return fn


# ----------------------------------------------------------------------------- project / kicad-cli
def write_project(outdir: str = OUTDIR, sheets=()):
    pro = {"meta": {"filename": PROJECT + ".kicad_pro", "version": 1},
           "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
           "sheets": [[ROOT_UUID, "Root"]] + [[sheet_uuid(n), n] for n in sheets],
           "boards": [], "text_variables": {}}
    import json
    open(os.path.join(outdir, PROJECT + ".kicad_pro"), "w").write(json.dumps(pro, indent=2) + "\n")
    open(os.path.join(outdir, "sym-lib-table"), "w").write(
        '(sym_lib_table\n  (lib (name "scope-fe")(type "KiCad")(uri "${KIPRJMOD}/scope-fe.kicad_sym")'
        '(options "")(descr "custom symbols generated by gen/"))\n)\n')


def kicad_cli(*args) -> str:
    r = subprocess.run(["kicad-cli", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"kicad-cli {' '.join(args)} failed:\n{r.stdout}\n{r.stderr}")
    return r.stdout + r.stderr


def nets(root_sch: str, out: str | None = None) -> dict:
    """Export the netlist of the hierarchy and return {net_name: {(ref, pin), ...}}."""
    out = out or os.path.splitext(root_sch)[0] + ".net"
    kicad_cli("sch", "export", "netlist", "--format", "kicadsexpr", "-o", out, root_sch)
    tree = parse_sexpr(open(out).read())
    res = {}
    for n in find(find(tree, "nets")[0], "net"):
        name = find(n, "name")[0][1]
        res[str(name)] = {(str(find(nd, "ref")[0][1]), str(find(nd, "pin")[0][1])) for nd in find(n, "node")}
    return res


def net_of(netd: dict, ref: str, pin: str) -> str | None:
    for k, v in netd.items():
        if (ref, str(pin)) in v:
            return k
    return None


def assert_net(netd: dict, name: str, members) -> None:
    """Assert that all (ref,pin) members are on one net whose name ends with 'name'."""
    cands = [k for k in netd if k == name or k.endswith("/" + name)]
    for k in cands:
        if set(members) <= netd[k]:
            return
    raise AssertionError(f"net {name}: {members} not together; candidates {[(k, netd[k]) for k in cands]}")


def export_pdf(root_sch: str, out: str):
    return kicad_cli("sch", "export", "pdf", "-o", out, root_sch)


def export_svg(root_sch: str, outdir: str):
    return kicad_cli("sch", "export", "svg", "-o", outdir, root_sch)
