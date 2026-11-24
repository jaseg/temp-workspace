# layout/board: scope-fe integrated board (six layers), as built 24 Nov 2026

One full run of `python3 gen_board.py` (about 80 s; `--prepower` stops before the supplies, `--powonly` after them; `--fast`
is still broken) builds `scope-fe.kicad_pcb` / `.kicad_pro` / `routes.json`. Renders (`render` helper of boardlib, refilled
copy): `scope-fe-L1.png` ... `L6`, `scope-fe-all.png`, `scope-fe-detail-{analog,fpga-south,mcu,power}.png`.

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
- DECOUPLING-5 / -6 (fpga block), DECOUPLING-8 (C602 moved to U608 pin 5), U603 / L601 compacted (switch nodes 1.9 mm).
- IO-3: not done (the schematic did not move CLK2 off pin 34).
- TIGHTEN (24 Nov, user review of the power render): decoupling capacitors at their pins, plane vias at the capacitors.
  U603: C601 / C610 courtyards on the chip's (0.0 mm), VBUS / +5V1 pad 0.93 mm from VIN / VOUT (was 2.0), GND pads
  returned to PGND on L1 through the channel between the pin columns; input / output hot loop 3.1 x 3.9 -> 1.9 x 2.8 mm
  (11.2 -> 2.8 mm2, now without plane vias in the loop); vias only behind the capacitors (none at the pins / under L601).
  U601 / U602: COUT under CIN (output loop 4.35 x 4.05 -> 4.0 x 2.7 mm), vias moved from the middle of the GND polygon to
  the capacitor pads, +3V3 vias behind C604 / C609. LM27762: GND vias at the CIN GND pads. Elsewhere (audit
  `decap_audit.py` over this board): analog U101 -5V rail via between pins 5 / 6 removed (via-only rule area over the pin
  row; the rail now lands on the vias behind C112), phase U310 C351 and mcuif C716 GND vias at the pads. Every primary
  capacitor now passes (0 D1 / D2s / D2g) except C621 (B, GND via 1.15 mm); the 9 remaining flags are bulk / second
  capacitors placed off the pins by design (C507, C510, C616, C505 / C506, C711, C714, C306, C717).
  Review renders: `net_view.py` (net-coloured copper, vias, courtyards), e.g. blocks/power/power_netview_*.png.

**Checks (last run)**
- check_board: missing 0, extra 4 (H1-H4), footprint / value / pad-net 0, unrouted 0, clearance 0, corners > 45 deg 0,
  off-axis pad exits 0, RF width / pour gap 0, courtyard 0, unconnected 0.
- gen_board checks: fast-net segments on L3 0; 371 L1 / L6 samples without L2 / L5 = 341 via antipads + 25 PTH antipads +
  5 deliberate windows, 0 real holes; L4 +3V3 one polygon.
- DRC jlc4 + parity: `total 451: warning 451`, 0 errors, 0 unconnected: 199 'Note' field, 199 lib_footprint_mismatch,
  32 DNP attribute, 11 lib_footprint_issues, 10 net_conflict (TL401-403 / J601 shell, as before).

**Open**
- +2V5 0.3 mm branch into the trigger front end (above); 52 router vias, i.e. about 26 short L6 sections (the 3-hop limit of
  TOPOLOGY.md section 8 is not kept: the router hops wherever L3 is not planar; each is a short track with a via at each end).
- `floorplan.membership` still lists C606 / C614-C616 / C620 / C622 under power (the blocks override it).
- C602 now sits at U608 (kicad/README.md still describes it as U601's HF input capacitor: schematic owner).
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

