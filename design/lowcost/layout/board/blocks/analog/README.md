# ANALOG block (input stage + sampler + sampler strobe chain), 56.0 x 21.5 mm at board (0, 1), rot 0
`python3 gen_analog.py` writes `analog.kicad_pcb`, `analog.ifaces.json`, `analog.png`, `analog_detail.png` (input stage, F.Cu) and prints all tables below. `analog_detail_L1L2.png` = F.Cu + In1 (L2) of a zone-filled scratch copy: the node windows and the pad cut-outs.

**Phase two (6-layer, JLC06161H-3313).** The script sets `BL_STACKUP=6L` and is now a native 6-layer file: In1 = L2 GND, In2 = L3 (slow), In3 = L4 (power), In4 = L5. Supply via landings are on In3 (L4); ifaces.json says `In3.Cu`. **Merge it with `layer_map=None`** (LAYER_MAP_4TO6 would move the L3 keep-outs to L4; L4 keep-outs survive either way, L3 is then lost). Placement, references, nets and every interface position are unchanged (no interface moved; only the RF width 0.36 -> 0.16 mm and the supply landing layer In2 -> In3).
check_board: 0 missing / extra / footprint / value / pad-net / no-net, 0 clearance, 0 corners, 0 off-axis pad exits, 0 RF width / gap, 0 courtyard overlaps; unrouted only the plane-fed +5V, -5V, +2V5, -2V5, +3V3.
DRC (`tools/run_drc.sh --rules jlc4`, KiCad 10.99, 6 layers): `total 134: error 14, warning 120` = 13 unconnected_items (the 5 plane-fed supplies) + 1 invalid_outline (no Edge.Cuts in a block); 87 lib_footprint_mismatch + 4 lib_footprint_issues + 20 via_dangling (supply vias waiting for L4) + 9 track_dangling (interface stubs). 0 courtyard, clearance, width, hole, silk.

## Impedance, JLC06161H-3313 (boardlib.microstrip, mask corrected; L1/L2 = L6/L5: h 0.0994 mm, er 4.1)
| Z0 target | computed w | drawn | Z0 drawn |
|---|---|---|---|
| 50 R | 0.161 mm | **0.16 mm** | 50.2 R |
| 73 R | 0.064 mm | 0.06 (below the 0.09 mm fab minimum: not used in this block) | 74.4 R |
| 100 R | 0.020 mm | not manufacturable on L1/L2 | |

| w (mm) | Z0 | eps_eff | ps/mm | fF/mm |
|---|---|---|---|---|
| 0.16 (RF) | 50.2 | 3.155 | 5.925 | 118 |
| 0.15 (hold) | 51.8 | 3.138 | 5.909 | 114 |
| 0.20 | 44.7 | 3.214 | 5.980 | 134 |
| 0.30 | 35.3 | 3.327 | 6.084 | 173 |
| 0.40 | 29.2 | 3.410 | 6.160 | 211 |

## RF lengths / delays (0.16 mm, 50 R, F.Cu over L2, no vias, 5.925 ps/mm)
| segment | intended | actual mm | ps |
|---|---|---|---|
| SMA pad end -> C101 pad 1 | min. by courtyard | 1.16 | 6.9 |
| BUF802 OUT -> R201 10 R | <= 3 mm | 2.947 | 17.5 |
| R201 -> D201.3 | short | 3.12 | 18.5 |
| bridge rails (4x, mirrored) | equal | 2.565 each | 15.2 |
| STRB_A / STRB_K arms (C201/C202 -> T401) | equal | 16.747 / 16.747 (mismatch 0) | 99.2 / 99.2 (was 101.4 on 4L) |
| TL401 shorted stub (tap -> NT401) | 80.0 ps | 13.503 (was 13.207) | 80.0 |
| BUF_OUT_T R113 -> S boundary | - | 8.708 | 51.6 |
| CLIP balun -> tap -> C410; clamp tap | short | 2.965; 0.40 | 17.6; 2.4 |
| TRF2/TRF1 OUT (C -> bead -> pin 7) | short | 2.02 / 2.02 | 12.0 |
| TRF RFIN pin 2 -> 100 nF | short | 1.08 / 1.08 | 6.4 |
| 12 dB pad series 1.01 + 1.01, shunt stubs 0.89 | short | | 6.0 / 5.3 |
| C401 -> R401; R401 -> E edge; R405 -> E edge | | 0.85; 0.51; 0.57 | 5.0; 3.0; 3.4 |
Necks: none needed (0.16 mm is narrower than every pad it meets; tracks leave all pads on-axis).

## Plane cut-outs (L2 only 0.0994 mm under L1)
Node windows, L2 + L3 + L4 cleared (and F.Cu / B.Cu pour), reference L5 at 1.354 mm: SMA centre pad (x 0-3.7, +-0.9), divider node (C101.2 / R104 / C102, L-shaped), BUF802 input strip (R104.2 -> U101.2; shortened to y <= 10.55 so the IN_BIAS via at (8.52, 10.80) stays outside), hold node (D202.3 / U201.3 / C205). No via of any net lies in a window or within 0.1 mm of RF / stub copper (script check: 0).
| node (layout copper only) | windowed | over solid L2 |
|---|---|---|
| hold node | 268 fF | 1027 fF |
| divider node GA | 196 fF | 811 fF |
| BUF802 input | 211 fF | 776 fF |
| SMA centre pad + taper | 824 fF | 2456 fF |

Pad compensation: every in-line RF pad whose excess C over L2 (pad vs. 0.16 mm line over the pad length) exceeds 30 fF gets an L2 cut of the pad size; under it L3 keeps its GND pour, with a no-track rule area on L3 (pad then sees L3 at 0.665 mm). 0402 R (0.64 x 0.54): +99 fF -> -17 fF; 0402 C (0.62 x 0.56): +99 -> -19; beads FB401/402: +105 -> -23; D201/D202 rails 0.70 x 0.45: +93 -> -13, D201.3 +78 -> -31; T401: +102 -> -31 (pads 1/2), +117 -> -12 (pad 4); D401.1 +67 -> -27; NT401.1 +65 -> -21; C101.1 +95 -> -23. Not cut (<= 30 fF): U401/U402 pins 2/7 +18 fF, U101.11 +29 fF. The full per-pad table is printed by the script.

## Interfaces (block-local mm)
| net | x, y | layer / side | note |
|---|---|---|---|
| /S_STROBE_P, /S_STROBE_N | 56, 9.865 / 10.865 | F.Cu E, 0.16 | FLOORPLAN gives 8.5 / 9.5: 1.37 mm lower (strobe line axis) |
| /BUF_OUT_T | 15.75, 21.5 | F.Cu S, 0.16 | 0.45 mm right of FLOORPLAN 15.3 |
| /VOFS, /VNEG_REF | 1.00, 1.94; 21.5 | B.Cu S, 0.2 | R119 / R123 at U102; outside the 20-35 window |
| /VBIAS_A, /VBIAS_K, /ADC_IN, /ADC_REF_MID | 15.40, 16.40, 19.06, 21.65; 21.5 | B.Cu S, 0.2 | |
| +5V, -5V, +2V5, -2V5, +3V3 | vias | In3 (L4) | FLOORPLAN partition |
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
- Phase two: the slow interfaces (VOFS, VNEG_REF, VBIAS_A/K, ADC_IN, ADC_REF_MID) still leave on B.Cu (L6) columns at the S edge, as in phase one; rule 10 wants bias on L3 -> integrator via to L3 at the boundary, or a later block change.
- Pad-cut residuals are -12 to -31 fF (slight under-capacitance, L3 reference); a rimmed cut could trim them, not done. The L2 pad cuts need L3 to stay GND pour under them (block rule area forbids L3 tracks there).
