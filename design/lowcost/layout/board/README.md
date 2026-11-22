# layout/board: scope-fe integrated board (six layers), fully routed (0 unconnected), reviewed 22 Nov 2026

**Status (22 Nov 2026, fourth pass, TOPOLOGY.md section 9 implemented):** one run of `python3 gen_board.py` (~75 s;
`--fast` reuses the cached pre-power board, `--powonly` stops after the power check) gives 0 unconnected items.

### Check results (last run, verbatim)
- board_power.verify: `missing links over the rail nets: 0;  pcbnew GetUnconnectedCount() board-wide: 0`; `VBUS below 1.0 mm: 0 mm`;
  `self-check of added copper: clearance/crossing 0, corners > 45 deg 0, off-axis pad exits 0`.
- check_board: missing 0, extra 4 (H1-H4), footprint 0, value 0, pad-net 0, unrouted 0, clearance 0, corners > 45 deg 0,
  off-axis pad exits 1 (R737.1, known), RF 0, courtyard 0, unconnected items 0.
- rule 10: `fast-net segments on L3: 0; L1/L6 samples 8170, without filled GND on L2/L5: 449` = 417 via antipads, 25 PTH
  antipads, 7 deliberate windows, 0 real plane holes; L4 `+3V3` one polygon.
- DRC jlc4 + parity: `total 462: warning 462`, 0 errors, 0 unconnected. Warnings: 199 footprint_symbol_field_mismatch ('Note'),
  199 lib_footprint_mismatch, 30 footprint_symbol_mismatch (DNP), 12 lib_footprint_issues, 10 net_conflict, 4 track_dangling,
  4 via_dangling, 2 silk_over_copper, 2 silk_overlap.
- ERC (re-run, schematic untouched): `total 18: warning 18` (9 footprint_link_issues, 9 lib_symbol_mismatch), 0 errors.

## Review (independent, 22 Nov 2026)

Checks after the review fixes (full `python3 gen_board.py`, 83 s):
- check_board: missing 0, extra 4 (H1-H4), footprint 0, value 0, pad-net 0, unrouted 0, clearance 0, corners > 45 deg 0,
  off-axis pad exits 1 (R737.1, known), RF width 0, RF pour gap 0, courtyard 0, unconnected items 0.
- board_power.verify: missing links 0, `GetUnconnectedCount()` 0, VBUS below 1.0 mm 0; rule 10: fast-net segments on L3 0,
  449 samples without L2 / L5 under them = 417 via antipads + 25 PTH antipads + 7 deliberate windows, 0 real holes; L4 +3V3 one polygon.
- DRC jlc4 + parity: `total 450: warning 450`, 0 errors, 0 unconnected (199 'Note' field, 199 lib_footprint_mismatch, 30 DNP /
  exclude-from-BOM attribute, 12 lib_footprint_issues, 10 net_conflict). ERC: `total 18: warning 18` (9 footprint_link_issues,
  9 lib_symbol_mismatch), 0 errors.

Remaining warning classes (none is a board fault):
- net_conflict (10): TL401-TL403 (6) are the copper-only transmission lines; their TLINE symbols have pins 2 / 4 = GND (the
  reference conductor), the board footprint has pads 1 / 3 only and the reference is the L2 plane, the shorted ends reach GND
  through NT401-NT403 pad 2 (on the L1 pour plus vias). J601 (4): the four shell tabs are all pad "S1" on GND, the symbol has
  one SHIELD pin S1 on GND; the netlist, the board pads and check_board agree, the nightly parity reports each duplicate pad.
  No ground pad is missing on any footprint.
- 'Note' field / DNP and exclude-from-BOM attributes / lib_footprint_mismatch / lib_footprint_issues: KiCad 7 board vs KiCad 10
  libraries and symbol fields (the custom `board:` TLine footprints and the SMA / WSON footprints are not in the nightly tables).

Found and fixed (in the generators):
1. 4 dangling vias: -2V5 (7.94, 31.1), the second U302 exposed-pad via, touched only L1 - now tied to its partner via on L3;
   -2V5 (17.85, 24.51) only joined two B tracks at R305.2 - replaced by a B track leaving the pad along its axis; VBUS
   (22.78, 26.345 / 27.045), the old pstrobe landing vias fed only by a B stub from C418.1 - removed with the stub
   (`board_finish.cleanup`).
2. 4 dangling tracks: VTAP_P / VTAP_N mcuif stubs north of the R725 / R726 vias (removed); VTH1 / VTH2 rails overhung their
   end pin stubs by 0.3 mm at both ends (each end stub now turns into the rail with a 45-degree bend).
3. Silkscreen: "USB" sat on the D601 pads and inside its outline (moved, vertical, west of J601); U603 / L601 library silk
   overlap (L601's touching silk segment dropped). Missing labels added: FPGA, POWER, PHASE (moved into the phase block),
   MCU / IF, PROG J501.
4. Minor-rail widths: new post-pass `board_power.widen()` widens maze tracks of +/-2V5, +/-5V and VBUS (<= 0.5 mm, L3 / L6)
   to 0.6 / 0.5 / 0.4 mm where 0.3 mm to slow lines / other rail zones and 0.2 mm to all other copper allow: +2V5 177 mm
   widened (L3 at 0.3 mm 220 -> 112 mm), -2V5 10 mm, +5V 16 mm, VBUS 2 mm.
5. Deliverable renders: the old detail crops did not show the regions named (the "fpga-south" crop showed the comparator row
   only); re-rendered: analog x 0-57 / y 0-24, FPGA south edge + staircases + highway x 24-98 / y 12-36, MCU + J501 x 25-97 /
   y 42-57.5.

Narrowest board-level copper per rail after the fix (pad-width fan-outs inside the blocks, 0.2-0.25 mm on F.Cu at IC pins, not
counted). Capacity: IPC-2221, 10 K rise, inner 0.5 oz (15.2 um): 0.3 mm 0.27 A, 0.5 mm 0.40 A, 0.8 mm 0.56 A, 1.0 mm 0.65 A;
outer 35 um: 0.4 mm 1.2 A, 1.2 mm 2.7 A.

| rail | load current | narrowest | where | adequate |
|---|---|---|---|---|
| VBUS | 0.85 A at J601 (power block, planes / wide F copper); about 0.2 A on the L3 / L6 run to the GVA-84+ chokes | L3 1.0 mm (3.9 mm), L6 0.4 mm (choke joins, about 0.1 A) | L3 band y 26.8, pstrobe choke column | yes |
| +5V | 0.04 A | L3 0.5 mm (3.4 mm) | analog block west, x 10-20 / y 10-20 | yes |
| -5V | 0.09 A (incl. -2V5) | L6 0.4 mm (0.3 mm), L3 0.6 mm | analog block, x 10-20 / y 10-20 | yes |
| +2V5 | 0.05 A | L3 0.3 mm (112 mm), L6 0.3 mm (35 mm) | L3 power / FPGA area x 60-100 / y 0-10 and east edge; L6 along the top edge x 33-63 | current yes; drop about 4 mV/mm-A (3.8 mOhm/mm) |
| -2V5 | 0.04 A | L6 0.3 mm (12 mm), L3 0.3 mm (0.4 mm) | L6 x 20-30 / y 20-30 (R305 / pstrobe north) | yes |
| +1V2 | 0.03 A | L3 0.8 mm | power -> FPGA | yes |
| VTAP_P / VTAP_N | 12.5 mA each | L3 0.5 mm | along the tap row | yes |

Supply copper near sensitive nodes (sampled check of every rail segment against the hold node, divider node, comparator
summing nodes, TRIG_LEVEL, TMUX output, ADC_IN): no supply track lies under an L2 node window; every crossing of a sensitive
L1 net is separated by solid L2, every crossing of an L3 / L6 sensitive line (ADC_IN, TRIG_LEVEL) by L4 + L5; no rail runs
on L3 within 0.5 mm of ADC_IN.

Left open (ranked):
1. The -2V5 L3 maze track (0.6 mm, y 10.4, x 23.4-27.8) passes 0.18 mm north of the hold-node window (L2 / L3 / L4 cut
   x 22.25-25.15, y 10.88-12.8). Static, decoupled rail and 0.6 mm lateral to the hold pad, so coupling is small, but it is
   the one supply run beside the hold node; a >= 1 mm keep-out around the node windows in the maze would move it.
2. +2V5 still 0.3 mm over 147 mm (L3 / L6): adequate for 50 mA (IPC 0.27 A) but against rule 2; a wider path needs space the
   slow lines and L6 buses hold (an L3 corridor zone from the power block would be the real fix).
3. R737.1 off-axis exit (known); TL / J601 parity warnings (artefacts, above).
4. Silkscreen: no reference designators are shown (all on F.Fab, rule 9: no room); EXT CLK (J102) has no silk label
   (no free silk room; F.Fab value only); test points are unlabelled on silk.
5. `gen_board.py --fast` fails (`rail_nets`: board.FindNet returns a bare SwigPyObject on the cached board); full runs only.
6. Not changed, not re-checked beyond the renders: sampler bridge / strobe arm symmetry, tap-cell and pstrobe-chain
   symmetry and the SMA launches as built by the blocks; the boost converter (U603 / L601, x 79-85, y 0-8) sits about 23 mm
   from the analog block's east edge with the FPGA between them.

### Slow lines (board_slow.py, section 9)
| net | route | mm |
|---|---|---|
| ADC_IN | L6 lane 66.85 -> via (66.85, 28.3) -> L3 band y 28.0 (north edge, >= 1 mm to the bundle) -> channel C x 30.85 -> y 19.35 north of R210's via -> (19.06, 20.0) | 77.25 |
| ADC_REF_MID | lane 52.7 -> via (52.7, 29.15) -> band 29.15 -> C x 29.65 -> A y 21.4 -> (21.65, 20.8) | 56.55 |
| VBIAS_K | lane 61.8 -> via (61.8, 29.75) -> band 29.75 -> C x 28.5 -> A y 21.7 -> (16.4, 20.3) | 73.04 |
| VBIAS_A | lane 57.85, L6 jog past U308.3's input trace -> via (59.5, 30.5) -> band 30.05 -> C x 28.2 -> A y 22.0 -> x 15.4 north to (15.4, 16.3) | 77.08 |
| VNEG_REF | lane 35.09 -> via (35.09, 30.5) -> band 30.5 -> C x 27.9 -> A y 22.3 / 22.45 -> (1.94, 19.2) | 58.88 |
| VOFS | lane 57.3 -> via (57.3, 32.0) -> band 30.95 -> C x 27.6 -> A y 22.6 / 22.75 -> (1.0, 19.2) | 82.61 |
| DAC_TRIG | lane 53.3 -> via (53.3, 32.0) -> band 32.0 -> C x 27.3 -> pstrobe N edge y 24.97 -> x 14.57 -> y 23.05 -> B (grid) -> (4.6, 41.0) | 89.98 |
| TRIG_SEL | lane 66.3 -> via (66.3, 32.0) -> band 32.45 -> C x 27.0 -> y 25.27 -> x 14.12 -> y 23.35 -> B (grid) -> (9.25, 44.6) | 104.5 |
| VTAP_TH | pure L6, lane 62.35 to the R380 / R381 link | 23.67 |

### Power (board_power.py)
Keep-free on L3 for all power copper: A (0..31, 21.5..24.6), B (0..12.5, 24.6..48), C (26..31, 24.6..33.5) plus access paths
A_N (14.8..31, 18.6..21.5), A_W (0.3..2.6, 18.95..21.5), A_V (14.8..16, 15.7..18.6), D (12.5..26, 24.6..25.7) and the explicit
slow-line copper (`SLOW_RESERVED` from `board_slow.reserve()`); corridor zones subtract them, branches / maze / via sites avoid them.
| rail | path | maze mm | narrowest |
|---|---|---|---|
| +1V2 | L3 corridors power block -> FPGA | 10.4 | 0.8 |
| VBUS | L3 band y 26.8 x 88 -> 32.4, 3-via array, L6 1.5 mm hop across channel C to L404.2 / C418.1, choke column + J501 by maze (L6) | 70.1 | 1.2 |
| +5V / -5V | L3 corridors along the top edge, maze in the analog block | 98.5 / 101.9 | 0.5 / 0.6 |
| +2V5 | L3 band y 23.2 (x >= 32), east loop y 50.8 to U701, rest maze (L3 / L6) | 357.7 | 0.3 |
| -2V5 | L3 band y 25.0 (x >= 32), mcuif run y 47, rest maze | 275.1 | 0.3 |

### Shortfalls / open points
- Minor rails are routed tracks, not planes; +/-2V5 maze pieces go down to 0.3 mm (the last-resort width added for them),
  +5V 0.5, -5V 0.6, VBUS 1.2 at its narrowest (no VBUS below 1.0 mm).
- **Deviation:** apply_rest treats area B and strip A west of x 12.5 / south of y 23.6 as passable on L3 (keeping clear of the
  routed DAC_TRIG / TRIG_SEL), because L6 there is walled by the front end's own tracks; the trunk stage keeps A, B, C closed.
- GND vias beside signal vias: 36 placed (second pass at 0.12 mm clearance, 0.05 mm search grid); 4 still without one within
  1.5 mm: (86.4, 27.2) USB_DP hop, (4.6, 41.0) DAC_TRIG, (71.0, 47.1) TRIG_SEL mcuif, (1.0, 19.2) VOFS (no free spot: block
  copper / pads / power corridors on some layer everywhere in the ring). Stitching now also keeps out of the L3 power corridors.
- Hand fixes in gen_board.py: dead +2V5 block via (11.1, 23.85) removed; R737.2 GND tied by a B track to R729.2 (its pour neck
  no longer fills); explicit +2V5 L3 stub into the corridor at U701's via (29.88, 49.3); the +2V5 join into C305.2 re-entered
  horizontally.
- Renders (L1-L6, all, three details) and board_power_plan.png regenerated from this board and looked at; L3 shows the
  slow bundle under the comparators, up channel C and along strip A; L6 shows the VBUS hop and long maze joins of the minor rails.
- Unchanged open design points: strobe lines load to about 41 R against 49.9 R terminations; effective tap spacing 30 ps;
  pstrobe input legs equal-length but not mirror images; TAP8 / TAP9 with a short L1 hop; USB pair with four layer changes.

### Previous status (third pass, superseded)
**Status (22 Nov 2026, third integration pass):** 100.0 x 57.0 mm, 4 x M3 3 mm in from the corners, JLC06161H-3313
(L1 signal / L2 GND / L3 slow + minor-rail corridors / L4 +3V3 / L5 GND / L6 signal). Every block is a native six-layer
file (merged with `layer_map=None`). **Every fast / RF / inter-block digital net is routed** by explicit coordinates in
`gen_board.py` (no auto-router). **Not routed:** the nine slow bias / control lines (VBIAS_A, VBIAS_K, VOFS, VNEG_REF,
DAC_TRIG, VTAP_TH, ADC_REF_MID, TRIG_SEL, ADC_IN; TOPOLOGY.md section 8 plan, see below) and whatever the L3 / L4
power module `board_power.py` (second agent, work in progress) leaves open.

Flow: `python3 gen_board.py` (~6 min; `--nofinish` stops after the signal routes and writes the scratch `routed.kicad_pcb`):
merge -> L1 / L6 routes -> planes (`board_finish.planes`, L2 / L3 / L5 / F / B GND) -> `board_power.apply` (L4 +3V3 and
the L3 rail corridors) -> `board_stitch.stitch` (GND vias) -> silk -> fill -> rule-10 check -> check_board. Then
`tools/run_drc.sh --rules jlc4 --parity layout/board/scope-fe.kicad_pcb`. Renders `scope-fe-L1.png` ... `L6`, `scope-fe-all.png`,
`scope-fe-detail-analog.png`, `scope-fe-detail-fpga-south.png`, `scope-fe-detail-mcu.png` (3600 px).

## Block / schematic changes (22 Nov)
- **power, mcuif, phase** converted to native 6-layer (`BL_STACKUP=6L`). USB pair 90 R on 0.0994 mm: power w 0.18 / s 0.22
  (89.1 R), mcuif w 0.19 / s 0.31 (89.7 R). Phase: VTAP strips on In3 in the block (the board module replaces them),
  **VTH rail on L1** under the comparator bodies (centre line, pins 2 / 4 by inward stubs; vias only at U308 pin 4 / U309
  pin 2 where the B-side R380 / R381 divider joins); **U309-U312 outputs on vias under the bodies** (y 27.0); U309's cap GND
  via and pin-5 GND via and U310's cap vias moved out of the drop area; C355's GND via moved west; C301 / C306 on B and the
  north-strip F pour keep-out removed (PH_STROBE path, top pour restored); VTAP_N / VTAP_P B feed columns removed.
- **fpga:** S edge order `COARSE | TAP0..7 | DBG2 TCK TMS TDI TDO | MCU_CLK CS SDA DONE MOSI MISO SCK SCL RECONFIG ADC_TRIG |
  TAP15 ... TAP8`; S_STROBE_P / _N exits 1 mm lower so they abut the analog interfaces (one straight-plus-jog L1 line, no
  via on P); PH pair below the S_STROBE_P exit, P = N = 16.181 mm in the block.
- **schematic** (`kicad/gen/gen_fpga_clock.py`, `gen_all.py` assertions, `kicad/README.md`): TAP15..TAP8 on U501 pins
  9, 10, 11, 13, 14, 15, 16, 17; PH_STROBE_P / _N on pins 39 / 40 (swapped). `gen_all.py`: 0 failed checks, 0 single-node nets.
  (A TAP9 / TAP8-between-JTAG-and-MCU permutation was tried and reverted: its L1 escapes cross the fpga's DONE / RECONFIG
  L1 runs and their L3 detour hits the via cluster at fpga local (4.3-4.9, 13.9-15.6).)

## Routes as built (net, layer, lane / corridor, length mm)
| group | layer | lane / corridor | mm |
|---|---|---|---|
| S_STROBE_P / _N | L1 | fpga W and analog E stubs abut | (6.06 / 12.23 in fpga) |
| BUF_OUT_T | L1 0.16 | analog S (15.75) -> y 22.35 -> phase N (8.79) | 11.76 |
| PH_STROBE_P / _N | L1 0.16 | fpga W y 21.85 / 22.19 -> y 22.85 / 23.21 -> pstrobe N (10.00 / 10.60, 25.00), 2 bumps on N | 48.388 / 48.388 |
| COARSE | L6 0.11 | lane y 20.90 north of TAP0, y 22.45 under the analog south row | 54.66 |
| TAP0..TAP7 | L6 0.11 / 0.11 | west staircase lanes y 21.12 + 0.22 k -> comparator vias y 23.92 | 32.67 31.75 24.35 23.43 16.02 15.30 8.09 10.77 |
| JTAG (DBG2, TCK, TMS, TDI, TDO) | L6 | slots 62.5-64.5 straight south, west on a band y 24.75-25.95 under U305-U308, tap-row lanes x 39.46 / 39.76 / 43.97 / 44.27 / 48.64, 45-degree jogs onto J501 (37.55 ... 47.72, 45.0) | 50.6 51.8 48.6 48.7 44.6 |
| MCU group (10) + TAP15..TAP10 | L6 0.11 / 0.25 pitch | fan-in to the drop column x 68.10-71.85 in the gap U309 / U310, highway y 29.35 (TAP10) ... 33.10 (MCU_CLK); TAPs peel north to the under-body vias (TAP10 / 11 U310, 12 / 13 U311, 14 / 15 U312); MCU group south in tap-row lanes 9 (71.21), 10 (75.47-75.97), 11 (79.81-80.51), 12 (84.62 / 84.87), jogs onto the mcuif interfaces | 33.4 ... 41.7; TAP 12.9-35.9 |
| TAP8 / TAP9 | L6 + L1 | from the eastmost slots (73.5 / 73.0) a via right below the fpga edge, then L1 west along y 22.75 / 23.15 over the L6 fan (L2 below) straight into U309 pads 7 / 6 | 11.7 / 10.7 |
| USB_DP / USB_DM | L1 then L6 | L1 from the power stubs east (y 23.25 / 22.85) and south in the gap U311 / U312 (x 86.4 / 86.8) across the highway band, vias (86.4, 31.06) / (87.39, 31.45), L6 diagonal between the GND via (88.09, 31.41) and the VTAP_N via (88.09, 33.66) into tap-row lane 13 (89.0 / 89.4), vias by the mcuif edge, L1 into the mcuif stubs | about 27.3 / 27.4 |
Rule check of the drawn geometry: 0 same-layer crossings, 0 clearance, 0 corners > 45 degrees (check_board). Ground vias
beside every inter-block signal via (stitching module; the highway-end USB pair uses the phase GND via at (88.09, 31.41)).

## Not done / open (ranked)
1. **Slow bias / control lines: 1 of 9 routed (VTAP_TH, pure L6 up lane 7 to the R380 / R381 link).** With the power
   trunks placed first (`board_power.apply_trunks`, as decided), the L3 VBUS trunk runs y 24.7-27.45 from x 22.5 to 87 and
   loops round the pstrobe block (west leg x 4.5-6, y 22-50; along y 21.95-23.45 for x 9-22.5; bottom y 50-51.5 to J501),
   and the +5V / -5V trunk runs y 19.95-20.7 from x 20.5 to 63. Every analog-side target (ADC_REF_MID (21.65, 20.8),
   ADC_IN (19.06, 20.0), VBIAS_K (16.4, 20.3), VBIAS_A (15.4, 16.3), VOFS (1.0, 19.2), VNEG_REF (1.94, 19.2)) lies north of
   VBUS, and DAC_TRIG (4.6, 41.0) / TRIG_SEL (9.25, 44.6) lie on / inside the VBUS loop; the only L3 gap left between the
   two trunks at x 20.5-22.5 is 0.65 mm. An L6 crossing exists only at x 32.0-34.2 (between U305 and U306) with via spots
   (32.15, 23.0), (32.85, 23.6), (33.5, 23.0), (34.15, 23.6), but north of it the same 0.65 mm gap blocks. `board_slow.py`
   removes a line it cannot finish (no dangling copper). Needed from the power module: a >= 3 mm L3 gap in VBUS and the
   +5V / -5V trunk around x 15-24, y 19-24.5, and a gap in the VBUS loop near x 6-10, y 44-46 for DAC_TRIG / TRIG_SEL.
   (Without the trunks, 5 of 9 were routed - see the history.)
2. Power (second agent's `board_power.py`): its current output is reported verbatim below; the rail corridors are its job.
3. TAP8 / TAP9 use an L1 hop (two vias per net, over L2 ground) - the only fast nets with a section on L1.
4. Phase still has the old open points (strobe lines load to about 41 R against 49.9 R terminations; effective tap spacing
   30 ps (39.4 / 69.4 ps per tap)); TRIG_SEL pull-down R737 = 2.0 k kept; S_STROBE_N two-via termination path accepted;
   pstrobe A / K legs equal length, not mirror images. FPGA_DONE runs on L3 inside the fpga block (static config line,
   excluded from the L3 fast-net check).

## Check results (last run, verbatim)
Order in gen_board.py: blocks -> signal routes -> planes -> `board_power.apply_trunks` (VBUS, +5V, -5V) -> `board_slow` ->
stitching -> silk -> routes.json -> `board_power.apply_rest` (last) -> fill -> checks.
- check_board: `missing 0, extra 4 (H1-H4), footprint 0, value 0, pad-net 0, nets with unrouted connections (after fill) 11,
  clearance < 0.1 mm 0, track corners > 45 deg 0, tracks leaving a pad off-axis 1 (R737.1), RF 0, courtyard 0,
  unconnected items 25`. Unrouted signals: the 8 slow lines above. Unrouted supplies after apply_rest: +2V5 (6), -2V5 (9)
  (power module, reported to the power agent); VBUS, +5V, -5V complete.
- rule 10: `fast-net segments on L3: 0`; `L1/L6 samples 8170, without filled GND on L2/L5: 449` = 417 via antipads + 25 PTH
  antipads + 7 deliberate L2 windows; **0 real plane holes**; L4 `+3V3` one polygon.
- Stitching: 27 GND vias beside inter-block signal vias (0.7-1.5 mm), 5 without room within 1.5 mm: (73.0, 23.25) TAP9 hop,
  (4.6, 41.0) DAC_TRIG, (71.0, 47.1) TRIG_SEL mcuif, (16.4, 14.47) VBIAS_K, (1.0, 19.2) VOFS; 12 RF fence vias, 323 grid vias.
- DRC jlc4 + parity: `total 504: error 24, warning 480` = 24 unconnected_items (the unrouted nets above); 0 clearance,
  0 crossing, 0 shorting, 0 hole errors. Warnings: 199 'Note' field, 199 + 12 library version, 30 DNP (KiCad 7),
  14 via_dangling + 12 track_dangling (stub ends of the unrouted slow lines and supply vias), 10 net_conflict
  (TL401-403, J601 shell), 2 silk_over_copper, 2 silk_overlap.
- ERC (re-run): `total 18: warning 18` (9 footprint_link_issues, 9 lib_symbol_mismatch), 0 errors.
- Renders looked at (L1-L6, all, three details): signal routing as intended; L2 / L5 solid apart from the deliberate
  windows; L3 shows the power corridors and no slow lines; the top pour stays out of the phase front column (x 0-9.5,
  deliberate block keep-out).

## History (short)
21 Nov: a 4-layer attempt and a first six-layer pass were auto-routed and failed on same-layer crossings at the fpga south
edge (TOPOLOGY.md written from that). 22 Nov: explicit routes; block, schematic and pin-order changes above.

## boardlib API

Netlist:
- `netlist()` returns a cached `Netlist`. Its fields are `comps {ref: {value, footprint "lib:name", sheet "/input/"}}`, `pads {(ref, pad): net}` and `nets {net: [(ref, pad)]}`.
- `net_of(ref, pad)` returns the net of one pad.
- `canon(name)` turns a short or verbatim net name into the verbatim netlist name. It raises KeyError if the name is unknown and ValueError if it is ambiguous.
- `Netlist.refs(sheet=None, prefix_digit=None)` lists refs.

**Canonical net name = netlist name verbatim**, for example `/BUF_OUT_S`, `/input/VIN`, `/trigger_phase/CMP_P`, `GND` or `Net-(C106-Pad2)`. This is what KiCad's
"Update PCB from schematic" writes. Scripts may pass short names (`"BUF_OUT_S"`, `"CMP_P"`). Auto-named nets go through `net_of()`.

Stack-up:
- Constants `H, T_CU, ER, ...`. Functions `microstrip(w)`, `cpwg(w, g)`, `width_for(z)`, `ps_mm(w)`, `c_per_mm(w)`, `loaded(tdu, z, cl)` and `solve_tdu(z, cl, td)`, copied from the phase_trigger fragment.
- `W50 = 0.36` (50.0 R, 6.057 ps/mm), `W73 = 0.16`, `W_LIN = 0.25`, `GAP_RF = 0.72`.
- `setup_board(b)` sets the layers, JLC rules (0.1 mm, via 0.45 / 0.2) and the aux origin. `save_board(b, path)` saves and inserts the stack-up block.

Footprints:
- `load_footprint(board, "lib:name")` loads from `/usr/share/kicad/footprints`, or from `FP_CUSTOM` if the id is registered there. The FPID is set to the netlist's lib:name.
- `FP_ALIAS` lists the library footprint for every special part: BUF802 RGT, TMUX136 RSE, TRF37D73 / TLV3801 DSG, SMA edge launch, balun, GW1NZ and others. All 454 netlist footprints exist in the library.
- `FP_CUSTOM` holds the fragment-defined lands: `board:CMC_0805_balun_fragment`, `board:NetTie_stub_short` and `board:IF_pad`.
- `build_footprint(board, name, pads, crt, copper)` creates new lands.

`Block(name)` is the builder for a block script. Local mm, origin (0, 0) = block top-left, stored at pcbnew (100, 100) as the aux origin. Methods:
- `place(ref, x, y, rot=0, side="F"|"B")`: the footprint, value and **every pad net come from the netlist**. A script cannot assign a net.
- `pad(ref, num)` returns local xy. `num` = `"@NET"` selects a pad by net.
- `track(net, w, pts, layer, name=, z=, ch=0.2)`: a polyline whose points may be `(ref, pad)`. Every corner sharper than 45 deg is cut by 45-degree chamfers, and the method **raises** if a sharper corner remains.
- `route_len(name)` returns the length of a named route.
- `tline(ref, pts, w)`: copper-only netlist parts TL401-TL403 (no library footprint). Pad 1 = start, pad 3 = end, net-tie copper. Returns `(pts, length)`.
- `via(x, y, net, dia, drill)` and `via_pair(...)`.
- `zone(net, layers, pts, clearance, prio, thermal=False)`.
- `keepout(pts, layers)`.
- `rf_keepout(pts, w, gap=2w)`: pour keep-out around an RF polyline.
- `line()`, `edge_rect()`, `circle()`, `text()`.
- `iface(net, x, y, layer, side "N|E|S|W", cls "rf50|pair|slow|supply", width, note)`.
- `save(dir)` writes `<name>.kicad_pcb` (with stack-up) and `<name>.ifaces.json`.

`check_board(pcb_path, refs=None, rf_widths=None, rf_gap=True, fill=True, clearance=0.1)`:
- `refs` is an iterable or a predicate; the default is all 454 parts.
- It prints a report and returns counts for:
  - `missing`, `extra`, `duplicate`
  - `footprint` (lib:name), `footprint_nolib`, `value`
  - `pad_net`, `pad_net_short` (differs only by the /sheet/ prefix), `pad_nonet`, `pad_missing`, `pad_unknown`
  - `unrouted` (own union-find over pads, tracks, vias and filled zone islands after zone fill), plus `unconnected_items` (pcbnew)
  - `clearance` (< 0.1 mm, tracks / vias / pads of different nets, grid-bucketed)
  - `corner` (track joint > 45 deg, joints inside a pad excused), `pad_axis` (track leaving a pad off its axes)
  - `rf_width` (vs `{net: w}`) and `rf_gap` (filled F.Cu pour of another net within 2 w of an RF trace edge)
- `["details"]` holds the item lists.

`merge(master_board, block_pcb, dx, dy, rot_deg=0, flip=False, skip_edge=True, skip_planes=False, origin=None, ref_map=None)`:
- It moves the footprints, tracks, vias, zones and drawings of a block file into the master.
- The block origin (its aux origin, else the top-left of its Edge.Cuts) is flipped left-right if requested, rotated CCW about itself, and placed at master-local (dx, dy).
- Nets are mapped by name. `skip_planes` drops the block's In1 / In2 zones.
- `new_master(w, h)` makes an empty board with the outline and 4 M3 holes 3 mm in.

`render(pcb, out_png, layers, crop=(x0, y0, x1, y1) pcbnew mm, mirror=False, tmpdir=)` runs `kicad-cli pcb export svg` and then `kicad/gen/svg2png.js` (3200 px). Write renders to the scratch directory and LOOK at them.

## Conventions for block scripts

1. Each block gets one directory with one script: `blocks/<block>/gen_<block>.py`, where block is analog, phase, pstrobe, fpga, power or mcuif. The script writes `<block>.kicad_pcb`, `<block>.ifaces.json` and
   `<block>.png` next to itself, and prints its own tables. Run it with `cd blocks/<block> && python3 gen_<block>.py`.
2. The script starts with `sys.path.insert(0, "../..")` and `import boardlib as bl`, then calls `blk = bl.Block("<block>")`. Only `blk.place` creates parts, so refs, values, footprints and nets
   come from the netlist. Do not create interface pads (`X1`, `IF1`) or test headers that are not in the netlist. Use `blk.iface()` for interfaces.
3. Units are mm. The local origin is the top-left of the block rectangle in `FLOORPLAN.md`, with +y down. Rotation is 0 for all six blocks, so local = board - (x, y) of the
   block. Draw the block rectangle on `Dwgs.User`, not on Edge.Cuts: blocks have no Edge.Cuts. Keep everything inside the rectangle, except
   interface stubs that end exactly on the iface point.
4. Layout rules (mandatory, from the user review):
   - Every RF trace has its computed width over its whole length (`bl.W50` etc.) and is listed in a `RF = {net: w}` table for check_board.
   - The pour gap is >= 2 w (`rf_keepout`). Critical RF stays on F.Cu without vias.
   - Supplies use planes, polygons, pad-wide copper and via pairs at the decoupling capacitor.
   - No 90-degree corners (`track()` enforces this). Tracks leave pads along the pad axis.
   - Mirror-symmetric structures are generated by one function with a mirror argument.
   - Meander same-net gaps are >= 0.5 mm.
   - Bias tees follow `sim/bias_tee/RESULT.md`.
   - The SMA to divider distance is 0.89 mm.
   - RF and analog parts go on top. Decoupling, bulk, power and slow parts may go on B.
5. At the end, each block script must call `bl.check_board("<block>.kicad_pcb", refs=<its refs>, rf_widths=RF)`. It must show 0 missing, 0 extra, 0 footprint, 0 pad_net,
   0 pad_nonet, 0 clearance and 0 corner. `unrouted` may only list nets that cross the block boundary (each one has an iface).
6. Then render with `bl.render(...)` and look at the PNG.

Block membership: refs 1xx / 2xx / sampler-strobe 4xx form analog. The full list is printed by `floorplan.py` (`membership()`).

