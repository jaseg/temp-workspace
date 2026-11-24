"""power.kicad_sch: USB-C 5 V in -> +3V3, +1V2, +5V1 -> +5V / -5V, +2V5 / -2V5 (docs/research/power-tree.md).

Tree (24 Nov 2026; replaces AMS1117, AP2112K, MT3608, LP2985, LM27761, LP5907, LM337):
  USB-C VBUS -> F601 PTC 1.5 A -> D601 SMAJ5.0A -> FB601 -> VBUS (global, 4.60-5.25 V at the converters)
  VBUS -> U601 TPS62A01A buck 2.4 MHz FPWM -> +3V3 3.327 V (TRF37D73 x5, COS3502, FPGA I/O, MCU, LVDS rx)  0.51 A
  +3V3 -> U602 TPS62A01A -> +1V2 (FPGA core, 1 ms soft start)                                              0.02 A
  VBUS -> U603 TPS63802 buck-boost FPWM -> +5V1 5.40 V (GVA-84+ x2 via 2.49 R each on the strobe sheet; U604) 0.30 A
  +5V1 -> FB602 -> +5V1F -> U604 LM27762 (pump + 2 LDOs) -> +4.80 V -> FB604 -> +5V ; -4.81 V -> FB603 -> -5V
  +3V3 -> FB605 -> +3V3_CP -> U605 LM27762 -> +2.52 V -> FB606 -> +2V5 ; -2.44 V -> FB607 -> -2V5
Set-points and tolerances (24 Nov 2026, SPEC decision 25 / 26): 1 % thick-film JLC dividers except U603 (0.1 %, the
+5V1 window between the U604 OUT- headroom and 5.5 V is only +/-1.6 %); docs/research/power-tree.md section 12.
U605 is enabled by the U603 power-good (PG_5V1): +/-2V5 rise after the BUF802 rails.
Existing capacitors are re-used (moved) wherever possible; refs are kept so the board keeps its parts.
Decoupling capacitors that belong at a load pin on another sheet are drawn here at the bottom (box "at the loads")
with a Note field naming the pin; kicad/README.md lists them for the layout."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schlib import g, ic_symbol
from common import new_sheet, R, C, FP

PIN_IN, PIN_PWR, PIN_OUT, PIN_P, PIN_OC = "input", "power_in", "power_out", "passive", "open_collector"

TPS62A01 = ic_symbol("TPS62A01ADRL", left=[("3", "VIN", PIN_PWR), ("4", "EN", PIN_IN)],
                     right=[("2", "SW", PIN_OUT), ("5", "FB", PIN_IN), ("6", "PG", PIN_OC)],
                     bottom=[("1", "GND", PIN_PWR)], footprint="Package_TO_SOT_SMD:SOT-563",
                     description="TI TPS62A01A 1 A sync. buck, 2.4 MHz forced PWM, SOT-563 (DRL): "
                                 "1 GND 2 SW 3 VIN 4 EN 5 FB 6 PG")
TPS63802 = ic_symbol("TPS63802DLA", left=[None, ("10", "VIN", PIN_PWR), ("1", "EN", PIN_IN), ("2", "MODE", PIN_IN),
                                          ("5", "PG", PIN_OC)],
                     right=[None, ("6", "VOUT", PIN_OUT), ("4", "FB", PIN_IN)], width=g(16),
                     top=[("9", "L1", PIN_P), None, None, ("7", "L2", PIN_P)],
                     bottom=[("3", "AGND", PIN_PWR), ("8", "GND", PIN_PWR)],
                     footprint="scope-fe:Texas_DLA0010A_VSON-HR-10_2x3mm_P0.5mm",
                     description="TI TPS63802 2 A buck-boost, VSON-HR-10 (DLA): 1 EN 2 MODE 3 AGND 4 FB 5 PG "
                                 "6 VOUT 7 L2 8 GND 9 L1 10 VIN")
LM27762 = ic_symbol("LM27762DSS", left=[None, ("3", "VIN", PIN_PWR), ("12", "EN+", PIN_IN), ("8", "EN-", PIN_IN),
                                        ("1", "PGOOD", PIN_P), None],
                    right=[None, ("2", "FB+", PIN_IN), ("11", "OUT+", PIN_OUT), None, ("6", "OUT-", PIN_OUT),
                           ("7", "FB-", PIN_IN)], width=g(20),
                    top=[("10", "C1+", PIN_P), None, None, ("9", "C1-", PIN_P)],
                    bottom=[("4", "GND", PIN_PWR), ("13", "EP", PIN_PWR), None, ("5", "CP", PIN_P)],
                    footprint="Package_SON:WSON-12-1EP_3x2mm_P0.5mm_EP1x2.65",
                    description="TI LM27762 inverting charge pump + positive and negative LDO, WSON-12 (DSS): "
                                "1 PGOOD 2 FB+ 3 VIN 4 GND 5 CP 6 OUT- 7 FB- 8 EN- 9 C1- 10 C1+ 11 OUT+ 12 EN+, EP GND")

BEAD = ("Device:FerriteBead_Small", FP["FB0603"], "BLM18KG601SN1D", "C85833")
BEAD_F = {"Price": "0.0166 USD (LCSC 50+)", "Note": "600 R @ 100 MHz, 1.3 A, 0.15 R DC"}
L1U = {"Price": "0.0763 USD (LCSC 10+)", "Note": "1 uH 2.5 A 1008 (FHD252010S-1R0MT); TI table 8-3: 1 uH"}
PCT = {"Note": "1 % (LM27762 R2 / R4 >= 50k; power-tree.md section 12)"}
PCT01 = {"Note": "0.1 % thin film: the +5V1 window (power-tree.md section 12)"}


def place(sym, pin, pt):
    """Move sym so that its pin <pin> sits on pt (schematic mm)."""
    p = sym[pin]
    sym.at = (round(sym.at[0] + pt[0] - p[0], 3), round(sym.at[1] + pt[1] - p[1], 3))
    return sym


def vpart(sh, kind, ref, value, top, gnd=True, **kw):
    """Vertical two-pin part with pin 1 on 'top' (pin 2 below); pin 2 to a GND symbol if gnd."""
    if kind == "C":
        s = C(sh, value, top, ref=ref, **kw)
    elif kind == "R":
        s = R(sh, value, top, ref=ref, **kw)
    else:
        lib, fp, lcsc = kind
        s = sh.add(lib, ref, value, top, fp=fp, lcsc=lcsc, **kw)
    place(s, "1", top)
    if gnd:
        sh.gnd(s["2"])
    return s


def hpart(sh, kind, ref, value, left, **kw):
    """Horizontal two-pin part with pin 1 on 'left' (pin 2 to the right)."""
    if kind == "C":
        s = C(sh, value, left, rot=90, ref=ref, **kw)
    elif kind == "R":
        s = R(sh, value, left, rot=90, ref=ref, **kw)
    else:
        lib, fp, lcsc = kind
        s = sh.add(lib, ref, value, left, rot=90, fp=fp, lcsc=lcsc, **kw)
    return place(s, "1", left)


def bead(sh, ref, left, value="600R@100MHz"):
    lib, fp, mpn, lcsc = BEAD
    s = sh.add(lib, ref, value, left, rot=90, fp=fp, lcsc=lcsc, mpn=mpn, fields=BEAD_F)
    return place(s, "1", left)


def rail(sh, a, b):
    sh.wire(a, b)


def buck(sh, uref, at, vin_name, out_name, cin, cout, lref, rtop, rbot, cff=None):
    """TPS62A01A cell. cin/cout: [(ref, value, kw)]; rtop/rbot: (ref, value); returns the IC."""
    u = sh.add(TPS62A01, uref, "TPS62A01ADRLR", at, fp="Package_TO_SOT_SMD:SOT-563", lcsc="C5181455",
               mpn="TPS62A01ADRLR",
               fields={"Price": "0.197 USD (LCSC 5+)",
                       "Note": "CIN at VIN(3)-GND(1) on the IC layer < 1 mm; L at SW(2); FB divider at pin 5"})
    vin, en, sw, fb = u["3"], u["4"], u["2"], u["5"]
    x0 = vin[0] - g(6 + 6 * len(cin))
    rail(sh, (x0, vin[1]), vin)
    sh.power(vin_name, (x0, vin[1]), dy=-2.54)
    for k, (ref, val, kw) in enumerate(cin):
        vpart(sh, "C", ref, val, (vin[0] - g(9 + 6 * k), vin[1]), **kw)
    xe = vin[0] - g(3)
    sh.path([en, (xe, en[1]), (xe, vin[1])])
    sh.gnd(u["1"])
    sh.nc(u["6"])
    lpt = (sw[0] + g(3), sw[1])
    sh.wire(sw, lpt)
    lw = hpart(sh, ("Device:L", "Inductor_SMD:L_1008_2520Metric", "C843292"), lref, "1u", lpt,
               mpn="FHD252010S-1R0MT", fields=L1U)
    xd = lw["2"][0] + g(4)
    y = sw[1]
    rt = vpart(sh, "R", rtop[0], rtop[1], (xd, y), gnd=False)
    rb = vpart(sh, "R", rbot[0], rbot[1], rt["2"])
    sh.path([fb, (fb[0] + g(2), fb[1]), (fb[0] + g(2), rt["2"][1]), rt["2"]])
    xe = xd
    if cff:
        cf = vpart(sh, "C", cff[0], cff[1], (xd + g(4), y), gnd=False, dnp=True,
                   fields={"Note": "DNP: feed-forward footprint across R1 (TPS62A01 DS 8.2.2.3, 120 pF)"})
        sh.wire(cf["2"], rt["2"])
        xe = xd + g(4)
    xs = []
    for k, (ref, val, kw) in enumerate(cout):
        x = xe + g(5 + 6 * k)
        vpart(sh, "C", ref, val, (x, y), **kw)
        xs.append(x)
    xend = (xs[-1] if xs else xe) + g(5)
    rail(sh, lw["2"], (xend, y))
    sh.power(out_name, (xend, y), dy=-2.54)
    return u, xend


def lm27762(sh, uref, at, vin_label, cin, c1, ccp, outp, outn, rpos, rneg, en=None, vin_y=None):
    """LM27762 cell drawn with wires. vin_label: name of the local input rail (label at its left end).
    c1, ccp: (ref, value, kw); outp/outn: (net label, [(ref, value, kw)] caps, bead ref, bead load rail);
    rpos = (R1 ref, val, R2 ref, val) FB+; rneg = (R3 ref, val, R4 ref, val) FB-.
    en: None -> EN+/EN- tied to VIN, PGOOD to GND; else (pull-up ref, value, label) -> EN+/EN- = label."""
    u = sh.add(LM27762, uref, "LM27762DSSR", at, fp="Package_SON:WSON-12-1EP_3x2mm_P0.5mm_EP1x2.65",
               lcsc="C473398", mpn="LM27762DSSR",
               fields={"Price": "0.960 USD (LCSC 1+)",
                       "Note": "CIN, CCP, C1 on the IC layer; CIN/CCP grounds join at pin 4; R1-R4 at the FB pins"})
    if vin_y is not None:
        place(u, "3", (u["3"][0], vin_y))
    vin = u["3"]
    # input rail (left), CIN
    x0 = vin[0] - g(14 + 6 * len(cin))
    rail(sh, (x0, vin[1]), vin)
    sh.label(vin_label, (x0, vin[1]), rot=180)
    for k, (ref, val, kw) in enumerate(cin):
        vpart(sh, "C", ref, val, (vin[0] - g(15 + 6 * k), vin[1]), **kw)
    xe = vin[0] - g(3)
    ep, en_m, pgd = u["12"], u["8"], u["1"]
    if en is None:
        sh.path([en_m, (xe, en_m[1]), (xe, vin[1])])
        sh.wire(ep, (xe, ep[1]))
    else:
        rref, rval, lab = en
        sh.path([ep, (xe, ep[1]), (xe, en_m[1])])
        sh.wire(en_m, (xe, en_m[1]))
        node = (xe, pgd[1] + g(3))
        sh.wire((xe, en_m[1]), node)
        xr = vin[0] - g(7)
        pu = vpart(sh, "R", rref, rval, (xr, vin[1]), gnd=False,
                   fields={"Note": "PG pull-up: U605 enabled by U603 power good (+/-2V5 after the BUF802 rails)"})
        sh.path([pu["2"], (xr, node[1]), node])
        sh.wire((xr, node[1]), (vin[0] - g(11), node[1]))
        sh.label(lab, (vin[0] - g(11), node[1]), rot=180)
    pe = (pgd[0] - g(1), pgd[1])
    sh.wire(pgd, pe)
    sh.gnd(pe)
    # flying cap C1 above the body
    c1p, c1n = u["10"], u["9"]
    yc = c1p[1] - g(3)
    ref, val, kw = c1
    cfly = hpart(sh, "C", ref, val, (c1p[0], yc), **kw)
    sh.wire(c1p, cfly["1"])
    sh.wire(c1n, cfly["2"])
    # GND / EP joined, CP cap
    gp, epp, cp = u["4"], u["13"], u["5"]
    yb = gp[1] + g(2)
    sh.path([gp, (gp[0], yb), (epp[0], yb), epp])
    sh.gnd((gp[0], yb))
    ref, val, kw = ccp
    vpart(sh, "C", ref, val, (cp[0], cp[1] + g(2)), **kw)
    sh.wire(cp, (cp[0], cp[1] + g(2)))
    # positive output: OUT+ (row 2) -> right g(5) -> up to the rail; FB+ (row 1) -> right g(2) -> up to the node
    op, fbp = u["11"], u["2"]
    xr0 = op[0]
    yP = op[1] - g(10)
    sh.path([op, (xr0 + g(5), op[1]), (xr0 + g(5), yP)])
    r1r, r1v, r2r, r2v = rpos
    xp = xr0 + g(9)
    r1 = vpart(sh, "R", r1r, r1v, (xp, yP - 7.62), gnd=False, fields=PCT)    # pin 1 = node (top), pin 2 = rail
    r2 = vpart(sh, "R", r2r, r2v, (xp, yP - 15.24), gnd=False, fields=PCT)   # pin 2 = node, pin 1 = GND (top)
    sh.power("GND", r2["1"], dy=-2.54, rot=180)
    sh.path([fbp, (xr0 + g(2), fbp[1]), (xr0 + g(2), r1["1"][1]), r1["1"]])
    lab, caps, bref, load = outp
    xs = xp + g(4)
    for k, (ref, val, kw) in enumerate(caps):
        vpart(sh, "C", ref, val, (xs + g(6 * k), yP), **kw)
    xb = xs + g(6 * len(caps))
    rail(sh, (xr0 + g(5), yP), (xb, yP))
    sh.label(lab, (xr0 + g(5), yP))
    b = bead(sh, bref, (xb, yP))
    sh.wire(b["2"], (b["2"][0] + g(4), yP))
    sh.power(load, (b["2"][0] + g(4), yP), dy=-2.54)
    # negative output: OUT- (row 4) -> right g(5) -> down to the rail; FB- (row 5) -> right g(2) -> down to the node
    on, fbn = u["6"], u["7"]
    yN = on[1] + g(10)
    sh.path([on, (xr0 + g(5), on[1]), (xr0 + g(5), yN)])
    r3r, r3v, r4r, r4v = rneg
    r3 = vpart(sh, "R", r3r, r3v, (xp, yN), gnd=False, fields=PCT)            # pin 1 = rail, pin 2 = node
    vpart(sh, "R", r4r, r4v, r3["2"], fields=PCT)                             # node -> GND
    sh.path([fbn, (xr0 + g(2), fbn[1]), (xr0 + g(2), r3["2"][1]), r3["2"]])
    lab, caps, bref, load = outn
    for k, (ref, val, kw) in enumerate(caps):
        vpart(sh, "C", ref, val, (xs + g(6 * k), yN), **kw)
    xb = xs + g(6 * len(caps))
    rail(sh, (xr0 + g(5), yN), (xb, yN))
    sh.label(lab, (xr0 + g(5), yN))
    b = bead(sh, bref, (xb, yN))
    sh.wire(b["2"], (b["2"][0] + g(4), yN))
    sh.power(load, (b["2"][0] + g(4), yN), dy=2.54)
    return u


def main():
    sh = new_sheet("power", comments=["Generated by gen/gen_power.py from docs/research/power-tree.md (24 Nov 2026).",
                                      "Rails are global power symbols; +5V1 goes to the strobe sheet (GVA-84+).",
                                      "Prices: LCSC product pages 24 Nov 2026 (power-tree.md section 6)."])
    T = 1.0
    # ------------------------------------------------------------------ USB-C input chain (wired)
    j = sh.add("Connector:USB_C_Receptacle_USB2.0_16P", "J601", "USB-C 16P", (g(22), g(40)),
               fp="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", lcsc="C165948", mpn="HRO TYPE-C-31-M-12",
               fields={"Note": "USB 2.0 receptacle (data for the STM32G474 USB FS); source must allow ~1 A"})
    for pin, net in (("A6", "USB_DP"), ("B6", "USB_DP"), ("A7", "USB_DM"), ("B7", "USB_DM")):
        sh.stub(j, pin, net, length=g(6))
    sh.nc(j["A8"])
    sh.nc(j["B8"])
    sh.stub(j, "A1", "GND", kind="gnd")
    sh.stub(j, "S1", "GND", kind="gnd")
    vb = j["A4"]
    yv = vb[1]
    xcc = vb[0] + g(4)
    for k, (pin, ref) in enumerate((("A5", "R601"), ("B5", "R602"))):
        p = j[pin]
        x = vb[0] + g(15 + 5 * k)
        sh.wire(p, (x, p[1]))
        sh.label(("CC1", "CC2")[k], (p[0] + g(3), p[1]))
        vpart(sh, "R", ref, "5.1k", (x, p[1]))
    f = sh.add("Device:Polyfuse_Small", "F601", "1.5A hold PTC", (0, 0), rot=90, fp="Fuse:Fuse_1206_3216Metric",
               lcsc="C118413")
    place(f, "1", (vb[0] + g(24), yv))
    sh.wire(vb, f["1"])
    sh.label("VBUS_IN", (vb[0] + g(18), yv))
    xt = f["2"][0] + g(5)
    tvs = sh.add("Device:D_TVS", "D601", "SMAJ5.0A", (0, 0), rot=90, fp="Diode_SMD:D_SMA", lcsc="C353442",
                 fields={"Note": "unidirectional SMAJ5.0A, cathode to VBUS_F (pin 2)"})
    place(tvs, "2", (xt, yv))
    sh.gnd(tvs["1"])
    fb1 = sh.add("Device:FerriteBead_Small", "FB601", "220R@100MHz 2A", (0, 0), rot=90, fp=FP["FB0805"],
                 lcsc="C88994", mpn="BLM21PG221SH1D")
    place(fb1, "1", (xt + g(5), yv))
    sh.wire(f["2"], fb1["1"])
    sh.label("VBUS_F", (xt, yv - 0.0))
    # VBUS rail: C602 / C603 (U601 input) are drawn at U601; C632 damper (fitted) here
    xv = fb1["2"][0] + g(4)
    sh.wire(fb1["2"], (xv + g(6), yv))
    sh.power("VBUS", (xv + g(6), yv), dy=-2.54)
    damp = sh.add("Device:C_Polarized", "C632", "47u 10V", (0, 0), fp="Capacitor_Tantalum_SMD:CP_EIA-3528-21_Kemet-B",
                  lcsc="C22036", mpn="TAJB476K010RNJ",
                  fields={"Note": "FITTED (recheck RP-3, 24 Nov): VBUS hot-plug damper, tantalum ESR ~1 R damps the "
                                  "cable-L / ceramic-C ringing that the SMAJ5.0A (clamp ~9 V) cannot keep under the "
                                  "U603 6.0 V abs max; measure the plug-in transient on the first board"})
    place(damp, "1", (xv, yv))
    sh.gnd(damp["2"])
    sh.text("USB-C sink, 5.1k CC pull-downs (default USB power, no PD).\n"
            "VBUS load 0.75 A typ / 0.97 A max at 4.75 V: needs a 5 V >= 1.5 A USB-C supply.\n"
            "F601 0.05-0.11 R + FB601 0.045 R: VBUS 4.60-5.25 V at the converters.\n"
            "D+/D- (both orientations) -> U608 USBLC6-2SC6 -> USB_DP/DM (mcu_if).", (g(8), g(68)), size=T)
    esd = sh.add("Power_Protection:USBLC6-2SC6", "U608", "USBLC6-2SC6", (g(30), g(85)),
                 fp="Package_TO_SOT_SMD:SOT-23-6", lcsc="C7519",
                 fields={"Note": "optional USB ESD array (pins 1/6 and 3/4 flow-through); may be left unfitted"})
    sh.stub(esd, "1", "USB_DP")
    sh.stub(esd, "3", "USB_DM")
    sh.stub(esd, "6", "USB_DP", length=g(3), kind="hlabel", shape="bidirectional")
    sh.stub(esd, "4", "USB_DM", length=g(3), kind="hlabel", shape="bidirectional")
    sh.stub(esd, "5", "VBUS", kind="power")
    sh.stub(esd, "2", "GND", kind="gnd")

    # ------------------------------------------------------------------ U603 buck-boost -> +5V1
    X3, Y3 = g(122), g(40)
    u3 = sh.add(TPS63802, "U603", "TPS63802DLAR", (X3, Y3), fp="scope-fe:Texas_DLA0010A_VSON-HR-10_2x3mm_P0.5mm",
                lcsc="C2845237", mpn="TPS63802DLAR",
                fields={"Price": "0.951 USD (LCSC 1+)",
                        "Note": "CIN (10/8) and COUT (6/8) both hot loops: tight on the top side; AGND(3) by its "
                                "own trace to GND near pin 8; FB(4) away from L1/L2"})
    vin = u3["10"]
    x0 = vin[0] - g(24)
    rail(sh, (x0, vin[1]), vin)
    sh.power("VBUS", (x0, vin[1]), dy=-2.54)
    vpart(sh, "C", "C601", "22u", (vin[0] - g(18), vin[1]),
          fields={"Note": "U603 CIN at pins 10/8 (moved; >= 4 uF effective, 25 V part)"})
    xe = vin[0] - g(3)
    sh.path([u3["2"], (xe, u3["2"][1]), (xe, vin[1])])
    sh.wire(u3["1"], (xe, u3["1"][1]))
    pg = u3["5"]
    sh.path([pg, (pg[0] - g(6), pg[1]), (pg[0] - g(6), pg[1] + g(5))])
    sh.label("PG_5V1", (pg[0] - g(6), pg[1] + g(5)), rot=180)
    l1, l2 = u3["9"], u3["7"]
    yl = l1[1] - g(3)
    lb = sh.add("Device:L", "L601", "0.47u", (0, 0), rot=90, fp="scope-fe:L_XR0420_4.4x4.2mm", lcsc="C167200",
                mpn="FXL0420-R47-M",
                fields={"Price": "0.294 USD (LCSC 5+)",
                        "Note": "0.47 uH +/-20 %, Isat 7.6 typ / 9.5 max A, 14 mR, 4.4 x 4.2 x 2.0 mm, land a 2.2 / "
                                "b 5.2 / c 2.5 mm = XR0420 (same footprint); alt. XR0420-R47M C5307593 (low stock)"})
    place(lb, "1", (l1[0], yl))
    sh.wire(l1, lb["1"])
    sh.wire(l2, lb["2"])
    a, gg = u3["3"], u3["8"]
    yb = a[1] + g(2)
    sh.path([a, (a[0], yb), (gg[0], yb), gg])
    sh.gnd((a[0], yb))
    vo, fb = u3["6"], u3["4"]
    xd = vo[0] + g(4)
    rt = vpart(sh, "R", "R603", "19.6k 0.1%", (xd, vo[1]), gnd=False,
               fields={"Note": "0.1 %: VOUT = 0.5 V x (1 + 19.6k/2.0k) = 5.40 V (5.334-5.466 V incl. FB +/-1 % "
                               "and 100 nA FB bias; was 499k/54.2k = 5.10 V)"})
    vpart(sh, "R", "R604", "2.0k 0.1%", rt["2"], fields=PCT01)
    sh.path([fb, (fb[0] + g(2), fb[1]), (fb[0] + g(2), rt["2"][1]), rt["2"]])
    for k, ref in enumerate(("C610", "C611")):
        vpart(sh, "C", ref, "22u", (xd + g(6 + 6 * k), vo[1]),
              fields={"Note": "U603 COUT at pins 6/8 (moved; 2 x 22 uF, 25 V part)"})
    xh = xd + g(20)
    rail(sh, vo, (xh + g(8), vo[1]))
    sh.hlabel("+5V1", (xh, vo[1] - g(3)), "output")
    sh.wire((xh, vo[1]), (xh, vo[1] - g(3)))
    sh.text("+5V1 = 5.40 V (5.334-5.466 V; OVP 5.5 V min): GVA-84+ x2 bias tees\n"
            "on the strobe sheet via R419 / R420 2.49 R, own track from C610/C611.\n"
            "EN, MODE = VIN: always on, forced PWM 1.4-2.1 MHz.", (X3 - g(22), Y3 + g(19)), size=T)
    fb2 = bead(sh, "FB602", (xh + g(8), vo[1]))

    # ------------------------------------------------------------------ U604 LM27762: +/-5 V for the BUF802
    X4 = g(205)                                     # VIN row of U604 = VOUT row of U603 (same Y)
    sh.wire(fb2["2"], (X4 - g(34), vo[1]))          # -> start of the U604 input rail (label +5V1F there)
    lm27762(sh, "U604", (X4, Y3), "+5V1F", vin_y=vo[1],
            cin=[("C613", "100n", {"fields": {"Note": "U604 pin 3, closest"}}),
                 ("C612", "22u", {"fields": {"Note": "U604 CIN on the IC layer at pin 3 (moved; DECOUPLING-4)"}})],
            c1=("C618", "1u", {"size": "0603",
                                 "fields": {"Note": "flying cap C1, 50 V X5R 0603 (JLC basic C15849; was C29936 "
                                                    "25 V X7R)"}}),
            ccp=("C626", "10u", {"fields": {"Note": "CCP at pin 5 (moved from the LM337 ADJ)"}}),
            outp=("+5V_LDO", [("C617", "10u", {"fields": {"Note": "OUT+ at pin 11 (moved)"}})], "FB604", "+5V"),
            outn=("-5V_LDO", [("C621", "10u", {"fields": {"Note": "OUT- at pin 6 (moved)"}})], "FB603", "-5V"),
            rpos=("R613", "300k", "R614", "100k"), rneg=("R605", "150k", "R606", "51k"))
    sh.text("U604: OUT+ = 1.2 V x (300k + 100k)/100k = +4.800 V (4.656-4.944); OUT- = -1.22 V x (150k + 51k)/51k\n"
            "= -4.808 V (4.664-4.952), 1 % dividers. BUF802 each side >= 4.65 V. VIN 5.319-5.466 V (<= 5.5 V).\n"
            "Headroom OUT- 0.156 V min (RNEG 4.5 R, 41 mA, 26 mV LDO). EN+/EN- = VIN, PGOOD to GND.", (g(185), g(78)), size=T)

    # ------------------------------------------------------------------ U601 +3V3, U602 +1V2
    Yb = g(130)
    buck(sh, "U601", (g(40), Yb), "VBUS", "+3V3",
         cin=[("C603", "10u", {"fields": {"Note": "U601 CIN at VIN(3)-GND(1), < 1 mm (moved)"}}),
              ("C602", "100n", {"fields": {"Note": "U601 pin 3 (moved)"}})],
         cout=[("C604", "22u", {"fields": {"Note": "U601 COUT (one 22 uF; +3V3 plane caps behind)"}})],
         lref="L602", rtop=("R609", "100k"), rbot=("R610", "22k"), cff=("C631", "120p"))
    buck(sh, "U602", (g(125), Yb), "+3V3", "+1V2",
         cin=[("C609", "10u", {"fields": {"Note": "U602 CIN at pin 3 (moved from +1V2)"}}),
              ("C607", "1u", {"fields": {"Note": "U602 pin 3"}})],
         cout=[("C605", "22u", {"fields": {"Note": "U602 COUT (moved from +3V3)"}}),
               ("C608", "1u", {})],
         lref="L603", rtop=("R611", "100k"), rbot=("R612", "100k"))
    sh.text("U601: VOUT = 0.6 V x (1 + 100k/22k) = 3.327 V (3.224-3.433 V with FB and 1 %).\n"
            "100 % mode dropout VIN >= 3.53 V at 0.67 A: margin >= 1.07 V at VBUS 4.60 V.\n"
            "0.19 W typ / 0.30 W max, +27 / +45 K. C631 Cff footprint DNP.\n"
            "U602: 0.6 V x 2 = 1.200 V; soft start 1 ms -> 1.2 mV/us (GW1NZ VCC 0.6-6 mV/us).",
            (g(15), Yb + g(20)), size=T)

    # ------------------------------------------------------------------ U605 LM27762: +/-2V5
    xu5, yu5 = g(250), g(132)
    s = (xu5 - g(38), yu5 - g(4))                    # U605 VIN row; its input rail starts at xu5 - g(28)
    sh.power("+3V3", (s[0] - g(4), s[1]), dy=-2.54)
    sh.wire((s[0] - g(4), s[1]), s)
    b5 = bead(sh, "FB605", s)
    sh.wire(b5["2"], (xu5 - g(28), s[1]))
    lm27762(sh, "U605", (xu5, yu5), "+3V3_CP",
            cin=[("C625", "10u", {"fields": {"Note": "U605 CIN on the IC layer at pin 3 (moved from +2V5)"}})],
            c1=("C624", "1u", {"fields": {"Note": "flying cap C1 (moved from +2V5)"}}),
            ccp=("C619", "4.7u", {"size": "0603",
                                    "fields": {"Note": "CCP at pin 5, 16 V X5R 0603: about 3 uF at 3.3 V (>= 2 uF "
                                                       "effective, DS 7.2.2.4.1; JLC basic C19666, same rating as "
                                                       "the former C99229)"}}),
            outp=("+2V5_LDO", [("C630", "10u", {"fields": {"Note": "NEW: OUT+ at pin 11 (DS: >= 2.2 uF)"}})],
                  "FB606", "+2V5"),
            outn=("-2V5_LDO", [("C628", "10u", {"fields": {"Note": "OUT- at pin 6 (moved)"}})], "FB607", "-2V5"),
            rpos=("R615", "110k", "R616", "100k"), rneg=("R607", "100k", "R608", "100k"),
            en=("R617", "100k", "PG_5V1"))
    sh.text("U605: OUT+ = 1.2 V x 210k/100k = +2.520 V (2.456-2.584); OUT- = -1.22 V x 200k/100k = -2.440 V\n"
            "(2.380-2.500; 1 % dividers). VIN 3.24-3.37 V; headroom OUT+ 0.66 V, OUT- 0.45 V\n"
            "(RNEG at 3.3 V not in the DS, 5 R assumed). EN+/EN- = U603 PG (R617 to VIN).", (g(208), g(166)), size=T)

    # ------------------------------------------------------------------ decoupling placed at the loads
    yL = g(190)
    sh.rect((g(8), yL - g(8)), (g(200), yL + g(22)))
    sh.text("DECOUPLING PLACED AT THE LOADS (moved parts; same rail nets, location per Note / kicad/README.md)",
            (g(10), yL - g(7)), size=T)
    remote = [("C606", "100n", "+3V3", "U401 pin 1 (TRF37D73 VCC) beside C404, top (PDN-7)", {}),
              ("C622", "100n", "+3V3", "U402 pin 1 (TRF37D73 VCC) beside C409, top (PDN-7)", {}),
              ("C616", "4.7u", "+5V", "U101 pins 1/12 (BUF802 +5V) beside C108 (PDN-6), 10 V part", {}),
              ("C614", "10n", "-5V", "U101 pin 10 (BUF802 VSO-) top side, between pin and R112 (DECOUPLING-1)", {}),
              ("C627", "1u", "-5V", "FB603 output (-5V load side)", {}),
              ("C615", "1u", "+2V5", "U302 pin 6 / U301 pin 10 (+2V5) (PDN-6)", {}),
              ("C620", "4.7u", "-2V5", "U302 pin 3 (TLV3801 VEE) beside C307 (PDN-6), 10 V part", {}),
              ("C629", "100n", "-2V5", "FB607 output (-2V5 load side)", {})]
    for k, (ref, val, net, note, kw) in enumerate(remote):
        x = g(16 + 23 * k)
        neg = net.startswith("-")
        c = C(sh, val, (x, yL + g(3)), rot=180 if neg else 0, ref=ref, fields={"Note": "placed at " + note}, **kw)
        if neg:                                  # pin 1 (rail) at the bottom, GND on top
            sh.power("GND", c["2"], dy=-2.54, rot=180)
            sh.power(net, c["1"], dy=2.54)
        else:
            sh.power(net, c["1"], dy=-2.54)
            sh.gnd(c["2"])
        sh.text(ref + ": " + note.split(" (")[0].replace(", top", "")[:22], (x - g(3), yL + g(14)), size=0.8)

    # ------------------------------------------------------------------ notes, PWR_FLAGs
    sh.text("Load (typ / max): +3V3 0.51 / 0.67 A, +1V2 20 / 30 mA, +5V1 0.29 / 0.34 A (GVA-84+ x2 + U604),\n"
            "+5V / -5V 37 / 41 mA, +2V5 40 / 48 mA, -2V5 42 / 50 mA. USB: 0.75 A typ, 0.97 A all maxima.\n"
            "Every regulator: VIN range, dropout and margin in docs/research/power-tree.md section 3.",
            (g(210), g(190)), size=T)
    flags = [("GND", True), ("VBUS", True), ("+3V3", True), ("+1V2", True), ("+5V", True), ("-5V", True),
             ("+2V5", True), ("-2V5", True), ("+5V1F", False), ("+3V3_CP", False)]
    for k, (net, israil) in enumerate(flags):
        x, y = g(40 + 11 * k), g(219)
        sh.power("PWR_FLAG", (x, y))
        if israil:
            sh.power(net, (x, y), dy=(2.54 if net == "GND" or net.startswith("-") else -2.54))
        else:
            sh.wire((x, y), (x, y + 2.54))
            sh.label(net, (x, y + 2.54))
    sh.save()


if __name__ == "__main__":
    main()
