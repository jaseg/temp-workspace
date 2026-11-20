"""Block diagram of the scope front end with delay-line phase recovery -> block-diagram.svg

Every connection carries its design targets: level, impedances, delay or length, coupling.
"""
import html

W, H = 2090, 1290
INK, SUB, LINE, BOX, ACC, STB, CTL = "#16181d", "#4a5160", "#2b3140", "#eef1f6", "#1f5fbf", "#b3401c", "#5b6472"
out = []


def esc(s):
    return html.escape(s, quote=False)


def box(x, y, w, h, title, lines=(), fill=BOX, stroke=LINE):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>')
    n = 1 + len(lines)
    y0 = y + h / 2 - (n - 1) * 8
    out.append(f'<text x="{x + w / 2}" y="{y0 + 4.5}" text-anchor="middle" font-size="14.5" font-weight="700" fill="{INK}">{esc(title)}</text>')
    for i, s in enumerate(lines):
        out.append(f'<text x="{x + w / 2}" y="{y0 + 4.5 + 16 * (i + 1)}" text-anchor="middle" font-size="11.5" fill="{SUB}">{esc(s)}</text>')


def edge(pts, color=LINE, arrow=True, both=False, dash=False):
    d = "M" + " L".join(f"{x},{y}" for x, y in pts)
    mk = f' marker-end="url(#ah-{color[1:]})"' if arrow else ""
    if both:
        mk += f' marker-start="url(#as-{color[1:]})"'
    da = ' stroke-dasharray="6 4"' if dash else ''
    out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2"{mk}{da}/>')


def note(x, y, lines, anchor="start", color=INK, num=None):
    """Annotation with a white backing; first line is the level and is bold."""
    w = max(len(s) for s in lines) * 6.1 + 14 + (22 if num else 0)
    h = len(lines) * 14.5 + 8
    x0 = x if anchor == "start" else x - w / 2 if anchor == "middle" else x - w
    out.append(f'<rect x="{x0}" y="{y}" width="{w}" height="{h}" rx="4" fill="#ffffff" fill-opacity="0.94" stroke="#c9ced8" stroke-width="0.8"/>')
    tx = x0 + 7 + (22 if num else 0)
    if num:
        out.append(f'<circle cx="{x0 + 13}" cy="{y + 13}" r="9" fill="{color}"/><text x="{x0 + 13}" y="{y + 17}" text-anchor="middle" font-size="10.5" font-weight="700" fill="#fff">{num}</text>')
    for i, s in enumerate(lines):
        wt = ' font-weight="700"' if i == 0 else ""
        out.append(f'<text x="{tx}" y="{y + 16 + 14.5 * i}" font-size="11.2"{wt} fill="{color if i == 0 else SUB}">{esc(s)}</text>')


def dot(x, y, c=LINE):
    out.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{c}"/>')


# ---------------------------------------------------------------- boxes
box(30, 95, 110, 60, "J1", ["input SMA"])
box(250, 85, 180, 80, "Divider 5:1", ["1.6 MΩ / 422 kΩ", "0.6 pF compensation"])
box(560, 75, 200, 100, "BUF802", ["composite loop with", "OPA197, offset DAC"])
box(960, 100, 90, 50, "10 Ω")
box(1170, 75, 200, 100, "Sampling bridge", ["2 × BAT15-04W", "bias ±1 V, 25 Ω per rail"])
box(1500, 75, 210, 100, "Hold + amplifier", ["2.2 pF, OPA810", "gain 2.2"])
box(1840, 85, 170, 80, "ADC", ["one conversion", "per strobe"])

box(800, 300, 120, 50, "50 Ω leg")
box(760, 440, 200, 90, "Limiter", ["2 × GVA-84+", "6 dB pad between"])
box(1080, 458, 120, 54, "14 dB pad")
box(1310, 425, 340, 120, "Tapped delay line", ["16 taps, 35 ps (5.8 mm) per section", "525 ps / 87 mm in total", "60 Ω unloaded, about 50 Ω loaded"])
box(1790, 458, 110, 54, "50 Ω", ["to ground"])
box(1310, 640, 340, 90, "16 two-diode gates", ["BAT15-04R pair per tap", "2 × 0.47 pF hold, 2 × 220 Ω, bias ±0.5 V"])
box(1040, 658, 130, 54, "2 × 50 Ω", ["to ground"])
box(1310, 830, 340, 70, "16 comparators", ["5–10 ns, CMOS input, common threshold"])

box(1760, 640, 250, 90, "TDC strobe finals P, N", ["2 × GVA-84+", "shorted clip stubs, 80 ps"], fill="#fbeee9", stroke=STB)
box(1760, 300, 250, 80, "Main strobe final", ["GVA-84+, clip stub 80 ps,", "common-mode choke as balun"], fill="#fbeee9", stroke=STB)
box(1760, 835, 250, 70, "Pre-drivers P, N", ["2 × GVA-84+"], fill="#fbeee9", stroke=STB)

box(930, 1000, 430, 120, "FPGA  GW1NZ-1", ["strobe timing: serialiser 1 ns + input/output delay 30 ps", "snapshot decode, slow-path time stamps", "sample and time-stamp stream to the MCU"], fill="#e9f0fb", stroke=ACC)
box(110, 440, 250, 80, "Slow trigger comparators", ["2 × TLV3602 (4 comparators)"])
box(570, 245, 110, 50, "100 Ω")
box(640, 1170, 160, 60, "50 MHz XO")
box(1040, 1180, 210, 60, "MCU", ["SPI, fit, display"])
box(1420, 1165, 300, 90, "Bias and threshold DACs", ["offset, bridge bias ±1 V, gate bias ±0.5 V,", "trigger level, comparator threshold", "(slow, RC filtered; not drawn to each block)"], fill="#f3f3f1", stroke=CTL)

# ---------------------------------------------------------------- signal path
edge([(140, 125), (250, 125)])
note(145, 40, ["±2.5 V full scale", "Zin 1 MΩ ∥ 1.1 pF", "DC coupled"], num=1)
edge([(430, 125), (560, 125)])
note(400, 180, ["±0.5 V", "HF: 330 pF AC into IN (2.4 pF)", "LF: DC via OPA197 into In_Aux", "divider to pin < 5 mm"], num=2)
edge([(760, 125), (960, 125)])
dot(860, 125)
note(775, 40, ["±0.48 V", "Zout 1.2 Ω", "DC coupled"], num=3)
edge([(1050, 125), (1170, 125)])
note(1040, 180, ["±0.48 V", "10 Ω source, bridge high-Z", "< 3 mm, DC"], num=4)
edge([(1370, 125), (1500, 125)])
note(1378, 40, ["±0.22 V (gain 0.46)", "hold node, no stub", "DC"], num=5)
edge([(1710, 125), (1840, 125)])
note(1716, 180, ["±0.5 V", "49.9 Ω series", "DC, settled < 30 ns"], num=6)

# ---------------------------------------------------------------- phase path
edge([(860, 125), (860, 300)])
edge([(860, 350), (860, 440)])
note(872, 366, ["±0.24 V at the limiter", "50 Ω leg into 50 Ω", "≤ 20 mm, AC 100 nF (16 kHz)"], num=7)
edge([(960, 485), (1080, 485)])
note(930, 545, ["about ±2.5 V, saturated", "50 Ω, AC 100 nF"], num=8)
edge([(1200, 485), (1310, 485)])
note(1150, 380, ["±0.5 V, edge about 150 ps", "50 Ω, AC coupled", "pad to first tap ≤ 10 mm"], num=9)
edge([(1650, 485), (1790, 485)])
note(1660, 400, ["line end", "50 Ω, DC to ground"], num=10)
edge([(1480, 545), (1480, 640)])
note(1492, 566, ["16 taps, stub < 1 mm", "about 0.3 pF per tap"], num=11)
edge([(1480, 730), (1480, 830)])
note(1492, 748, ["±60 to ±115 mV at readout (5 ns)", "source 10 kΩ ∥ 1 pF, DC, < 5 mm"], num=12)
edge([(1480, 900), (1480, 960), (1300, 960), (1300, 1000)])
note(1492, 915, ["16 × 3.3 V CMOS", "22 Ω series, read 5–8 ns after the strobe"], num=13)

# ---------------------------------------------------------------- strobe
edge([(1360, 1060), (1885, 1060), (1885, 905)], color=STB)
note(1500, 1003, ["LVCMOS33 complementary pair, 3.3 V, about 1 ns edge", "100 Ω / 68 Ω pad into 50 Ω, AC 100 nF", "P to N skew < 10 ps"], color=STB, num=14)
edge([(1885, 835), (1885, 730)], color=STB)
note(1722, 752, ["about ±1 V after a 6 dB pad", "50 Ω, AC 100 nF, P and N matched"], color=STB, num=15)
edge([(1760, 685), (1650, 685)], color=STB)
note(1668, 596, ["+3 V and −3 V pulses, 160 ps", "two 50 Ω lines, AC 100 nF"], color=STB, num=16)
edge([(1310, 685), (1170, 685)], color=STB)
note(1020, 740, ["strobe pair runs against the signal", "35 ps (5.8 mm) per section", "terminated 50 Ω each"], color=STB, num=17)
edge([(2010, 870), (2028, 870), (2028, 340), (2010, 340)], color=STB)
note(1800, 250, ["same level as 15, 50 Ω, AC", "length matched to the TDC finals"], color=STB, num=18)
edge([(1760, 340), (1270, 340), (1270, 175)], color=STB)
note(1290, 250, ["±1.5 V pulse, 160 ps, at the bridge", "choke to bridge < 5 mm", "AC 1 nF per rail"], color=STB, num=19)

# ---------------------------------------------------------------- slow trigger
edge([(860, 270), (680, 270)])
dot(860, 270)
edge([(570, 270), (235, 270), (235, 440)])
note(250, 300, ["±0.48 V", "100 Ω isolation, 4 inputs ≈ 4 pF", "DC, threshold from the trigger-level DAC"], num=20)
edge([(235, 520), (235, 1040), (930, 1040)])
note(250, 700, ["4 × 3.3 V CMOS, each to 4 FPGA pins", "22–33 Ω series, 20 pF per group", "one trace across 4 pads, < 3 mm"], num=21)

# ---------------------------------------------------------------- clocks and control
edge([(720, 1170), (720, 1090), (930, 1090)], color=CTL)
note(520, 1105, ["50 MHz, 3.3 V CMOS", "33 Ω series, DC"], color=CTL, num=22)
edge([(1145, 1120), (1145, 1180)], color=CTL, both=True)
note(1158, 1132, ["SPI, 3.3 V"], color=CTL, num=23)
edge([(1250, 1210), (1420, 1210)], color=CTL)
edge([(1360, 1100), (2065, 1100), (2065, 125), (2010, 125)], color=CTL)
note(1600, 1110, ["ADC convert clock, 3.3 V CMOS", "strobe rate ≤ 10 MHz", "20–30 ns after the strobe"], color=CTL, num=24)

# ---------------------------------------------------------------- legend
out.append(f'<text x="30" y="1180" font-size="13" font-weight="700" fill="{INK}">Reading the labels</text>')
for i, s in enumerate(["first line: signal level at the receiving end", "then: source and load impedance, length or delay target, coupling",
                       "black: signal   red: strobe   grey: clock and control",
                       "Levels 8, 9, 14–19 are targets; the strobe chain is not simulated or built."]):
    out.append(f'<text x="30" y="{1200 + 16 * i}" font-size="11.5" fill="{SUB}">{esc(s)}</text>')

defs = "".join(
    f'<marker id="ah-{c[1:]}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>'
    f'<marker id="as-{c[1:]}" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M10,0 L0,5 L10,10 z" fill="{c}"/></marker>'
    for c in (LINE, STB, CTL))
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="Helvetica, Arial, sans-serif">'
       f'<defs>{defs}</defs><rect width="{W}" height="{H}" fill="#ffffff"/>'
       f'<text x="30" y="26" font-size="17" font-weight="700" fill="{INK}">Sampling scope front end with delay-line phase recovery</text>'
       + "".join(out) + "</svg>")
open("block-diagram.svg", "w").write(svg)
