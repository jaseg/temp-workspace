"""Schematic of the phase sampling stage (delay-line snapshot converter) -> phase-sampler-schematic.svg

Hand-placed SVG. Taps 2 to 14 are identical to the ones drawn and are abbreviated.
"""
import html

W, H = 2920, 1000
INK, SUB, WIRE, STB, FILL = "#16181d", "#4a5160", "#1c2330", "#b3401c", "#ffffff"
o = []


def esc(s):
    return html.escape(s, quote=False)


def wire(pts, c=WIRE, dash=False):
    d = "M" + " L".join(f"{x},{y}" for x, y in pts)
    da = ' stroke-dasharray="7 6"' if dash else ""
    o.append(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="1.8"{da}/>')


def dot(x, y, c=WIRE):
    o.append(f'<circle cx="{x}" cy="{y}" r="3.6" fill="{c}"/>')


def text(x, y, s, size=11, anchor="start", c=SUB, bold=False):
    b = ' font-weight="700"' if bold else ""
    o.append(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" fill="{c}"{b}>{esc(s)}</text>')


def label(p1, p2, ref, val, side):
    """Reference and value next to a part between p1 and p2. side: 'a' above/right, 'b' below/left."""
    (x1, y1), (x2, y2) = p1, p2
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    if y1 == y2:
        if side == "a":
            text(mx, my - 22, ref, anchor="middle", c=INK, bold=True)
            text(mx, my - 11, val, anchor="middle")
        else:
            text(mx, my + 21, ref, anchor="middle", c=INK, bold=True)
            text(mx, my + 32, val, anchor="middle")
    else:
        dx, an = (13, "start") if side == "a" else (-13, "end")
        text(mx + dx, my - 2, ref, anchor=an, c=INK, bold=True)
        text(mx + dx, my + 10, val, anchor=an)


def res(p1, p2, ref="", val="", side="a", c=WIRE):
    (x1, y1), (x2, y2) = p1, p2
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    if y1 == y2:
        s = 1 if x2 > x1 else -1
        wire([p1, (mx - 18 * s, my)], c); wire([(mx + 18 * s, my), p2], c)
        o.append(f'<rect x="{mx - 18}" y="{my - 7}" width="36" height="14" fill="{FILL}" stroke="{c}" stroke-width="1.8"/>')
    else:
        s = 1 if y2 > y1 else -1
        wire([p1, (mx, my - 18 * s)], c); wire([(mx, my + 18 * s), p2], c)
        o.append(f'<rect x="{mx - 7}" y="{my - 18}" width="14" height="36" fill="{FILL}" stroke="{c}" stroke-width="1.8"/>')
    if ref or val:
        label(p1, p2, ref, val, side)


def cap(p1, p2, ref="", val="", side="a", c=WIRE):
    (x1, y1), (x2, y2) = p1, p2
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    if y1 == y2:
        s = 1 if x2 > x1 else -1
        wire([p1, (mx - 4 * s, my)], c); wire([(mx + 4 * s, my), p2], c)
        for dx in (-4, 4):
            o.append(f'<path d="M{mx + dx},{my - 11} L{mx + dx},{my + 11}" stroke="{c}" stroke-width="2.6"/>')
    else:
        s = 1 if y2 > y1 else -1
        wire([p1, (mx, my - 4 * s)], c); wire([(mx, my + 4 * s), p2], c)
        for dy in (-4, 4):
            o.append(f'<path d="M{mx - 11},{my + dy} L{mx + 11},{my + dy}" stroke="{c}" stroke-width="2.6"/>')
    if ref or val:
        label(p1, p2, ref, val, side)


def ind(p1, p2, ref="", val="", side="a", c=WIRE):
    (x1, y1), (x2, y2) = p1, p2
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    s = 1 if y2 > y1 else -1
    wire([p1, (mx, my - 18 * s)], c); wire([(mx, my + 18 * s), p2], c)
    d = f"M{mx},{my - 18}" + "".join(f" a6,6 0 0 1 0,12" for _ in range(3))
    o.append(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="1.8"/>')
    if ref or val:
        label(p1, p2, ref, val, side)


def diode(anode, cathode, ref="", val="", side="a"):
    (x1, y1), (x2, y2) = anode, cathode
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    s = 1 if y2 > y1 else -1                      # vertical only
    wire([anode, (mx, my - 9 * s)]); wire([(mx, my + 9 * s), cathode])
    o.append(f'<path d="M{mx - 9},{my - 9 * s} L{mx + 9},{my - 9 * s} L{mx},{my + 9 * s} Z" fill="{FILL}" stroke="{WIRE}" stroke-width="1.8"/>')
    o.append(f'<path d="M{mx - 9},{my + 9 * s} L{mx + 9},{my + 9 * s}" stroke="{WIRE}" stroke-width="2.4"/>')
    if ref or val:
        label(anode, cathode, ref, val, side)


def gnd(x, y, c=WIRE):
    for i, w in enumerate((11, 7, 3)):
        o.append(f'<path d="M{x - w},{y + 4 * i} L{x + w},{y + 4 * i}" stroke="{c}" stroke-width="1.8"/>')


def flag(x, y, s, c=WIRE, up=True):
    """Supply or bias rail symbol at the end of a wire."""
    d = -1 if up else 1
    wire([(x, y), (x, y + 10 * d)], c)
    o.append(f'<path d="M{x - 9},{y + 10 * d} L{x + 9},{y + 10 * d}" stroke="{c}" stroke-width="2.4"/>')
    text(x, y + (10 * d - 5 if up else 10 * d + 14), s, anchor="middle", c=INK, bold=True)


def tline(p1, p2, s1, s2="", c=WIRE, side="a"):
    """A length of transmission line on a wire."""
    (x1, y1), (x2, y2) = p1, p2
    if y1 == y2:
        a, b = min(x1, x2), max(x1, x2)
        wire([(x1, y1), (x2, y2)], c)
        o.append(f'<rect x="{a + 8}" y="{y1 - 6}" width="{b - a - 16}" height="12" rx="6" fill="#e6ebf3" stroke="{c}" stroke-width="1.8"/>')
        yy = y1 - 12 if side == "a" else y1 + 20
        text((a + b) / 2, yy, s1 + ("  " + s2 if s2 else ""), anchor="middle", size=10.5)
    else:
        a, b = min(y1, y2), max(y1, y2)
        wire([(x1, y1), (x2, y2)], c)
        o.append(f'<rect x="{x1 - 6}" y="{a + 8}" width="12" height="{b - a - 16}" rx="6" fill="#e6ebf3" stroke="{c}" stroke-width="1.8"/>')
        text(x1 + 13, (a + b) / 2 - 2, s1, size=10.5)
        text(x1 + 13, (a + b) / 2 + 10, s2, size=10.5)


def amp(xin, y, ref, right=True, c=WIRE):
    """Amplifier triangle, 56 long; returns the output x."""
    s = 1 if right else -1
    xo = xin + 56 * s
    o.append(f'<path d="M{xin},{y - 26} L{xin},{y + 26} L{xo},{y} Z" fill="{FILL}" stroke="{c}" stroke-width="1.8"/>')
    text(xin + 20 * s, y + 4, ref, anchor="middle", c=INK, bold=True, size=10.5)
    return xo


def port(x, y, s, left=True, c=WIRE):
    d = -1 if left else 1
    o.append(f'<path d="M{x},{y} L{x + 12 * d},{y - 8} L{x + 12 * d + 0.01},{y + 8} Z" fill="{c}"/>')
    text(x + 18 * d, y + 4, s, anchor="end" if left else "start", c=INK, bold=True, size=11.5)


def bias_tee(x, y, ref_l, ref_c, c=WIRE, side="b"):
    """Collector feed: choke from the output node up to +5 V, with a decoupling capacitor."""
    ind((x, y), (x, y - 70), ref_l, "RF choke", side, c)
    dot(x, y, c)
    dot(x, y - 70, c)
    flag(x, y - 70, "+5 V", c)
    cap((x, y - 70), (x + 46, y - 70), "", "", "a", c)
    text(x + 62, y - 76, f"{ref_c} 100n", size=10)
    wire([(x + 46, y - 70), (x + 46, y - 52)], c)
    gnd(x + 46, y - 52, c)


def pad_pi(x, y, r1, r2, r3, v_sh, v_se, c=WIRE):
    """Pi attenuator starting at x on a horizontal wire; returns the end x."""
    dot(x, y, c)
    res((x, y), (x, y + 74), r1, v_sh, "b", c); gnd(x, y + 74, c)
    res((x, y), (x + 80, y), r2, v_se, "a", c)
    dot(x + 80, y, c)
    res((x + 80, y), (x + 80, y + 74), r3, v_sh, "a", c); gnd(x + 80, y + 74, c)
    return x + 80


# ============================================================ limiter chain
YS = 300
text(40, 40, "Phase sampling stage: limiter, tapped delay line, 16 two-diode gates, readout", 18, c=INK, bold=True)
text(40, 62, "Concept schematic of the simulated circuit. Taps 2 to 14 repeat tap 1. Strobe chain values are targets and have not been simulated.", 12)

port(120, YS, "BUF802 OUT", left=True)
res((120, YS), (198, YS), "R1", "49.9")
cap((198, YS), (248, YS), "C1", "100n")
x = amp(258, YS, "U1")
wire([(248, YS), (258, YS)])
wire([(x, YS), (x + 24, YS)])
bias_tee(x + 24, YS, "L1", "C2")
cap((x + 24, YS), (x + 84, YS), "C3", "100n")
x = pad_pi(x + 84, YS, "R2", "R3", "R4", "150", "37.4")
text(x - 40, YS + 108, "6 dB", anchor="middle", size=10.5)
wire([(x, YS), (x + 30, YS)])
x = amp(x + 30, YS, "U2")
wire([(x, YS), (x + 24, YS)])
bias_tee(x + 24, YS, "L2", "C4")
cap((x + 24, YS), (x + 84, YS), "C5", "100n")
x = pad_pi(x + 84, YS, "R5", "R6", "R7", "75", "121")
text(x - 40, YS + 108, "14 dB", anchor="middle", size=10.5)
text(258, YS + 60, "U1, U2: GVA-84+", size=10.5)
text(x + 6, YS - 40, "±0.5 V", size=11, c=INK, bold=True)

# ============================================================ lines and taps
YP, YN = 600, 660
XT = [1010, 1370, 1870]
NAMES = ["0", "1", "15"]
BRK = (1560, 1700)
tline((x, YS), (XT[0], YS), "TL0  lead-in ≤ 10 mm", "")
SEC = "35 ps, 5.8 mm, 60 Ω unloaded"
tline((XT[0], YS), (XT[1], YS), SEC)
wire([(XT[1], YS), (BRK[0], YS)])
wire([(BRK[0], YS), (BRK[1], YS)], dash=True)
tline((BRK[1], YS), (XT[2], YS), "35 ps")
wire([(XT[2], YS), (2060, YS)])
res((2060, YS), (2060, YS + 90), "R8", "49.9"); gnd(2060, YS + 90)
text(XT[0] - 150, YS - 34, "SIGNAL LINE →", 11.5, c=INK, bold=True)

# strobe lines, driven from the right, terminated at the left
XLP, XLN = 850, 910
for yl, xl, pol, xoff in ((YP, XLP, "+", -70), (YN, XLN, "−", 70)):
    xs = [xt + xoff for xt in XT]
    res((xl, yl), (xl, yl + 80), "R9" if pol == "+" else "R10", "49.9", "b", STB); gnd(xl, yl + 80, STB)
    wire([(xl, yl), (xs[0], yl)], STB)
    tline((xs[0], yl), (xs[1], yl), "" if pol == "+" else "35 ps, 5.8 mm per section, both strobe lines", c=STB, side="b")
    wire([(xs[1], yl), (BRK[0], yl)], STB)
    wire([(BRK[0], yl), (BRK[1], yl)], STB, dash=True)
    tline((BRK[1], yl), (xs[2], yl), "", c=STB)
    wire([(xs[2], yl), (1960 if pol == "+" else 2030, yl)], STB)
text(XLP - 10, YP - 12, "← STROBE+", 11.5, c=STB, bold=True)
text(XLN + 12, YN + 20, "← STROBE−", 11.5, c=STB, bold=True)
text((BRK[0] + BRK[1]) / 2, YS - 16, "taps 2 … 14", 12, "middle", INK, True)
text((BRK[0] + BRK[1]) / 2, 450, "13 more gates,", 11.5, "middle")
text((BRK[0] + BRK[1]) / 2, 466, "identical to tap 1", 11.5, "middle")

for xt, nm in zip(XT, NAMES):
    full = nm == "0"
    xa, xk = xt - 70, xt + 70
    dot(xt, YS)
    wire([(xt, YS), (xt, 340)]); dot(xt, 340)
    wire([(xa, 340), (xk, 340)])
    diode((xa, 404), (xa, 340), "Da", "BAT15-04R" if full else "", "b")
    diode((xk, 340), (xk, 404), "Dk", "(series pair)" if full else "", "a")
    wire([(xa, 404), (xa, 420)]); wire([(xk, 404), (xk, 420)])
    dot(xa, 420); dot(xk, 420); dot(xt, 420)
    res((xa, 420), (xt, 420), "", "20k", "b")
    res((xt, 420), (xk, 420), "", "20k", "b")
    # bias and bleed
    res((xa, 420), (xa - 80, 420), "", "43k", "a"); flag(xa - 80, 420, "−VB")
    res((xk, 420), (xk + 80, 420), "", "43k", "a"); flag(xk + 80, 420, "+VB")
    # hold capacitors and isolation to the strobe lines
    cap((xa, 420), (xa, 480), "Ca", "0.47p", "b"); res((xa, 480), (xa, YP), "", "220", "b", STB); dot(xa, YP, STB)
    cap((xk, 420), (xk, 480), "Ck", "0.47p", "a"); res((xk, 480), (xk, YN), "", "220", "a", STB); dot(xk, YN, STB)
    # readout
    wire([(xt, 420), (xt, 730)])
    o.append(f'<path d="M{xt - 28},730 L{xt + 60},730 L{xt + 16},800 Z" fill="{FILL}" stroke="{WIRE}" stroke-width="1.8"/>')
    text(xt + 1, 746, "+", 12, "middle", INK, True); text(xt + 36, 746, "−", 12, "middle", INK, True)
    wire([(xt + 36, 730), (xt + 36, 706)]); flag(xt + 36, 706, "VTH")
    wire([(xt + 16, 800), (xt + 16, 838)])
    o.append(f'<path d="M{xt + 16},850 L{xt + 8},838 L{xt + 24},838 Z" fill="{WIRE}"/>')
    text(xt + 16, 868, f"TDC{nm} → FPGA", 11.5, "middle", INK, True)
    text(xt + 66, 772, "comparator, 5–10 ns" if full else "", 10.5)
    text(xt, YS - 12, f"tap {nm}", 12, "middle", INK, True)

# ============================================================ strobe drivers
def chain(y, x0, pol, n0, c0):
    """Final and pre-driver for one strobe polarity, drawn right to left towards x0."""
    c = STB
    dot(x0 + 40, y, c)
    tline((x0 + 40, y), (x0 + 40, y + 96), "clip stub", "80 ps, shorted", c); gnd(x0 + 40, y + 96, c)
    wire([(x0, y), (x0 + 40, y)], c)
    cap((x0 + 40, y), (x0 + 110, y), f"C{c0}", "100n", "a", c)
    bias_tee(x0 + 110, y, f"L{n0}", f"C{c0 + 1}", c, side="a")
    wire([(x0 + 110, y), (x0 + 196, y)], c)
    xi = x0 + 252
    amp(xi, y, f"U{n0}", right=False, c=c)
    cap((xi, y), (xi + 60, y), f"C{c0 + 2}", "100n", "a", c)
    xe = pad_pi(xi + 60, y, "", "", "", "150", "37.4", c)
    text(xi + 100, y + 108, "6 dB", anchor="middle", size=10.5)
    bias_tee(xe + 30, y, f"L{n0 + 1}", f"C{c0 + 3}", c, side="a")
    wire([(xe, y), (xe + 116, y)], c)
    xi2 = xe + 172
    amp(xi2, y, f"U{n0 + 1}", right=False, c=c)
    cap((xi2, y), (xi2 + 60, y), f"C{c0 + 4}", "100n", "a", c)
    dot(xi2 + 60, y, c)
    res((xi2 + 60, y), (xi2 + 60, y + 74), "", "68", "b", c); gnd(xi2 + 60, y + 74, c)
    res((xi2 + 60, y), (xi2 + 150, y), "", "100", "a", c)
    port(xi2 + 150, y, f"FPGA STROBE_{pol}", left=False, c=c)
    text(xi2 + 168, y + 22, "LVCMOS33, about 1 ns edge", size=10.5)


wire([(1960, YP), (1960, 470), (2080, 470)], STB)
chain(470, 2080, "P", 3, 11)
wire([(2030, YN), (2030, 800), (2080, 800)], STB)
chain(800, 2080, "N", 5, 21)
text(1968, 512, "+3 V pulse,", 11, c=STB, bold=True)
text(1968, 526, "160 ps", 11, c=STB, bold=True)
text(2038, 716, "−3 V pulse, 160 ps", 11, c=STB, bold=True)
text(2360, 640, "U3–U6: GVA-84+. Both chains identical and length matched;", 11)
text(2360, 656, "STROBE_N is the complementary FPGA output.", 11)

# ============================================================ notes
NX, NY = 40, 500
text(NX, NY, "Design targets", 13, c=INK, bold=True)
notes = [
    "Signal on the line: ±0.5 V, edge about 150 ps, AC coupled; line 60 Ω unloaded, about 50 Ω with the taps.",
    "Tap spacing in signal time = signal section + strobe section = 70 ps (simulated: 72 ps mean).",
    "Signal line 15 × 5.8 mm = 87 mm; strobe pair the same length, run in the opposite direction.",
    "Gate: aperture 55–70 ps; captures 16–31 % of the line voltage with 220 Ω isolation and ±3 V strobe.",
    "Hold nodes return to ±VB through 43 kΩ (20 ns); read the comparators 5–8 ns after the strobe.",
    "±VB = ±0.5 V reverse bias. VTH = common threshold, about 0 V, trimmed by a DAC.",
    "Comparator: CMOS input, offset below about 10 mV, 3.3 V CMOS output, 22 Ω series to the FPGA.",
    "Tap stubs under 1 mm; Da/Dk, Ca/Ck and the 220 Ω resistors placed symmetrically about the tap.",
]
for i, s in enumerate(notes):
    text(NX, NY + 20 + 17 * i, f"{i + 1}.  {s}", 11.5)

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="Helvetica, Arial, sans-serif">'
       f'<rect width="{W}" height="{H}" fill="#ffffff"/>' + "".join(o) + "</svg>")
open("phase-sampler-schematic.svg", "w").write(svg)
