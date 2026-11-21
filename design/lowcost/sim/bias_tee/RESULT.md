# Bias tees (TRF37D73 x5, GVA-84+ x2): verification and correction
Scripts: `models.py` (part + layout models), `tees.py` (present / corrected tees with layout parasitics), `ac.py` (|Z|, S21/S11,
stub-loaded stage, 100 kHz-8 GHz), `tran.py` (strobe chains with `sim/strobe/chain.py` stages, line driver with
`sim/phase/line_drive.py`), `sens.py`. Plots: `plot_branch.png` (|Z|, S21), `plot_strobe.png`, `plot_line.png`. Data: `ac.json`, `tran.json`.
## Requirements (per tee)
| Tee | load / waveform | band the choke must cover | DC |
|---|---|---|---|
| TRF #1 sampler, TRF phase x2 (stage 1) | 50 R pad, saturated square +/-2.3 V, 3.125 / 50 MHz | 3 MHz (tau >= ~1 us: stage 2 stays saturated) to ~5 GHz | 53 mA typ, 65 max; pin >= 3.0 V |
| TRF line driver | 12 dB pad + line, 1 kHz edges .. 3 Gbps | tau ~2 us (47 uH, design choice) to 5 GHz, no ripple (DDJ) | as above |
| TRF #2 sampler, GVA-84+ x2 (final) | 100 nF + 80 ps **shorted stub** | stub shorts < ~300 MHz: only 0.3-5 GHz matters | GVA 108 typ / 130 max mA, Vd >= 4.8 V |
Shunt branch on a 50 R line: |S21| > -0.3 dB needs |Z| > 700 R if resistive, > 93 R if reactive. Square-wave check: step at the edge,
droop over the half period, ringing. Resistive feed: TRF 3.3 V/55 mA leaves < 0.3 V -> R < 5 R (shunts the line, -16 dB); from 5 V:
31 R (-5 dB). 150-220 R would need 12-29 V and 0.45-2.6 W (TRF..GVA) and still cost 1.3-0.9 dB. Rejected; R only as damping.
## Models
- **Vendor data**: BLM15HD102SN1 and LQW15ANR12J00 Murata S2P (0 mA), fitted to Foster ladders (bead: 3 sections, max error 6.9 %,
  1 MHz-3 GHz; above 3 GHz extrapolated, ~65 fF). LQW15ANR12 fitted 50 MHz-1.75 GHz (110 nH, SRF 1.6 GHz).
  S2P files: murata.com S-parameter libraries (blm15-s, lqw15an-00-s), not redistributed; set BIASTEE_DATA to their folder.
- **Datasheet-built** (L || Cpar || Rp + DCR): LQH32CN470K23L 47 uH, 170 mA, DCR 1.3 (1.69 max), SRF >= 15 MHz (18 used, 15/22 in
  `sens.py`); LQH2MCN470K02L 47 uH **0806**, 120 mA, DCR 5.1 (6.63 max), SRF >= 18 MHz; LQM21PN2R2MGHL 2.2 uH, Isat 450 mA, DCR 0.125, SRF 40 MHz.
  Rp (15 k / 1.5 k) assumed from typical Q. Bead DC-bias derating assumed (x0.85 at 55 mA, x0.65 at 108-130 mA): not vendor data.
- **Layout** (JLC04161H-7628, microstrip formula of the generators): 0402 pad over In1 0.104 pF, on the line +32 fF; 1210 pad 0.70 pF;
  via to In1 0.09 nH, to In2 (+3V3) 0.99 nH; 0.3 mm track 0.33 nH/mm. IPC-2221: 0.3 mm / 35 um carries ~1 A at 10 K, 1.6 mR/mm.
## Verdicts (present design)
| Tee | present | worst S21 1 MHz-3 GHz / 3-6 GHz | time domain | verdict |
|---|---|---|---|---|
| **Line driver** (trigger sheet / phase_trigger) | 120 nH 0402 + 47 uH "1008" | **-11.4 dB at 313 MHz** / -0.2 | PRBS7 3 Gbps DDJ **16.6 ps rms / 76 pp** (corrected 1.2 / 5.3), eye nearly closed | **wrong, badly** |
| same, DC | LQH2MCN470K02 is 0806 on a 1008 land, DCR 5.1-6.6 R | - | 0.29-0.45 V drop -> TRF pin 2.85-3.0 V (< 3.0 V min) | wrong |
| TRF stage 1 (strobe sheet: sampler #1, phase x2) | BLM15HD102 + 47 uH 1210 | -0.50 dB at 73 MHz (bead L vs 47 uH self-C) / -0.55 | 3.125 MHz square: 132 mV pp ringing (corrected 20); step equal | marginal: fixed |
| TRF #2 sampler (fragment) | same + layout | -0.50 / **-0.55 dB at 5.6 GHz** (off-axis pad + stub + link) | into the stub: 2.52 V / 213 ps, same as ideal | parts OK, layout fixed |
| GVA-84+ x2 | BLM15HD102 + 2.2 uH LQM21PN | through line -3.4 dB at 1 MHz, but stub-loaded stage -0.21 dB (worst, 4.8 GHz) | launch 3.59 V (ideal 3.62) | **OK as is**: 2.2 uH suffices behind the stub |
"25 % loss with 2.2 uH" (strobe RESULT) applies to stage-1 chokes into 50 R; the final stages drive a shorted stub, so their LF choke
value is irrelevant. Narrow tracks: electrically harmless in series with a choke (0.3 nH vs > 300 R) and trivial for DC; what mattered
was the 0.3 mm stub to an off-axis bead pad. Vias at the inductor with caps beside it: works (cold node is quiet) but lets the choke
ripple into the +3V3 plane first; changed so the supply enters through the cold-end capacitor.
## Corrected circuit (applied in kicad/gen and both fragments)
**Every TRF37D73 (5x)**: RF pin -> **BLM15HD102SN1D** (LCSC C21516, 0.0197 USD, pad ON the line) -> **LQH32CN470K23L** 47 uH 1210
(C701189, 0.1632 USD @5) **|| 1 k 0402** (C11702, ~0.001) -> **own 100 nF 0402** (C1525) at the cold pad -> +3V3.
S21 worst -0.28 dB (53 MHz), -0.30 derated, -0.33 at SRF 15 MHz; 3-5.5 GHz -0.13 dB; S11 < -20.7 dB; 3.125 MHz square step 4.46 V
(ideal 47 uH 4.56: the 1 k costs 2.2 %), ringing 20 mV pp; line driver DDJ 1.2 ps rms, 1 MHz droop as ideal (0.284 -> 0.223 V).
DC drop 55 mA x 2.94 R max = 0.16 V (0.19 V at 65 mA): TRF pin >= 3.11 V at 3.30 V.
**GVA-84+ (2x)**: unchanged parts (BLM15HD102SN1D + LQM21PN2R2MGHL C341781 0.3667), cold end = VBUS 1 nF/100 nF/10 uF; drop 0.15-0.18 V.
## Placement rules (all tees; strobe chains without fragment included)
1. First element (bead) with its pad centred on the 50 R trace, body perpendicular; no stub. No In1 cut-out (+32 fF = -32 dB at 5 GHz).
2. Straight chain, courtyards touching: bead -> 1210/0805 inductor with a pad-wide (0.64 mm) link; 1 k 0402 beside the 1210, 45-degree links.
3. Cold-end 100 nF directly across the inductor's cold pad, GND via at its GND pad; +3V3 (VBUS) plane via pair on the far side of the
   capacitor, bulk next to the vias. No 90-degree corners; TRF VCC pin keeps its own 1 nF + 100 nF.
4. Phase chains: both polarities mirror images; tee on the side away from the launch stub.
## BOM delta (for gen_bom.py PRICE / CLASS)
Removed: L301 120n 0402 (est 0.02), L302 47u L_1008 (est 0.10). Added: FB301 BLM15HD102SN1D (key ("1k","L_0402_1005Metric"), 0.0197),
L302 LQH32CN470K23L (key ("47u","L_1210_3225Metric"), 0.1632), R382 + R415-R418 1k 0402 (5x R_0402 class), C432-C435 100n 0402 (4x C_0402_X7R).
Net +0.08 USD per board. Strobe refs added explicitly (no renumbering): R415-R418, C432-C435; trigger: FB301, R382 (L301 gone).
## Residual risks
- Bead under DC bias (GVA 43-52 % of 250 mA) only assumed; DC-bias S2P or a VNA check on the first board.
- Above ~6 GHz a cold-node resonance (47 uH self-C, 1210 pads, cap ESL) shows through the bead's 65 fF: -0.4 dB at 6.5 GHz (SRF 18 MHz),
  -1.3 dB at SRF 15 MHz; the bead model is extrapolated there. Fix if measured: 47 R + 22 pF 0402 from the cold pad to GND (-0.16 dB).
- LQH32CN SRF/self-C only from the min-SRF spec; real core loss above SRF makes all resonances milder than modelled.
- GVA Vd follows VBUS (USB 4.75 V -> Vd ~4.6 V < 4.8 V min): supply question, not the tee.
