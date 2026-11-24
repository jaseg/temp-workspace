# ANALOG block (input stage + sampler + sampler strobe chain), 56.0 x 21.5 mm at board (0, 1), rot 0
`python3 gen_analog.py` writes `analog.kicad_pcb`, `analog.ifaces.json`, `analog.png`, `analog_detail.png` (input stage, F.Cu) and prints all tables below. `analog_detail_L1L2.png` = F.Cu + In1 (L2) of a zone-filled scratch copy: the node windows and the pad cut-outs.

**Phase two (6-layer, JLC06161H-3313).** The script sets `BL_STACKUP=6L` and is now a native 6-layer file: In1 = L2 GND, In2 = L3 (slow), In3 = L4 (power), In4 = L5. Supply via landings are on In3 (L4); ifaces.json says `In3.Cu`. **Merge it with `layer_map=None`** (LAYER_MAP_4TO6 would move the L3 keep-outs to L4; L4 keep-outs survive either way, L3 is then lost). Placement, references, nets and every interface position are unchanged (no interface moved; only the RF width 0.36 -> 0.16 mm and the supply landing layer In2 -> In3).
check_board (24 Nov, 107 refs): 0 missing / extra / footprint / value / pad-net / no-net, 0 clearance, 0 corners, 0 off-axis pad exits, 0 RF width / gap, 0 courtyard overlaps; unrouted only the plane-fed +5V, -5V, +2V5, -2V5, +3V3. Script checks: 0 vias in node windows or near RF copper, 0 vias in or touching a soldered pad (net-tie, test-point and IC exposed pads excepted).
DRC (`tools/run_drc.sh --rules jlc4`, KiCad 10.99, 6 layers): `total 138: error 14, warning 124` = 13 unconnected_items (the 5 plane-fed supplies) + 1 invalid_outline (no Edge.Cuts in a block); 91 lib_footprint_mismatch + 4 lib_footprint_issues + 20 via_dangling (supply vias waiting for L4) + 9 track_dangling (interface stubs). 0 courtyard, clearance, width, hole, silk.

## Changes 24 Nov 2026 (validation fixes)
- **RF-1 / RF-4 (sim/strobe_arms/RESULT.md):** T401 position and the uncoupled 50 R arms kept. R204 now stands on the bridge axis (x 30.54, pads y 9.79 / 10.81) with one pad in each arm. The arms are mirror images about the bridge axis from C201 / C202 through R204 to the T401 centre column. Only the last 0.38 mm into the balun's diagonal output pads differs (pad 2 is entered from the right, pad 4 from the left), so the two lengths are equal by construction: 17.827 / 17.827 mm, 105.6 ps each (was 99.2 ps with an A-side bump and a K-side R204 stub). A strict mirror into the pads is impossible because the TL balun puts its outputs on opposite corners.
- **RF-2:** the TL401 short is now a GND via in NT401 pad 2 (net-tie pads are tented copper: no mask opening, no paste) plus two flanking vias. The 1.0 mm net-tie strip and the L1 -> L2 barrel (155 + 42 pH = 3.9 ps) are taken off the line: line 12.838 mm (76.1 ps) + 3.9 ps = 80.0 ps. NT401 pad 1 no longer gets a pad cut (shorted end). The same recipe applies to NT402 / NT403 (pstrobe owner): via in pad 2, line = (80 - 3.9 ps) / 5.925 ps/mm.
- **DECOUPLING-1:** C614 (10n, moved from the power sheet) sits top side at BUF802 pin 10 like C109 at pin 12: 0.25 mm track along the pin row, pad 1.2 mm from the pin, GND via below. C115 stays on B under it as the second capacitor, on the same pin-10 via. To make room, the R112 / R113 column moved +0.47 mm to x 14.27, the R118 column (both taps now on one x). BUF_OUT_T from R113 is 8.513 mm (was 8.708).
- **PDN-6:** C616 (2.2u, moved) sits top side beside C108 and is tied to its +5V pad with 0.5 mm copper. GND via above.
- **PDN-7 / BIASTEE-2:** C606 / C622 (100n, moved) sit beside C404 / C409 at the U401 / U402 VCC pins: pin 1 -> 1 nF -> 100 nF -> via pair (now 1.55 / 2.07 mm from the 1 nF) -> 10 uF on B below the pair. The tee cold pads keep C403 / C408 (100n, same net and value). The schematic names the cold-pad capacitor C432 / C433 and the VCC 100 nF C403 / C408. That is a reference swap only; it is recorded here for the schematic owner (swap the refs) and not changed in the layout, because C432 / C433 belong to the pstrobe block.
- **BIASTEE-6:** TP401 / TP402 vias moved out of the L401 / L402 pads: each via is now 0.75 mm beside the bead's cold pad (on its axis), 0.57 mm from the choke pad. The script check finds no via in any soldered pad. Two old near-misses were also fixed: C110 moved +0.1 mm and C116 / C111 moved +0.2 mm in y, so they clear the U102 / R107 vias.
- **PARTS-1:** R402 is now 0603 (netlist). It is lifted so that its courtyard sits on the series row's courtyard; the shunt stub is 1.125 mm (6.7 ps, R403 0.89 mm).
- **RF-6:** README and layout now agree. A pad cut clears L2, L3 and L4 under the pad (the integrated board did this already), so the cut part sees L5. The cut length along the line is sized so that the pad's excess C is 0 (the remaining pad length stays over L2): 0402 pads 0.41-0.45 mm, T401 0.52, R402 0.70 mm.
- **RF-5 / RF-7:** nothing to change in this block. The BUF_OUT_T / PH_STROBE_P parallel run (board y 22.35 / 22.85) and the +2V5 via (9.32, 24.70) lie south of the block (board route / phase). The S_STROBE_N pour gap (56.40, 8.21) is in the fpga block. The block's own S_STROBE_N stub keeps a pour gap of 2 w or more (check_board 0).

## Interface changes (24 Nov 2026)
- Interface positions are unchanged (`analog.ifaces.json` is identical).
- New refs in this block: C606, C614, C616 and C622 (power sheet, placed at their loads). **The power block must stop placing them.** It currently places them at power-block positions.
- The pad cuts are rule areas on In1, In2 and In3 (L2 / L3 / L4); before, they were In1 plus a track-only area on In2. The block's In3 (L4) rule areas must survive the merge. With `layer_map=None` they do.

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
| STRB_A / STRB_K arms (C201/C202 -> R204 -> T401) | equal, mirrored | 17.827 / 17.827 (mismatch 0) | 105.6 / 105.6 |
| TL401 shorted stub (tap -> NT401 pad 1) + via short | 80.0 ps | 12.838 + 3.9 ps end | 76.1 + 3.9 = 80.0 |
| BUF_OUT_T R113 -> S boundary | - | 8.513 | 50.4 |
| CLIP balun -> tap -> C410; clamp tap | short | 2.965; 0.40 | 17.6; 2.4 |
| TRF2/TRF1 OUT (C -> bead -> pin 7) | short | 2.02 / 2.02 | 12.0 |
| TRF RFIN pin 2 -> 100 nF | short | 1.08 / 1.08 | 6.4 |
| 12 dB pad series 1.01 + 1.01, shunt stubs 0.89 (R403) / 1.125 (R402 0603) | short | | 6.0 / 5.3 / 6.7 |
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

Pad compensation (RF-6, 24 Nov): every in-line RF pad whose excess C over L2 (pad vs. 0.16 mm line over the pad length) exceeds 30 fF gets a cut on L2, L3 and L4 (rule area In1 / In2 / In3). The cut part of the pad sees L5 at 1.354 mm. The cut is the full pad width across the line and is shortened along the line so that the excess is 0 fF (the pad ends stay over L2). Excess before the cut and cut length: 0402 R +99 fF, 0.41 mm; 0402 C +99 fF, 0.42; FB401/402 +105 fF, 0.47; D201/D202 rails +93 fF, 0.36; D201.3 +78 fF, 0.45; T401.1/2/4 +102 fF, 0.52; D401.1 +67 fF, 0.38; R402 (0603) +240 fF, 0.70; C101.1 +95 fF, 0.45. Not cut: U401/U402 pins 2/7 (+18 fF), U101.11 (+29 fF) and NT401.1 (shorted stub end). The model is the microstrip formula per section, without fringing at the cut edges. The script prints the full per-pad table.

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
- T401 uses the netlist land (Coilcraft 0805USB, 1/4 | 2/3). Since 24 Nov both arms pass R204 on the axis and enter T401 through the 0.91 mm gap between its pad columns. They are mirror images except for the last 0.38 mm (see Changes).
- Added from membership "pstrobe": C402-C404 and C407-C409 (U401 / U402 decoupling, as in sim/bias_tee). J102 / R122 stay with phase.
- Local helpers: Frame.place (Block.place side="B" segfaults in pcbnew 7.0.11), pad_escape / split_at_pads (pad-axis exits), strip_silk_over_pads (4 library silk segments over neighbouring pads were removed), courtyard_overlaps, and a render crop offset.
- Block GND zones are on In1 / F / B with the fragment cut-outs. merge(skip_planes=True) would lose the In1 cut-outs.
## Open points
- Balun pin map (Murata DLW21SN vs Coilcraft land): fix this in the schematic / footprint. R201 -> D201.3 is 3.12 mm.
- Integrator: GND stitching, the In2 partition, and the BUF_OUT_T and S_STROBE pair routing. kicad-cli 7 has no DRC / ERC, so the nightly DRC was used.
- Phase two: the slow interfaces (VOFS, VNEG_REF, VBIAS_A/K, ADC_IN, ADC_REF_MID) still leave on B.Cu (L6) columns at the S edge, as in phase one; rule 10 wants bias on L3 -> integrator via to L3 at the boundary, or a later block change.
- The strobe arms are now 105.6 ps (sim/strobe_arms used 99 ps). Re-run sim/strobe_arms with 105.6 ps arms and the symmetric R204; then set the per-board bias trim from that. Expect a slightly wider aperture than the 100 ps at +/-1.3 V.
- The pad-cut sizing (0 fF) is a per-section microstrip estimate. A field solver or TDR on the first board would confirm it.
- NT402 / NT403 (pstrobe) still need the same stub-end recipe (RF-2). The C403 / C408 <-> C432 / C433 reference swap needs a decision from the schematic owner.
