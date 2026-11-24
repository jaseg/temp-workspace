# Inter-block routing topology (six layers) — the plan every block and the integrator follow

Layer use is RULES.md rule 10: L1 RF/analog, L2 GND, L3 slow bias/control, L4 power, L5 GND,
L6 fast inter-block digital + bottom-side parts. Board 100 x 57 mm, origin top-left.
Blocks: analog (0..56, 1..22.5), fpga (56..74, 0.5..22.5), power (74..100, 0..22.5),
phase (0..99.5, 22.5..45; tap axis y 37.5, taps at x 26.71 + 4.514 n), pstrobe (9.5..26.5, 25..50),
mcuif (27..93.5, 45..57). Comparators U305..U312 sit north of the tap row (bodies about y 25..30.5),
outputs on their north pins, inputs on their south pins.

The first six-layer pass failed for one reason: on L6 everything leaving the FPGA's south edge had to
cross the east-west TAP ribbon. The plan below removes every same-layer crossing by ORDERING.

## 1. FPGA south edge (L6), west to east
`COARSE | TAP0 TAP1 ... TAP7 | DBG2 JTAG_TCK JTAG_TMS JTAG_TDI JTAG_TDO MCU_CLK SPI_CS I2C_SDA FPGA_DONE
SPI_MOSI SPI_MISO SPI_SCK I2C_SCL FPGA_RECONFIG ADC_TRIG | TAP8 TAP9 ... TAP15`
- TAP0..7 turn WEST into a staircase ribbon along y about 23..25 (north of the comparators) and drop to
  the comparator output pins U305..U308; TAP0 is the outermost (northmost, furthest west).
- TAP8..15 turn EAST the same way to U309..U312; TAP15 outermost.
- The middle group goes straight SOUTH between the two ribbons (between U308 and U309) to the highway.
- COARSE arrives from the west, north of the TAP0 track.
- This needs the FPGA pins permuted (all are ordinary bank I/O after configuration; the README says TAP
  pins may be permuted; SPI / JTAG pins keep their functions, only their fan-out order at the block
  edge changes). The schematic generator and netlist are updated with the permutation.

## 2. Highway (L6), y about 26..32, under the comparator bodies
East-west bus corridor, about 20 tracks at 0.3 mm pitch, over solid L5 ground.
- The VTH rail that ran here on B.Cu moves to L3 (it is a static threshold voltage); its vias stay.
- From the drop point at x about 60..66 the middle group splits:
  - `DBG2 TCK TMS TDI TDO` go WEST along the highway to x about 37..48,
  - `MCU_CLK SPI_CS I2C_SDA FPGA_DONE SPI_MOSI SPI_MISO SPI_SCK I2C_SCL FPGA_RECONFIG ADC_TRIG` go EAST
    to x about 70..88.
  Bus order is kept west-to-east equal to the target order, so the two turns nest without crossings.

## 3. Tap-row crossings (L6)
Between two tap cells there is one clear lane (about 1 mm: three 0.15 mm tracks at 0.3 mm pitch) between the
node window of one cell and the summing-jumper / tap-branch tracks of the next. Lanes are used straight
north-south from the highway (y 32) to the mcuif north edge (y 45):
- JTAG group: two lanes near x 38..48, landing on the mcuif interfaces above J501
  (DBG2 37.55, TCK 40.09, TMS 42.63, TDI 45.17, TDO 47.72).
- MCU group: four lanes near x 70..88, landing on MCU_CLK 73.35, SPI_CS 77.25, SDA 78.25, DONE 78.75,
  MOSI 79.25, MISO 79.75, SCK 80.25, SCL 80.75, RECONFIG 85.10, ADC_TRIG 85.80 (short jogs in the 3 mm
  between the tap row and the mcuif edge; the mcuif interfaces may be re-spaced to sit under the lanes).
- USB_DP / USB_DM: 90 ohm pair on L6 in its own lane near x 84..88 from the power block (south edge) to the
  mcuif interface at (88.0 / 88.5, 45); the pair crosses the highway band at right angles east of the
  MCU group.
No L6 track may pass under a node window (hold-node cut-outs) of a tap cell.

## 4. L1 inter-block RF
- BUF_OUT_T: analog south edge to the TMUX136, 50 ohm.
- S_STROBE_P: FPGA west edge straight into the analog block's east end (abutting); S_STROBE_N to its
  termination by the shortest path. No vias.
- PSTRB_A / PSTRB_K: pstrobe to the tap row (abutting, mirror images).
- PH_STROBE_P / _N: FPGA west edge, as a pair on L1 westward along y about 23 to the pstrobe block's
  NORTH edge at x about 10.0 / 10.5. Inside pstrobe both lines take the SAME structure to reach their
  chains on either side of the trigger corridor: L1 -> via -> L6 -> via -> L1, equal total length
  (the A-side line gets the detour the K-side needs to pass under the corridor), ground via beside each
  signal via. These are the FPGA's 300-600 ps edges before the amplifiers sharpen them.

## 5. L3 (slow)
VBIAS_A, VBIAS_K, VOFS, VNEG_REF, DAC_TRIG, VTAP_TH / VTH, ADC_REF_MID, TRIG_SEL from the mcuif north edge
(x about 37..72) to the analog block and the trigger front end, flanked by ground pour; never under the
hold node, the divider node or comparator inputs. ADC_IN: analog block to the MCU pin on L6 or L1 inside a
ground-poured corridor away from the highway and the clocks (it is a settled DC level sampled 40 ns after
the strobe: treat as sensitive, not fast).

## 6. L4 (power)
+3V3 is the background zone. Islands, each at least 2 mm wide along its whole run from the regulator:
+5V and -5V (power block to the input stage along the top edge), +2V5 and -2V5 (to hold amp, level
shifter, TLV3801, U701, tap readout), +1V2 (to the FPGA), VBUS (to the GVA-84+ chokes in pstrobe and to
J501 pin 1), VTAP_P / VTAP_N strips under the tap row (fed from +2V5 / -2V5 at the east end). L4 is cleared
under the node windows. Every supply via lands inside its zone; no supply runs as a track.

## 7. Revision of 22 Nov 2026 (integration, second pass)
- Section 1 order as built in the fpga block: `COARSE | TAP0..TAP7 | DBG2 TCK TMS TDI TDO | MCU_CLK SPI_CS I2C_SDA FPGA_DONE
  SPI_MOSI SPI_MISO SPI_SCK I2C_SCL FPGA_RECONFIG ADC_TRIG | TAP15 TAP14 ... TAP8` (east group reversed, TAP8 eastmost:
  pins 9, 10, 11, 13, 14, 15, 16, 17 = TAP15 ... TAP8 in gen_fpga_clock.py). Intended: the middle group and the east TAPs
  drop south together to the highway; turning east, TAP8 / TAP9 are northmost and peel north first to U309, then
  TAP10 / 11 to U310 and so on; the MCU group lies south of them and turns south into its lanes; JTAG turns west.
- PH_STROBE_P / _N now on U501 pins 39 / 40 (swapped), so the pair reaches the pstrobe inputs (10.00 / 10.60, 25.00)
  without a crossing; it runs on L1 along y 21.85 / 22.19, then 22.85 / 23.21 (south of BUF_OUT_T at y 22.35).
- S_STROBE_P / _N: the fpga block now ends them on the analog E rows (board y 10.865 / 11.865): abutting, no vias on P.
- NOT yet buildable (blocker, see README): the drop of the 23-track middle + east group. U309 (x 63.5-68) sits directly
  under the MCU-group slots (x 65.0-69.5); its output vias (65.10 / 66.37, 23.92) and pin-5 GND via are in the fan-in area;
  each comparator gap is only 4.4 mm (17 tracks at 0.25 mm). A buildable variant needs: (a) comparator outputs U309-U312
  on vias under the SOIC body (about y 26.9, L1 stub from pins 6 / 7) and the cap / pin-5 vias moved off y 23-24.3,
  (b) R380 / R381 / C354 / C355 + the VTAP_TH column out of the U308|U309 gap, (c) JTAG through gap U308|U309, MCU + TAP
  through gap U309|U310, with TAP8 / TAP9 reaching U309 from that gap on a short west-going L6 band at y 27.4 / 27.75
  (below the under-body output vias, above the VTH via row), which needs the fpga slot order
  `... | MCU | TAP9 TAP8 | TAP15 ... TAP10` - and that order needs the fpga's DONE / RECONFIG F runs (local y 18.1 / 18.5)
  moved, because the TAP F escapes would cross them.

## 8. Power and slow-layer plan, revised by the lead (supersedes section 6 and the L3 parts of sections 2 and 5)

Two automatic attempts showed that seven rails cannot be planar on one layer next to a +3V3 background.
The rails are therefore split over two layers by role:

- **L4 (In3): +3V3 only, one solid unsplit plane over the whole board.** No islands, no strips (the FPGA
  block's small +1V2 island at its east edge may stay if it does not cut the plane). L4 is cleared only
  under the node windows.
- **L3 (In2): the minor rails as nested corridors, plus the slow lines.** Corridor strips are 1.5 mm wide
  (1.0 mm allowed for a short neck), pairs separated by 0.3 mm, 45-degree corners, each rail one connected
  piece of copper from its regulator output vias to every load via (short 0.8-1.0 mm branches to the vias).
  Suggested nesting, all starting at the power block (x 74..100, y 0..22.5):
  - `-5V`, `+5V`: west along the top edge (y about 0.6..4) over the FPGA and analog blocks to the input
    stage in the top-left corner. Outermost pair.
  - `+2V5`, `-2V5`, branch (i): west along the band between the analog and phase blocks (y about 22..25)
    to the hold amplifier / level shifter vias, on to the west edge, then south along x about 1..8 to the
    trigger front chain (y 30..40).
  - `+2V5`, `-2V5`, branch (ii): from the power block south just inside the east edge, past the east end
    of the tap row, then west along y about 45..46.5 (the mcuif north edge) to U701 and the bias dividers.
    The tap-row VTAP tracks end west of this branch; VTAP_P / VTAP_N are fed from it at the east end
    through their 0 R links.
  - `VBUS`: with branch (i) along the y 22..25 band to x about 21, then south as the pstrobe choke column
    (x about 19..23, y 26..49). J501 pin 1 gets VBUS by one 0.5 mm track on L6 (it is only a programmer
    supply pin).
  - `+1V2`: short local strip from the power block to the FPGA (or the block's L4 island).
  - A rail may hop to L6 as a 1.5 mm strip with a three-via array at each end where a crossing is
    unavoidable; at most three hops on the whole board, each listed in the README.
- **VTAP_P / VTAP_N**: 0.5 mm tracks on L3 along the tap row at the y of their resistor vias.
- **VTH (comparator threshold rail)**: on **L1**, as a 0.3 mm track at the comparators' centre line under
  the SOIC bodies between their pin rows (pins 2 and 4 reach it with short inward stubs). Nothing of VTH on
  L3 or L6.
- **Slow bias and control lines** (VBIAS_A, VBIAS_K, VOFS, VNEG_REF, DAC_TRIG, VTAP_TH, ADC_REF_MID,
  TRIG_SEL, ADC_IN): they leave the mcuif block on B.Cu, cross the 45..46.5 corridor and the tap row on
  **L6 in tap-row lanes** (slow lines are allowed on L6; lanes not used by the fast groups), change to
  **L3 just north of the tap row** (via at y about 32.3..32.8, south edge of the highway band), and run
  on L3 north / west to the analog block and the trigger front end, passing under the L6 highway and
  between the L3 corridors. They never cross an L3 corridor: where one would, the line stays on L6 a little
  longer or the corridor necks around it.
- Order of work on the board: signal vias first (L6 buses), then the L3 corridors (board_power.py), then
  the L3 slow lines around them.

## 9. L3 space allocation between power trunks and slow lines (lead, final)

Two agents fought over L3: with slow lines first the trunks could not complete, with trunks first only one
slow line routed. Every layer has an east-west structure in the band between the analog and phase blocks
(L1 phase-strobe pair at y about 23, L6 tap staircase and COARSE at y 20.9..22.9, L3 trunks), so north-south
slow lines need reserved gaps. One owner now handles both modules, with this allocation:

- The slow lines only have to reach the analog block's SOUTH-EDGE interfaces (y 22.5; the block brings its
  nets there) and the trigger front end / pstrobe-side targets (DAC_TRIG near (4.6, 41.0), TRIG_SEL near
  (9.25, 44.6)). They do not need to cross the +5V / -5V runs inside the analog block.
- Keep-free areas on L3 for power copper (trunks and rest alike):
  - A: x 0..31, y 21.5..24.6 (strip in front of the analog south-edge interfaces),
  - B: x 0..12.5, y 24.6..48 (west side: trigger front end targets),
  - C: x 26..31, y 24.6..33.5 (the slow lines' way north from their band under the comparators).
- VBUS therefore does not loop around the pstrobe block on L3. It runs its band y about 24.7..27.5 only for
  x >= 31, crosses channel C on L6 (1.5 mm strip, three-via arrays; L6 is free there between the staircase
  at y <= 22.9 and the JTAG band, which starts at x 37), reaches the pstrobe landing at (22.83, 26.4), and the
  other two choke landings ((18.95, 31.65), (19.85, 43.05)) by local joins on L6 or L1 inside the pstrobe
  rectangle (clear of its strobe input serpentine and bottom-side parts).
- Slow-line bundle: nine tracks, 0.15 mm at 0.3 mm pitch = about 3 mm; ADC_IN at the edge of the bundle with
  1 mm spacing to its neighbour. Route: mcuif north edge (L6) -> tap-row lanes (L6) -> via to L3 at
  y 26.9..32 -> west in the band under the comparators -> channel C -> strip A west to each analog interface
  x, or on through B to the front-end targets.
- Order in gen_board.py: signals -> apply_trunks (respecting A, B, C) -> slow lines (using A, B, C) -> pours,
  stitching, silkscreen -> apply_rest (also respecting A, B, C; +2V5 / -2V5 reach the analog interfaces and
  the front end by passing strip A / area B on L6, or at their far west / east ends).

## 10. Revision of 24 Nov 2026 (new power tree; supersedes the corridor / trunk parts of sections 8 and 9)
- Sources (power block, board mm): +3V3 (82.7, 6.05) into L4; +1V2 (75.0, 7.9); +5V (83.05, 8.77); -5V (74.45, 14.0);
  +2V5 (84.45, 15.3); -2V5 (74.6, 20.75); /+5V1 (86.3, 20.9 / 21.7, GVA-84+ chokes, replaces the old VBUS run);
  VBUS (88.0, 17.4 / 18.3) feeds J501 pin 1 only.
- L4: +3V3 plane plus the FPGA +1V2 island, joined to the +1V2 source by an L4 finger at x 73.2-75.65 (the power block's
  In2 sense / PG lines wall the L3 exits there).
- Order: signals -> slow lines (explicit, section 9 geometry) -> supplies. The keep-free areas A / B / C are no longer
  needed: the supplies are routed after the slow lines and keep 0.3 mm from them.
- Minor rails: grid-routed tracks on L3 (L6 where L3 is not planar), widest that fits, guided: /+5V1 along y 25-27
  then the pstrobe choke column; +5V around the PG line's south end, up the power block's west edge and along the top
  edge (outer); -5V west at y 13-14 (inner); VTAP_P / VTAP_N along their tap-row via rows.
