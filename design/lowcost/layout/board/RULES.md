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
