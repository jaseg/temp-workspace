# 16-tap phase array, co-propagating strobes (SPEC decision 4): verification result
Scripts: `deck.py` (full deck: 2 strobe chains TRF37D73+10 dB+GVA-84+ "nominal" from `strobe/chain.py`, replayed as
50 R sources with both edges of the 50 % square wave; shorted stub at the launch; PSTRB_A/K = 16 x (73 R / 24 ps trace
+ gate) + 50 R; signal = TLV3801 -> TRF37D73 -> 12 dB pad (`phase/line_drive.chain`), 16 x 70 ps (loaded design),
50 R; 16 BAT15-04W gates, 2 x 0.47 pF, 2.2 k to -/+2.5 V, 2 x 1 k, Cin), `run.py` (all runs, `results.json`, plots),
`extra.py` (80 ps stub, clean line edge, `extra.json`), `bridge_rev.py` (sampler bridge, `bridge_rev.json`).
Plots: `strobe_spacing.png`, `capture.png`, `reverse.png`. Behavioural amplifiers as in `strobe/RESULT.md`. Captured value = comparator input 3 ns after the strobe; line -0.25 -> +0.25 V (0.50 V step from the model).
## (1) Strobe along the loaded lines (A / K, peak at gate node, FWHM)
| launch | tap 0 | tap 8 | tap 15 | half swing, taps 0 / mid / 13-15 (3 pF) |
|---|---|---|---|---|
| 50 ps stub (strobe/RESULT) | +3.29 / -3.33 V, 185 ps | +2.75 / -2.61 V, 188-204 ps | +2.23 / -2.16 V, 234-238 ps | 38 / 27-30 / 23-18 mV |
| **80 ps stub** | +4.14 V, 221 ps | +3.47 V, 248 ps | +2.87 / -2.75 V, 286-319 ps | 38 / 24 / 24-28 mV |
| 50 ps stub, launch x1.3 (no part does this) | - | - | - | 38 / 26-27 / 26-29 mV |
Reference (one gate as `phase/gate50.py`, 2.0 V unloaded, 170 ps): node peak 2.00 V, half swing 25.3 mV (3 pF),
17.1 mV (6 pF); 1.5 V: 3.5 mV. Attenuation 3.3 -> 2.2 V (-33 %) and widening 185 -> 237 ps over 15 taps come from
the charge the conducting gates take (without diodes: 3.5 -> 1.7 V by dispersion of the lightly loaded line).
**Every gate gets >= 2.0 V with the 50 ps stub (tap 15: 2.16 V, 8 % margin), but taps 13-15 capture only 70-90 % of
the reference.** Fix without a new part: **80 ps stub** (13 mm) -> >= 2.75 V everywhere, all taps >= 24 mV.
Needed launch: about 4 V peak / >= 2.5 V at tap 15 (the 7.2 V GVA step through an 80 ps stub gives it).
## (2) Tap spacing and resolution
Strobe peak arrival 0, 42, 78, ... 478, 512 ps (34.2 ps/tap; last 31-34 ps as the pulse shrinks; no diodes 25 ps/tap).
Signal line (strobes idle) 75.7 ps/tap (design 70). Effective tap position = half-way crossing of each tap curve:
| case | spacing mean +/- sd (min-max) | 10-90 width | single-shot rms (offsets nominal / 6.5 mV) |
|---|---|---|---|
| 50 ps stub, Cin 3 pF | 36.9 +/- 6.9 ps (23-53; taps 0-11: 32-40) | 340 ps | 19 / 22 ps |
| 50 ps stub, Cin 6 pF | 36.5 +/- 6.9 ps | 366 ps | 23 / 27 ps |
| **80 ps stub, Cin 3 pF** | **34.7 +/- 3.1 ps (31-44)**, window 58-579 ps | ~340 ps | **19 / 22 ps** |
| counter-prop., 30 ps signal + 30 ps strobe | 69.8 +/- 7.4 ps (59-83) | 70-255 ps | 51 / 64 ps |
Estimator = `sim/snapshot_tdc.py` (code density, last-0/first-1 midpoint) re-implemented with the simulated tap
positions, per-tap half swing and width (`run.tdc`); offsets 3.7 mV nominal, noise 1.9 mV. Capture curves:
`capture.png`. Plateaus (3 pF): edge passed +45..+55 mV, edge not yet arrived -8..-21 mV (feed-through) -> mid
point +17 mV for all taps (6 pF: +10 mV), as VTAP_TH in `phase/RESULT.md`. **Co-propagation works**;
counter-propagation is worse (taps far from the strobe launch get 5-15 mV).
## (3) Wrong-polarity pulse (falling FPGA edge, +10 ns at 50 MHz / 50 %)
| | tap-diode peak reverse (tap 0 / 8 / 15) | comparator input change, any time 8-17 ns after strobe |
|---|---|---|
| no reverse edge | 1.8-2.0 / 1.3-1.6 / 1.0-1.2 V | - |
| 50 % duty | **2.95 / 2.74 / 2.46 V** (BV 4 V: 74 %) | <= 0.46 mV (<= 0.17 mV at +12 ns) |
| 50 % + BAT15 shunt clamp at each launch | 2.0 / 1.9 / 1.75 V | <= 0.7 mV; wanted pulse unchanged (3.34 / 2.80 / 2.27 V) |
| 70 % duty (reverse at +14 ns) | 2.95 / 2.74 / 2.46 V | 0.0 mV at +12 ns |
**Timing**: the reverse pulse moves the comparator inputs by < 0.5 mV (A and K couple in opposition and cancel at the
2 x 1 k sum) against 15-20 mV overdrive; and any effect would reach the COS3502 output only after its 4.5-7 ns
delay (>= +14.5 ns), after the +12 ns latch. No conflict; **keep 50 % duty and latch at +12 ns**. Free extra margin:
FPGA pattern 70 % high (reverse at +14 ns) – same captures. Clamp not needed on PSTRB_A/K (keep a DNP footprint).
**Sampler bridge** (`bridge_rev.py`, deck D, 10 R, 80 ps stub, +/-1 V bias, -4.6 V / 150 ps step): peak reverse
**3.27 V** on one BAT15 (82 % of BV; +0.2 V more at +/-1.2 V bias). BAT15 shunt clamp (cathode to the stub node, anode
GND) -> 1.90 V; wanted pulse unaffected (drive 0.83 V, held change 9.8 vs 10.0 mV). **Fit the clamp on STRB.**
The reverse pulse also shifts the sampler hold by -13 mV (-17 mV with clamp): the ADC must sample the hold before the
S_STROBE falling edge (160 ns after the strobe) - to the sampler sheet.
## (4) Signal line with 16 loaded taps
Return loss at the line input (small-signal, idle bias): 32 / 28 / 24 / 31 / 14 / 6 dB at 0.5 / 1 / 2 / 3 / 4 / 6 GHz.
Edge 10-90 / 20-80: tap 0 229 / 152 ps, tap 8 253 / 163 ps, **tap 15 321 / 183 ps**, step 0.50 V kept, overshoot
<= 2.3 %. The strobe kick onto the signal line is in all transients (included in the captures).
## Changes vs SPEC / earlier RESULTs
Phase-strobe stub **80 ps** (not 40-50). Signal line measures 75.7 ps/tap with the 70 ps design: aim the meander ~5 ps
shorter (calibration absorbs the rest). No clamp on PSTRB; BAT15 clamp on STRB. Duty 50 % OK (70 % optional).
`results.json` "signal_edge" is contaminated by the strobe kick; use `extra.json` "signal_edge_clean".
## Open points
Behavioural amplifier edges (pessimistic GVA gives 2.0-2.3 V at launch: then tap 15 falls below 2 V even with 80 ps
stub - measure early); gate load modelled as BAT15 + package only; COS3502 Cin/delay; first strobe section 42 ps (launch geometry); end-tap irregularity (taps 12-15) is from the pulse widening, calibrated by code density.
