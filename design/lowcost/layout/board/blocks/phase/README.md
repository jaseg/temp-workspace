# Block "phase": trigger front chain and 16-tap phase delay line
Run `python3 gen_phase.py [--render]` → `phase.kicad_pcb`, `phase.ifaces.json`, `phase.png`, `phase_detail.png` (taps 0-2), `front_chain_detail.png` (local x 0-30).
**Size**: 99.5 x 22.5 mm at board (0, 22.5). pstrobe rectangle kept free: local x 9.5-26.5, y 2.5-22.5 except the corridor y 12-18. 181 parts (trigger_phase sheet + J102, R122).

## Checks (21 Nov 2026)
- Nightly DRC `run_drc.sh --rules jlc4`: 244 items, all allowed: 14 unconnected_items (+3V3 / +2V5 / -2V5, plane-fed), 25 track_dangling (interface stubs), 24 via_dangling (supply plane vias), 1 invalid_outline, 180 lib_footprint_mismatch / issues. **0 courtyard, clearance, track-width, hole, silk, text, isolated-copper.**
- check_board: 0 missing / extra / footprint / value / pad-net / no-net, 0 clearance, 0 corners, 0 off-axis pad exits, 0 RF width, 0 RF pour gap, 0 courtyard overlaps. Unrouted only +3V3 (10), +2V5 (1), -2V5 (3).

## Front chain (all RF on F.Cu, 50 R = 0.16 mm on the 6-layer stack-up, no vias in the signal path)
- Column x 0-9.5: J102 (corner, y 4) → R301 / R122 shunts north of the line (staggered, 0.94 mm) → U301 TMUX136 (rot 270; BUF_OUT_T straight down into pin 1, EXT_CLK into pin 3) → COM1 1.7 mm straight → U302 TLV3801 → CMP_P / CMP_N straight down through R306, R311 / R312 taps, C308 / C312; R310 terminates CMP_N. U304 LVDS2 west of the taps.
- Corridor on the axis: C308 → RFIN → U303 TRF37D73 → FB301 (pad on the line) → C311 → pi pad R307 / R308 / R309 (shunts north) → 50 R launch (0.16) → 0.10 mm step 1.6 mm before tap 0.
- Bias tee: FB301 pad 2 → via pair → L302 47 uH on B (along the axis, directly below) with R382 beside it (B) → C313 at the cold pad (B) → +3V3 via pair beyond C313.
- On B: decoupling (C305, C307, C309, C310), VSW_GND network C302-C305/R304/R305/TP301 in the strip y 0-2.5 above pstrobe (C301, C306 on F there), SEL divider R302/R303, level network R383-R385/C304/TP302, TP303, TP304.
- RF lengths (mm): EXT_CLK 6.40, BUF_OUT_T 4.63, COM1 1.68, CMP_P 6.87, CMP_N 2.96, RFIN 5.58, RFOUT 2.04, pad in 1.81, launch 10.09 + 2.60.

## Delay line (identical in all 16 cells)
- Pitch 4.514 mm (kept), strobes 0.10 mm (62 R), PH_LINE 0.10 mm S meander 9.707 mm (gaps 0.632 / 0.932 mm), summing jumper midpoint tap A = B = 3.849 mm.
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

## Six-layer RF geometry (phase two, 21 Nov 2026)
`gen_phase.py` derives every RF width from `boardlib.microstrip(h=0.0994, er=4.1)` (STACKUPS["6L"], mask-corrected; L1 over L2).
The block file stays 4-copper (In1 = GND -> L2, In2 = supply landings / VTAP strips -> L4 via `LAYER_MAP_4TO6`).

| w mm | 0.09 | 0.10 | 0.11 | 0.12 | 0.14 | 0.16 | 0.20 | 0.26 | 0.36 |
|---|---|---|---|---|---|---|---|---|---|
| Z0 R | 64.6 | 62.0 | 59.6 | 57.4 | 53.6 | 50.2 | 44.7 | 38.5 | 31.4 |
| ps/mm | 5.79 | 5.82 | 5.84 | 5.86 | 5.89 | 5.93 | 5.98 | 6.05 | 6.13 |

| line | width | Z0 unloaded | load per tap (gate + pad) | section | unloaded | loaded delay | loaded Z |
|---|---|---|---|---|---|---|---|
| PSTRB_A / K | 0.10 mm | 62.0 R | 0.530 pF (0.42 + 0.110) | 4.514 mm | 26.25 ps | **39.40 ps** (target 40) | 41.3 R |
| PH_LINE | 0.10 mm | 62.0 R | 0.465 pF (0.37 + 0.095) | 9.707 mm | 56.46 ps | **69.40 ps** | 50.45 R |
| (4-layer, old) PSTRB / PH_LINE | 0.16 / 0.26 | 72.8 / 59.0 | 0.469 / 0.396 | 4.514 / 9.929 | 26.4 / 59.3 | 40.0 / 70.0 | 48.1 / 50.0 |

- Pad loading over L2 roughly doubles (strobe cap pad 0.049 -> 0.110 pF, BAT15 pad 3 0.026 -> 0.095 pF). It is absorbed by the lower Z0 and is not cut out:
  at the kept 4.514 mm pitch the loaded Z = Z0 x tdu / td depends only on Z0, so the narrowest line wins. 0.10 mm is used (0.09 is the JLC
  minimum: 39.8 ps / 42.5 R; kept 10 % etch margin instead). The line delay follows the strobe (69.40 = 39.40 + 30), so the
  line - strobe difference per tap is unchanged (30.00 ps model, the spacing SPEC.md calls 35 ps).
- Hold-node cut-outs (L2): now y 0.40-2.35 from the axis (were 0.55): the BAT15 pads 1 / 2 lie fully over the cut. L2 AND L4 (block In2) are
  cleared there and under the J102 pin; the integrator clears L3 under every L2 cut-out, so the nodes reference L5 (1.37 mm, was In2 1.29 mm).
  The meander (0.35 mm = 3.5 h) and the strobe rows (0.35 mm) stay referenced to solid L2.
- YL kept 2.75 (required 2.60), tap x positions, comparators, summing node, all interfaces: **no interface moved** (ifaces.json: only the
  rf50 widths 0.36 -> 0.16 of BUF_OUT_T, PSTRB_A, PSTRB_K).
- Width transitions (necks): PH_LINE 0.16 -> 0.10 step 1.6 mm before tap 0 (2.60 mm of 0.10 to D301 pad 3); PSTRB 0.16 (pstrobe) -> 0.10 at x 26.5;
  all 50 R lines (0.16) are narrower than every pad they meet (0402 0.54-0.56, WSON 0.25, UQFN 0.2-0.25 lands; SMA 1.27): no necking down
  into a pad is left. Front-chain 0402 series pads are not compensated (excess about 0.09 pF per pad over solid L2).

Intended vs actual (drawn) lengths / delays (6L ps/mm):
| route | intended | drawn | delay |
|---|---|---|---|
| PH_LINE cell 0-14 | 9.707 mm | 9.707 mm | 56.5 ps unloaded, 69.4 loaded |
| PSTRB section 1-15 | 4.514 mm | 4.514 mm | 26.3 ps unloaded, 39.4 loaded |
| PSTRB section 0 (A = K) | 4.224 mm | 4.224 mm | 24.6 ps (0.29 mm west shift) |
| summing tap A / B | equal | 3.849 / 3.849 mm | |
| EXT_CLK, BUF_OUT_T, COM1 | | 6.40, 4.63, 1.68 mm | 37.9, 27.4, 9.9 ps |
| CMP_P, CMP_N, RFIN, RFOUT, pad in | | 6.87, 2.96, 5.58, 2.04, 1.81 mm | 40.7, 17.5, 33.0, 12.1, 10.7 ps |
| launch 50 R + 0.10 | | 10.09 + 2.60 mm | 59.8 + 15.1 ps |

Checks (6-layer geometry): check_board 0 in every class except unrouted +3V3 (10) / +2V5 (1) / -2V5 (3) (plane-fed); nightly DRC jlc4:
`total 244: error 15, warning 229` = 177 lib_footprint_mismatch, 25 track_dangling, 24 via_dangling, 14 unconnected_items (plane-fed),
3 lib_footprint_issues, 1 invalid_outline. Renders `phase.png`, `phase_detail.png`, `front_chain_detail.png` looked at.
Open: strobe terminations R378 / R379 49.9 R vs 41.3 R loaded (|G| 0.09; schematic value 43 R would match); PH_LINE launch from the 50 R pad
into 50.45 R loaded line fine. 40 / 70 ps re-simulation still open.
