# Block "power": USB-C, protection, TPS62A01A x2, TPS63802, LM27762 x2 (refs 6xx, 61 parts, both sides)
Run `python3 gen_power.py [--norender]` -> `power.kicad_pcb`, `power.ifaces.json`, `power.png` (F), `power_b.png` (B),
`power_detail.png` (U603 / L601). KiCad 7.0.11; DRC with the nightly (`tools/run_drc.sh --rules jlc4`).
Power tree: `docs/research/power-tree.md` (24 Nov 2026). **Size 26.0 x 22.5 mm at board (74, 0), unchanged.** J601, U608,
F601, D601, FB601, R601 / R602 and the USB pair are unchanged. M3 hole (97, 3): 3.5 mm keep-out (F, In1, In2, B).

## Placement (local mm)
| cell | side | where | layout (datasheet layout section) |
|---|---|---|---|
| U601 TPS62A01A VBUS -> +3V3 | F | x 0-9.5, y 0-8 | C603 10u straddles VIN (3) / GND (1) on the IC layer; SW (2) leaves between the C603 pads (0.9 mm gap, 0.35 mm track, 3.9 mm) to L602; **C604 (COUT) directly under C603** (courtyards touching C603 / U601 / L602): VOUT pad against L602 pad 2, GND pad straight under pin 1 / the C603 GND pad; plane vias at the capacitors only (GND east of the C603 GND pad and under the C604 GND pad, +3V3 pair behind C604); R609 / R610 / C631 at FB (5) |
| U602 TPS62A01A +3V3 -> +1V2 | B | mirror image of U601, under it | C609 / C607 at VIN fed by a +3V3 (L4) via behind C609; L603, C605 (under C609) + C608 at the output, +1V2 via (1.0, 7.9) behind C608 |
| U603 TPS63802 VBUS -> +5V1 | F | x 9.5-18, y 0-12 | (TIGHTEN, 24 Nov, datasheet 12.2 layout example) chip at x 11.35; L601 against L1 (9) / L2 (7) (courtyards touching); C601 courtyard on the chip's north edge, C610 on its south edge (0.0 mm, also touching L601 / L602), VBUS / +5V1 pad straight above VIN (10) / below VOUT (6) (0.93 mm pad to pin), GND pads west, returned to PGND (8) through a 0.45 mm GND channel between the two pin columns; C611 stacked under C610. Vias only at the capacitors: VBUS x 3 behind C601 (north-east), +5V1 x 2 behind C611 (south), GND west of C601 / C610 and south of C611; none at the pins or under L601 (PGND copper under L601 kept, no vias). EN / MODE tied to VBUS through In2; FB through In2 to R603 / R604 east of C611 (away from L1 / L2); PG via In2 as before |
| U604 LM27762 +5V1F -> +5V / -5V | F | x 0-8, y 7.9-15.6, chip (4.8, 11.65) | C613 100n + C612 22u at VIN (3) / GND (4) on the IC layer (DECOUPLING-4); C626 CCP at CP (5); C618 C1 at pins 10 / 9; **C617 COUT+ north (courtyard on the chip's, OUT+ pad 1.13 mm from pin 11) -> FB604 (vertical, NE) -> +5V via behind the bead; C621 COUT- vertical under the chip (OUT- pad 0.63 mm from pin 6), rail via east of its pad**; FB dividers R613 / R614 (FB+) and R605 / R606 (FB-) on **B** under the cell (FB vias at the pins: signal ties, no current); EP 2 vias |
| U605 LM27762 +3V3_CP -> +/-2V5 | F | x 0-8, y 15.6-22.4, chip (4.8, 18.55) | C625 CIN, C619 CCP, C624 C1; **C630 COUT+ vertical east of C621 (pad 0.66 mm from pin 11), C628 COUT- under the chip (0.75 mm from pin 6)**, rail vias behind both; R615 / R616 (FB+) on F north of C625 (OUT+ sense from behind C630 through In2), R607 / R608 (FB-) on B |
| beads | B / F | under the LM27762 cells | FB602 / FB603 / C627 / FB605 / R617 / C629 / FB607 / FB606 on B; FB604 on F |
| C632 47u (damper, **fitted** since recheck RP-3) | B | (15.2, 6.0), VBUS pad on the B VBUS strip (moved off the C601 via area), GND via east | |
Not placed here: C606, C614, C616, C622 (analog block) and C615, C620 (phase block), placed at their loads per
kicad/README.md; `floorplan.PLACED_IN` now maps them to those blocks.

## Supply paths
- VBUS: FB601 -> vias (14.0, 17.4 / 18.3) -> B strip (1.1-1.4 mm, x 13-14.2) -> 3 vias (13.0, 0.65-1.95) behind C601 ->
  F polygon over the C601 VBUS pad -> U603 VIN (10), and along the top edge (widened to y 2.05 over L602) to C603 ->
  U601 VIN (3).
- +5V1: VOUT (6) -> C610 / C611 +5V1 pads -> 2 vias (12.4, 10.95 / 11.65) behind C611 -> B strip (x 12.6) -> FB602 (B)
  -> +5V1F to U604 VIN / EN+ / EN- (B 0.4 mm); GVA-84+ feed: the B strip south to the via pair (12.3, 20.9 / 21.7).
- +3V3: L602 -> C604 -> 2 vias behind C604 (6.35 / 7.0, 6.95) to the L4 plane; U602 takes its input from L4 through the
  via (3.6, 0.9) behind C609 (the block carries an L4 +3V3 stand-in zone, removed at merge).
- In2 (slow / static layer, rule 10) carries two block-internal lines: +1V2 sense R611 -> (8.0, 1.2) -> top edge y 0.4 ->
  x 0.5 -> (1.0, 7.9); PG_5V1 U603.5 -> (9.6, 6.15) -> x 8.3 -> (7.9, 18.6);
  U603 FB (9.65, 5.4) -> x 10.15 -> y 10.45 -> (14.71, 9.94); U603 EN / MODE VBUS tie (9.6, 4.15) -> (13.0, 1.95). The integrator's L3 copper must avoid them.

## Regulator input headroom (layout drops included)
| | Vin at the pin | needed | margin |
|---|---|---|---|
| U601 +3V3 0.67 A | 4.59-5.25 V (VBUS minus 5 mV B strip) | 3.53 V (100 % mode) | >= 1.06 V |
| U602 +1V2 30 mA | 3.21-3.42 V (1 % divider) | 1.2 V + 0.03 V | >= 2.0 V |
| U603 +5V1 0.34 A | 4.59-5.25 V | buck-boost, any VIN 2.3-5.5 V | n/a |
| U604 +4.80 / -4.64 V 41 mA | 5.02-5.15 V after FB602 | 4.88 V (OUT+), 4.91-4.97 V (OUT-, RCP 4.5-5.5 R, recheck RP-2) | 0.14 V / 0.06-0.11 V (typ 0.26 V) |
| U605 +/-2.50 V 50 mA | 3.24-3.37 V after FB605 (8 mV) | 2.54 V / 2.82 V (RNEG 5 R assumed) | 0.70 V / 0.42 V |

## Interfaces (local mm; board = local + (74, 0))
| net | local x, y | layer | note |
|---|---|---|---|
| /USB_DP, /USB_DM | 8.6 / 9.0, 22.5 | F.Cu S, pair | unchanged |
| VBUS | 14.0, 17.85 | via pair | unchanged position; now feeds J501 pin 1 only |
| +3V3 | 6.68, 6.95 | via pair | U601 output (behind C604) |
| +5V | 8.05, 7.0 | via | FB604 output (REPAIR: was 9.05, 8.77) |
| -5V | 0.4, 13.6 | via | FB603 / C627 (REPAIR: was 0.45, 14.0) |
| +2V5 | 10.45, 15.3 | via | FB606 output |
| -2V5 | 0.6, 20.75 | via | FB607 / C629 |
| +1V2 | 1.0, 7.9 | via | C605 / C608 (B) |
| /+5V1 | 12.3, 21.3 | via pair (20.9 / 21.7) | NEW: GVA-84+ chokes L404.2 / L406.2, C418-C420 / C428-C430 (pstrobe), 0.34 A |

## Interface changes
- Moved (old -> new, local mm): +3V3 (0.45, 5.5) -> (8.72, 6.05); +5V (0.45, 12.6) -> (9.05, 8.77); -5V (15.72, 9.3) ->
  (0.45, 14.0); +2V5 (0.45, 16.2) -> (10.45, 15.3); -2V5 (9.75, 18.5) -> (0.6, 20.75); +1V2 (1.25, 21.95) -> (1.0, 7.9).
  Reason: new regulators and footprints; the old W-edge via positions sit under the LM27762 cells.
- New: /+5V1 at (12.3, 21.3) S. The board's old VBUS L3 / L4 run to the GVA chokes must carry /+5V1 instead
  (0.34 A, same width); VBUS to J501 only.
- In2 tracks inside the block (above). Hole keep-out now also on In2.

## Checks (24 Nov 2026, after TIGHTEN)
- check_board (61 refs): all 0, including unrouted (the L4 +3V3 stand-in zone joins the plane-fed +3V3 vias).
- Nightly DRC jlc4: 67 = 56 lib_footprint_mismatch + 2 lib_footprint_issues, 6 via_dangling (supply interface vias),
  2 track_dangling (USB pair ends at the S edge), 1 invalid_outline (no Edge.Cuts in a block); 0 unconnected, clearance,
  courtyard, hole, track-width, silk errors.
- Decoupling audit (`../../decap_audit.py`): every primary capacitor at its pin (U603 C601 / C610 0.93 mm pad to pin,
  courtyards 0.0 mm), no supply via between pin and capacitor, GND via <= 0.6 mm from each GND pad except C621 (B, 1.15 mm).
- Hot loops (pad-centre polygons, mm): U603 input VIN-C601-PGND 3.1 x 3.9 (11.2 mm2, return through two via pairs and
  the planes) -> 1.9 x 2.8 (2.8 mm2, all on L1); output VOUT-C610-PGND the same; U601 / U602 output loop
  SW-L-COUT-GND 4.35 x 4.05 -> 4.0 x 2.7 mm (COUT GND 1.4 mm from pin 1, was 3.6 mm); input loop (C603 straddle)
  1.6 x 1.9 unchanged.
- Net-coloured review renders: `power_netview_u603.png`, `power_netview_bucks.png` (F), `power_netview_bucks_b.png` (B)
  (`../../net_view.py`, from the integrated board).

## Integration changes (24 Nov 2026)
- U603 / L601 compacted (table above).  U601 / U602: the switch node stays 2.6 mm pin-to-pad (3.95 mm to the pad centre):
  CIN (C603 / C609, 0805) straddles the VIN / GND pins with SW between its pads and L602 / L603 courtyards already touch it;
  turning CIN 90 deg would move it off the VIN / GND pins and lengthen the input hot loop, so it was not done.
- PDN-2 (thermal): U601 (0.30 W) GND polygon now has 3 + 3 vias (the F and B cells' mirrored positions; were 8 + 8 in the
  middle of the polygon), all at the capacitor GND pads (TIGHTEN).
- DECOUPLING-8: C602 100n moved from U601 (2 mm from its pins, C603 straddles them) to the B side under U608 pin 5
  (VBUS pad on the B VBUS strip, GND pad into the B pour); nets unchanged (VBUS / GND).

## Open points
- Thermal: U601 0.30 W max into its GND polygon (about 9 mm2 on F) + 6 vias; U603 0.20 W, PGND via the GND channel to the
  capacitor GND vias (no vias at the chip any more); not simulated.
- U601 / U602 HF input caps (C602 / C607 0402) sit 2 mm from the pins (the 0805 CIN is at the pins).
- LM27762 (REPAIR, recheck RP-5, not done): the CCP ground returns (C626 / C619 to pin 4) stay 3.6-4.0 mm on L1; rotating
  the CCP would move it off CP (5), which the datasheet ranks above the ground path; the GND pour plus the CIN GND via
  shorten the return. U603's GND channel stays 0.45 mm (the pin columns fix it).
- LM27762: GND vias at the CIN GND pads (C613 / C612 at (2.55, 13.0), C625 at (2.0, 20.45)), at every COUT GND pad
  (C617 via the U601 cell via (4.3, 7.65), C621 (6.0, 16.2), C630 (7.65, 14.15), C628 (7.45, 21.4)) and at C632.
- Pair impedance from IPC-2141 only.

## REPAIR (24 Nov 2026, recheck RP-1 / RP-3 / RP-9)
- The four LM27762 LDO output capacitors moved from B to F next to OUT+ / OUT- (datasheet SNVSAF7C 7.4.1; user rule:
  plane vias at the capacitors): C617 / C621 (U604), C630 / C628 (U605); no via between pin and capacitor; the bead /
  rail / sense vias sit behind each capacitor. Moved, not added. To make room U604 went up 0.30 mm, U605 up 0.45 mm,
  the U604 dividers and U605's FB- divider to B, FB604 vertical NE of C617, FB605 0.7 mm east (its +3V3 via east of it).
  Output loops (pin -> COUT -> GND pad -> EP, bounding box of the pad centres, all on L1; before: through two vias and
  B): C617 1.9 x 2.0 mm, C621 1.0 x 3.2 mm, C630 2.5 x 2.9 mm, C628 2.7 x 1.6 mm.
- C632 fitted (schematic). C618 / C619 have LCSC numbers (C15849 / C19666).
- Checks: check_board 0 in every class; nightly DRC jlc4 67 = 56 lib_footprint_mismatch + 2 lib_footprint_issues +
  6 via_dangling + 2 track_dangling (interfaces) + 1 invalid_outline; decap_audit: U604 / U605 all output and input
  capacitors pass (C613 flagged only by its EN+ tie via, a signal via). Review render: `power_netview_lm27762.png` (F),
  `power_netview_lm27762_b.png` (B).

**Vias out of pads (24 Nov, RULES rule 12):** LM27762 EP vias removed (EP tied to GND pins 1 / 4), U608 GND via 0.25 mm off its pad, U605 EN- via 0.35 / 0.15. `python3 ../../via_in_pad.py power.kicad_pcb`: FAIL 0.
