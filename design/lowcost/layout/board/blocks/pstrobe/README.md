# Block "pstrobe": chains A (PH_STROBE_P -> R407 -> PSTRB_A) and K (PH_STROBE_N -> R411 -> PSTRB_K), six-layer
`python3 gen_pstrobe.py [--norender]` (BL_STACKUP=6L, native 6-layer file; merge with `layer_map=None`). Outputs: `pstrobe.kicad_pcb`, `.ifaces.json`, `pstrobe.png`, `pstrobe_detail.png` (L1 red + L6 blue, inputs), `pstrobe_detail_L1L2.png`. Block 17 x 25 mm at board (9.5, 25.0); local = board - (9.5, 25.0); axis y 12.5; corridor y 9.5..15.5 (phase).
Chain (each): 47 R -> 100 nF -> TRF37D73 + bias tee (bead on line, 47 uH 1210 on B beside the bead via, L4 via pair at cold cap) -> U-folded 10 dB pi pad (first shunt 0603) -> GVA-84+ + bias tee (2.2 uH on B beside the bead via, 1 nF + 100 nF at the cold pad, +5V1 via pair at the 100 nF) -> 100 nF -> launch T: 80 ps shorted stub (NT, GND via in NT pad 2 + one beside), DNP BAT15, output E. L6 under the chokes carries nothing else.

## Validation and netlist changes (24 Nov 2026)
Outline and interface positions are unchanged. The supply interface `VBUS` is renamed **`/+5V1`**: the GVA-84+ tees, C418-C420 and C428-C430 are on +5V1 (TPS63802) in the netlist.
- **Netlist:** R408 / R412 (first pi-pad shunts) are 0603.
  - The shunt goes 0.53 mm higher in the U. The second shunt moved 0.18 mm east, and its node track drops into series pad 2.
  - C417 / C427 moved 0.5 mm east (the U is 0.45 mm wider).
  - The shunt GND vias sit east of their pads (clear of the choke on B).
  - Chain lengths to TRF pin 2, the stub and the output are unchanged.
- **BIASTEE-4:**
  - Both cold ends are now identical (mirror): L404 / L406 cold pad -> C418 / C428 1 nF on the pad's row -> C419 / C429 100 nF below it.
  - Each cap has its own GND via, none in a pad.
  - +5V1 enters through the 100 nF: a via pair 0.3 mm from its pad.
  - The 100 nF moved from the bulk group, so C420 / C430 10 uF stay below the GVA with their own via pair.
  - Integrator: chain A's cold-end via pair (board 23.05 / 23.70, 27.40) must be fed on L4, and not removed as dangling as the old VBUS pair was.
- **BIASTEE-6:** no via in a choke pad any more.
  - L403 / L405 moved 1.0 mm east: 0.15 mm from the bead via to pad 1, with a B track into the pad. R417 / R418, C434 / C435, C432 / C433 and TP403 / TP405 moved with them.
  - The GVA tab vias moved to the east half of the tab.
  - L404 / L406 stand 1.25 mm east of their bead via: 0.43 mm gap and a B track. TP404 / TP406 are below the choke pad.
- **RF-2:** each shorted end now has a GND via in NT pad 2 (net-tie pads have no paste) plus a second via 0.6 mm west.
  - The remaining short (1.0 mm tie bar, 0.5 mm wide over L2: 155 pH, plus the L1-L2 via: 48 pH) is 4.06 ps at 50 R.
  - The drawn stub is shortened to **12.817 mm (75.94 ps)**, so the stub is **80.00 ps** electrically, the same in A and K.
  - NT401 (analog block) should get the same treatment.

**Interface changes:** the supply iface `VBUS` is now `/+5V1` (same In3 / L4 via-pair landing, plane-fed). No position, layer or width changed.

## Impedance (L1 over L2 3313 0.0994 mm er 4.1, mask corrected; L6 over L5 identical)
| w mm | Z0 R | ps/mm | use |
|---|---|---|---|
| **0.16** | **50.2** | **5.925** | all RF on L1 and the PH_STROBE L6 sections (computed 0.161) |
Pad compensation (excess C vs. 0.16 mm line, L2 cut + L3 no-track/no-via area if > 30 fF; no L4 zone in the block): 0402 C +98.5 -> -18.6 fF; 0402 R +93..99 -> -17..-25; beads +108 -> -19; GVA pins +387 -> +9.5; BAT15 +67 -> -27; TRF pins 2/7 +17.6 fF, no cut.

## Lengths (5.925 ps/mm; vias: 2 per input path, both alike)
| route | A mm | K mm | note |
|---|---|---|---|
| stub TL402 / TL403 (node -> NT pad 1) | 12.817 | 12.817 | 75.94 ps drawn + 4.06 ps short = 80.00 ps |
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
| +3V3, /+5V1 | via pairs | - | In3 (L4), plane-fed |

## Checks
check_board (24 Nov): 0 missing/extra/footprint/value/pad-net, 0 clearance, 0 corners, 0 off-axis exits, 0 RF width, 0 RF pour gap, 0 courtyard overlaps; unrouted only +3V3 (3), /+5V1 (3), GND (1, A/K islands joined by the board plane).
Nightly DRC jlc4 (24 Nov): `total 70: error 8, warning 62`: 7 unconnected (plane-fed), 12 via_dangling (L4 supply vias), 4 track_dangling (interface stubs), 1 invalid_outline, 46 lib_footprint_*. 0 courtyard/clearance/width/hole/silk. Renders `pstrobe.png`, `pstrobe_detail.png` looked at.

## GVA-84+ drain feed resistors (24 Nov 2026, SPEC decision 26)
+5V1 is 5.40 V now, so each chain gets a series 2.49 R 0402 (R419 chain A, R420 chain K) between the 10 uF (C420 / C430,
own +5V1 via pair) and the cold-end node (C419 100 nF, C418 1 nF, choke cold pad): supply -> 10 uF -> 2.49 R -> 100 nF /
1 nF -> choke (rule 7: the node still enters through C419). Placement, B side: R419 centre (13.95, 2.845) local, 0.5 mm
west of the C419 column and 1.18 mm below it (0.24 mm courtyard gap) so its node pad clears the bead via (0.165 mm); node
track C419 pad -> down 0.325 -> 45 deg -> down into the R pad (0.4 mm); +5V1 track (0.5 mm) R pad -> down -> 45 deg ->
into the C420 pad from the north, clear of C432's GND via. The +5V1 via pair that sat beside C419 is removed. K mirrored.
check_board 0 apart from the plane-fed interfaces; via_in_pad FAIL 0; RF geometry unchanged (stub, output, input lengths
as before).

## Deviations / open points
- Mirror: everything is mirrored except the TRF37D73 and GVA-84+ bodies (chiral) and the **chain-A input leg**. R407 is horizontal under U403 and C412 sits below the line, because the north edge now carries both entries. The mirror spot in K is taken by the TRF pin-1 caps and their GND vias (the TRF is not mirrored). The K leg keeps its column toward the S edge. Lumped parts; the electrical length to TRF pin 2 is equal.
- The spare 100 nF C432 / C433 is on B under C434 / C435, with its own GND via, to free the west L6 strip.
- K's via pair at y 24.6 lies 0.18 mm inside the S edge. The PH_STROBE pair arrives at y ~23 through the phase block's strip (board y 22.5..25), which is the integrator's job.
- Unchanged open points: the GVA-84+ land was not checked against the datasheet. The stub keep-out reaches 0.18 mm into the corridor. Phase C346 touches the NE corner.

**Vias out of pads (24 Nov, RULES rule 12):** C413 / C423 (10 uF, B) lie horizontal off the 0402 GND vias, their +3V3 via pairs north of them; K-chain GVA tab vias in one column west of C430; C420 / C430 and C434 / C435 GND vias, R408 / R412 GND vias off their pads. `python3 ../../via_in_pad.py pstrobe.kicad_pcb`: FAIL 0.
