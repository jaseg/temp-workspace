# ANALOG block (input stage + sampler + sampler strobe chain), 56.0 x 21.5 mm at board (0, 1), rot 0
`python3 gen_analog.py` writes `analog.kicad_pcb`, `analog.ifaces.json`, `analog.png` and `analog_detail.png` (the input stage, which is the densest area).
check_board (103 refs, netlist of 21 Nov 17:42, incl. the new R123): 0 missing / extra / footprint / value / pad-net / no-net, 0 clearance, 0 corners, 0 off-axis pad exits, 0 RF width / gap.
Courtyard check in the script (pairwise BooleanIntersection, > 0.005 mm2, same side): **0**. Unrouted: only the plane-fed +5V, -5V, +2V5, -2V5, +3V3 (via pairs to In2).
DRC (`tools/run_drc.sh --rules jlc4`, KiCad 10.99): 14 errors = 13 unconnected (only the 5 supply nets above) + invalid_outline (no Edge.Cuts in a block). 120 warnings = 87 lib_footprint_mismatch + 4 lib_footprint_issues + 20 via_dangling (supply vias that wait for In2) + 9 track_dangling (the interface stubs). 0 courtyard, clearance, width, hole or silk violations.
## Interfaces (block-local mm)
| net | x, y | layer / side | note |
|---|---|---|---|
| /S_STROBE_P, /S_STROBE_N | 56, 9.865 / 10.865 | F.Cu E, 0.36 | FLOORPLAN gives 8.5 / 9.5: 1.37 mm lower (strobe line axis) |
| /BUF_OUT_T | 15.75, 21.5 | F.Cu S, 0.36 | 0.45 mm right of FLOORPLAN 15.3 |
| /VOFS, /VNEG_REF | 1.00, 1.94; 21.5 | B.Cu S, 0.2 | R119 / R123 at U102; outside the 20-35 window |
| /VBIAS_A, /VBIAS_K, /ADC_IN, /ADC_REF_MID | 15.40, 16.40, 19.06, 21.65; 21.5 | B.Cu S, 0.2 | |
| +5V, -5V, +2V5, -2V5, +3V3 | vias | In2 | FLOORPLAN partition |
## RF lengths (0.36 mm, 50 R, F.Cu over In1, no vias, 6.057 ps/mm)
| segment | mm | ps |
|---|---|---|
| SMA pad end -> C101 pad 1 | 1.16 | 7.0 |
| BUF802 OUT -> R201 10 R (<= 3 mm) | 2.95 | 17.9 |
| R201 -> D201.3; bridge rails (4x, mirrored) | 3.12; 2.565 | 18.9; 15.5 |
| STRB_A / STRB_K arms (C201/C202 -> T401) | 16.747 / 16.747 | 101.4, mismatch 0 |
| TL401 shorted stub | 13.207 | 80.0 |
| BUF_OUT_T (R113 -> S boundary) | 8.71 | 52.7 |
| S_STROBE_P edge -> R401; C401 -> R401; U401 in / out; 12 dB pad 1.01 + 1.01 (shunt stubs 0.89) | 0.51; 0.85; 1.08 / 2.02 | |
## Deviations
- Courtyard rule: **SMA -> divider grew from 0.89 to 1.16 mm** (C101's courtyard would otherwise overlap J101's). 0402s now sit at courtyard pitch. The pi-pad shunts R403 / R402 hang above the line on 0.89 mm 50 R stubs. C401 -> R401 has 0.85 mm of line. The R405 / C411 / R406 column is at 1.84 mm pitch.
- The input servo was re-placed: U102 is at the bottom left, the R114-R117 column is beside J101, IN_BIAS uses B.Cu through 2 vias, and FB runs on B.Cu from R118 to R120. TP103 / TP104, C110 / C114 (U102), C115 and the bulk C111 / C116 are on B.Cu. R201 sits 0.16 mm further right, so the sampler and the chain moved +0.16 mm.
- T401 uses the netlist land (Coilcraft 0805USB, 1/4 | 2/3). The K arm passes under T401, and the A arm has a 45-degree bump (h 1.73 mm) for equal length. The arms are mirror images up to XV.
- Added from membership "pstrobe": C402-C404 and C407-C409 (U401 / U402 decoupling, as in sim/bias_tee). J102 / R122 stay with phase.
- Local helpers: Frame.place (Block.place side="B" segfaults in pcbnew 7.0.11), pad_escape / split_at_pads (pad-axis exits), strip_silk_over_pads (4 library silk segments over neighbouring pads were removed), courtyard_overlaps, and a render crop offset.
- Block GND zones are on In1 / F / B with the fragment cut-outs. merge(skip_planes=True) would lose the In1 cut-outs.
## Open points
- Balun pin map (Murata DLW21SN vs Coilcraft land): fix this in the schematic / footprint. R201 -> D201.3 is 3.12 mm.
- Integrator: GND stitching, the In2 partition, and the BUF_OUT_T and S_STROBE pair routing. kicad-cli 7 has no DRC / ERC, so the nightly DRC was used.
