# Block "phase": trigger front chain and 16-tap phase delay line
Run `python3 gen_phase.py [--render]` → `phase.kicad_pcb`, `phase.ifaces.json`, `phase.png`, `phase_detail.png` (taps 0-2), `front_chain_detail.png` (local x 0-30).
**Size**: 99.5 x 22.5 mm at board (0, 22.5). pstrobe rectangle kept free: local x 9.5-26.5, y 2.5-22.5 except the corridor y 12-18. 189 parts (trigger_phase sheet + J102, R122, and C615 / C620 from the power sheet).

## BOM review 2 (25 Nov 2026, SPEC decisions 27-34; netlist `kicad/export/scope-fe.net` regenerated)
Netlist changes in this block: U301 TMUX136 (+ R302-R305, C301-C303, TP301, VSW_GND) and U304 SN65LVDS2 removed; added the
trigger selector D317-D320 (2 x 2 BAT15-04W SOT-323), Q301 SS8550 / Q302 MMBT3904 (SOT-23), R386-R394 and U313 COS3502
(SOIC-8, COARSE receiver); C313 now decouples U313 pin 8 and C310 is the line-driver bias-tee cold capacitor (roles of the
two 100 n swapped by the schematic numbering); value changes C314-C345 (C76912), R307-R309 100 R, R378 / R379 49.9 R,
R384 10k, R385 3.3k (no layout effect). check_board: 0 missing / extra / footprint / value / pad-net.

**Front column re-laid (x 0-9.5; outline, interfaces and the corridor / tap row unchanged):**
- Switch (RF, all on F.Cu, 0.16 mm = 50.2 R, no via in any signal path): D320 (EXT b, rot 0) and D318 (signal b, rot 180)
  side by side, pins 3 facing across a 1.40 mm Y bar (TRIG_IN), Y stub 1.95 mm straight down into U302 pin 5 (IN+).
  The two b packages are a copper mirror about the Y node (x 6.09). D317 (signal a) above D318 takes BUF_OUT_T at pin 3
  (5.57 mm from the interface, was 4.63 to U301); D319 (EXT a) west of D320 takes EXT_CLK at pin 3 (11.10 mm from J102,
  was 6.40 to U301). T / B traces: B1 1.35, T1 3.69, T2 4.09, B2 1.95 mm (same-side SOT-323 pairs cannot face each other
  without a crossing, so one trace of each bridge runs through the other package's body channel; the two branches of a
  bridge are parallel paths, a 2 mm difference puts the first notch above 40 GHz).
- Pad compensation (rule as BIASTEE-5 / pstrobe): pins 3 of D317-D320 have 78 fF excess each over the 0.16 mm line ->
  L2 cut of the pad size + L3 no-track / no-via area. T / B pads keep solid L2 (bom2-trigger.md: ground continuous under
  the bridges).
- R301 / R122 (EXT_CLK 49.9 R, R122 DNP) sit with a pad ON the down leg of EXT_CLK (x 5.15, 2.1 / 3.0 mm from the SMA
  pin), one shared GND via. Decision: the termination stays near the SMA (as with the TMUX136) instead of "at D319 pin 3"
  (bom2-trigger.md): there is no room for a shunt + GND via at pin 3 between the SMA courtyard and the bridge; the line
  behind it is doubly matched up to the 500 R bridge as before (11 mm instead of 6.4 mm).
- Feeds R391-R394 (1 k) on B, each on a via in the middle of its T / B trace (via in a trace, not in a pad; hole edge
  >= 0.15 mm from every pad). Their far ends, R387 / R390 (west) and the drive meet on L3 (block In2): SW_S / SW_SB are
  static bias lines with no capacitor (bom2-trigger.md asks for L3). Drive on B in the north of the column: Q301 / Q302
  rot 90 stacked (x 4.7-8.1), R386 / R389 / R388 in a column east of them, TRIG_SEL keeps its B lane x 9.25 from the S
  interface. The only via within 1 mm of BUF_OUT_T is the -2V5 via of R389 / Q302 (0.43 mm edge to edge).
- U302 TLV3801 and its CMP_P / CMP_N network (R306, R311 / R312, C308 / C312, R310) keep their relative geometry,
  moved 2.2 mm west and 3.6 mm south (U302 at (5.34, 12.2)). RFIN (7.98 mm, was 5.58) runs east under C312 / R310 and
  climbs at 45 degrees into U303 pin 2. U302 +2V5: pins 6 / 7 -> one via -> C615 1 u (north), C305 100 n (east),
  C306 100 n (west, moved here from the north strip) on B, each with its own GND via; VEE / C620 / C307 as before.
- U313 COS3502 on B under the south of the column (x 0.5-7.9, y 17-22.4): a slow logic-level receiver (COARSE valid to
  60 MHz), so B per rule 8; C313 at pin 8 with its +3V3 / GND vias behind it. Inputs from R311 / R312 (top, at the U302
  lines) through a via each and two B lanes; COARSE leaves pin 7 west, runs up x 0.4 and under the SMA's south pad to the
  unchanged interface (4.45, 0) (TP303 on it).
- Level network (R383-R385, C304, TP302) now on top south of RFIN; TRIG_LEVEL from the U302 pin-4 via on L3, DAC_TRIG
  from the S interface through one via.
- J102: the outer via row of the south ground pad is gone (EXT_CLK passes 0.32 mm below that pad); the inner rows of
  both pads stay. Stitching via (6.5, 17.3) removed (on the new RFIN / U313 lanes).

**Interface changes:** none (positions, layers, widths; `phase.ifaces.json` identical). Board-level notes for the
integrator: L3 (In2) now carries block tracks in the column (SW_S / SW_SB x 2-9.4, y 0.6-12.75; TRIG_LEVEL x 6.6-8.75,
y 14-19.3); the +2V5 branch into the column now lands on the U302 / Q301 / R390 vias (no C306 / U301 in the north strip);
-2V5 islands: U302 EP via, VMN (7.40, 4.52), VM (6.85, 8.30), R384 and R387 vias.

**Checks (25 Nov 2026):** check_board 0 in every class (missing / extra / footprint / value / pad-net / clearance /
corners / off-axis exits / RF width / RF pour gap / courtyards); unrouted only +3V3 (11), +2V5 (2), -2V5 (4), plane-fed.
Nightly DRC jlc4: `total 257: error 18, warning 239` = 17 unconnected_items (+3V3 / +2V5 / -2V5 plane-fed), 1
invalid_outline, 35 via_dangling (supply vias, TAP8-15 interface vias), 15 track_dangling (interface stubs, VTH rails),
189 lib_footprint_*; 0 courtyard / clearance / track-width / hole / silk. via_in_pad.py: FAIL 0. decap_audit on the
block: only the known U310 D2p. Renders looked at: `front_chain_detail.png`, `phase.png`, scratch crops of the switch on
F, B and L3 and of the south of the column.

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

## Front chain (before BOM review 2; superseded by the section above for the column x 0-9.5)
- Column x 0-9.5: J102 (corner, y 4) → R301 / R122 shunts north of the line (staggered, 0.94 mm) → U301 TMUX136 (rot 270; BUF_OUT_T straight down into pin 1, EXT_CLK into pin 3) → COM1 1.7 mm straight → U302 TLV3801 → CMP_P / CMP_N straight down through R306, R311 / R312 taps, C308 / C312; R310 terminates CMP_N. U304 LVDS2 west of the taps.
- Corridor on the axis: C308 → RFIN → U303 TRF37D73 → FB301 (pad on the line) → C311 → pi pad R307 / R308 / R309 (shunts north) → 50 R launch (0.16) → 0.10 mm step 1.6 mm before tap 0.
- Bias tee: FB301 pad 2 → via pair → (B track) L302 47 uH on B (along the axis, 1.1 mm east of the vias) with R382 beside it (B) → C313 at the cold pad (B) → +3V3 via pair beyond C313.
- On B: decoupling C301 / C302 (under U301), C305 / C615 / C620 / C307 (under U302), C310; in the strip y 0-2.5 above pstrobe: C306, R304 / R305 / TP301 (VSW); SEL divider R302/R303, level network R383-R385/C304/TP302, TP303, TP304. On top: C303 (U301 pin 5), C309 (U303 pin 1).
- RF lengths (mm): EXT_CLK 6.40, BUF_OUT_T 4.63, COM1 1.68, CMP_P 6.87, CMP_N 2.96, RFIN 5.58, RFOUT 2.04, pad in 1.81, launch 10.09 + 2.60.

## Delay line (identical in all 16 cells)
- Pitch 4.514 mm (kept), strobes 0.10 mm (62 R), PH_LINE 0.10 mm S meander 9.707 mm (gaps 0.632 / 0.932 mm), summing jumper midpoint tap A = B = 3.849 mm.
- **Line moved 0.29 mm west** (tap 0 at local 29.467, tap 15 at 97.177). The pstrobe interface stays at x 26.5; the first strobe half-section is 0.29 mm shorter for A and K alike (common delay, 1.7 ps). 0.29 mm is the limit: the tap-0 summing via must stay off the pstrobe rectangle.
- Tap cells: node chamfers 0.1 mm so tracks enter the resistor pads on-axis (was 74 off-axis exits).
- Far end: R377 horizontal below D316 (x 97.64-99.5), PH_LINE end 45° jog into pad 1; TP304 on B on a 0.35 / 0.15 via in the straight line section 0.6 mm before the jog into R377 pad 1 (24 Nov: no via in a soldered pad, RULES rule 12).
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

- TIGHTEN (24 Nov): U310 cap C351 gets a GND via 0.6 mm east of its GND pad (just east of the board L6 fan-in, joined by the F pour); was 1.6 mm to the nearest GND via.

## REPAIR (24 Nov, recheck RF2-1 / RF-7)
- U301 pin 10 (+2V5): short F stub east and south to a 0.4 mm via beside pin 9 (1.5 mm from BUF_OUT_T's end), B track to
  C301's +2V5 pad and north (x 9.03, under the old F track) to C306 / its via. The F track at x 9.20 beside BUF_OUT_T and
  its two vias (0.105 mm via edge to the trace, antipads under it) are gone; L2 is solid under BUF_OUT_T. The pstrobe
  cut-out (x >= 9.5) forbids a feed further east. Render: `phase_netview_u301.png`.

**Vias out of pads (24 Nov, RULES rule 12):** J102 GND via rows at the pad edges (inner rows + south outer row, F / B necks), U302 EP via -> one via 0.2 mm beyond the EP end, VSW via 0.18 mm off U301 pin 5, C310 east of its via, U304 pin 4 / 5 vias, TP304 off R377. `python3 ../../via_in_pad.py phase.kicad_pcb`: FAIL 0.

## Board integration (25 Nov 2026)
- **SW_SB L3 route:** the trunk runs x 6.1 from VSB_N down to y 11.3, with the east branch at y 9.9 as before. The
  west branch now leaves at y 11.3, south of U302's +2V5 via (5.34, 10.4) and north of the -2V5 via XEV, and runs
  to VSB_W. The old y 7.6 / x 3.3 branch is removed: with SW_S's y 12.75 run it sealed the U302 +2V5 via in an L3
  pocket that no rail could reach.
- **TRIG_SEL lane:** the board removes the x 9.25 B lane. TRIG_SEL reaches R386.1 from a board via at (11.3, 23.85),
  and the lane now carries -2V5. The `TRIG_SEL` iface entry is kept, but the board does not use it.
- **Checks:** check_board 0 clearance / corner / courtyard; the unrouted nets are the plane-fed supplies only.
