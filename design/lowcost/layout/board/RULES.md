# Layout rules for every block and for the integrated board

Source of truth: the schematic netlist `design/lowcost/kicad/export/scope-fe.net` (references, values,
footprints, pad nets). Library and conventions: `README.md` and `boardlib.py` in this directory.

Board: **100.0 mm wide (hard limit) x 57 mm high**, origin top-left, 4 x M3 holes 3 mm in from the corners.
JLCPCB 6-layer stack-up JLC06161H-3313 (rule 10).

User-set rules (all mandatory)
1. Controlled impedance from the impedance function in `boardlib.py` for the stack-up of rule 10 (50 R was
   0.36 mm on the earlier 4-layer 7628 stack-up; about 0.17 mm now, phase two). Every RF trace has its computed width over its whole length; F.Cu ground pour stays
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

10. SIX layers (user decision after the first merged 4-layer board; JLCPCB JLC06161H-3313, 1.6 mm):
    L1 F.Cu 0.035 / prepreg 3313 0.0994 / L2 In1 0.0152 / core 0.55 / L3 In2 0.0152 / prepreg 2116 0.1088 /
    L4 In3 0.0152 / core 0.55 / L5 In4 0.0152 / prepreg 3313 0.0994 / L6 B.Cu 0.035 (mm).
    Layer assignment:
    - L1 F.Cu: components, all RF and analog routing.
    - L2 In1: solid GROUND (reference for L1). Only the deliberate cut-outs (hold nodes, divider node, SMA pads).
    - L3 In2: signal layer: the fast inter-block digital nets (TAP0..15, COARSE, FPGA_CLK, MCU_CLK, SPI,
      ADC_TRIG, JTAG) and the bias / control voltages (VBIAS_A/K, VOFS, VNEG_REF, TRIG_LEVEL / DAC_TRIG,
      VTAP_TH, ADC_REF_MID, ADC_IN), kept apart from each other (bias lines flanked by ground pour, not next
      to clocks). Unused L3 area is ground pour stitched to L2 / L4.
    - L4 In3: solid GROUND (reference for L3, 0.109 mm below it). No splits under L3 traces.
    - L5 In4: POWER planes: contiguous zones per rail with proper width from regulator to loads; no thin
      power tracks anywhere.
    - L6 B.Cu: bottom-side components (decoupling, chokes, bulk, slow parts) and short slow connections only.
      L6 lies next to the power layer, so NO RF, clock or fast-edge net may run on L6 beyond a via fan-out
      stub of 2 mm; move it to L3.
    - Fast or RF signals never run over a power plane or cross a gap between planes; only slow static lines may.
    - RF geometry on L1 over the 0.0994 mm prepreg: 50 R microstrip is about 0.17 mm (compute with the
      impedance function for this stack-up; solder-mask corrected). PHASE ONE of the conversion keeps the
      block geometries drawn for the old 0.21 mm prepreg and settles layer use and routing topology;
      PHASE TWO re-derives every RF width, the delay-line and strobe-line sections, stub lengths, pad
      compensation and plane cut-outs for this stack-up.
    - gen_board.py checks: every net in the fast list has no L6 segment longer than 2 mm, and every L3 segment
      of those nets has filled GND on L4 below and L2 above at sampled points (count of violations 0);
      every L5 zone is a contiguous region reaching its regulator.
11. Clocking (for routing): FPGA_CLK and MCU_CLK come from the same MS5351M and must stay clean: series
    resistor at the source, short, on L3 between grounds, away from the analog block. ADC_TRIG (FPGA pin 41 to
    MCU PB11) is a timing-critical line that firmware may drive in either direction: route it like a clock.

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
