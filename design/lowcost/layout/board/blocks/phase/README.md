# Block "phase": trigger front chain (folded) and 16-tap phase delay line
To run: `python3 gen_phase.py [--render]`. Outputs: `phase.kicad_pcb`, `phase.ifaces.json`, `phase.png` (F red / B blue) and `phase_detail.png` (front chain, local x 0-14). KiCad 7.0.11. kicad-cli 7 has no DRC or ERC, so the checks below are boardlib's scripted ones.
**Size**: 99.5 x 22.5 mm at board (0, 22.5), as in FLOORPLAN, with the pstrobe cut-out (local x 9.5-26.5, y 3.5-22.5, except the corridor y 12-18) kept free. The block did not grow.
181 parts: the whole trigger_phase sheet (179, incl. the new R383-R385 level network on B) plus J102 and R122, all with `Block.place`.

**check_board results (refs = this block)**:
- 0 missing / extra / footprint / value / pad-net / no-net; 0 clearance; 0 corners above 45 deg; 0 RF width deviations; 0 RF pour-gap violations.
- Unrouted nets: only the plane-fed supplies +3V3 (10), +2V5 (1) and -2V5 (2). GND reaches In1 through vias.
- Pad-axis exits: 74. They are the inherited tap-cell resistors (node and via legs) plus a few WSON / SOT-23 corner pins.

## Geometry (copied unchanged from layout/phase_trigger)
- Tap pitch is 4.514 mm. Tap 0 (D301) is at local x 29.757 and tap 15 at 97.467; the axis is at local y 15.0 (board 37.5).
- PSTRB_A / PSTRB_K: 0.16 mm (73 R), 4.514 mm = 26.4 ps unloaded / 40 ps loaded per tap. Ends: R379 / R378, 49.9 R.
- PH_LINE (`Net-(D301-common)`): 0.26 mm S meander, 9.929 mm = 59.3 ps unloaded / 70 ps loaded per tap. Same-net gaps are >= 0.5 mm. It ends in R377.
- Summing node: identical B.Cu jumper per tap with the tap taken from its midpoint. Comparator routes A = B = 3.849 mm (asserted).
- Bias tee: as corrected in sim/bias_tee. FB301 pad on the line → L302 1210 (with R382 beside it) → C313 at the cold pad → +3V3 via pair beyond C313.

| RF route (all 0.36 mm 50 R unless stated) | length mm | ps |
|---|---|---|
| BUF_OUT_T N edge → U301.1 / EXT_CLK J102 → U301.3 | 3.00 / 3.03 | 18.2 / 18.3 |
| COM1 U301.8 → U302.5 | 5.36 | 32.4 |
| CMP_P → C308 (R311 and R306 tees) / CMP_N → C312 (R306, R312) | 7.79 / 2.41 | 47.2 / 14.6 |
| RFIN C308 → U303.2 / RFOUT U303.7 → FB301 → C311 / C311 → R308 | 1.74 / 1.60 / 1.53 | |
| PH_LINE launch: R308 → step (0.36 mm), then step → D301.3 (0.26 mm) | 15.80 + 2.60 | 95.7 + 15.5 |

## Interfaces (local mm; board = local + (0, 22.5))
| net | x, y | layer / side | note |
|---|---|---|---|
| /BUF_OUT_T | 4.925, 0 | F.Cu N, rf50 | Straight down into U301.1. FLOORPLAN had x 7. |
| /PSTRB_A, /PSTRB_K | 26.5, 12.25 / 17.75 | F.Cu W, rf50 | **Deviation**: axis ±2.75, not ±4.4. pstrobe must make the 45° jog (1.65 mm in x) inside its own block. The 0.16 mm section starts on the boundary. |
| /TAP0-15 | x 29.27-93.74, y 0 | B.Cu N, slow | Via at each comparator pin. |
| /COARSE | 4.45, 0 | B.Cu N | |
| /DAC_TRIG, /TRIG_SEL | 4.6 / 9.25, 22.5 | B.Cu S | DAC_TRIG via R383 (TRIG_LEVEL is now block-internal) |
| /VTAP_N, /VTAP_P, /VTAP_TH | 44.15 / 48.66 / 62.22, 22.5 | B.Cu S | VTAP_TH feeds R380 / R381 (on B) between U308 and U309. |

Supplies use via pairs to In2: +3V3 at U303, U304, the comparators and C313; +2V5 at U301 / U302; -2V5 at the U302 EP, R303 and R305. The integrator must provide In2 islands for these. The **VTAP_N / VTAP_P In2 strips are drawn by this block**: merge without `skip_planes`, or redraw them. The In1 GND zone, the In1 cut-outs and an F.Cu GND pour with the RF keep-outs are also in the file.

## Deviations
- **J102** is at board y 26.5 (local 4.0), not 37.5. The front chain is folded into x 0-9.5 because the corridor is only 6 mm high: TMUX at the top, TLV in the middle, TRF and bias tee on the axis.
- **Local helper**: `Block.place(side="B")` segfaults in pcbnew 7.0.11, because it flips before `Board.Add`. `bplace()` places on F, then flips. boardlib.py was not edited.
- **On B.Cu**: decoupling and slow parts (C302-C307, C309, C310, R304, R305, R380, R381, C354, C355, TP301-TP303, TP305).
- **R303 / R302** (SEL divider) are on top, next to the TMUX.

## Open points
- **NOT DONE: 24 courtyard overlaps remain** (DRC courtyards_overlap 24): front chain J102/R301/R122/U301/C301, R306/R311/R312/C308/C312/R310/U302, U303/FB301/L302, B-side C302/C303/R304/R305/TP301, J102/TP303/C310 (B); far end R377/TP304/D316 (no 0402 fits inside x 99.5). Fix = shift U301 cluster east 2.2 mm (shunts staggered at x 5.17/6.11), U302 to x 8.2, VSW network to the top strip on B, R377 needs ~0.3 mm block growth or TP304 on B.
- Silk text 0.3-0.5 mm (DRC text_height/line_width 18 warnings): move refs to F.Fab.
- The netlist has **both R122 and R301** (49.9 R from EXT_CLK to GND), giving 25 R at the SMA. Both are placed at the pin. Check the schematic.
- TP304 (LINE_IN) sits after R377 at the far end: a 1.2 mm stub behind the termination.
- U304 has one +3V3 via (the board edge is too close for a pair).
- The pstrobe interface shift needs agreement with the pstrobe block.
- 40 / 75 ps per tap is not re-simulated (inherited).
