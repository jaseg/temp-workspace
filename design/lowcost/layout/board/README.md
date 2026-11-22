# layout/board: scope-fe integrated board (six layers) - NOT FINISHED: 47 nets unrouted

**Status (integration, 22 Nov 2026, second pass; honest):** 100.0 x 57.0 mm, 4 x M3 3 mm in from the corners,
JLC06161H-3313 (L1 signal / L2 GND / L3 slow / L4 power / L5 GND / L6 signal). All six blocks merge with 0 missing /
mismatched parts, 0 courtyard, 0 corners. Every inter-block route is drawn by explicit coordinates in `gen_board.py`
(no auto-router). **42 nets are still unrouted** (list below); DRC errors are only `unconnected_items` of those nets.

Flow: `python3 gen_board.py` (~4 min; `--nofinish` stops after the routes and writes the scratch `routed.kicad_pcb`), then
`tools/run_drc.sh --rules jlc4 --parity layout/board/scope-fe.kicad_pcb`. Renders: `scope-fe-L1.png` ... `scope-fe-L6.png`,
`scope-fe-all.png` (3600 px), `scope-fe-detail-analog.png`, `scope-fe-detail-fpga-south.png`, `scope-fe-detail-mcu.png`
(re-rendered from the final board).

## Block and schematic changes in this pass
- **power, mcuif** -> native 6-layer (`BL_STACKUP=6L`, supply landings L4). USB pair: power w 0.18 / s 0.22 (pitch 0.40 kept,
  89.1 R), mcuif w 0.19 / s 0.31 (0.5 mm pin pitch, 89.7 R), microstrip over L2 0.0994 mm (IPC-2141). Both check_board 0
  (except plane-fed supplies; mcuif keeps the known R737.1 off-axis exit).
- **schematic** `kicad/gen/gen_fpga_clock.py`: TAP8..15 reversed on U501 pins 9, 10, 11, 13, 14, 15, 16, 17 (= TAP15 ... TAP8);
  PH_STROBE_P / _N swapped to pins 39 / 40. `gen_all.py` assertions added (TAP15 = 9, TAP8 = 17, PH_STROBE pins);
  `gen_all.py`: **0 failed checks**, 0 single-node nets. kicad/README.md pin table updated.
- **fpga** (`gen_fpga.py`): east slots TAP15..TAP8 (TAP8 eastmost); S_STROBE_P exit jogs 1.0 mm south in the W margin
  (one L1 line, no via) and S_STROBE_N's L6 hop ends 1.0 mm lower: both now abut the analog E interfaces (board y 10.865 /
  11.865); the PH pair (pin 39 = P outer) jogs below the S_STROBE_P exit; P = N = 16.181 mm. check_board 0 in every class.
- **phase** (`gen_phase.py`): C301 / C306 moved to B, their +2V5 via pair at x 11.1, U302's VCC run ends in its own via, so
  the F side above the pstrobe inputs is free. check_board 0 except plane-fed supplies and C306 GND (B pour on the board).
  Phase is still a 4-layer file (merged with LAYER_MAP_4TO6); its VTH rail is moved to L3 in gen_board.py.

## Routes as built (net, layer, lane / corridor, length mm)
| net | layer | lane / corridor | mm |
|---|---|---|---|
| VTH1 / VTH2 rail | L3 | y 28.92, x 28.98-58.61 / 65.10-94.72 (B kept only into R380 / R381) | 29.62 / 29.62 |
| S_STROBE_P / _N | L1 | fpga W and analog E stubs abut (no board route) | - |
| BUF_OUT_T | L1 0.16 | analog S (15.75) -> y 22.35 -> phase N (8.79) | 11.76 |
| PH_STROBE_P / _N | L1 0.16 | fpga W y 21.85 / 22.19 -> x 25 -> y 22.85 / 23.21 -> pstrobe N (10.00 / 10.60, 25.00); N has two 45-degree bumps h 0.574 | **48.388 / 48.388** |
| COARSE | L6 0.11 | lane y 20.90 north of TAP0, then y 22.45 under the analog south row | 54.66 |
| TAP0..TAP7 | L6 0.11 / 0.11 | west staircase lanes y 21.12 + 0.22 k, drop at the comparator vias y 23.92 | 32.67 31.75 24.35 23.43 16.02 15.30 8.09 10.77 |
| USB_DP / USB_DM | L6 0.18 / 0.22 (L1 stubs) | power S vias (82.6, 23.0) / (83.4, 23.0), east at y 23.45 / 22.8, gap U311-U312 x 86.25 / 86.65, jog to tap-row lane 13 x 89.0 / 89.4, vias near the mcuif edge; 3 GND vias beside | about 27.4 / 27.3 |
| VBIAS_A / VBIAS_K / ADC_IN / ADC_REF_MID | B -> L3 via | analog B columns end in L3 vias (y 16.3 / 20.3 / 20.0 / 20.8); the L3 runs are not drawn | - |
No two tracks cross on a layer; no corner > 45 degrees. Inter-block RF lengths: PH pair 48.388 mm each on the board (+16.181 in
the fpga, +30.512 in pstrobe to TRF pin 2), BUF_OUT_T 11.76 mm, S_STROBE_P 6.06 mm in the fpga.

## NOT placed (exact obstacles)
- **Middle group (DBG2, JTAG x4, MCU_CLK, SPI x4, I2C x2, DONE, RECONFIG, ADC_TRIG) and TAP8..TAP15**: U309 (x 63.5-68) lies
  directly under the MCU-group slots (x 65.0-69.5); its output vias (65.10 / 66.37, 23.92) and pin-5 GND via (67.64, 23.97),
  and U310's cap vias (70.85, 23.61 / 24.25), (71.55, 23.07) sit in the fan-in area; the comparator gaps are 4.4 mm
  (U308|U309 x 59.0-63.4 holds R380 / R381 / C354 / C355, GND vias (59.04 / 64.66, 27.0), the VTAP_TH B column x 61.93 and
  U309's cap vias (61.83, 23.61 / 24.25), (62.53, 23.07)). The buildable variant (TOPOLOGY.md section 7) needs under-body
  output vias for U309-U312, the divider moved, and the fpga slot order `... MCU | TAP9 TAP8 | TAP15..TAP10`, which requires
  re-routing the fpga's DONE / RECONFIG F runs (local y 18.1 / 18.5). Not done in this pass.
- **L3 slow lines** (VNEG_REF, VOFS, VBIAS_A/K, ADC_IN, ADC_REF_MID, DAC_TRIG, TRIG_SEL, VTAP_TH): not drawn (two-channel plan
  in TOPOLOGY.md section 7 discussion; mcuif re-ordering not done). VTAP_TH's phase B column (x 61.93) is still on L6.
- **L4**: only the +3V3 background zone (1 polygon) and the block islands (+1V2 under U501, VTAP_P / VTAP_N strips, 1 polygon
  each). +5V, -5V, +2V5, -2V5, +1V2 feed, VBUS islands and the VTAP_P / VTAP_N feeds from mcuif are NOT drawn.
- Stitching grid / fences: not added (only the GND vias beside the USB vias). Silkscreen: the old labels only.

## Check results (last run, verbatim)
- check_board: `missing 0, extra 4 (H1-H4), footprint 0, value 0, pad-net 0, nets with unrouted connections (after fill) 42,
  clearance < 0.1 mm 0, track corners > 45 deg 0, tracks leaving a pad off-axis 1 (R737.1), RF width 0, RF pour gap 0,
  courtyard overlaps 0, unconnected items 72`. Unrouted: the supplies (+1V2, +2V5, +3V3, +5V, -2V5, -5V, VBUS: no L4 islands),
  the middle group (15), TAP8..15, the L3 slow lines, VTAP_P / VTAP_N feeds, GND (1).
- rule 10: `fast-net segments on L3: 0` (FPGA_DONE excluded as a static config line); `L1/L6 samples 5207, without filled GND
  on L2/L5: 419` (samples inside via antipads, over the L2 pad cut-outs and the unrouted interface stubs); L4 zones: +3V3 1,
  +1V2 1, VTAP_P 1, VTAP_N 1 polygon (no other rail islands exist yet).
- DRC jlc4 + parity: `total 640: error 71, warning 569` = 71 unconnected_items (the unrouted nets); warnings 199
  footprint_symbol_field_mismatch ('Note'), 199 lib_footprint_mismatch + 12 lib_footprint_issues (library version), 59
  via_dangling + 56 track_dangling (stubs / vias of the unrouted nets, plane-fed supply vias), 30 footprint_symbol_mismatch
  (DNP; KiCad 7 cannot store it), 10 net_conflict (TL401-403 GND pins, J601 shell), 2 silk_over_copper, 2 silk_overlap.
  0 clearance, 0 shorting, 0 crossing, 0 hole errors.
- ERC (tools/run_erc.sh, after gen_all): `total 18: warning 18` (9 footprint_link_issues, 9 lib_symbol_mismatch), 0 errors.

## Open design points (not changed)
Phase strobe lines load to about 41 R against 49.9 R terminations; effective tap spacing 30 ps (39.4 / 69.4 ps per tap).
TRIG_SEL pull-down R737 = 2.0 k kept. S_STROBE_N two-via termination path accepted. pstrobe A / K legs equal length, not mirror.
FPGA_DONE runs on L3 inside the fpga block: static config line, allowed (excluded from the L3 fast-net check).

## History (short)
4-layer attempt and a first six-layer pass (21 Nov) were auto-routed and failed on same-layer crossings at the fpga south edge;
TOPOLOGY.md was written from that. 22 Nov: explicit routes, block / schematic fixes above, blockers recorded.

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

