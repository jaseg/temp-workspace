# Block "pstrobe": chains A (PH_STROBE_P -> R407 -> PSTRB_A) and K (PH_STROBE_N -> R411 -> PSTRB_K), six-layer
`python3 gen_pstrobe.py [--norender]` (BL_STACKUP=6L, native 6-layer file; merge with `layer_map=None`). Outputs: `pstrobe.kicad_pcb`, `.ifaces.json`, `pstrobe.png`, `pstrobe_detail.png` (L1 red + L6 blue, inputs), `pstrobe_detail_L1L2.png`. Block 17 x 25 mm at board (9.5, 25.0); local = board - (9.5, 25.0); axis y 12.5; corridor y 9.5..15.5 (phase).
Chain (each): 47 R -> 100 nF -> TRF37D73 + bias tee (bead on line, 47 uH 1210 on B behind a via, L4 via pair at cold cap) -> U-folded 10 dB pi pad -> GVA-84+ + bias tee (2.2 uH on B, VBUS L4 via pair at 1 nF) -> 100 nF -> launch T: 80 ps shorted stub (NT + 2 GND vias), DNP BAT15, output E. L6 under the chokes carries nothing else.

## Impedance (L1 over L2 3313 0.0994 mm er 4.1, mask corrected; L6 over L5 identical)
| w mm | Z0 R | ps/mm | use |
|---|---|---|---|
| **0.16** | **50.2** | **5.925** | all RF on L1 and the PH_STROBE L6 sections (computed 0.161) |
Pad compensation (excess C vs. 0.16 mm line, L2 cut + L3 no-track/no-via area if > 30 fF; no L4 zone in the block): 0402 C +98.5 -> -18.6 fF; 0402 R +93..99 -> -17..-25; beads +108 -> -19; GVA pins +387 -> +9.5; BAT15 +67 -> -27; TRF pins 2/7 +17.6 fF, no cut.

## Lengths (5.925 ps/mm; vias: 2 per input path, both alike)
| route | A mm | K mm | note |
|---|---|---|---|
| stub TL402 / TL403 (node -> NT pad 1) | 13.503 | 13.503 | 80.00 ps |
| output C421/C431 pad -> E edge | 5.577 | 5.577 | 0.0 um mismatch |
| PH_STROBE L1 entry (N edge -> dive via) | 1.557 | 0.450 | |
| PH_STROBE L6 | 24.969 | 26.889 | K under the corridor at x 2.37; A serpentine (7 legs, gap 0.54) |
| L1 return (via -> 47 R pad) | 0.640 | 0.620 | |
| = edge -> 47 R | 27.166 | 27.959 | |
| + leg 47 R -> C -> TRF pin 2 | 3.346 | 2.553 | legs differ (see deviations) |
| **= edge -> TRF pin 2** | **30.512** | **30.512** | **180.77 ps, mismatch 0.0 um** (solved) |
Both: L1 -> via (+GND via) -> L6 over L5 -> via (+GND via) -> L1 -> 47 R. K's L6 path: down the west strip at x 0.45, 45° to x 2.37, under the corridor in the B.Cu channel between the phase block's C309 / GND vias (end x 1.79) and L302 pad 2 (starts x 2.95), then west at y 16.25 and down x 0.52 to its via at (0.52, 24.6) south of R411. Signal vias: A (1.00, 1.35) / (3.45, 6.4); K (1.10, 0.45) / (0.52, 24.6); GND vias (1.60, 0.95), (4.10, 6.4), (1.70, 0.45), (1.15, 24.6).

## Interfaces
| net | local | board | layer / class |
|---|---|---|---|
| /PH_STROBE_P | 0.50, 0 | **10.00, 25.00** | F.Cu N, pair 0.16 (U501 pin 40) |
| /PH_STROBE_N | 1.10, 0 | **10.60, 25.00** | F.Cu N, pair 0.16 (U501 pin 39) |
| /PSTRB_A, /PSTRB_K | 17.0, 9.75 / 15.25 | 26.5, 34.75 / 40.25 | F.Cu E, rf50 0.16 (meets phase) |
| +3V3, VBUS | via pairs | - | In3 (L4), plane-fed |

## Checks
check_board: 0 missing/extra/footprint/value/pad-net, 0 clearance, 0 corners, 0 off-axis exits, 0 RF width, 0 RF pour gap, 0 courtyard overlaps; unrouted only +3V3 (3), VBUS (3), GND (1, A/K islands joined by the board plane).
Nightly DRC jlc4: `total 70: error 8, warning 62`: 7 unconnected (plane-fed), 12 via_dangling (L4 supply vias), 4 track_dangling (interface stubs), 1 invalid_outline, 46 lib_footprint_*. 0 courtyard/clearance/width/hole/silk.

## Deviations / open points
- Mirror: everything is mirrored except the TRF37D73 and GVA-84+ bodies (chiral) and the **chain-A input leg**. R407 is horizontal under U403 and C412 sits below the line, because the north edge now carries both entries. The mirror spot in K is taken by the TRF pin-1 caps and their GND vias (the TRF is not mirrored). The K leg keeps its column toward the S edge. Lumped parts; the electrical length to TRF pin 2 is equal.
- The spare 100 nF C432 / C433 moved onto B under C434 / C435, with its own GND via, to free the west L6 strip.
- K's via pair at y 24.6 lies 0.18 mm inside the S edge. The PH_STROBE pair arrives at y ~23 through the phase block's strip (board y 22.5..25), which is the integrator's job.
- Unchanged open points: the GVA-84+ land was not checked against the datasheet. The stub keep-out reaches 0.18 mm into the corridor. Phase C346 touches the NE corner.
