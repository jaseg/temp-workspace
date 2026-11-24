# input_stage layout fragment (15.30 x 17.60 mm, origin top-left), JLC04161H-7628, no 50R termination
`gen_input_stage.py` (pcbnew 7.0.11) writes `input_stage.kicad_pcb` and prints the tables and checks.
Renders (kicad-cli 7 `pcb export svg` -> playwright PNG): `input_stage.png` (F.Cu + silk + fab, plus In1, In2 and B.Cu)
and `input_stage_detail.png` (SMA -> divider -> BUF802 -> splitter). **kicad-cli 7 has no DRC.** The script checks
copper clearance < 0.1 mm, corners > 45 deg, courtyard overlaps and unrouted nets after zone fill. All four are 0
(37 vias, no stitching). Accepted courtyard pairs: C101/R114, R117/U102, C105/U102, R121/TP103 (pad-to-pad bridges),
J3/TP101 (header courtyard only).

## Stack-up (in the board setup, unchanged)
JLC04161H-7628, 1.6 mm: L1 35 um | 7628 0.2104 mm, er 4.4 | L2 (In1) solid GND | core 1.065 mm | L3 (In2) +5V/-5V,
GND island at the SMA | 7628 0.2104 mm | L4 GND pour plus slow traces. Mask er 3.8, 15/30 um.
50R masked microstrip from `line_z()`: **w 0.36 mm**, 50.0 R, eps_eff 3.29, 6.05 ps/mm. Pour gap 0.75 mm (2.1 w),
CPWG check 47.9 R. SMA pin pad 1.27 mm over the In1 cut (L3 reference, pour gap 0.25): 51.3 R.

## What changed (user decision: switchable 50R termination removed)
- Removed: K101 (HFD3), R101/R102 (2 x 100R), R103 (coil 39R), nets TERM_50, VBUS, COIL_P, K_COM1/2, the 0603 tap
  cut-outs and the VBUS/TERM_50 header pins. The input is now the bare 1 Mohm divider.
- Ctop (C101) sits right after the launch taper: SMA pad -> 0.8 mm zone taper (1.27 -> 0.36) -> 0.07 mm gap -> Ctop
  pad 1. The 0.36 mm 50R segment between taper and pad centre is 0.42 mm. In1 is still cut under the SMA pad.
- The first alpha resistor R114 (300k) taps VIN by bridging its pad onto Ctop pad 1 (no extra line, no tap length).
- Divider (C101, C102, R104), bias string (R105/R106) and U101 keep their previous relative geometry, so the
  BUF802 moved 9.6 mm left. Clamp dividers, decoupling, splitter and J3 moved with it.
- Servo pulled in: U102 under the alpha column, Raux R121 right above OPA OUT, Cint C106 beside it, FB line at the
  bottom with Rofs/Rf2 pads on it, RV101 rotated into the bottom-right corner.
- Header J2 is now 4 pins (-5V, +5V, GND, VOFS), bottom left. The 10u bulk caps are on B.Cu, straight into the pins.
- BUF_OUT_T (49.9R + 0R leg) now leaves at the **right** edge (IF2, y = 10.09), 2.15 mm of 0.36 mm microstrip.
- In2: GND island under the SMA, -5V band under U101/U102 with a tongue to J2 pin 1, +5V elsewhere (top band, right
  corridor, bottom band). F.Cu local polygons and via pairs at the U101 caps as before; no thin IC power tracks.
- Two functional GND vias beside the SMA ground legs tie F/B legs, In1 and the In2 island (the island needs them).

## Lengths and delays (script table)
| element | mm | ps |
|---|---|---|
| **SMA pad end -> Ctop pad 1 edge (1 Mohm stub)** | **0.89** | **5.4** (10.8 round trip) |
| SMA pad end -> Ctop pad 1 centre | 1.17 | 7.1 |
| Rg pad 2 -> U101 pin 2 (BUF_IN, 0.15 mm, over the cut-out) | 1.66 | 10.1 |
| BUF_OUT_S: OUT pin -> edge pad IF1 (sampler 10R, <= 3 mm) | 2.89 | 17.5 |
| BUF_OUT_S: OUT pin -> R112 tap | 1.40 | 8.5 |
| BUF_OUT_T: 0R pad -> right edge | 2.15 | 13.0 |

Old: SMA -> termination 9.70 mm (59 ps), plus 1.03 mm to Ctop. Outline old 24.85 x 19.2 mm, now 15.30 x 17.60 (-44 %).
Excess pad C: Ctop pad 1 0.046 pF, R114 pad 0.048 pF, R112 + R118 0.13 pF, R113 0.03 pF.

## Remaining deviations
- The SMA centre pad (solder land, 3.6 mm) is not counted in the stub; it is the connector's own launch.
- Neck: U101 OUT pad is 0.25 mm wide; the 0.36 mm line starts at the pad centre (0.41 mm neck).
- BUF_OUT_S edge pad 2.89 mm from the OUT pin: the sampler 10R must sit right at the edge.
- CPWG estimate at the 0.75 mm gap is 47.9 R (within JLC +-10 %); widen to 1 mm if needed.
- U101 EP has 4 GND vias in the pad (QFN): kept as 0.2 mm vias tented on B (no plugging; board README 'Vias out of pads'). Two-sided assembly (C112, C113, C115, C116 on B.Cu).
- The BUF_IN trace (1.66 mm) kept the old pin 3 / pin 4 fan-out room; it lies over the all-layer cut-out.

## Interfaces / open
- IF1 BUF_OUT_S: right edge, y = 6.30 (S>). IF2 BUF_OUT_T: right edge, y = 10.09 (T>). Continue both as 0.36 mm over GND.
- J3 (top: GND, -2V5, +2V5), J2 (bottom: -5V, +5V, GND, VOFS).
- Via stitching is added when the fragments are assembled. Run full DRC in the KiCad GUI.
