# Block "pstrobe": phase-strobe chains A (PH_STROBE_P -> PSTRB_A) and K (PH_STROBE_N -> PSTRB_K)
Run `python3 gen_pstrobe.py [--norender]`. It writes `pstrobe.kicad_pcb`, `pstrobe.ifaces.json`, `pstrobe.png`, `pstrobe_detail.png` (TRF + pi pad of chain A) and `pstrobe_detail_L1L2.png` (chain A, F.Cu + In1). KiCad 7.0.11 + nightly DRC (`tools/run_drc.sh --rules jlc4`; the limits are the same for 6 layers).

**Phase two (6-layer, JLC06161H-3313).** The script sets `BL_STACKUP=6L`, so the file is a native 6-layer board: In1 = L2 GND, In2 = L3 (slow), In3 = L4 (power), In4 = L5. The supply interfaces are on In3 (L4). **Merge with `layer_map=None`**, as for the analog block. `LAYER_MAP_4TO6` would move the L3 rule areas under the pad cuts onto L4.
Placement, references, nets and all four signal interface positions are unchanged. No interface moved. Only the width (0.36 -> 0.16 mm) and the supply landing layer (In2 -> In3) changed.

**Size: 17 x 25 mm at board (9.5, 25.0).** FLOORPLAN gave 17 x 23 at (9.5, 26.0), so the block grew 1 mm N and 1 mm S. The reason is the GVA-84+ (SOT-89): it cannot be mirrored, and in K its tab and courtyard face the axis. The phase corridor (board y 34.5-40.5) is kept free.

Chain (each): 47 R + 100 nF on the input leg -> TRF37D73 -> bead on the corner (+ 47 uH 1210 || 1 k, cold-pad 100 nF on B) -> **U-folded** 100 nF / 68 R (shunts 100 R inside the U) / 100 nF -> GVA-84+ -> bead on the corner (+ 2.2 uH 0805 on B to VBUS, 1 nF at the cold pad) -> 100 nF down the output column -> launch node: 80 ps shorted stub west + DNP BAT15 beside the column -> output E.

The fold and the input leg are needed because no two courtyards on the same side may overlap. Inline, the chain would need 22 mm.

## Impedance (L1 over L2: 3313 prepreg 0.0994 mm, er 4.1, solder mask corrected; L6 over L5 is the same)
50 R: computed width 0.161 mm, drawn **0.16 mm = 50.2 R**. RULES says "about 0.17". boardlib gives 0.161, and a 0.17 mm line would be 48.7 R.

| w mm | Z0 R | eps_eff | ps/mm | fF/mm |
|---|---|---|---|---|
| 0.10 | 62.0 | 3.040 | 5.816 | 94 |
| **0.16** | **50.2** | **3.155** | **5.925** | **118** |
| 0.25 | 39.4 | 3.275 | 6.037 | 153 |
| 0.36 (old 4L width) | 31.4 | 3.380 | 6.132 | 196 |

## Geometry changes for 6L
- All RF tracks are 0.16 mm. The RF pour gap is 2 w + 0.03 = 0.35 mm. Necks: none. 0.16 mm is narrower than every pad it meets: 0402 0.54-0.64, WSON pins 0.25, SOT-89 pins 0.9, SOD-323 0.45. All pad exits are on-axis.
- **Stubs TL402 / TL403:** 80 ps / 5.925 ps/mm = **13.503 mm** (4L: 13.207 mm). They are 0.30 mm longer and still straight.
  - The net tie NT402 / NT403 now stands across the stub end: pad 1 is on the stub end, and pad 2 plus its two GND vias are towards the line, at local x 1.10, y 6.9-8.3 (mirror for K).
  - In-line, pad 2 and the vias would have landed at x 0.10, off the block edge.
- **Launch node:** now a T at (14.6, 9.25 / 15.75). The drop from C421 / C431 arrives from the north, the stub leaves west and the output leaves east. The old 0.3 mm chamfer at the node left the 0.16 mm stub start 0.21 mm away from the line copper, so it was disconnected.
- **Pad compensation**, the same method as the analog block. Every in-line RF pad whose excess C over L2 is above 30 fF gets an L2 (In1) cut the size of the pad. The excess C is measured against the 0.16 mm line over the pad length.
  - Under the cut, L3 keeps its GND pour. A no-track / no-via rule area on In2 keeps it free, so the pad sees L3 at 0.665 mm.

| pad | excess over L2 | action | after |
|---|---|---|---|
| 0402 C (C412/416/417/421, C422/426/427/431, both pads) | +98.5 fF | L2 cut | -18.6 fF |
| 0402 R in-line (R407, R411 both; R410/R414 series both; shunt hot pads R408/409/412/413) | +93 to +99 fF | L2 cut | -17 to -25 fF |
| beads FB403-406 pad 1 (line corner) | +108 fF | L2 cut | -19 fF |
| GVA-84+ U404/U406 pins 1 / 3 | +387 fF | L2 cut | +9.5 fF |
| D402.1 / D403.2 (DNP clamp) | +67 fF | L2 cut | -27 fF |
| TRF37D73 U403/U405 pins 2 / 7 | +17.6 fF | none (< 30 fF) | +17.6 fF |

## Lengths, intended vs actual (6L, 5.925 ps/mm; A = K by construction)
| route | intended | drawn mm | ps |
|---|---|---|---|
| input: N edge (A) / S edge (K) -> 47 R | short | 1.020 | 6.0 |
| 47 R -> C -> TRF pin 2 | short | 0.88 + 1.673 | 15.1 |
| TRF pin 7 -> bead -> C416; pi pad in / out; shunt tees | short | 1.12 + 0.92; 1.454 / 1.454; 0.91 | 12.1; 8.6; 5.4 |
| C417 -> GVA pin 1; GVA pin 3 -> bead -> C421 | short | 3.124; 1.47 + 0.92 | 18.5; 14.2 |
| **output: C421 / C431 pad -> node -> E edge** | **A = K** | **2.970 + 2.607 = 5.577 (mismatch 0.0 um)** | **33.0** |
| **stub TL402 / TL403, node -> NT pad 1** | **80.0 ps = 13.503 mm** | **13.503** | **80.00** |

## Checks (6L)
- check_board (56 refs: the pstrobe membership minus C402-C404 / C407-C409, which the analog block placed): 0 missing / extra / footprint / value / pad-net / no-net, 0 clearance, 0 corners > 45 deg, 0 off-axis pad exits, 0 RF width, 0 RF pour gap, 0 courtyard overlaps.
  - The only unrouted nets are the plane-fed ones: +3V3 (3) and VBUS (3), fed by L4 via pairs, and GND (1), whose A / K In1 islands are joined by the board plane.
- Nightly DRC (jlc4): `total 70: error 8, warning 62`. The breakdown:
  - 7 unconnected_items: +3V3 3, VBUS 3, GND 1, all plane-fed.
  - 12 via_dangling: the +3V3 / VBUS via pairs that land on L4.
  - 4 track_dangling: the 4 interface stubs.
  - 1 invalid_outline: a block has no Edge.Cuts.
  - 46 library artefacts: 42 lib_footprint_mismatch, 4 lib_footprint_issues.
  - 0 courtyard, clearance, track-width, hole or silk violations.

## Interfaces (local mm; board = local + (9.5, 25.0)); none moved in phase two
| net | local x, y | board | layer | note |
|---|---|---|---|---|
| /PSTRB_A, /PSTRB_K | 17.0, 9.75 / 15.25 | 26.5, 34.75 / 40.25 | F.Cu E, rf50, 0.16 | Meets the phase interfaces. The phase block necks to 0.10 at x 26.5. |
| /PH_STROBE_P | 0.52, 0 | 10.02, 25.0 | F.Cu N, pair, 0.16 | |
| /PH_STROBE_N | 0.52, 25 | 10.02, 50.0 | F.Cu S, pair, 0.16 | Mirror of P. The integrator matches the P/N lengths. |
| +3V3, VBUS | via pairs | x 0-12 / x 9-15 | **In3 (L4)** | Plane-fed |

## Deviations / notes
- **Mirror symmetry**: every 2-pin part, track, via, stub, pad cut and net tie comes from `chain(s)`, mirrored about y = 12.5. The TRF37D73 (rot 0) and GVA-84+ (rot 90) are not mirrored, because their pin-outs are chiral. Their RF pins sit on the mirrored line points.
- Bias tees are unchanged: bead pad on the line, straight chain on B.Cu behind a via, cold-pad decoupling, and the supply enters through the capacitor.
- The local helpers are `bplace`, `two`, `snap`, `render`, `courtyard_overlaps`, `c_mm` and `_pad_axis`. boardlib.py is not edited.
- Open from phase one:
  - The GVA-84+ land was not checked against the datasheet.
  - The stub / output keep-out still reaches into the phase corridor, now by 0.18 mm (was 0.9 mm). It reaches board y 34.5-34.68 and 40.32-40.5. The integrator keeps the F.Cu pour out there.
  - The phase part C346 touches the NE corner.
