# Layout rules for every block and for the integrated board

Source of truth: the schematic netlist `design/lowcost/kicad/export/scope-fe.net` (references, values,
footprints, pad nets). Library and conventions: `README.md` and `boardlib.py` in this directory.

Board: **100.0 mm wide (hard limit) x 57 mm high**, origin top-left, 4 x M3 holes 3 mm in from the corners.
JLCPCB standard 4-layer stack-up JLC04161H-7628; In1 solid ground, In2 power planes.

User-set rules (all mandatory)
1. 50 R microstrip is 0.36 mm on F.Cu over In1 (6.057 ps/mm); other impedances from the impedance function in
   `boardlib.py`. Every RF trace has its computed width over its whole length; F.Cu ground pour stays
   >= 2 x trace width away from RF traces. Critical RF structures stay on F.Cu with no vias in the signal path.
2. IC supply connections as wide as possible: planes, pours, pad-wide copper, via pairs at the decoupling
   capacitor. Never thin power tracks.
3. No 90 degree corners anywhere (45 degree bends or arcs). Tracks leave pads along the pad axis.
4. Compact, tidy placement, but **no courtyard overlaps**: no two footprints on the same side may have
   overlapping courtyards (touching at 0.0 mm is allowed). No shared or bridged pads; series RF parts get a
   short piece of correctly sized trace between them. No whitelisting of "intentional" overlaps.
5. Symmetric structures are true mirror images: sampler bridge and strobe arms; tap cells; the summing node
   tapped from the jumper midpoint with equal lengths for both comparator channels; the two phase-strobe chains.
6. Delay-line meander same-net gaps >= 0.5 mm.
7. Bias tees as in `sim/bias_tee/RESULT.md`: bead pad on the line, straight chain, decoupling at the cold pad,
   supply entering through the capacitor.
8. Double-sided assembly is allowed for decoupling, bulk capacitors, power and slow parts; RF and analog parts
   stay on top.
9. Silkscreen text at least 0.8 mm high, 0.15 mm line; if a reference does not fit, hide it on F.Fab. No silk
   over pads.

10. Four layers only, so return paths are planned (user review of the first merged board):
    - In1 (L2) is solid ground under everything on F.Cu.
    - In2 (L3) is GROUND BY DEFAULT. Power zones on In2 are local islands sized to the pins they feed
      (plus the feed from the regulator); the rest of In2 is a ground zone stitched to In1.
    - Any RF, clock or fast-edge trace on B.Cu (L4) must have ground on In2 directly above it over its whole
      length: a ground reference strip on L3 placed between the power zones, at least 3 x the trace width
      wide (1 mm minimum), stitched to In1 at both ends and every 5 mm or so. This applies to: FPGA_CLK,
      MCU_CLK, CLK lines of the clock generator, SPI_SCK and the other SPI lines, ADC_TRIG, COARSE, TAP0..TAP15,
      JTAG_TCK, the strobe lines S_STROBE / PH_STROBE if any part of them is on B.Cu (avoid that), and USB if
      any part is on B.Cu (avoid that). No such trace may cross a gap between two In2 zones or run under a
      power island; route around or move the island boundary.
    - Slow control voltages and static lines on B.Cu should also stay over In2 ground where practical, and
      must not run under or beside the hold node, the divider node, the comparator inputs or ADC_IN.
    - gen_board.py must check this: for every net in the list above, sample its B.Cu segments and verify
      that the filled In2 copper above each sample point is GND; report violations (count must be 0).
11. Clocking (for routing): FPGA_CLK and MCU_CLK come from the same MS5351M and must stay clean: series
    resistor at the source, short, over ground, away from the analog block. ADC_TRIG (FPGA pin 41 to MCU PB11)
    is a timing-critical line that firmware may drive in either direction: route it like a clock.

Checks (the authority is KiCad's own DRC)
- `design/lowcost/tools/run_drc.sh --rules jlc4 <board.kicad_pcb>` (KiCad nightly CLI; runs on a scratch copy;
  never open or save project files with the nightly). For a block the DRC must end with 0 violations other
  than: unconnected items that are registered inter-block interfaces or plane-fed supply nets, dangling
  tracks / vias at those interfaces, the missing board outline, and library-version artefacts
  (lib_footprint_mismatch / lib_footprint_issues). In particular 0 courtyards_overlap, 0 clearance,
  0 track-width, 0 hole, 0 silkscreen violations. Footprints that carry their own larger pad clearance
  (for example the MS5351M U502, 0.2 mm) must be respected.
- `boardlib.check_board` on the block: 0 missing / extra / footprint / value / pad-net mismatches,
  0 clearance, 0 sharp corners, 0 off-axis pad exits, 0 RF width or pour-gap faults.
- Render, look at the PNG, iterate. A layout that has not been looked at is not finished.

General: do not commit or push; write only inside your own block directory unless told otherwise; scratch
files under `/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/board/`.
