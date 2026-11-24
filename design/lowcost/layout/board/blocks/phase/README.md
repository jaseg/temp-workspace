# Block "phase": trigger front chain and 16-tap phase delay line
Run `python3 gen_phase.py [--render]` → `phase.kicad_pcb`, `phase.ifaces.json`, `phase.png`, `phase_detail.png` (taps 0-2), `front_chain_detail.png` (local x 0-30).
**Size**: 99.5 x 22.5 mm at board (0, 22.5). pstrobe rectangle kept free: local x 9.5-26.5, y 2.5-22.5 except the corridor y 12-18. 183 parts (trigger_phase sheet + J102, R122, and C615 / C620 from the power sheet).

## Validation fixes (24 Nov 2026)
Existing capacitors moved; no part added. Outline and every interface position unchanged.
- **DECOUPLING-3 (U301):**
  - The VSW_GND pins 2 / 4 / 5 / 6 / 7 now join a 0.5 mm bar under the body. They were joined by 0.15 mm stubs before.
  - C303 (1 n C0G) is on top at pin 5. Its VSW pad is 0.4 mm from the pin.
  - C302 (100 n, VSW to GND) and C301 (100 n, +2V5 to VSW) are on B directly under U301. A 0.5 mm B bar joins them through the VSW via.
  - C301's +2V5 pad is on a via at pin 10 (0.6 mm of track). C302 and C303 share one GND via.
  - The B VSW feed to R304 / R305 / TP301 in the north strip is unchanged.
- **DECOUPLING-2 / PDN-6 (U302):**
  - There is no top-side room. COM1, SEL, CMP_P and both pin rows fill the 1.15 mm between U301 and U302, and R306 sits under the VEE pin.
  - The caps are therefore on B, in line with the vias, with no via in a pad.
  - +2V5: C305 (100 n) west and C615 (1 u, moved here) east of the pin-6/7 via, 0.3 / 0.1 mm of track, each with its own GND via.
  - -2V5: C620 (2.2 u, moved here) and C307 (100 n), each pad straight below one exposed-pad via (0.55 mm). One GND via south of them also takes GND pin 2.
  - TRIG_LEVEL now reaches its via by a 45-degree stub (8.8, 10.46). The U304-B B lane moved 0.5 mm south.
- **DECOUPLING-7:** C309 is now on top at U303 pin 1 (0.65 mm), with a +3V3 via pair beside it and its own GND via. All of these are at x <= 11.3, clear of the pstrobe L6 line at 11.87.
- **BIASTEE-5:** FB301.1, C311.1 and C311.2 have about 100 fF excess each (105 / 99 / 99 fF). Each now gets an L2 cut of the pad size plus an L3 no-track / no-via area, as in pstrobe.
- **BIASTEE-6:** L302 moved 1.1 mm east. The FB301 via pair now lies 0.25 mm outside choke pad 2, and two B tracks enter the pad along its axis. R382 and C313 moved with L302.
- **RF-3:** R378 / R379 are 43 R (netlist). The loaded strobe lines are 41.3 R, so |Gamma| = 0.02 (it was 0.09 with 49.9 R).
- **ZONES-1 / -2:** 21 GND stitching vias were added (`STITCH` in the generator).
  - One per meander cell 0-14 at (tap x + 1.9, axis + 1.95), pitch 4.514 mm. Each is 0.23 mm from the meander, 0.18 mm from the next 1 k pad, and 0.23 mm east of the board's tap-row L6 lanes, in the L3 web outside both node windows. They are on the K side only, because the next cell's B summing tap blocks the A side.
  - One more at each of these: the west row end (26.85, 16.1), the L6 fingers x 40-44 (42.0, 3.75 / 10.75) and x 80.8-84.4 (82.7, 10.0), the L3 island under the front column (6.5, 17.3), and the B island (20.1, 1.5).
  - All positions were checked at >= 0.15 mm against every copper item of `scope-fe.kicad_pcb`.
  - The block now also carries the L5 (In4) GND zone, as pstrobe does.
  - C306 has its own GND via.
- Not done here (board level): the L3 L-finger and the 0.3 mm sliver at board y 25-31 are formed by board slow lines. The L1 / L3 islands outside this block were not touched. Cell 15 has no via, because a board +2V5 L3 track passes at (99.08, 39.45).

**Interface changes:** none (positions, layers and widths unchanged). New refs in this block: C615, C620 (power sheet, placed at U302). The power block must not place them.

## Checks (24 Nov 2026)
- Nightly DRC `run_drc.sh --rules jlc4`: `total 245: error 15, warning 230`, all allowed:
  - 14 unconnected_items (+3V3 / +2V5 / -2V5, plane-fed);
  - 16 track_dangling (interface stubs);
  - 32 via_dangling (supply plane vias and the TAP8-15 interface vias; no GND via);
  - 1 invalid_outline;
  - 182 lib_footprint_mismatch / issues.
  - **0 courtyard, clearance, track-width, hole, silk, text or isolated-copper violations.**
- check_board: 0 missing / extra / footprint / value / pad-net / no-net, 0 clearance, 0 corners, 0 off-axis pad exits, 0 RF width, 0 RF pour gap, 0 courtyard overlaps. Unrouted only +3V3 (10), +2V5 (1), -2V5 (3).
- Renders `phase.png` and `front_chain_detail.png`, plus scratch close-ups of U301 / U302 and the tap cells, were looked at.

## Front chain (all RF on F.Cu, 50 R = 0.16 mm on the 6-layer stack-up, no vias in the signal path)
- Column x 0-9.5: J102 (corner, y 4) → R301 / R122 shunts north of the line (staggered, 0.94 mm) → U301 TMUX136 (rot 270; BUF_OUT_T straight down into pin 1, EXT_CLK into pin 3) → COM1 1.7 mm straight → U302 TLV3801 → CMP_P / CMP_N straight down through R306, R311 / R312 taps, C308 / C312; R310 terminates CMP_N. U304 LVDS2 west of the taps.
- Corridor on the axis: C308 → RFIN → U303 TRF37D73 → FB301 (pad on the line) → C311 → pi pad R307 / R308 / R309 (shunts north) → 50 R launch (0.16) → 0.10 mm step 1.6 mm before tap 0.
- Bias tee: FB301 pad 2 → via pair → (B track) L302 47 uH on B (along the axis, 1.1 mm east of the vias) with R382 beside it (B) → C313 at the cold pad (B) → +3V3 via pair beyond C313.
- On B: decoupling C301 / C302 (under U301), C305 / C615 / C620 / C307 (under U302), C310; in the strip y 0-2.5 above pstrobe: C306, R304 / R305 / TP301 (VSW); SEL divider R302/R303, level network R383-R385/C304/TP302, TP303, TP304. On top: C303 (U301 pin 5), C309 (U303 pin 1).
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
- U302 +2V5 has one via at the pins (C305 / C615 beside it on B); the second 100 n (C306) sits at the +2V5 via pair in the north strip. U304 has one +3V3 via.
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
Strobe terminations R378 / R379 are 43 R since 24 Nov (|G| 0.02). PH_LINE launch from the 50 R pad
into 50.45 R loaded line fine. 40 / 70 ps re-simulation still open.

## Integration changes (24 Nov 2026)
- C306 moved 0.12 mm south; the +2V5 via at x 10.45 (under the board PH_STROBE_N run x 10.60) removed; C306's own GND via
  removed (it sat on the board's DAC_TRIG / TRIG_SEL L3 lines): its GND pad is fed by the board's B pour.
- The phase L4 VTAP_P / VTAP_N strips are removed on the board (L4 = +3V3 only); board_power.py joins the tap-row vias on L3.
