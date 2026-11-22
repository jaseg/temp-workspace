# layout/board: scope-fe integrated board (six layers) - signal routing complete except the nine L3 slow lines

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
1. **Nine slow lines (TOPOLOGY.md section 8): not drawn.** `board_slow.py` (planner: fixed layer sequence / via points,
   octilinear grid search per single-layer leg) exists but is NOT called by gen_board.py. Measured against the current
   board (after `board_power.apply`), the obstacles are:
   - L3: the +2V5 / -2V5 / VBUS corridors run across the board at y 22.7-23.6 / 24.5-25.4 / 26.3-27.2 from x about 5-26
     to 85-89, +2V5 turns north at x 28.3-28.7 (y 8.5-22.4), VBUS turns south at x 21.4-21.9 (y 27.5-47), -2V5 south at
     x 12.7-13.8 and x 4.4-6.0, and VTAP_N / VTAP_P run along the whole tap row (y 32.9 / 41.3). The only L3 space south
     of the corridors that the mcuif lines can reach is the channel y 27.5-32.4 (x 22-88), closed in the west by VBUS.
   - L6 crossings of the corridor band: COARSE (y 20.9, x 23.6-58; y 22.45, x 4.45-22.15), the TAP0-7 staircase, the JTAG
     band (y 24.75-25.95, x 39.4-64.5) and the MCU fan wall it off except a passage x 26.75-28.6 (between the comparator
     GND via (26.41, 23.07) and TAP0's drop x 28.98). Its south end lies under U305's pin 1 / 8 pads and the VTH1 rail
     start (28.68, 27.755), its north end between COARSE (L6, y 20.9) and the PH_STROBE pair (L1, y 21.85): vias fit only
     in y 21.28-21.45 there - room for about two lines, not six.
   - Tap-row crossing on L6: via spots in the channel exist only in lanes 5 (2 lines), 6 and 8 (one each, under U308 /
     U309 between the pad rows) and 7 (the VTAP_TH column); MCU_CLK's jog (lane 9 -> 73.35) encloses the ADC_IN / TRIG_SEL
     stubs (71.0 / 71.5): MCU_CLK must move to lane 10 first.
   - VOFS / VNEG_REF (analog x 1.0 / 1.94) and DAC_TRIG / TRIG_SEL (phase x 4.6 / 9.25) sit behind the -2V5 / VBUS
     verticals (pockets x 0-4.4 and x 6-21, y 33-50) with no L3 or L6 path from the mcuif.
   Needed (power module / lead): a 2-3 mm wide L3 gap in the corridor band near x 24-28 (or a slow channel along y 20-22
   west of x 28), a gap in the VBUS / -2V5 verticals at y 29-31 for the west group, then the plan above is drawable.
2. Power (second agent's `board_power.py`): its current output is reported verbatim below; the rail corridors are its job.
3. TAP8 / TAP9 use an L1 hop (two vias per net, over L2 ground) - the only fast nets with a section on L1.
4. Phase still has the old open points (strobe lines load to about 41 R against 49.9 R terminations; effective tap spacing
   30 ps (39.4 / 69.4 ps per tap)); TRIG_SEL pull-down R737 = 2.0 k kept; S_STROBE_N two-via termination path accepted;
   pstrobe A / K legs equal length, not mirror images. FPGA_DONE runs on L3 inside the fpga block (static config line,
   excluded from the L3 fast-net check).

## Check results (last run, verbatim)
- check_board: `missing 0, extra 4 (H1-H4), footprint 0, value 0, pad-net 0, nets with unrouted connections (after fill) 15,
  clearance < 0.1 mm 1, track corners > 45 deg 29, tracks leaving a pad off-axis 2 (C111.1, R737.1), RF width 0,
  RF pour gap 0, courtyard overlaps 0, unconnected items 17`. Unrouted: the nine slow lines plus +2V5 (1), +3V3 (1), +5V (1),
  -2V5 (3) and others of the power module. The clearance (VBUS / VREFP on B.Cu at (22.73, 48.60)), the 29 corners (VTAP_P /
  VTAP_N 90-degree joints, +2V5 / +5V joints) and C111.1 are in copper added by `board_power.py` (second agent); the signal
  routing of this file has 0 clearance, 0 corners, 0 crossings.
- rule 10: `fast-net segments on L3: 0` (FPGA_DONE excluded: static config line); `L1/L6 samples 8155, without filled GND on
  L2/L5: 449` = 417 via antipads + 25 PTH antipads + 7 deliberate L2 windows (tap pads / hold nodes); **0 real plane holes**.
  L4: `+3V3` one polygon. L5 solid except antipads.
- Stitching (`board_stitch.py`): 14 GND vias beside inter-block signal vias (6 signal vias without room within 1.1 mm),
  14 RF fence vias, 357 grid vias.
- DRC jlc4 + parity: `total 503: error 17, warning 486` = 16 unconnected_items (unrouted nets above) + 1 tracks_crossing
  (board_power.py's VBUS L6 feeder over the mcuif VREFP B track at (22.73, 48.60)); warnings 199 'Note' field, 199
  lib_footprint_mismatch + 12 lib_footprint_issues (library version), 30 DNP (KiCad 7), 18 track_dangling + 14 via_dangling
  (slow-line stubs and analog-side L3 vias waiting for their lines), 10 net_conflict (TL401-403, J601 shell), 2
  silk_over_copper, 2 silk_overlap.
- ERC (re-run after the schematic change): `total 18: warning 18` (9 footprint_link_issues, 9 lib_symbol_mismatch), 0 errors.
- Renders (all looked at): L1-L6, all, three details: staircase, JTAG band, drop column / highway / peel-offs, USB L1-L6
  hops and the PH pair as intended; L2 / L5 solid apart from the deliberate windows; L3 / L4 from board_power.py.

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

