# layout/board: scope-fe integrated board (six layers), as built 25 Nov 2026 (BOM-2)

One full run of `python3 gen_board.py` (about 115 s; `--prepower` stops before the supplies, `--powonly` after them; `--fast`
is still broken) builds `scope-fe.kicad_pcb` / `.kicad_pro` / `routes.json`. Renders: `python3 render_board.py` (boardlib `render`, refilled
copy): `scope-fe-L1.png` ... `L6`, `scope-fe-all.png`, `scope-fe-detail-{analog,fpga-south,mcu,power}.png`.

## As built 25 Nov 2026 (BOM-2 integration)
All six blocks were regenerated against the BOM-2 netlist, and the board was rebuilt with a full `gen_board.py` run.
The outline is unchanged (100.0 x 57.0 mm), and so are every block position and every interface.

**Front column fix.** The new diode-bridge switch first left the phase column's +2V5 / -2V5 vias unreachable by the
rail router (5 islands failed). Changes (TOPOLOGY.md section 11):
- **TRIG_SEL:** L3 via at (11.3, 23.85), then a 4.3 mm L6 piece to R386. The block's full-height L6 lane is removed.
- **DAC_TRIG:** swaps places with TRIG_SEL in the slow bundle. It is grid-routed east of a fence and enters only
  the column's south end.
- **-2V5:** L6 along x 9.4 (11.2 mm) and an L3 link (4.0 mm).
- **+2V5:** L3 from the Q301 via down the x 9.85 lane (15.9 mm) and to U302's via (10.6 mm). `widen()` grows these
  where room allows.
- **Phase block:** SW_SB now branches south of the U302 +2V5 via (gen_phase.py).

Slow lines: DAC_TRIG 92.5 mm, TRIG_SEL 81.6 mm (incl. the L6 piece 4.3).
Rails: +2V5 is 202 mm on L3 and 33 mm on L6, narrowest 0.25 mm over 15 mm (the explicit column feed, a few mA).
-2V5 is 206 / 31 mm, narrowest 0.3 mm over 8 mm. The minimum rail-to-signal gap in the column is 0.20 mm, to SW_S;
PH_STROBE is more than 0.3 mm away.

**Checks (25 Nov):**
- **check_board:** 0 missing, extra 4 (H1-H4), 0 footprint / value / pad-net, 0 unrouted, 0 clearance, 0 corner,
  0 off-axis, 0 RF width / gap, 0 courtyard, 0 unconnected (486 footprints, 3467 tracks, 1018 vias).
- **gen_board:** fast-net segments on L3 0; 370 L1 / L6 samples without L2 / L5, all antipads or listed windows
  (0 real holes); L4 +3V3 is one polygon.
- **via_in_pad:** FAIL 0 (23 near, 31 in listed exposed pads).
- **DRC jlc4 + parity:** 451 warnings, 0 errors, 0 unconnected.
  - New since 24 Nov: 1 silk_edge_clearance (D319 silk at the west edge, x 0.25).
  - Otherwise as before: field / library mismatches, 31 attribute (5 DNP: C631, D402, D403, D601, R122),
    10 net_conflict.
- **decap_audit:** 77 capacitors; D1 1, D2s 8, D2g 1 (was 3; C301 / C306 are gone), D2p 10.
- **GND stitching:** 44 of 81 fast vias have a GND via within 1 mm.

**Not redone:** the block `*_netview_*.png` crops (they show the 24 Nov board) and `phase_netview_u301.png`
(U301 no longer exists).

## As built (24 Nov 2026, new power tree)
Board 100.0 x 57.0 mm (unchanged), JLC06161H-3313: L1 RF / parts, L2 GND, L3 slow lines + minor rails, L4 +3V3, L5 GND, L6 buses.
Flow: merge blocks -> L1 / L6 signal routes -> planes -> slow lines (`board_slow.py`, explicit) -> block clean-up ->
supplies (`board_power.py`) -> widen -> GND stitching -> silk -> fill -> rule-10 check -> check_board.

**Supplies** (`board_power.py`, rewritten): L4 is one +3V3 plane (one polygon) plus the FPGA block's +1V2 island, joined to
the U602 output via (75.0, 7.9) by an L4 finger along the power block's west edge (x 73.2-75.65, y 7.35-15.2). Every other
rail is a set of TRACKS from its regulator via: a 0.1 mm grid router (L3, L6 at 3x cost + via cost) joins each copper island
of the rail to the tree at the widest width that fits (rail widths 1.2 / 0.8 mm first), keeping 0.18 mm to other copper
(Power netclass 0.15), 0.3 mm to slow lines, 0.5 mm to ADC_IN, a soft 0.6 mm keep-off around L3 cut-outs (node windows);
`widen()` then fattens each segment to the widest that fits (<= 1.5 mm +5V1, 1.0 mm others). Router copper only (block
copper excluded):

| rail | load | L3 mm | L6 mm | >= 0.5 mm | narrowest stretch |
|---|---|---|---|---|---|
| /+5V1 (GVA-84+ chokes) | 0.34 A | 86.5 | 5.8 | 100 % | 0.6 mm, 6.3 mm in total (choke joins in pstrobe, about 0.17 A each); trunk 0.8-1.5 mm |
| +5V | 41 mA | 125.8 | 0 | 100 % | 0.6 mm, 6.4 mm (x 12, y 10-16, BUF802 area) |
| -5V | 41 mA | 74.4 | 7.3 | 100 % | 0.6 mm, 57 mm (x 17-70, y 13-17) |
| +2V5 | 50 mA | 269.1 | 10.5 | 91 % | **0.3 mm, 26 mm** (x 10-12, y 26-49: the branch to U301 / C301 / C306 through the trigger front end, < 1 mA) |
| -2V5 | 50 mA | 204.6 | 24.6 | 100 % | 0.4 mm, 1.0 mm |
| VBUS (J501 pin 1 only) | programmer | 85.3 | 9.5 | 100 % | 0.6 mm, 85 mm |
| /VTAP_P, /VTAP_N | 12.5 mA | 78 / 119 | 21 / 43 | 95 / 100 % | 0.4 mm 4.9 mm / 0.6 mm |
IPC-2221 (10 K, inner 0.5 oz): 0.3 mm 0.27 A, 0.6 mm 0.45 A, 1.0 mm 0.65 A. Regulator input headroom: blocks/power/README.md.

**Slow lines** (`board_slow.py`, TOPOLOGY.md section 9 geometry, drawn before the supplies): all 9 routed (ADC_REF_MID
56.6, DAC_TRIG 90.0, VOFS 82.6, VBIAS_A 77.5, VBIAS_K 73.0, VTAP_TH 23.7, TRIG_SEL 104.5, ADC_IN 77.3, VNEG_REF 58.9 mm).
VBIAS_A's analog via moved to (15.4, 15.9) (the analog block's BUF_OUT_T moved).

**Validation items done at board level**
- PDN-2 type: U601 (0.30 W, hottest) GND polygon with 6 vias at the capacitor GND pads (TIGHTEN), shared with U602 (B).
- ZONES-3: L2 / L5 GND clearance 0.15 mm, min width 0.15 mm; fpga east-pin vias and TAP8-15 via rows staggered to
  >= 1.0 mm (blocks/fpga/README.md). Not feasible: the COARSE / TAP0-4 via stair (0.57 mm pitch) and the mcuif row.
- ZONES-4: GND via within 1 mm of 42 of 82 fast-net vias (validation: 22 of 72), incl. both S_STROBE_N vias (0.65 mm).
  The other 40 sit in the dense fpga fan-out, the TAP output vias and the mcuif row; no free spot within 1 mm there.
- DECOUPLING-5 / -6 (fpga block; C502 / C506 still share one GND via), DECOUPLING-8 (C602 moved to U608 pin 5), U603 /
  L601 compacted (switch nodes 1.9 mm).
- IO-3: not done (the schematic did not move CLK2 off pin 34).
- TIGHTEN (24 Nov, user review of the power render): decoupling capacitors at their pins, plane vias at the capacitors.
  U603: C601 / C610 courtyards on the chip's (0.0 mm), VBUS / +5V1 pad 0.93 mm from VIN / VOUT (was 2.0), GND pads
  returned to PGND on L1 through the channel between the pin columns; input / output hot loop 3.1 x 3.9 -> 1.9 x 2.8 mm
  (11.2 -> 2.8 mm2, now without plane vias in the loop); vias only behind the capacitors (none at the pins / under L601).
  U601 / U602: COUT under CIN (output loop 4.35 x 4.05 -> 4.0 x 2.7 mm), vias moved from the middle of the GND polygon to
  the capacitor pads, +3V3 vias behind C604 / C609. LM27762: GND vias at the CIN GND pads. Elsewhere (audit
  `decap_audit.py` over this board): analog U101 -5V rail via between pins 5 / 6 removed (via-only rule area over the pin
  row; the rail now lands on the vias behind C112), phase U310 C351 and mcuif C716 GND vias at the pads. At TIGHTEN every
  primary capacitor passed D1 / D2s / D2g except C621 (then on B; on F since REPAIR); the 9 remaining flags were bulk /
  second capacitors placed off the pins by design (C507, C510, C616, C505 / C506, C711, C714, C306, C717).
  Audit of the current board (after REPAIR, with the per-pin class D2p): 78 capacitors, D1 1 (U101.6 / C116 on B: pins
  5 / 6 share C112 on top), D2s 8, D2g 3, D2p 10; the D2p / D2s cases at the primary capacitors are the ones listed under
  REPAIR (RF2-3) plus U501.25 / .36 (C505 / C506) and U502.1 (C509), see docs/VALIDATION.md.
  Review renders: `net_view.py` (net-coloured copper, vias, courtyards), e.g. blocks/power/power_netview_*.png.

**REPAIR (24 Nov, independent re-check docs/validation/recheck-*.md)**
- RP-1: LM27762 output capacitors C617 / C621 / C630 / C628 moved from B to the IC layer at OUT+ / OUT- (no vias between
  pin and capacitor, rail vias behind them); dividers rearranged (blocks/power/README.md). +5V / -5V sources moved to
  (82.05, 7.0) / (74.4, 13.6).
- RF2-1: U301 pin 10 (+2V5) fed through a 0.4 mm via beside pin 9 and a B track to C301 / C306: no +2V5 copper or via
  beside BUF_OUT_T any more (was 0.105 mm via edge), L2 solid under the trace.
- RF2-5: TAP5 via 0.15 mm east, 0.4 mm: its antipad stays 0.03 mm clear of PH_STROBE_N's edge (L2 solid under it).
- RF2-3 (vias at the IC pins): U704 pin 24 via now north of C712; U502 pin-1 end of the VDDO link lands at C623;
  U101 pin 8 polygon starts at C113 (vias east of C113, not at the pin end). `decap_audit.py` has a new class D2p
  (via nearer the pin than any capacitor pad of the net, per pin). Remaining D2p, kept: U101.1 / .12 and U501.1 (vias
  join a polygon / tracks that end in the capacitor pad: cap first in the copper path), U704.36 (R727 I2C pull-up feed,
  not a decoupling via), U704.48 / .1 (inner via is C710's (B) via; no room behind C713: bus track north, pins east /
  south), U502.7 (C508 boxed in by the CLK2 track), U310.8 (the L6 fan-in west of C351), U604.3 (EN+ tie via); U201.5 (not in the re-check list, not examined).
- board_power.widen(): exact distance check to foreign vias / tracks (raster missed a /+5V1 interface via), shrinks a
  rail segment that would violate the netclass gap (+2V5 0.8 -> 0.6 mm at (87.1, 20.3); /+5V1 0.5 -> 0.4 mm at two
  pstrobe choke joins).
- RF2-6: the rail router keeps 0.15 mm extra from fast / clock / strobe / comparator nets (rail edge >= 0.33 mm on
  L3 / L6; the VTAP_N / MCU_CLK, +2V5 / PH_STROBE_N and VTAP_N / U310A+ cases are gone). Left: block pin necks at the
  FPGA (+3V3 / TAP8 0.155 mm, +1V2 / S_STROBE_P and +3V3 / S_STROBE_N 0.22 mm, set by the 0.5 mm pin pitch).
- RF2-9: schematic DNP parts (C631, D402, D403, R122) are excluded from the pos file by gen_board.
- floorplan.PLACED_IN: C606 / C614 / C616 / C622 / C402-C409 -> analog, C615 / C620 / J102 / R122 -> phase, J501 / R511 /
  R512 -> mcuif.
- RF2-4: superseded by 'Vias out of pads' below (no plugged vias are ordered).
- Net-view crops: blocks/power/power_netview_lm27762*.png, blocks/phase/phase_netview_u301.png,
  blocks/analog/analog_netview_u101.png, blocks/mcuif/mcuif_netview_u704.png, blocks/fpga/fpga_netview_{u502,tap5}.png.

**Vias out of pads (24 Nov, user decision: no plugged / capped / filled vias; RULES.md rule 12)**
Standard JLCPCB six-layer order, ordinary tented vias. `via_in_pad.py` (run by gen_board.py, also per block) lists every
via whose hole is < 0.15 mm from a soldered SMD pad (copper, mask or paste opening; JP solder jumpers count as soldered)
or whose ring reaches into a mask opening: board FAIL 0 (was 88 pad hits), 30 legal at 0.15-0.2 mm. Fixed in the
generators: pstrobe (C413 / C423 10 uF re-placed off the 0402 GND vias, their +3V3 via pairs moved north; C430 / C420 bulk
and C434 / C435 GND vias, K-chain GVA tab vias clear of C430; 19 vias), phase (J102 GND rows moved out of the pads to
the pad edges, 12 vias; U302 EP vias -> one via at the EP end; VSW via, C310, U304 pins 4 / 5, TP304 off R377 pad 1;
16 vias), fpga (C502 / C506 GND via, one shared +3V3 via for R502-R504, router vias kept 0.31 mm off every SMD pad: 6),
power (LM27762 EP vias, U608 GND, U605 EN-: 6), mcuif (U701 pins 2 / 3, R728: 3), analog (C209 moved, 0 vias), board
(rail router: no via within 0.33 mm of an SMD pad, e.g. +5V at FB604, VTAP_P at R334; board_slow keeps TRIG_SEL on its
east route past U301 / U302). Exposed pads, decided per part (allowed list `EP_ALLOW`, 32 vias, all 0.45 / 0.2 mm,
wholly inside the pad, tented on the far side; solder fills some of the 0.2 mm holes, the paste windows cover this):
| part | decision |
|---|---|
| BUF802 U101 (RGT) | 4 vias in the EP kept: datasheet layout has thermal vias in the pad; 0.4 W and the GHz ground return |
| TRF37D73 U303, U401-U403, U405 (DSG) | 3 vias each kept: TI asks for ground vias in the thermal pad (RF ground at 2 GHz) |
| GVA-84+ U404 / U406 (SOT-89 tab) | 5 / 3 vias kept, moved wholly inside the tab: Mini-Circuits mounting layout has holes in the tab |
| GW1NZ U501 (QN48) | 5 vias kept: the EP is the die's only GND |
| TLV3801 U302 (DSG, EP = VEE) | vias removed from the EP (< 50 mW): 0.4 mm neck to one via 0.2 mm beyond the EP end |
| LM27762 U604 / U605 (WSON) | vias removed (a few mW): EP tied on L1 to GND pins 1 and 4, which reach the CIN GND via |
| TPS63802 U603, TMUX136 U301 | none in a pad (U603 grounded through its PGND pads and the capacitor vias; U301 has no EP) |
Net-tie pads NT401-NT403 keep their GND via: copper only, no mask and no paste opening (checked). Test points (TP104,
TP201, TP304, TP401, TP402; not soldered) keep vias in their pads.

**Checks (last run)**
- Last run 24 Nov 2026 after the BOM optimisation and the asymmetric +/-5V rails (SPEC decisions 25 / 26): values carried
  from the netlist into the analog, phase, power and mcuif blocks (footprints, positions and tracks unchanged, compared
  with the previous block files); pstrobe unchanged (the interim R419 / R420 GVA feed resistors were withdrawn).
- check_board: missing 0, extra 4 (H1-H4), footprint / value / pad-net 0, unrouted 0, clearance 0, corners > 45 deg 0,
  off-axis pad exits 0, RF width / pour gap 0, courtyard 0, unconnected 0 (477 footprints, 3411 tracks, 999 vias).
- gen_board checks: fast-net segments on L3 0; 372 L1 / L6 samples without L2 / L5 = 342 via antipads + 25 PTH antipads +
  5 deliberate windows, 0 real holes; L4 +3V3 one polygon; via-in-pad FAIL 0 (999 vias, 32 in listed exposed pads).
- decap_audit: unchanged (D1 1, D2s 8, D2g 3, D2p 10).
- DRC jlc4 + parity: `total 450: warning 450`, 0 errors, 0 unconnected: 199 field mismatch, 199 lib_footprint_mismatch,
  31 attribute (4 'Do not populate': the KiCad 7 board format has no footprint DNP flag; C632 is fitted now; 27
  exclude-from-BOM of TP / JP / NT footprints), 11 lib_footprint_issues, 10 net_conflict (TL401-403 / J601 shell).

**Open**
- +2V5 0.3 mm branch into the trigger front end (above); 52 router vias, i.e. about 26 short L6 sections (the 3-hop limit of
  TOPOLOGY.md section 8 is not kept: the router hops wherever L3 is not planar; each is a short track with a via at each end).
- The fpga COARSE / TAP0-4 via stair still forms an L2 / L5 slot; 40 fast vias without a GND via within 1 mm.
- No reference designators on silk (as before).


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


## History (short)
21 Nov: a 4-layer attempt and a first six-layer pass were auto-routed and failed on same-layer crossings at the fpga south
edge (TOPOLOGY.md written from that). 22 Nov: explicit routes; block, schematic and pin-order changes above. 24 Nov: new
power tree (blocks re-laid), supplies rewritten as routed tracks, validation fixes (section above).

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

