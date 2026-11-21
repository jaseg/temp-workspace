# input_stage layout fragment (24.85 x 19.2 mm, origin top-left), re-layout for JLC04161H-7628
`gen_input_stage.py` (pcbnew 7.0.11) writes `input_stage.kicad_pcb`. Renders: `input_stage.png` (F.Cu, In1, In2, B.Cu)
and `input_stage_detail.png` (divider, BUF802, splitter). kicad-cli 7 has no DRC. The script checks for courtyard
overlaps, copper clearance < 0.1 mm, corners > 45 deg and unrouted nets after zone fill. All four counts are 0.
The listed courtyard overlaps are intended pad-to-pad bridges.

## Stack-up (in the board setup)
JLC04161H-7628, 1.6 mm: L1 35 um | 7628 prepreg 0.2104 mm, er 4.4 | L2 (In1) solid GND | core 1.065 mm | L3 (In2) +5V/-5V,
GND island at the SMA | 7628 0.2104 mm | L4 GND pour plus slow traces. Mask er 3.8: 15 um over the trace, 30 um over the
substrate. The numbers match the JLCPCB stack-up/impedance page (downloaded earlier in this session).

## Impedance (one function, `line_z()`)
Hammerstad-Jensen with thickness correction, plus a solder-mask correction (empirical fill factor), plus a CPWG ratio check.
| line | w mm | Z0 | eps_eff | ps/mm |
|---|---|---|---|---|
| 50R microstrip, masked (bare 51.0 R) | **0.36** | 50.0 | 3.29 | 6.05 |
| same, F.Cu pour at 0.75 mm (2.1 w), CPWG check | 0.36 | 47.9 | | |
| SMA pin pad 1.27 mm: In1 cut, L3 GND, pour gap 0.25 | 1.27 | 51.3 | | |

RF segments (net, w, Z0, length): VIN 0.36/50 R/9.97 mm (60 ps); BUF_OUT_S 0.36/50 R/2.89 mm; BUF_OUT_T 0.36/50 R/10.16 mm.
Intended vs. actual: SMA to termination 6 mm (36 ps) vs. 9.7 mm (59 ps), set by the relay pin pitch. The line is
terminated, so this is delay only. Termination to Ctop is 0 vs. 1.03 mm. OUT pin to R112 tap is 1.40 mm.
Each termination stub (VIN tap -> 100R -> COM pin) is 2.54 mm.

## What changed
- New stack-up. Every RF width is computed. VIN, BUF_OUT_S and BUF_OUT_T are 0.36 mm over their whole length, with
  F.Cu pour kept 0.75 mm away by rule areas. The SMA launch uses a 0.8 mm zone taper (1.27 -> 0.36). In1 is cut under the pin pad.
- Compact in-line RF chain: SMA - R114 tap - 100R taps (0603, pads touch the line, In1+In2 cut out under them) - Ctop - Rg
  - BUF802 pin 2. The 0402 taps (R114, R112, R118) touch the line edge directly, so each tap has zero length.
- Supplies: In2 planes (+5V / -5V split shaped around the via sites). Local F.Cu polygons join U101 pins 1, 5/6, 8 and 12
  to their 100n caps. Via pairs sit at the caps. Pin 10 has its own via. The OPA197 100n caps are on B.Cu under the pin vias.
- All bends are 45 deg (script-checked). CLH/CLL fan out as mirror images. IN_BIAS and IN_AUX fan out in parallel.
- No stitching grid and no via fences. The 38 vias are functional: pad ground, decoupling, plane and layer-change vias.
- The headers are now J2 (bottom: VBUS, TERM_50, GND, +5V, -5V, VOFS) and J3 (top: GND, -2V5, +2V5).
  R103 is now 0603 (coil 39R).

## Remaining deviations
- Neck: the U101 OUT pad is 0.25 mm wide. The 0.36 mm line starts at the pad centre (0.41 mm neck).
- Excess pad C (parallel plate): R114 0.064 pF, R112+R118 0.13 pF on the OUT node, C101/R113 pad 0.03 pF each,
  R101/R102 0.04 pF (with cut-out).
- BUF_OUT_S edge pad is 2.9 mm from the OUT pin. The sampler 10R must sit right at the edge (spec: <= 3 mm).
  R112 moved outward so pins 10 and 12 can escape.
- The coplanar check estimates 47.9 R at a 0.75 mm pour gap. This is within JLC's +-10 %. Widen the gap to 1 mm if needed.
- The U101 EP has 4 GND vias inside the pad (unavoidable for the QFN). Tent or plug them.

## Interfaces / open
- IF1 BUF_OUT_S: right edge, y = 5.8 (S>). IF2 BUF_OUT_T: bottom edge, x = 23.17 (T). Continue both as 0.36 mm over In1 GND.
- K101 HFD3 is on the bottom side. Verify the Kemet EC2 footprint against the Hongfa drawing.
- Apply via stitching when the fragments are assembled into the board. Run full DRC in the KiCad GUI.
