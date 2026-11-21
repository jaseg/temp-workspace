# Block "pstrobe": phase-strobe chains A (PH_STROBE_P -> PSTRB_A) and K (PH_STROBE_N -> PSTRB_K)
Run `python3 gen_pstrobe.py [--norender]`. It writes `pstrobe.kicad_pcb`, `pstrobe.ifaces.json`, `pstrobe.png` and `pstrobe_detail.png` (TRF + pi pad of chain A). KiCad 7.0.11 + nightly DRC (`tools/run_drc.sh --rules jlc4`).
**Size: 17 x 25 mm at board (9.5, 25.0).** FLOORPLAN gave 17 x 23 at (9.5, 26.0), so the block grew 1 mm N and 1 mm S. The reason is the GVA-84+ (SOT-89): it cannot be mirrored, and in K its tab and courtyard face the axis. The phase corridor (board y 34.5-40.5) is kept free.
Chain (each): 47 R + 100 nF on the input leg -> TRF37D73 -> bead on the corner (+ 47 uH 1210 || 1 k, cold-pad 100 nF on B) -> **U-folded** 100 nF / 68 R (shunts 100 R inside the U) / 100 nF -> GVA-84+ -> bead on the corner (+ 2.2 uH 0805 on B to VBUS, 1 nF at the cold pad) -> 100 nF down the output column -> launch node: 80 ps shorted stub west + DNP BAT15 beside the column -> output E.
The fold and the input leg are needed because no two courtyards on the same side may overlap. Inline, the chain would need 22 mm.
## Checks
- check_board (56 refs: pstrobe membership minus C402-C404 / C407-C409, which the analog block placed): 0 missing / extra / footprint / value / pad-net / no-net, 0 clearance, 0 corners > 45 deg, 0 off-axis pad exits, 0 RF width, 0 RF pour gap. The only unrouted nets are +3V3 (3) and VBUS (3), which are plane-fed (In2 via pairs), and GND (1): the A / K In1 islands are joined by the board plane.
- Courtyard overlaps (scripted, BooleanIntersection > 0.005 mm2): **0**. TL402/403 and NT402/403 have no courtyard.
- Nightly DRC (jlc4): 70 items. 7 unconnected_items (the plane-fed supply and GND nets above), 12 via_dangling (+3V3 / VBUS plane via pairs, which wait for In2), 4 track_dangling (the 4 interface stubs), 1 invalid_outline (blocks have no Edge.Cuts), 46 library artefacts (42 lib_footprint_mismatch, 4 lib_footprint_issues). 0 courtyard, clearance, track-width, hole, silk or text violations. Reference designators are on F.Fab / B.Fab, because 0.8 mm silk text does not fit.
## RF lengths (0.36 mm, 50 R, F.Cu, no vias in the signal path; A = K by construction, mismatch 0.000 mm)
| route | mm | ps |
|---|---|---|
| input: N edge (A) / S edge (K) -> 47 R | 1.020 | 6.2 |
| 47 R -> C -> TRF pin 2 (leg, 45-degree corner) | 0.88 + 1.67 | 15.4 |
| TRF pin 7 -> bead -> C416; pi pad in / out (U); shunt tees | 1.12 + 0.92; 1.45 / 1.45; 0.91 | 30.0 |
| C417 -> GVA pin 1; GVA pin 3 -> bead -> C421 | 3.12; 1.47 + 0.92 | 33.4 |
| **output: C421 / C431 pad -> node -> E edge (A = K)** | **5.401** | 32.7 |
| **stub TL402 / TL403, node -> NT pad 1, straight** | **13.207** | **80.0** |
## Interfaces (local mm; board = local + (9.5, 25.0))
| net | local x, y | board | layer | note |
|---|---|---|---|---|
| /PSTRB_A, /PSTRB_K | 17.0, 9.75 / 15.25 | 26.5, 34.75 / 40.25 | F.Cu E, rf50 | Meets the phase ifaces. The line arrives at 45 degrees. |
| /PH_STROBE_P | 0.52, 0 | 10.02, 25.0 | F.Cu N, pair | **Deviation**: FLOORPLAN had (24, 26.5). The input leg is at the NW corner. |
| /PH_STROBE_N | 0.52, 25 | 10.02, 50.0 | F.Cu S, pair | Mirror of P. The integrator must match the P/N lengths up to these points. |
| +3V3, VBUS | via pairs | x 0-10 / x 9-14 | In2 | +3V3: TRF VCC (C415 / C414 on F, C413 10 uF + C432 / C433 spare on B), cold caps C434 / C435. VBUS: C418 / C428, C419 + C420 / C429 + C430. |
## Deviations
- **Mirror symmetry**: every 2-pin part, track, via and stub comes from `chain(s)`, mirrored about y = 12.5. The TRF37D73 (rot 0) and GVA-84+ (rot 90) are not mirrored, because their pin-outs are chiral. Their RF pins sit on the mirrored line points. TRF VCC parts follow pin 1, so they are north in both chains.
- The bias-tee chokes, cold caps and 1 k are on B.Cu, in a straight chain behind a via at the bead's pad 2. The beads stay on top, with pad 1 on the line corner.
- The clamp pad is 1.42 mm (8.6 ps) from the launch node, on the output row. It is DNP.
- **Local helpers**: `bplace` (B placement + flip), `two`, `snap`, `render` (crop offset) and `courtyard_overlaps`. boardlib.py is not edited.
## Open points
- The GVA-84+ land was not checked online (minicircuits.com returned 403 earlier). The script uses KiCad SOT-89-3: pin 1 RF in, 2 / tab GND (4 vias), pin 3 RF out + bias. Bias: VBUS -> bead -> 2.2 uH, so Vd ≈ VBUS - 0.15 V, which is below 4.8 V on a 4.75 V USB supply (sim/bias_tee).
- The stub keep-out (2 w) still reaches 0.9 mm into the phase corridor (board y 34.5-35.4 / 39.6-40.5). The integrator must keep the F.Cu GND pour out of it.
- The phase part C346 sits at board (26.24-27.16, 23.8-25.6) and touches this block's NE corner on F. Nothing of pstrobe is there.
