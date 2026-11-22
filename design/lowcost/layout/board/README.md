# layout/board: scope-fe integrated board (six layers) - NOT FINISHED: 47 nets unrouted

**Status (integration pass 22 Nov 2026, honest):** 100.0 x 57.0 mm, 4 x M3 3 mm in from the corners, JLC06161H-3313
(L1 signal / L2 GND / L3 slow / L4 power / L5 GND / L6 signal). All six blocks merge cleanly (0 missing / mismatched parts,
0 clearance, 0 courtyard, 0 corners). Only a part of TOPOLOGY.md is drawn; the rest is **reported, not auto-routed**
(the old `boardroute.py` is no longer called). DRC has no clearance / short / hole errors; its 74 errors are all
`unconnected_items` of the nets listed below.

Flow: `python3 gen_board.py` (~4 min: merge, planned routes, planes, rule-10 check, check_board; `--nofinish` stops after the
routes and writes the scratch `routed.kicad_pcb`), then `tools/run_drc.sh --rules jlc4 --parity layout/board/scope-fe.kicad_pcb`.
Renders: `scope-fe-L1.png` ... `scope-fe-L6.png`, `scope-fe-all.png` (3600 px), `scope-fe-detail-analog.png`,
`scope-fe-detail-fpga-south.png` (TAP staircase), `scope-fe-detail-mcu.png`. Stale 4-layer PNGs deleted.

## Blocks
All blocks except phase are native six-layer files (`BL_STACKUP=6L`, supply landings on In3 = L4) and merge with
`layer_map=None`; phase is still a 4-layer file and merges with `LAYER_MAP_4TO6`. This pass converted **power** (USB pair
w 0.18 / s 0.22 at the kept 0.40 pitch, 89.1 R IPC-2141 microstrip at 0.0994 mm; check_board 0 in every class, only the
plane-fed +1V2 / +2V5 / +3V3 / +5V / -5V unrouted) and **mcuif** (USB w 0.19 / s 0.31 at the 0.5 mm pin pitch, 89.7 R;
check_board 0 except 1 known off-axis exit at R737.1 and plane-fed +3V3 / +-2V5). mcuif interfaces were NOT re-spaced
(the lanes they would serve are not drawn, see below); the C721 / sliver items were already fixed in the block.
gen_board.py drops the phase block's all-layer north_cut keep-out (kept from the review), removes every block GND zone and
the block +3V3 L4 zones, and clears L3 under every L2 cut-out.

## Routes as built (net, layer, lane, length mm)
| net | layer | lane / corridor | mm |
|---|---|---|---|
| VTH1 / VTH2 rail | L3 (moved from B.Cu in gen_board.py, not gen_phase.py) | y 28.92, x 28.98-58.61 / 65.10-94.72 (B kept only into R380 / R381) | 29.62 / 29.62 |
| S_STROBE_N | L1 + L6 | fpga W edge, its L6 hop extended 1 mm to the analog N row (y 11.865) | +1.0 |
| BUF_OUT_T | L1 0.16 | analog S (15.75) -> along y 22.5 -> phase N (8.79) | 11.91 |
| COARSE | L6 0.11 | lane y 20.90 (north of TAP0), then y 22.45 under the analog south row to (4.45, 22.75) | 54.66 |
| TAP0..TAP7 | L6 0.11 / 0.11 | west staircase lanes y 21.12 + 0.22 k, drop at the comparator vias (y 23.92) | 32.67, 31.75, 24.35, 23.43, 16.02, 15.30, 8.09, 10.77 |
| VBIAS_K / ADC_IN / ADC_REF_MID / VBIAS_A | B -> via | analog B columns end in an L3 via at y 20.3 / 20.0 / 20.8 / 16.3 (L3 lines themselves not drawn) | - |
No two tracks cross; no 90-degree corner (check_board 0). Lanes were checked against the merged copper (vias, B parts, stubs).

## NOT placed (and why)
- **TAP8..TAP15 east staircase**: east of x 67 there is no L6 lane between the power block's B parts / vias (bottom y 22.33)
  and the comparator via rows (GND 23.07 / 23.97, +3V3 23.61 / 24.25). The phase B stubs were removed (they touched the fpga
  middle-group stubs at y 22.5), the comparator vias stay.
- **Middle group (DBG2, JTAG x4, MCU_CLK, SPI x4, I2C x2, DONE, RECONFIG, ADC_TRIG)**: the drop between U308 and U309
  (x 57.6-64.9) is blocked on L6 by the B-side R380 / R381 / VTAP_TH network (y 26.5-29.2) and the vias (61.83, 23.61 / 24.25),
  (62.53, 23.07). Needs a gen_phase.py change (move that network to F or west, move the 3 vias) before the highway can be fed.
- **S_STROBE_P**: fpga W interface at y 9.865 vs analog E at 10.865 (1.0 mm off; analog block-local y was taken as board y).
  The jog is blocked by the fpga's PH_STROBE pair turning down the W margin at x 56.9 / 57.26. Fix in gen_fpga.py
  (strobe row 1 mm lower) or gen_analog.py.
- **PH_STROBE_P / N**: P is south of N at the fpga edge but west of N at the pstrobe inputs: a planar pair cannot join them
  without one crossing (needs an equal L6 hop on both lines, or a pin swap in the fpga block). Not drawn.
- **L3 slow lines** (VNEG_REF, VOFS, VBIAS_A/K, ADC_IN, ADC_REF_MID, DAC_TRIG, TRIG_SEL, VTAP_TH): the mcuif edge order
  (VNEG, ARM, DAC_TRIG, VOFS, VA, VK, TRIG_SEL, ADC_IN) does not match the analog edge order (VOFS, VNEG, VA, VK, ADC_IN, ARM)
  for one planar bus; needs a two-channel plan (west of tap 0 and through the VTH-rail gap x 58.6-65.1). ADC_IN is planned on L3
  (no planar L6 / L1 path exists across COARSE / TAP and the JTAG lanes). VTAP_TH's phase B column (x 61.93) still sits on L6.
- **USB pair**, **VTAP_P / VTAP_N feeds** and every **L4 rail island** (+5V, -5V, +2V5, -2V5, +1V2 feed, VBUS): not drawn; L4 is
  one +3V3 background zone plus the block islands (+1V2 under U501, VTAP_P / VTAP_N strips).
- Stitching fences / grid and ground vias beside signal vias: not added. Silkscreen: only the old labels (bf.silk); no new
  "6L JLC06161H-3313" label.

## Check results (this run, verbatim)
- check_board: `missing 0, extra 4 (H1-H4), footprint 0, value 0, pad-net 0, nets with unrouted connections (after fill) 47,
  clearance < 0.1 mm 0, track corners > 45 deg 0, tracks leaving a pad off-axis 1 (R737.1), RF width 0, RF pour gap 0,
  courtyard overlaps 0, unconnected items 75`.
- rule 10: `fast-net segments on L3: 3` (FPGA_DONE inside the fpga block: config line on L3, block-internal);
  `L1/L6 samples 4577, without filled GND on L2/L5: 397`; L4 zones: VTAP_P 1, VTAP_N 1, +1V2 1, +3V3 1 polygon.
- DRC jlc4 + parity: `total 652: error 74, warning 578` = 74 unconnected_items; warnings 199 footprint_symbol_field_mismatch
  ('Note' field), 199 lib_footprint_mismatch + 12 lib_footprint_issues (library version), 66 track_dangling + 58 via_dangling
  (interface stubs / vias of the unplaced nets and plane-fed supply vias), 30 footprint_symbol_mismatch (DNP: KiCad 7 cannot
  store it), 10 net_conflict (TL401-403 GND pins, J601 shell), 2 silk_over_copper, 2 silk_overlap. 0 clearance / short / hole.
- ERC: `total 18: warning 18` (9 footprint_link_issues, 9 lib_symbol_mismatch), 0 errors.

## Open design points (not changed)
Phase strobe lines load to about 41 R against 49.9 R terminations; effective tap spacing 30 ps (39.4 / 69.4 ps per tap).
TRIG_SEL pull-down R737 = 2.0 k kept. S_STROBE_N two-via termination path accepted. pstrobe A / K legs equal length, not mirror.

## History (short)
4-layer attempt and a first six-layer pass (21 Nov) were auto-routed and failed on same-layer crossings at the fpga south edge;
TOPOLOGY.md was written from that. This pass replaced the router with explicit routes and found the block-level blockers above.

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

