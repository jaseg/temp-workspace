"""Generates scope-frontend.kicad_sch (KiCad 7 format) for the proposal in ../docs/scope-frontend.md.

The schematic is described below as rows of series parts with shunt branches, and IC
boxes whose pins carry net labels. Run:

  python3 gen_scope_frontend.py && kicad-cli sch export pdf scope-frontend.kicad_sch
"""
from __future__ import annotations

import math
import os
import uuid

U = 2.54
ROOT = "6f0a1c7e-0000-4000-8000-000000000001"
LOW = False   # set by main(): low-cost variant

GLOBAL = {
    "I2C_SCL", "I2C_SDA", "ADC_CLK",  # nets that leave this sheet (MCU, ADC, DACs) and the supply rails on IC pins
    "+5V", "-5V", "+3V3", "+1V8", "GND",
    "SAMPLE_OUT", "ADC_CLK_P", "ADC_CLK_N", "SIG_CLK_P", "SIG_CLK_N",
    "SPI_SCK", "SPI_MOSI", "SPI_MISO", "PLL_CS", "PLL_RST", "PLL_INT", "PLL_LOL", "PLL_INSEL0", "PLL_INSEL1",
    "VOFS", "VCLH", "VCLL", "VBIAS_A", "VBIAS_K", "TRIG_LEVEL",
}
POWER = {"GND": "dn", "-5V": "dn", "+5V": "up", "+3V3": "up", "+1V8": "up"}

_n = 0


def uid() -> str:
    global _n
    _n += 1
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"scope-frontend-{_n}"))


def f(v: float) -> str:
    return f"{round(v, 3):g}"


FONT = "(effects (font (size 1.27 1.27)))"


def pin(num: str, name: str, x: float, y: float, ang: int, length: float = U, hide: bool = False) -> str:
    return (f'(pin passive line (at {f(x)} {f(y)} {ang}) (length {f(length)}){" hide" if hide else ""} '
            f'(name "{name}" {FONT}) (number "{num}" {FONT}))')


def poly(pts, fill="none", w=0.254) -> str:
    return (f'(polyline (pts {" ".join(f"(xy {f(x)} {f(y)})" for x, y in pts)}) '
            f'(stroke (width {w}) (type default)) (fill (type {fill})))')


def rect(x1, y1, x2, y2, fill="none") -> str:
    return f'(rectangle (start {f(x1)} {f(y1)}) (end {f(x2)} {f(y2)}) (stroke (width 0.254) (type default)) (fill (type {fill})))'


class Lib:
    """Library symbols. pins[name][number] = (x, y) in library coordinates (y up)."""

    def __init__(self) -> None:
        self.sexp: dict[str, str] = {}
        self.pins: dict[str, dict[str, tuple[float, float]]] = {}

    def add(self, name: str, ref: str, graphics: list[str], pins: list[tuple], power: bool = False,
            hide_numbers: bool = False, name_offset: float = 0.508, hide_names: bool = False) -> None:
        self.pins[name] = {p[0]: (p[2], p[3]) for p in pins}
        pn = f'(pin_names (offset {name_offset}){" hide" if hide_names else ""})'
        self.sexp[name] = (
            f'(symbol "scope:{name}" {"(power) " if power else ""}{"(pin_numbers hide) " if hide_numbers else ""}{pn} '
            f'(in_bom yes) (on_board yes)\n'
            f'  (property "Reference" "{ref}" (at 0 0 0) {FONT})\n'
            f'  (property "Value" "{name}" (at 0 0 0) {FONT})\n'
            f'  (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
            f'  (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
            f'  (symbol "{name}_0_1" {" ".join(graphics)})\n'
            f'  (symbol "{name}_1_1" {" ".join(pin(*p) for p in pins)}))')

    def box(self, name: str, left: list[tuple[str, str]], right: list[tuple[str, str]], half_w: float = 4 * U) -> None:
        rows = max(len(left), len(right))
        top = (rows - 1) * U / 2
        pins = [(num, nm, -half_w - U, top - i * U, 0) for i, (num, nm) in enumerate(left)]
        pins += [(num, nm, half_w + U, top - i * U, 180) for i, (num, nm) in enumerate(right)]
        self.add(name, "U", [rect(-half_w, top + U, half_w, top - rows * U, "background")], pins)


lib = Lib()
lib.add("R", "R", [rect(-1.016, -2.54, 1.016, 2.54)], [("1", "~", 0, 3.81, 270, 1.27), ("2", "~", 0, -3.81, 90, 1.27)],
        hide_numbers=True, hide_names=True)
lib.add("C", "C", [poly([(-2.032, 0.762), (2.032, 0.762)], w=0.508), poly([(-2.032, -0.762), (2.032, -0.762)], w=0.508)],
        [("1", "~", 0, 3.81, 270, 3.048), ("2", "~", 0, -3.81, 90, 3.048)], hide_numbers=True, hide_names=True)
lib.add("L", "L", [rect(-1.016, -2.54, 1.016, 2.54, "outline")],
        [("1", "~", 0, 3.81, 270, 1.27), ("2", "~", 0, -3.81, 90, 1.27)], hide_numbers=True, hide_names=True)
lib.add("TLSTUB", "TL", [rect(-0.635, -2.54, 0.635, 2.54), poly([(-1.5, -2.54), (1.5, -2.54)], w=0.508)],
        [("1", "~", 0, 3.81, 270, 1.27), ("2", "~", 0, -3.81, 90, 1.27)], hide_numbers=True, hide_names=True)
lib.add("GND", "#PWR", [poly([(0, 0), (0, -1.27), (1.27, -1.27), (0, -2.54), (-1.27, -1.27), (0, -1.27)])],
        [("1", "GND", 0, 0, 270, 0, True)], power=True, hide_numbers=True, hide_names=True)
for rail in ("+5V", "+3V3", "+1V8"):
    lib.add(rail, "#PWR", [poly([(0, 0), (0, 1.27)]), poly([(-0.762, 1.27), (0, 2.54), (0.762, 1.27), (-0.762, 1.27)])],
            [("1", rail, 0, 0, 90, 0, True)], power=True, hide_numbers=True, hide_names=True)
lib.add("-5V", "#PWR", [poly([(0, 0), (0, -1.27)]), poly([(-0.762, -1.27), (0, -2.54), (0.762, -1.27), (-0.762, -1.27)])],
        [("1", "-5V", 0, 0, 270, 0, True)], power=True, hide_numbers=True, hide_names=True)
TRI = [poly([(-5.08, 5.08), (5.08, 0), (-5.08, -5.08), (-5.08, 5.08)], "background")]
lib.add("OPA140", "U", TRI, [("3", "+", -7.62, 2.54, 0), ("2", "-", -7.62, -2.54, 0), ("6", "~", 7.62, 0, 180),
                             ("7", "V+", -2.54, 7.62, 270, 3.81), ("4", "V-", -2.54, -7.62, 90, 3.81)])
lib.add("OPA656", "U", TRI, [("3", "+", -7.62, 2.54, 0), ("4", "-", -7.62, -2.54, 0), ("1", "~", 7.62, 0, 180),
                             ("5", "V+", -2.54, 7.62, 270, 3.81), ("2", "V-", -2.54, -7.62, 90, 3.81)])
lib.add("BAT15-04W", "D", [
    poly([(-4.445, 1.27), (-4.445, -1.27), (-1.905, 0), (-4.445, 1.27)]), poly([(-1.905, 1.27), (-1.905, -1.27)]),
    poly([(0.635, 1.27), (0.635, -1.27), (3.175, 0), (0.635, 1.27)]), poly([(3.175, 1.27), (3.175, -1.27)]),
    poly([(-5.08, 0), (-4.445, 0)]), poly([(-1.905, 0), (0.635, 0)]), poly([(3.175, 0), (5.08, 0)]), poly([(0, 0), (0, -2.54)])],
    [("1", "A", -7.62, 0, 0), ("2", "K", 7.62, 0, 180), ("3", "COM", 0, -5.08, 90)], hide_names=True)
lib.add("SMA", "J", ['(circle (center 0 0) (radius 1.905) (stroke (width 0.254) (type default)) (fill (type none)))',
                     '(circle (center 0 0) (radius 0.508) (stroke (width 0.254) (type default)) (fill (type outline)))'],
        [("1", "In", 5.08, 0, 180, 4.572), ("2", "Ext", 0, -5.08, 90, 3.175)], hide_names=True)
lib.box("BUF802", [("2", "IN"), ("3", "In_Bias"), ("4", "In_Aux"), ("7", "R_Bias"), ("15", "CLH"), ("14", "CLL"), ("6", "Aux_Bias")],
        [("11", "OUT"), ("1", "VS+"), ("12", "VSO+"), ("5", "VS-"), ("8", "VS-"), ("10", "VSO-"), ("17", "PAD")], 5 * U)
lib.box("ADCMP572", [("2", "VP"), ("3", "VN"), ("1", "VTP"), ("4", "VTN"), ("7", "LE"), ("6", "~{LE}"), ("14", "HYS")],
        [("11", "Q"), ("10", "~{Q}"), ("5", "VCCI"), ("16", "VCCI"), ("9", "VCCO"), ("12", "VCCO"), ("8", "VCCO/VTT"), ("13", "GND"), ("15", "GND")], 5 * U)
lib.box("GVA-84+", [("1", "RF_IN")], [("3", "RF_OUT/DC"), ("2", "GND"), ("4", "GND")], 4 * U)
lib.add("SOT23-5_AMP", "U", TRI, [("3", "+", -7.62, 2.54, 0), ("4", "-", -7.62, -2.54, 0), ("1", "~", 7.62, 0, 180),
                                  ("5", "V+", -2.54, 7.62, 270, 3.81), ("2", "V-", -2.54, -7.62, 90, 3.81)])
lib.box("CM_CHOKE", [("1", "A"), ("4", "B")], [("2", "A'"), ("3", "B'")], 3 * U)
lib.box("Si5351C", [("1", "XA"), ("2", "XB"), ("6", "CLKIN"), ("4", "SCL"), ("5", "SDA"), ("3", "OEB")],
        [("10", "CLK0"), ("7", "CLK1"), ("13", "CLK2"), ("12", "CLK3"), ("16", "VDD"), ("9", "VDDOA"), ("8", "VDDOB"),
         ("14", "VDDOC"), ("11", "VDDOD"), ("15", "GND"), ("17", "PAD")], 5 * U)
lib.box("TCM1-83X+", [("P1", "PRI"), ("P2", "PRI")], [("S1", "SEC"), ("S2", "SEC")], 3 * U)
lib.box("XTAL_4P", [("1", "X1"), ("2", "GND")], [("3", "X2"), ("4", "GND")], 3 * U)
lib.box("Si5344", [
    ("5", "XA"), ("6", "XB"), ("4", "X1"), ("7", "X2"), ("43", "IN0"), ("44", "~{IN0}"), ("1", "IN1"), ("2", "~{IN1}"),
    ("10", "IN2"), ("11", "~{IN2}"), ("41", "IN3/FB_IN"), ("42", "~{IN3}"), ("3", "IN_SEL0"), ("37", "IN_SEL1"),
    ("17", "~{RST}"), ("12", "~{OE}"), ("38", "I2C_SEL"), ("14", "SCLK"), ("13", "SDA/SDIO"), ("15", "A1/SDO"),
    ("16", "A0/~{CS}"), ("33", "~{INTR}"), ("27", "~{LOL}"), ("28", "~{LOS_XAXB}")],
    [("20", "OUT0"), ("19", "~{OUT0}"), ("25", "OUT1"), ("24", "~{OUT1}"), ("31", "OUT2"), ("30", "~{OUT2}"),
     ("36", "OUT3"), ("35", "~{OUT3}"), ("21", "VDD"), ("32", "VDD"), ("39", "VDD"), ("40", "VDD"), ("8", "VDDA"),
     ("9", "VDDA"), ("26", "VDDS"), ("18", "VDDO0"), ("23", "VDDO1"), ("29", "VDDO2"), ("34", "VDDO3"), ("45", "GND_PAD")], 7 * U)


class Sch:
    def __init__(self) -> None:
        self.items: list[str] = []
        self.pwr = 0
        self.refs: set[str] = set()

    # ---- primitives
    def wire(self, a, b) -> None:
        if a != b:
            self.items.append(f'(wire (pts (xy {f(a[0])} {f(a[1])}) (xy {f(b[0])} {f(b[1])})) (stroke (width 0) (type default)) (uuid {uid()}))')

    def junction(self, p) -> None:
        self.items.append(f'(junction (at {f(p[0])} {f(p[1])}) (diameter 0) (color 0 0 0 0) (uuid {uid()}))')

    def nc(self, p) -> None:
        self.items.append(f'(no_connect (at {f(p[0])} {f(p[1])}) (uuid {uid()}))')

    def text(self, s: str, x: float, y: float, size: float = 1.6) -> None:
        s = s.replace('"', "'").replace("\n", "\\n")
        self.items.append(f'(text "{s}" (at {f(x)} {f(y)} 0) (effects (font (size {size} {size})) (justify left bottom)) (uuid {uid()}))')

    def label(self, p, name: str, side: str = "r") -> None:
        """Net label at p, text running to the right ('r') or left ('l') of it."""
        ang, just = (0, "left") if side == "r" else (180, "right")
        if name in GLOBAL:
            self.items.append(f'(global_label "{name}" (shape passive) (at {f(p[0])} {f(p[1])} {ang}) '
                              f'(effects (font (size 1.27 1.27)) (justify {just})) (uuid {uid()}))')
        else:
            self.items.append(f'(label "{name}" (at {f(p[0])} {f(p[1])} {ang}) '
                              f'(effects (font (size 1.27 1.27)) (justify {just} bottom)) (uuid {uid()}))')

    def symbol(self, name: str, ref: str, value: str, x: float, y: float, rot: int = 0, mirror: str = "",
               ref_at=None, val_at=None, dnp: bool = False, field_ang: int = 0) -> dict[str, tuple[float, float]]:
        assert ref not in self.refs or ref.startswith("#"), ref
        self.refs.add(ref)
        r = math.radians(rot)
        pos = {}
        for num, (px, py) in lib.pins[name].items():
            py = -py
            qx, qy = px * math.cos(r) + py * math.sin(r), -px * math.sin(r) + py * math.cos(r)
            if mirror == "y":
                qx = -qx
            pos[num] = (round(x + qx, 3), round(y + qy, 3))
        ra = ref_at or (x, y - 3.5)
        va = val_at or (x, y + 3.5)
        hide = " hide" if ref.startswith("#") else ""
        vhide = " hide" if ref.startswith("#") and name == "GND" else ""
        self.items.append(
            f'(symbol (lib_id "scope:{name}") (at {f(x)} {f(y)} {rot}){f" (mirror {mirror})" if mirror else ""} (unit 1) '
            f'(in_bom yes) (on_board yes) (dnp {"yes" if dnp else "no"}) (uuid {uid()})\n'
            f'  (property "Reference" "{ref}" (at {f(ra[0])} {f(ra[1])} {field_ang}) (effects (font (size 1.27 1.27)){hide}))\n'
            f'  (property "Value" "{value}" (at {f(va[0])} {f(va[1])} {field_ang}) (effects (font (size 1.27 1.27)){vhide}))\n'
            f'  (property "Footprint" "" (at {f(x)} {f(y)} 0) (effects (font (size 1.27 1.27)) hide))\n'
            f'  (property "Datasheet" "" (at {f(x)} {f(y)} 0) (effects (font (size 1.27 1.27)) hide))\n'
            + "".join(f'  (pin "{n}" (uuid {uid()}))\n' for n in lib.pins[name])
            + f'  (instances (project "scope-frontend" (path "/{ROOT}" (reference "{ref}") (unit 1)))))')
        return pos

    def power(self, p, rail: str) -> None:
        self.pwr += 1
        up = POWER[rail] == "up"
        self.symbol(rail, f"#PWR{self.pwr:03d}", rail, p[0], p[1], val_at=(p[0], p[1] + (-3.6 if up else 3.9)))

    def end(self, p, net: str, side: str = "r") -> None:
        """Terminate a wire end at p on a rail (power symbol) or a net (label)."""
        if net in POWER:
            self.power(p, net)
        else:
            self.label(p, net, side)

    # ---- two-pin parts
    def hpart(self, kind: str, ref: str, val: str, p, dnp: bool = False):
        """Horizontal part with pin 1 at p; returns the position of pin 2."""
        val = val + (" DNP" if dnp else "")
        pos = self.symbol(kind, ref, val, p[0] + 3.81, p[1], 90, ref_at=(p[0] + 3.81, p[1] - 2.6), val_at=(p[0] + 3.81, p[1] + 2.9), dnp=dnp, field_ang=90)
        assert pos["1"] == (round(p[0], 3), round(p[1], 3)), (pos, p)
        return pos["2"]

    def vpart(self, kind: str, ref: str, val: str, p):
        pos = self.symbol(kind, ref, val, p[0], p[1] + 3.81, 0, ref_at=(p[0] + 4.6, p[1] + 2.9), val_at=(p[0] + 4.6, p[1] + 5.0))
        return pos["2"]

    def row(self, x: float, y: float, start, items: list, stop=None):
        """A horizontal signal path. start/stop: net name, or None when the caller wires that end.
        Items: (kind, ref, value[, 'DNP']) in series; ('n', net) names the wire here;
        ('|', net, (kind, ref, value), ...) hangs a shunt chain ending on net."""
        p = (x, y)
        if start:
            if start in POWER:
                self.power(p, start)
            else:
                self.label(p, start, "l")
        for it in items:
            if it[0] == "n":
                q = (p[0] + 2 * U, p[1])
                self.wire(p, q)
                self.label((p[0] + 0.5 * U, p[1]), it[1], "r")
                p = q
            elif it[0] == "|":
                q = (p[0] + U, p[1])
                self.wire(p, q)
                self.junction(q)
                b = (q[0], q[1] + U)
                self.wire(q, b)
                for part in it[2:]:
                    b2 = self.vpart(*part, b)
                    b = (b2[0], b2[1] + U)
                    self.wire(b2, b)
                if it[1] in POWER and POWER[it[1]] == "up":
                    self.label(b, it[1], "r")
                else:
                    self.end(b, it[1], "r")
                p = (q[0] + 4 * U, q[1])
                self.wire(q, p)
            else:
                q = (p[0] + U, p[1])
                self.wire(p, q)
                q2 = self.hpart(it[0], it[1], it[2], q, dnp=len(it) > 3)
                p = (q2[0] + U, q2[1])
                self.wire(q2, p)
        if stop:
            if stop in POWER:
                d = (p[0], p[1] + U) if POWER[stop] == "dn" else (p[0], p[1] - U)
                self.wire(p, d)
                self.power(d, stop)
            else:
                self.label(p, stop, "r")
        return p

    def ic(self, name: str, ref: str, x: float, y: float, nets: dict[str, str | None], value: str | None = None):
        """IC box; nets maps pin number to a net name, or None for a no-connect."""
        rows = max(sum(1 for (px, _) in lib.pins[name].values() if px < 0), sum(1 for (px, _) in lib.pins[name].values() if px > 0))
        top = y - (rows - 1) * U / 2 - U
        pos = self.symbol(name, ref, value or name, x, y, ref_at=(x - 6, top - 3.2), val_at=(x + 4, top - 3.2))
        for num, p in pos.items():
            left = p[0] < x
            if nets.get(num, "") is None:
                self.nc(p)
                continue
            q = (p[0] + (-U if left else U), p[1])
            self.wire(p, q)
            self.label(q, nets[num], "l" if left else "r")
        missing = set(pos) - set(nets)
        assert not missing, (ref, missing)
        return pos

    def decap(self, x: float, y: float, rail: str, caps: list[tuple[str, str]]) -> None:
        """Decoupling capacitors from a rail to ground, drawn side by side."""
        for i, (ref, val) in enumerate(caps):
            p = (x + i * 5 * U, y)
            if POWER[rail] == "up":
                self.power(p, rail)
                b = self.vpart("C", ref, val, p)
                self.power(b, "GND")
            else:
                # negative rail: rail label on top, ground symbol below
                self.label(p, rail, "r")
                b = self.vpart("C", ref, val, p)
                self.power(b, "GND")

    def _next(self) -> int:
        self.pwr += 1
        return self.pwr

    def render(self) -> str:
        libs = "\n".join(lib.sexp.values())
        return (f'(kicad_sch (version 20230121) (generator eeschema)\n(uuid {ROOT})\n(paper "User" 841 400)\n'
                f'(title_block (title "Sampling oscilloscope front end, one channel{", low-cost variant" if LOW else ""}") (date "2026-11-19") (rev "concept 1")\n'
                f' (comment 1 "Concept schematic generated from docs/scope-frontend.md. Not reviewed, not built.")\n'
                f' (comment 2 "Input stage after the jmw active probe (CERN-OHL-S); see notes on unverified pins."))\n'
                f'(lib_symbols\n{libs}\n)\n' + "\n".join(self.items) +
                f'\n(sheet_instances (path "/" (page "1")))\n)\n')


def build() -> Sch:
    s = Sch()
    amp_lf, amp_hold = ("OPA197", "OPA810") if LOW else ("OPA140", "OPA656")
    T = 2.2

    # ============================================================ input buffer
    X, Y = 25.4, 58.42
    s.text("INPUT BUFFER  -  BUF802 in composite-loop mode with OPA140, after the jmw active probe.\n"
           "Changes: high-value resistors split in two (parasitic C), offset DAC input, clamp inputs, 10 R drive to the bridge.", X, Y - 12 * U, T)
    j = s.symbol("SMA", "J1", "IN", X, Y + 12 * U, mirror="", ref_at=(X - 4, Y + 12 * U - 4), val_at=(X - 4, Y + 12 * U + 4.5))
    s.power(j["2"], "GND")
    s.row(j["1"][0], j["1"][1], None, [("R", "R1", "100"), ("n", "INA"), ("R", "R3", "806k"), ("R", "R4", "806k"), ("n", "INB"),
                                         ("|", "GND", ("R", "R5", "422k")), ("C", "C1", "330p"), ("R", "R2", "0")], "BUF_IN")
    s.row(X + 10 * U, Y + 4 * U, "INA", [("C", "C4", "1.1p"), ("C", "C5", "1.3p")], "INB")
    s.row(X + 10 * U, Y + 22 * U, "INA", [("R", "R6", "953k"), ("R", "R7", "953k"), ("n", "LF_DIV"), ("|", "GND", ("R", "R8", "66.5k")),
                                           ("R", "R9", "68")], "LF_P")
    s.row(X + 10 * U, Y + 32 * U, "VOFS", [("R", "R14", "1M")], "LF_DIV")
    s.row(X + 10 * U, Y - 2 * U, "BUF_IN", [("R", "R10", "4.99M"), ("R", "R27", "4.99M")], "IN_BIAS")

    ox, oy = X + 46 * U, Y + 30 * U
    o = s.symbol("OPA140", "U2", amp_lf, ox, oy, ref_at=(ox + 4, oy - 6), val_at=(ox + 6, oy + 6))
    for num, net, side in (("3", "LF_P", "l"), ("2", "LF_N", "l"), ("6", "LF_OUT", "r")):
        q = (o[num][0] + (-U if side == "l" else U), o[num][1])
        s.wire(o[num], q)
        s.label(q, net, side)
    s.power(o["7"], "+5V")
    s.power(o["4"], "-5V")
    s.row(ox + 12 * U, oy - 6 * U, "LF_OUT", [("R", "R15", "5.6k"), ("|", "GND", ("C", "C3", "100p"))], "IN_AUX")
    s.row(ox + 12 * U, oy + 6 * U, "LF_OUT", [("C", "C2", "47p")], "LF_N")
    s.row(ox + 12 * U, oy + 12 * U, "BUF_OUT", [("R", "R11", "51k"), ("n", "LF_N"), ("|", "GND", ("R", "R12", "10k"), ("R", "R13", "1k trim"))], "LF_N")

    bx, by = X + 62 * U, Y + 8 * U
    s.ic("BUF802", "U1", bx, by, {"2": "BUF_IN", "3": "IN_BIAS", "4": "IN_AUX", "7": "RBIAS", "15": "CLH", "14": "CLL", "6": "-5V",
                                   "11": "BUF_OUT", "1": "+5V", "12": "+5V", "5": "-5V", "8": "-5V", "10": "-5V", "17": "GND"})
    s.text("U1 pins 9, 13, 16: NC", bx - 5 * U, by + 7 * U, 1.27)
    s.row(bx - 8 * U, by + 12 * U, "RBIAS", [("R", "R16", "17.8k")], "-5V")
    s.row(bx - 16 * U, by - 12 * U, "VCLH", [("R", "R17", "1k"), ("|", "GND", ("C", "C6", "100n"))], "CLH")
    s.row(bx + 6 * U, by - 12 * U, "VCLL", [("R", "R18", "1k"), ("|", "GND", ("C", "C7", "100n"))], "CLL")
    s.row(bx + 14 * U, by + 2 * U, "BUF_OUT", [("R", "R19", "10")], "HS")
    s.row(bx + 14 * U, by + 8 * U, "BUF_OUT", [("R", "R40", "453", "DNP")], "TRIG_INT")
    s.decap(bx + 10 * U, by + 16 * U, "+5V", [("C8", "100n"), ("C9", "2.2u")])
    s.decap(bx + 22 * U, by + 16 * U, "-5V", [("C10", "100n"), ("C11", "2.2u")])
    s.decap(ox - 12 * U, oy + 10 * U, "+5V", [("C12", "100n")])
    s.decap(ox - 6 * U, oy + 10 * U, "-5V", [("C13", "100n")])

    # ================================================================= sampler
    X2, Y2 = 350.52, 58.42
    s.text("SAMPLER  -  four-diode bridge (2 x BAT15-04W), fixed reverse bias, 2.2 pF hold, gain 2.2.\n"
           "Simulated: 73 ps (10-90 %), gain 0.46, 72 % per strobe.  R20/R21 and C22 at the diodes; U3 next to C22.", X2, Y2 - 12 * U, T)
    for ref, yy, com in (("D1", Y2 + 2 * U, "HOLD"), ("D2", Y2 + 14 * U, "HS")):
        d = s.symbol("BAT15-04W", ref, "BAT15-04W", X2 + 20 * U, yy, ref_at=(X2 + 20 * U - 6, yy - 3.2), val_at=(X2 + 20 * U + 9, yy - 3.2))
        for num, net, dx in (("1", "RAIL_A", -U), ("2", "RAIL_K", U)):
            q = (d[num][0] + dx, d[num][1])
            s.wire(d[num], q)
            s.label(q, net, "l" if dx < 0 else "r")
        q = (d["3"][0], d["3"][1] + U)
        s.wire(d["3"], q)
        s.label(q, com, "r")
    s.row(X2, Y2, "BAL_A", [("C", "C20", "1n"), ("n", "STROBE_A"), ("R", "R20", "24.9")], "RAIL_A")
    s.row(X2, Y2 + 8 * U, "BAL_K", [("C", "C21", "1n"), ("n", "STROBE_K"), ("R", "R21", "24.9")], "RAIL_K")
    s.row(X2, Y2 + 18 * U, "VBIAS_A", [("|", "GND", ("C", "C23", "100n")), ("R", "R22", "2k")], "STROBE_A")
    s.row(X2, Y2 + 30 * U, "VBIAS_K", [("|", "GND", ("C", "C24", "100n")), ("R", "R23", "2k")], "STROBE_K")
    s.text("VBIAS_A = -1 V, VBIAS_K = +1 V nominal,\nseparately adjustable for offset trim", X2, Y2 + 42 * U, 1.27)

    ax, ay = X2 + 48 * U, Y2 + 8 * U
    s.row(ax - 22 * U, ay - 1 * U, "HOLD", [("|", "GND", ("C", "C22", "2.2p C0G"))], "HOLD")
    a = s.symbol("OPA656", "U3", amp_hold, ax, ay, ref_at=(ax + 4, ay - 6), val_at=(ax + 6, ay + 6))
    for num, net, side in (("3", "HOLD", "l"), ("4", "AMP_FB", "l"), ("1", "AMP_OUT", "r")):
        q = (a[num][0] + (-U if side == "l" else U), a[num][1])
        s.wire(a[num], q)
        s.label(q, net, side)
    s.power(a["5"], "+5V")
    s.power(a["2"], "-5V")
    s.row(ax - 10 * U, ay + 10 * U, "AMP_OUT", [("R", "R24", "604"), ("|", "GND", ("R", "R25", "499"))], "AMP_FB")
    s.row(ax + 8 * U, ay + 4 * U, "AMP_OUT", [("R", "R26", "49.9")], "SAMPLE_OUT")
    s.decap(ax + 14 * U, ay - 10 * U, "+5V", [("C25", "100n")])
    s.decap(ax + 20 * U, ay - 10 * U, "-5V", [("C26", "100n")])
    s.text("U3 input directly at C22 (no stub).\nSAMPLE_OUT to an ADC that converts once per strobe (ADC_CLK).", ax - 22 * U, ay + 24 * U, 1.27)

    if LOW:
        # ---------------------------------------------------------------- low-cost variant of the three blocks
        X3, Y3 = 350.52, 241.3
        s.text("STROBE DRIVER (low cost)  -  PLL CMOS output -> two saturating MMIC stages -> clip stub -> common-mode choke as balun.\n"
               "Unproven: needs an edge under about 120 ps and 2 V at CLIP (simulated: 71 ps sampler with a 160 ps pulse).  L3 pin numbers are placeholders.", X3, Y3 - 12 * U, T)
        s.row(X3, Y3, "STROBE_CLK", [("R", "R30", "100"), ("|", "GND", ("R", "R31", "68")), ("C", "C30", "100n")], "AMP1_IN")
        g1x, g1y = X3 + 40 * U, Y3
        s.ic("GVA-84+", "U5", g1x, g1y, {"1": "AMP1_IN", "3": "RF1", "2": "GND", "4": "GND"})
        s.row(g1x - 6 * U, g1y + 10 * U, "+5V", [("|", "GND", ("C", "C31", "100n")), ("L", "L1", "wideband choke")], "RF1")
        s.row(g1x + 12 * U, g1y - 8 * U, "RF1", [("C", "C32", "100n"), ("R", "R32", "attenuator, 6 dB")], "AMP2_IN")
        g2x, g2y = g1x + 40 * U, Y3
        s.ic("GVA-84+", "U7", g2x, g2y, {"1": "AMP2_IN", "3": "RF_AMP", "2": "GND", "4": "GND"})
        s.row(g2x - 6 * U, g2y + 10 * U, "+5V", [("|", "GND", ("C", "C35", "100n")), ("L", "L2", "wideband choke")], "RF_AMP")
        s.row(g2x + 12 * U, g2y - 8 * U, "RF_AMP", [("C", "C36", "100n"), ("|", "GND", ("TLSTUB", "TL1", "shorted stub 80 ps"))], "CLIP")
        s.ic("CM_CHOKE", "L3", g2x + 20 * U, g2y + 14 * U, {"1": "CLIP", "4": "GND", "2": "BAL_A", "3": "BAL_K"}, value="USB3 CM choke")

        X4, Y4 = 25.4, 241.3
        s.text("TIMEBASE (low cost)  -  Si5351C: strobe and signal clock from its two PLLs, offset by the beat frequency.\n"
               "Reference: 25 MHz crystal (free run) or CLKIN from the trigger comparator, 10-100 MHz only.  No jitter cleaning.", X4, Y4 - 12 * U, T)
        px, py = X4 + 40 * U, Y4 + 12 * U
        s.ic("Si5351C", "U4", px, py, {"1": "XA", "2": "XB", "6": "TRIG_CMOS", "4": "I2C_SCL", "5": "I2C_SDA", "3": "GND",
                                       "10": "STROBE_CLK", "7": "ADC_CLK", "13": "CAL_CLK", "12": "SIG_CLK_P",
                                       "16": "+3V3", "9": "+3V3", "8": "+3V3", "14": "+3V3", "11": "+3V3", "15": "GND", "17": "GND"})
        s.ic("XTAL_4P", "Y1", X4 + 12 * U, Y4 + 2 * U, {"1": "XA", "2": "GND", "3": "XB", "4": "GND"}, value="25 MHz")
        cal = s.row(px + 24 * U, py - 10 * U, "CAL_CLK", [("R", "R42", "0", "DNP")], None)
        j = s.symbol("SMA", "J4", "CAL / TDR OUT (option)", cal[0] + 5.08, cal[1], mirror="y", ref_at=(cal[0] + 9, cal[1] - 4), val_at=(cal[0] + 14, cal[1] + 4.5))
        s.power(j["2"], "GND")
        s.decap(px + 24 * U, py + 4 * U, "+3V3", [("C46", "1u"), ("C47", "100n"), ("C48", "100n")])
        s.text("CLK0 strobe f_s      CLK1 ADC clock f_s (MCU ADC trigger)\nCLK2 calibrator / TDR step f_sig      CLK3 f_sig to MCU (time zero)\n"
               "I2C pull-ups at the MCU.  CMOS outputs, about 1 ns edges: the MMIC stages do the sharpening.", X4, Y4 + 36 * U, 1.27)

        X5, Y5 = 591.82, 58.42
        s.text("TRIGGER / CLOCK INPUT (low cost)  -  TLV3601 squares the input; its output is the PLL reference.\n"
               "One connector for clock and trigger.  Periodic signals of 10-100 MHz only.", X5, Y5 - 12 * U, T)
        j = s.symbol("SMA", "J3", "TRIG / CLK IN", X5, Y5, ref_at=(X5 - 4, Y5 - 4), val_at=(X5 - 2, Y5 + 4.5))
        s.power(j["2"], "GND")
        s.row(j["1"][0], j["1"][1], None, [("n", "TRIG_IN"), ("|", "GND", ("R", "R50", "49.9")), ("R", "R51", "100")], "TRIG_VP")
        s.row(X5 + 4 * U, Y5 + 14 * U, "TRIG_INT", [("R", "R52", "0", "DNP")], "TRIG_IN")
        d = s.symbol("BAT15-04W", "D3", "BAT54S", X5 + 12 * U, Y5 + 24 * U, ref_at=(X5 + 12 * U - 6, Y5 + 24 * U - 3.2), val_at=(X5 + 12 * U + 9, Y5 + 24 * U - 3.2))
        q = (d["1"][0] - U, d["1"][1]); s.wire(d["1"], q); s.wire(q, (q[0], q[1] + U)); s.power((q[0], q[1] + U), "GND")
        q = (d["2"][0] + U, d["2"][1]); s.wire(d["2"], q); s.wire(q, (q[0], q[1] - U)); s.power((q[0], q[1] - U), "+3V3")
        q = (d["3"][0], d["3"][1] + U); s.wire(d["3"], q); s.label(q, "TRIG_VP", "r")
        s.row(X5 + 4 * U, Y5 + 36 * U, "TRIG_LEVEL", [("R", "R54", "1k"), ("|", "GND", ("C", "C55", "100n"))], "TRIG_VN")
        kx, ky = X5 + 50 * U, Y5 + 4 * U
        k = s.symbol("SOT23-5_AMP", "U6", "TLV3601", kx, ky, ref_at=(kx + 4, ky - 6), val_at=(kx + 6, ky + 6))
        for num, net, side in (("3", "TRIG_VP", "l"), ("4", "TRIG_VN", "l"), ("1", "TRIG_CMP", "r")):
            q = (k[num][0] + (-U if side == "l" else U), k[num][1])
            s.wire(k[num], q)
            s.label(q, net, side)
        s.power(k["5"], "+3V3")
        s.power(k["2"], "GND")
        s.row(kx + 14 * U, ky + 10 * U, "TRIG_CMP", [("R", "R55", "33")], "TRIG_CMOS")
        s.row(kx - 12 * U, ky + 18 * U, "TRIG_CMP", [("R", "R53", "hysteresis, 100k")], "TRIG_VP")
        s.decap(kx + 14 * U, ky + 18 * U, "+3V3", [("C57", "100n")])

    else:
        # ========================================================== strobe driver
        X3, Y3 = 350.52, 241.3
        s.text("STROBE DRIVER  -  PLL clock -> 35 ps limiter (ADCMP572) -> saturating amplifier (GVA-84+) -> clip stub -> balun.\n"
               "Unproven: output edge and amplitude of U7 need a test coupon.  T1 pin numbers are placeholders.", X3, Y3 - 12 * U, T)
        s.row(X3, Y3, "STROBE_CLK_P", [("C", "C30", "100n")], "STB_P")
        s.row(X3, Y3 + 6 * U, "STROBE_CLK_N", [("C", "C31", "100n")], "STB_N")
        s.row(X3, Y3 + 14 * U, "+3V3", [("R", "R30", "10k"), ("|", "GND", ("R", "R31", "2.2k")), ("|", "GND", ("C", "C32", "100n"))], "STB_VT")
        s.row(X3, Y3 + 28 * U, "+3V3", [("R", "R32", "0")], "STB_LE")
        s.row(X3, Y3 + 34 * U, "STB_LEB", [("R", "R33", "390")], "GND")
        cx, cy = X3 + 34 * U, Y3 + 4 * U
        s.ic("ADCMP572", "U5", cx, cy, {"2": "STB_P", "3": "STB_N", "1": "STB_VT", "4": "STB_VT", "7": "STB_LE", "6": "STB_LEB", "14": None,
                                        "11": "STB_Q", "10": "STB_QB", "5": "+3V3", "16": "+3V3", "9": "+3V3", "12": "+3V3", "8": "+3V3",
                                        "13": "GND", "15": "GND"})
        s.row(cx + 14 * U, cy - 8 * U, "STB_Q", [("C", "C33", "100n")], "AMP_IN")
        s.row(cx + 14 * U, cy + 12 * U, "STB_QB", [("C", "C34", "100n"), ("R", "R34", "49.9")], "GND")
        gx, gy = cx + 36 * U, cy - 2 * U
        s.ic("GVA-84+", "U7", gx, gy, {"1": "AMP_IN", "3": "RF_AMP", "2": "GND", "4": "GND"})
        s.row(gx - 6 * U, gy + 10 * U, "+5V", [("|", "GND", ("C", "C35", "100n")), ("L", "L1", "wideband choke")], "RF_AMP")
        s.row(gx + 12 * U, gy - 10 * U, "RF_AMP", [("C", "C36", "100n"), ("|", "GND", ("TLSTUB", "TL1", "shorted stub 80 ps"))], "CLIP")
        tx, ty = gx + 20 * U, gy + 12 * U
        s.ic("TCM1-83X+", "T1", tx, ty, {"P1": "CLIP", "P2": "GND", "S1": "BAL_A", "S2": "BAL_K"})
        s.decap(cx - 6 * U, cy + 16 * U, "+3V3", [("C37", "100n"), ("C38", "100n")])

        # =============================================================== timebase
        X4, Y4 = 25.4, 241.3
        s.text("TIMEBASE  -  Si5344: strobe and signal clock from two fractional dividers of one PLL, offset by the beat frequency.\n"
               "Reference: crystal (free run), clock input (IN0) or trigger comparator (IN1).  Supply pin grouping to be checked (VDDS).", X4, Y4 - 12 * U, T)
        px, py = X4 + 52 * U, Y4 + 28 * U
        s.ic("Si5344", "U4", px, py, {
            "5": "XA", "6": "XB", "4": "XGND", "7": "XGND", "43": "CLKIN_P", "44": "CLKIN_N", "1": "TRIG_P", "2": "TRIG_N",
            "10": None, "11": None, "41": None, "42": None, "3": "PLL_INSEL0", "37": "PLL_INSEL1", "17": "PLL_RST", "12": "GND",
            "38": "GND", "14": "SPI_SCK", "13": "SPI_MOSI", "15": "SPI_MISO", "16": "PLL_CS", "33": "PLL_INT", "27": "PLL_LOL", "28": None,
            "20": "STROBE_CLK_P", "19": "STROBE_CLK_N", "25": "ADC_CLK_P", "24": "ADC_CLK_N", "31": "CAL_P", "30": "CAL_N",
            "36": "SIG_CLK_P", "35": "SIG_CLK_N", "21": "+1V8", "32": "+1V8", "39": "+1V8", "40": "+1V8", "8": "+3V3", "9": "+3V3",
            "26": "+3V3", "18": "+3V3", "23": "+3V3", "29": "+3V3", "34": "+3V3", "45": "GND"})
        s.ic("XTAL_4P", "Y1", X4 + 14 * U, Y4 + 2 * U, {"1": "XA", "2": "XGND", "3": "XB", "4": "XGND"}, value="48 MHz")
        j = s.symbol("SMA", "J2", "CLK IN", X4, Y4 + 16 * U, ref_at=(X4 - 4, Y4 + 16 * U - 4), val_at=(X4 - 4, Y4 + 16 * U + 4.5))
        s.power(j["2"], "GND")
        s.row(j["1"][0], j["1"][1], None, [("|", "GND", ("R", "R41", "49.9")), ("C", "C40", "100n")], "CLKIN_P")
        s.row(X4 + 4 * U, Y4 + 30 * U, "CLKIN_N", [("C", "C41", "100n")], "GND")
        s.row(X4 + 4 * U, Y4 + 40 * U, "TRIG_Q", [("C", "C42", "100n")], "TRIG_P")
        s.row(X4 + 4 * U, Y4 + 46 * U, "TRIG_QB", [("C", "C43", "100n")], "TRIG_N")
        cal = s.row(px + 30 * U, py - 6 * U, "CAL_P", [("C", "C44", "100n"), ("R", "R42", "0")], None)
        j = s.symbol("SMA", "J4", "CAL / TDR OUT", cal[0] + 5.08, cal[1], mirror="y", ref_at=(cal[0] + 9, cal[1] - 4), val_at=(cal[0] + 9, cal[1] + 4.5))
        s.power(j["2"], "GND")
        s.row(px + 30 * U, py + 2 * U, "CAL_N", [("C", "C45", "100n"), ("R", "R43", "49.9")], "GND")
        s.decap(px + 30 * U, py + 16 * U, "+1V8", [("C46", "1u"), ("C47", "100n"), ("C48", "100n")])
        s.decap(px + 48 * U, py + 16 * U, "+3V3", [("C49", "1u"), ("C50", "100n"), ("C51", "100n"), ("C52", "100n")])
        s.text("OUT0 strobe f_s      OUT1 ADC clock f_s (delayed)\nOUT2 calibrator / TDR step f_sig      OUT3 f_sig to MCU (time zero)\n"
               "~{OE} low = outputs on; I2C_SEL low = SPI", px + 30 * U, py - 14 * U, 1.27)

        # ================================================================ trigger
        X5, Y5 = 591.82, 58.42
        s.text("TRIGGER INPUT  -  ADCMP572 squares the trigger signal; its output is PLL reference IN1 (periodic signals only).\n"
               "VCCI = 5 V gives an input range of -0.2 ... +3.1 V.  R53 (hysteresis) per datasheet figure 7.", X5, Y5 - 12 * U, T)
        j = s.symbol("SMA", "J3", "TRIG IN", X5, Y5, ref_at=(X5 - 4, Y5 - 4), val_at=(X5 - 4, Y5 + 4.5))
        s.power(j["2"], "GND")
        s.row(j["1"][0], j["1"][1], None, [("n", "TRIG_IN"), ("|", "GND", ("R", "R50", "49.9")), ("R", "R51", "100")], "TRIG_VP")
        s.row(X5 + 4 * U, Y5 + 14 * U, "TRIG_INT", [("R", "R52", "0", "DNP")], "TRIG_IN")
        d = s.symbol("BAT15-04W", "D3", "BAT15-04W", X5 + 12 * U, Y5 + 24 * U, ref_at=(X5 + 12 * U - 6, Y5 + 24 * U - 3.2), val_at=(X5 + 12 * U + 9, Y5 + 24 * U - 3.2))
        q = (d["1"][0] - U, d["1"][1]); s.wire(d["1"], q); s.wire(q, (q[0], q[1] + U)); s.power((q[0], q[1] + U), "GND")
        q = (d["2"][0] + U, d["2"][1]); s.wire(d["2"], q); s.wire(q, (q[0], q[1] - U)); s.power((q[0], q[1] - U), "+3V3")
        q = (d["3"][0], d["3"][1] + U); s.wire(d["3"], q); s.label(q, "TRIG_VP", "r")
        s.row(X5 + 4 * U, Y5 + 36 * U, "TRIG_LEVEL", [("R", "R54", "1k"), ("|", "GND", ("C", "C55", "100n"))], "TRIG_VN")
        kx, ky = X5 + 50 * U, Y5 + 4 * U
        s.ic("ADCMP572", "U6", kx, ky, {"2": "TRIG_VP", "3": "TRIG_VN", "1": None, "4": None, "7": "TRG_LE", "6": "TRG_LEB", "14": "TRG_HYS",
                                        "11": "TRIG_Q", "10": "TRIG_QB", "5": "+5V", "16": "+5V", "9": "+3V3", "12": "+3V3", "8": "+3V3",
                                        "13": "GND", "15": "GND"})
        s.row(kx + 14 * U, ky + 12 * U, "+3V3", [("R", "R55", "0")], "TRG_LE")
        s.row(kx + 14 * U, ky + 18 * U, "TRG_LEB", [("R", "R56", "390")], "GND")
        s.row(kx + 14 * U, ky + 24 * U, "TRG_HYS", [("R", "R53", "RHYS")], "GND")
        s.decap(kx - 10 * U, ky + 22 * U, "+5V", [("C56", "100n")])
        s.decap(kx - 4 * U, ky + 22 * U, "+3V3", [("C57", "100n")])


    # ================================================================== notes
    s.text("NOTES\n"
           "1. Concept schematic for docs/scope-frontend.md. Values in the input stage are from the jmw active probe; the rest are first estimates.\n"
           "2. Supplies +5 V, -5 V, +3.3 V, +1.8 V come from off-sheet regulators (reference design: LTC3261 + TPS7A39 for the split rails).\n"
           "3. Off-sheet: MCU (SPI, PLL control), DACs (VOFS, VCLH, VCLL, VBIAS_A, VBIAS_K, TRIG_LEVEL), ADC (SAMPLE_OUT, ADC_CLK).\n"
           "4. Pin numbers read from datasheets: BUF802, ADCMP572, GVA-84+, OPA656, Si5344 (signal pins). Not verified: T1, Y1, OPA140 (standard\n"
           "   SOIC-8 assumed), BAT15-04W (as on the yanartas board: 1 anode, 2 cathode, 3 common), Si5344 supply pin grouping.\n"
           + ("5. Low-cost variant: see docs/scope-frontend.md, section Cost-down. OPA197, OPA810 and BAT54S pinouts assumed standard; L3 pins are placeholders."
              if LOW else "5. LE / ~{LE} of U5 and U6 are strapped for compare mode with estimated values; check against the ADCMP572 datasheet."),
           480, 385, 1.6)
    return s


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    for LOW, name in ((False, "scope-frontend"), (True, "scope-frontend-lowcost")):
        _n = 0
        with open(os.path.join(here, name + ".kicad_sch"), "w") as fh:
            fh.write(build().render())
