# BOM review 2: input trimmer, C101, capacitors below 1 nF, tap capacitors (24 Nov 2026)

Scope: the user's review items "What's the trimmer for?", "What's going on with C101, why 100 V", "a lot of capacitor
values below 1 nF ... defragmented" and "Do we really need 0.5 pF caps or can we DNP them".
Simulations: `sim/bom2_input/RESULT.md` and `sim/bom2_taps/RESULT.md` (the original sim scripts are copied or
imported, never edited). This file only proposes; schematic, layout and BOM are unchanged.

## Decisions
| # | Item | Decision | Main number |
|---|---|---|---|
| 1 | RV101 50k trimmer | **Remove.** Fixed 1 % network plus a firmware LF/HF correction, calibrated once with any square wave | residual flatness 0.34-0.78 % (trimmed today: 0.67 %) |
| 2 | Servo network | R118 10k -> **4.7k**, R119 24.9k -> **10k**, R123 33k -> **15k**, R120 **22k** (no RV101), C106 470p -> **1n C0G** | all resistors JLC basic; same dynamics |
| 3 | C101 1.5 pF 100 V | **1.5 pF +/-0.05 pF 50 V** Murata GJM1555C1H1R5WB01D (C76901), same footprint | Ctop sees <= 47.7 V at the +/-50 V claim |
| 4 | C207 220p C0G | **100p C0G** (C1546, basic, the C107 line) | ADC settling unchanged (0.21 LSB) |
| 5 | C631 120p (DNP) | **100p** (C1546) | value only, not fitted |
| 6 | C205 2.2 pF hold | **keep** | 3.3 pF costs 26 ps aperture (126 vs 100 ps) |
| 7 | C314-C345 0.5 pF | **Not DNP** (no capture). Replace by **printed L1/L2 capacitors**, 0402 footprints kept DNP | 17-18 ps rms at the +/-15 % corners |
| 8 | Phase array as built | Re-simulated (the open item of SPEC decision 4) | 33.7 +/- 5.1 ps spacing, 16.8 ps rms |

## A. What RV101 trims, and why it is mechanical
The input has two paths:
- **HF path**: Ctop C101 1.5p / Cbot C102 3.3p into the BUF802 (k = 1.53 / (1.53 + 3.3 + 2.4 Cin + 0.3) = 0.206,
  times G 0.971 = 0.200).
- **LF path**: the 900k / 100k alpha divider into the OPA197 integrator servo, which drives In_Aux. LF gain =
  0.1 x Rf1 x (1/Rf1 + 1/Rf2 + 1/Rofs + 1/Rmid). RV101 sits in Rf2 and sets the LF gain equal to the HF gain.
  The crossover is the servo loop (Ga / (2 pi Rf1 Cint) = 8.8 kHz, median tau 18.6 us).

A mismatch eps = G_LF / G_HF - 1 is a pole-zero doublet. A step jumps to the HF level and moves to the LF level over
2-150 us, with an undershoot of about 0.17 |eps| near 70 us. Error budget without the trimmer: Ctop +/-0.1 pF (part
fitted today) +/-5.3 %, BUF802 Cin +/-0.3 pF (typical only, assumed) +/-4.0 %, Cbot +/-0.1 pF +/-1.3 %, pads +/-0.4 %,
G +/-1 %, alpha string (1 % parts) +/-1.8 %, servo resistors +/-1 %; worst case +/-15 %. Monte Carlo over 60 boards: -6.5 ... +9.1 % (sd 3.8 %); with Ctop +/-0.05 pF: -7.1 ... +6.0 %.
**Tighter parts cannot remove the Cin term.** A divider insensitive to Cin needs about twice the Ctop, which halves
the unterminated bandwidth. So option 3 is rejected: one per-board calibration remains.

Why a mechanical part, then? It was the simplest analog way to change a gain: none of the seven DAC channels can
change a gain. VOFS only adds an offset. The analog alternatives fail on this bipolar, high-impedance loop:
**PWM shunt** on an open-drain pin at FB / TAP (they swing +/-0.5 V in range, about -0.75 V in overload; the pin clamp
conducts below -0.3 V, so the gain would depend on input polarity); **NMOS switch** (same body diode, about 15 pC gate
charge per edge = 30 mV steps at the servo output); **JFET / diode** (no JFET available, diode nonlinear over
+/-0.5 V); **G474 OPAMP / PGA** (single supply against a bipolar node, offset and drift x10 at the input).
**Software correction** needs no part: the sampler ADC stream is real time at 3.0 MS/s in 8-10 ms bursts (> 400 tau).

**Recommended scheme (simulated in sim/bom2_input).**

RV101 removed; R120 22k; R118 Rf1 4.7k (C25900); R119 Rofs 10k (C25744); R123 Rmid 15k (C25756); C106 Cint 1n C0G
(C53547). Rf1 x Cint stays 4.7 us, Rpar x Cint = 2.35 us = tap RC, so Cp 18p stays. Results: LF / HF gain
0.19970 / 0.19971; VOFS 0.2 / 1.289 / 2.7 V -> OUT +0.512 / 0.000 / -0.663 V (+/-2.5 V at the input covered,
1.7 mV/LSB at the input; DAC load 10k to the virtual ground, minimum 5k); HF unchanged (3.29 / 1.71 GHz with / without
terminator, 130 ps rise); overload recovery 48 us. RV101 and 24.9k (both extended) go; 470p is swapped for 1n C0G, the
C303 line. If C303 becomes X7R (user remark on C0G at 1 nF), C53547 stays for Cint only. Cint must stay C0G: X7R
would make tau voltage- and temperature-dependent.

**Firmware procedure. No MCU pin is added.**
1. **Calibration** (once in production, like RV101 was; repeat after repair):
   - Apply any 0.2-2 kHz square wave with flat tops to SIG_IN, without a terminator. The amplitude does not matter
     because eps is a ratio. A function generator works, or PA9 (J501 pin 4) toggled as a GPIO via a clip lead.
   - Average 64 edges from the real-time ADC stream (0-520 us after each edge).
   - Fit y = a [1 + e1 (1 - e^(-t/t1)) + e2 (1 - e^(-t/t2))] and store e1, t1, e2 and t2 in flash.
   - Optionally re-check t1 / t2 at every start with a VOFS step, which exercises the same servo loop without any input.
2. **Correction**: C(s) = (1 + e1 + e2) / (1 + e1/(1 + s t1) + e2/(1 + s t2)). It is unity at DC, so the result
   carries the resistor-ratio LF gain.
   - Real-time stream or records longer than about 5 us: apply C as an IIR at 3 MS/s.
   - Short ET records of periodic signals: x = m + (1 + eps)(y - m), where m is the mean over all phases (a record
     covering one period, or a per-phase-bin accumulator over all strobe samples).
   - TRIG_LEVEL: apply the same scaling around m.
3. **Simulated on 4 boards** (eps -7.1 / -6.8 / -2.9 / +0.1 %):
   - Flatness 1 Hz-100 MHz: 7.7 / 7.5 / 3.5 / 0.6 % raw, **0.34 / 0.49 / 0.73 / 0.78 %** corrected.
   - Step 1-500 us: 7.1 % raw, **0.19-0.36 %** corrected.

## B. C101 "100 V" and the capacitors below 1 nF
**Why 100 V.** sim/input claimed a maximum input of +/-50 V peak (DC + AC, 1 Mohm mode). The cap was chosen for
margin, not by a circuit need:
At DC, Ctop holds the input minus GA, and GA is clamped by the BUF802 diodes at +2.3 / -5.2 V: C101 sees at most
47.7 V at +50 V (44.8 V at -50 V). Other limits: the 0402 string R114-R116 (50 V each; 15 V per resistor at 50 V since
TAP stops near the OPA197 rail), the BUF802 clamp current (1.5 pF x 50 V/ns = 75 mA), the SMA (not limiting).
**A 50 V C0G is sufficient: state the range as +/-50 V peak, below 50 V/ns.** The fitted 100 V part is also a supply
risk (45 left at LCSC). Murata 50 V +/-0.05 pF (C76901, 17.5k stock, 0.035 USD) restores the +/-0.05 pF the design
asked for, same footprint. Two 3.3 pF in series (C102 line, 100 V together) would save the line but peak +0.55 dB at
2 GHz with the terminator (17.6 % overshoot vs 12.7 %) and need a new footprint: rejected.

**JLC basic 0402 C0G values** (checked one by one, jlcpcb.com parts API and lcsc.com product detail, 24 Nov 2026):
10p C32949, 12p C1547, 15p C1548, 18p C1549, 20p C1554, 22p C1555, 33p C1562, 47p C1567, 100p C1546. There is **no
basic C0G below 10 pF or above 100 pF**: C1544 0.5p, C1550-C1575 1-6 pF, 120p, 220p, 470p and 1n C0G are all
extended. Basic X7R: 220p C1530, 1n C1523, 4.7n C1538. Series combinations of basic parts cannot reach the HF values
(seven 10 pF in series for 1.5 pF). The HF values therefore stay extended, and the defragmentation removes the
values above 10 pF.

| Ref | Value now | Function | New | Class | Check |
|---|---|---|---|---|---|
| C314-C345 | 0.5p x 32 | strobe-to-hold-node coupling of the 16 tap gates | printed L1/L2 0.5 pF (section C) | none | sim/bom2_taps |
| C101 | 1.5p 100 V | Ctop, HF divider | 1.5p 50 V +/-0.05 pF C76901 | ext | sim/bom2_input |
| C205 | 2.2p | sampler hold | 2.2p (keep) | ext | hold_cap.json |
| C102 | 3.3p | Cbot, HF divider | 3.3p (keep) | ext | - |
| C105 | 18p | tap RC at TAP | 18p | basic | unchanged dynamics |
| C201, C202 | 47p | strobe rail coupling | 47p | basic | - |
| C107 | 100p | Caux at In_Aux | 100p | basic | - |
| C631 | 120p DNP | U602 feed-forward | 100p DNP | basic | not fitted |
| C207 | 220p | ADC pin reservoir | 100p | basic | chain_100p.json |
| C106 | 470p | servo Cint | 1n C0G (with section A resistors) | ext (C303 line) | sim/bom2_input |

Result: sub-1 nF lines go from 7 extended (6 fitted) to 3 extended (1.5p, 2.2p, 3.3p), plus 1n C0G on the C303 line.

## C. Tap capacitors C314-C345: DNP?
**No.** Each capacitor sits in series from PSTRB_A/K to the hold node and is the only path for the strobe into the
gate. With the part not fitted, the empty 0402 pad pair gives about 0.03 pF. The hold node then peaks at -0.65 V
(bias -0.78 V), and no tap ever captures: -6 mV of pure feed-through, no stamps.

As-built hold-node capacitance to ground, extracted from the board with pcbnew (L2 fill per pad and track):
**about 0.40 pF**. The 1 k node pad lies over solid L2 (0.17 pF) and 0.95 mm of node track runs over L2 (0.10 pF);
the rest is in the cut-out.

Coupling capacitance (cc) survey at c_node 0.40 pF: 0.03 / 0.1 / 0.2 pF fail; 0.3 pF marginal (14 mV minimum swing
at 3 ns); 0.4-0.8 pF flat (35-56 mV). Threshold midpoint 16.7 mV at 3 ns / 13.5 mV at 5 ns, tap-to-tap spread 2.3 mV;
droop to the +12 ns latch about 74 %, but the comparator acts on its input at 5-7.5 ns, where 35 mV remains.
**The fitted FH part (+/-0.25 pF) is a risk**: its 0.25 pF corner gives 0.4-10 mV half swings and 60 ps rms.

**As-built array, re-simulated** (39.4 / 69.4 ps per tap, 62 R sections, 43 R terminations, 80 ps stub, c_node
0.40 pF): strobe 39.3 ps/tap, tap-15 peak 3.36 V; effective spacing 33.7 +/- 5.1 ps (taps 3-11: 29.8-31.7 ps; taps
12-15 irregular), window 506 ps; half swing 23.6-50.6 mV; **single-shot rms 16.8 ps** (19.3 ps with 6.5 mV offsets).

**Recommendation: printed capacitors.** Replace C1544 x 32 with an L1/L2 overlap in each node window. The 0402
footprints stay, DNP, as a fallback.

Layout change per hold node in gen_phase.py (to be confirmed by DRC and a field solve):
- **L1 patch** on the hold-node net: 1.20 x 1.00 mm (x -1.60 ... -0.40 from the diode centre, y 1.25 ... 2.25 from
  the axis). It joins the C pad 2, node track and resistor pads, all the same net, and stays 0.19 mm from C pad 1.
- **L2 island** on PSTRB_A / PSTRB_K: the patch plus 0.15 mm on every side (registration-proof), extended to a
  0.2 / 0.45 mm via beside C pad 1 (not in a pad) that drops from the strobe trace.
- **L2 window** widened so the plane stays 0.25 mm from the island (west edge to about x -2.0).
- **Value**: C = e0 x 4.1 x (1.20 + 0.08)(1.00 + 0.08) / 0.0994 mm = 0.50 pF, with fringe.
- **Tolerance** (assumed: prepreg +/-10 %, er +/-2.5 %, etch +/-0.025 mm per edge): -19 / +23 % (0.40-0.62 pF),
  about +/-3 % tap to tap.

- Simulated corners: 0.43 pF 31.8 +/- 3.9 ps, 18.0 ps rms, half swing >= 23.9 mV; 0.58 pF 31.8 +/- 3.0 ps,
  17.2 ps rms, >= 19.9 mV.
- Strobe load: the island adds about 0.08 pF to L5, against the 0.110 pF strobe pad over L2 it replaces. The strobe
  delay per tap stays 39 ps.
- Saving: the C1544 line (extended), 32 placements and 64 joints, and the +/-0.25 pF risk.
- First board: measure the PSTRB TDR and the code-density plateaus. If the printed value is below about 0.35 pF, fit
  C76912 in parallel.
- **Minimum alternative without a layout change**: C1544 -> **C76912** (Murata GJM1555C1HR50WB01D, +/-0.05 pF,
  121k in stock, 0.026 USD @200). Its 0.45 pF corner gives 17.1 ps rms.
- Enlarging the L2 cut under the 1 k node pad (c_node 0.12 pF) gains nothing at 0.5 pF: not proposed.

## Open points
BUF802 Cin spread (+/-0.3 pF) assumed, not specified; correction firmware (fit, IIR, per-phase mean) does not exist;
c_node and the printed capacitance are hand / pcbnew estimates, not field-solved; JLC publishes no prepreg tolerance;
COS3502 Cin assumed 3 pF; behavioural models throughout, as in the original simulations.
