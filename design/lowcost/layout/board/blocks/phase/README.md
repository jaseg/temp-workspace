# Block "phase": trigger front chain and 16-tap phase delay line
Run `python3 gen_phase.py [--render]` → `phase.kicad_pcb`, `phase.ifaces.json`, `phase.png`, `phase_detail.png` (taps 0-2), `front_chain_detail.png` (local x 0-30).
**Size**: 99.5 x 22.5 mm at board (0, 22.5). pstrobe rectangle kept free: local x 9.5-26.5, y 2.5-22.5 except the corridor y 12-18. 181 parts (trigger_phase sheet + J102, R122).

## Checks (21 Nov 2026)
- Nightly DRC `run_drc.sh --rules jlc4`: 244 items, all allowed: 14 unconnected_items (+3V3 / +2V5 / -2V5, plane-fed), 25 track_dangling (interface stubs), 24 via_dangling (supply plane vias), 1 invalid_outline, 180 lib_footprint_mismatch / issues. **0 courtyard, clearance, track-width, hole, silk, text, isolated-copper.**
- check_board: 0 missing / extra / footprint / value / pad-net / no-net, 0 clearance, 0 corners, 0 off-axis pad exits, 0 RF width, 0 RF pour gap, 0 courtyard overlaps. Unrouted only +3V3 (10), +2V5 (1), -2V5 (3).

## Front chain (all RF on F.Cu, 0.36 mm, no vias in the signal path)
- Column x 0-9.5: J102 (corner, y 4) → R301 / R122 shunts north of the line (staggered, 0.94 mm) → U301 TMUX136 (rot 270; BUF_OUT_T straight down into pin 1, EXT_CLK into pin 3) → COM1 1.7 mm straight → U302 TLV3801 → CMP_P / CMP_N straight down through R306, R311 / R312 taps, C308 / C312; R310 terminates CMP_N. U304 LVDS2 west of the taps.
- Corridor on the axis: C308 → RFIN → U303 TRF37D73 → FB301 (pad on the line) → C311 → pi pad R307 / R308 / R309 (shunts north) → 50 R launch → 0.26 mm step 1.6 mm before tap 0.
- Bias tee: FB301 pad 2 → via pair → L302 47 uH on B (along the axis, directly below) with R382 beside it (B) → C313 at the cold pad (B) → +3V3 via pair beyond C313.
- On B: decoupling (C305, C307, C309, C310), VSW_GND network C302-C305/R304/R305/TP301 in the strip y 0-2.5 above pstrobe (C301, C306 on F there), SEL divider R302/R303, level network R383-R385/C304/TP302, TP303, TP304.
- RF lengths (mm): EXT_CLK 6.40, BUF_OUT_T 4.63, COM1 1.68, CMP_P 6.87, CMP_N 2.96, RFIN 5.58, RFOUT 2.04, pad in 1.81, launch 10.09 + 2.60.

## Delay line (geometry unchanged, identical in all 16 cells)
- Pitch 4.514 mm, strobes 0.16 mm (73 R), PH_LINE 0.26 mm S meander (gaps >= 0.5 mm), summing jumper midpoint tap A = B = 3.849 mm.
- **Line moved 0.29 mm west** (tap 0 at local 29.467, tap 15 at 97.177). The pstrobe interface stays at x 26.5; the first strobe half-section is 0.29 mm shorter for A and K alike (common delay, 1.7 ps). 0.29 mm is the limit: the tap-0 summing via must stay off the pstrobe rectangle.
- Tap cells: node chamfers 0.1 mm so tracks enter the resistor pads on-axis (was 74 off-axis exits).
- Far end: R377 horizontal below D316 (x 97.64-99.5), PH_LINE end 45° jog into pad 1; TP304 on B under R377 pad 1 (0.35 / 0.15 via in pad, stub behind the termination).
- Comparator 100 n caps raised 0.5 mm (U305's cap was inside the pstrobe rectangle); all 8 identical.

## Interfaces (local; board = local + (0, 22.5)) - changed vs. the previous version
| net | x, y | layer | note |
|---|---|---|---|
| /BUF_OUT_T | **8.79**, 0 | F.Cu N rf50 | was 4.925 |
| /PSTRB_A, /PSTRB_K | 26.5, 12.25 / 17.75 | F.Cu W | unchanged (meets pstrobe) |
| /TAP0-15, /VTAP_N, /VTAP_P, /VTAP_TH | x **-0.29** | B.Cu | moved with the line |
| /COARSE 4.45, 0; /DAC_TRIG 4.6, 22.5; /TRIG_SEL 9.25, 22.5 | | B.Cu | unchanged |

## Open points
- Reference designators and labels are on F.Fab / B.Fab; footprint silk touching pads or other silk is moved to Fab by `silk_fix()`.
- U302 +2V5 has one via at the pins (C305 via-in-pad on B); the second 100 n (C306) sits at the +2V5 via pair in the north strip. U304 has one +3V3 via.
- netlist has both R122 and R301 (25 R at the SMA): check the schematic. 40 / 70 ps per tap not re-simulated.
- Integrator: In2 islands for +3V3 / +2V5 / -2V5; VTAP_N / VTAP_P In2 strips are drawn here.
