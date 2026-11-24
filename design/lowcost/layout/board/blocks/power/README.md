# Block "power": USB-C, protection, TPS62A01A x2, TPS63802, LM27762 x2 (refs 6xx, 61 parts, both sides)
Run `python3 gen_power.py [--norender]` -> `power.kicad_pcb`, `power.ifaces.json`, `power.png` (F), `power_b.png` (B),
`power_detail.png` (U603 / L601). KiCad 7.0.11; DRC with the nightly (`tools/run_drc.sh --rules jlc4`).
Power tree: `docs/research/power-tree.md` (24 Nov 2026). **Size 26.0 x 22.5 mm at board (74, 0), unchanged.** J601, U608,
F601, D601, FB601, R601 / R602 and the USB pair are unchanged. M3 hole (97, 3): 3.5 mm keep-out (F, In1, In2, B).

## Placement (local mm)
| cell | side | where | layout (datasheet layout section) |
|---|---|---|---|
| U601 TPS62A01A VBUS -> +3V3 | F | x 0-9.5, y 0-8 | C603 10u straddles VIN (3) / GND (1) on the IC layer; SW (2) leaves between the C603 pads (0.9 mm gap, 0.35 mm track, 3.9 mm) to L602; C604 GND returns to C603 / pin 1 in one GND polygon (5 vias); R609 / R610 / C631 at FB (5) on the side away from SW |
| U602 TPS62A01A +3V3 -> +1V2 | B | mirror image of U601, under it | C609 / C607 at VIN, L603, C605 + C608 at the output |
| U603 TPS63802 VBUS -> +5V1 | F | x 9.5-19.5, y 0-10 (east-most free area, 17 mm from the analog block) | C601 at VIN (10), C610 / C611 at VOUT (6); L601 east between L1 (9) / L2 (7) on two polygons; GND (8) runs between them under L601 to 3 vias; AGND (3) by its own track to pin 8; FB divider R603 / R604 south-west, away from L1 / L2 |
| U604 LM27762 +5V1F -> +5V / -5V | F | x 0-8, y 9-16 | C613 100n + C612 22u at VIN (3) / GND (4) on the IC layer (DECOUPLING-4); C626 CCP at CP (5); C618 C1 at pins 10 / 9; R613 / R614 at FB+ (north), R605 / R606 at FB- (south); EP 2 vias |
| U605 LM27762 +3V3_CP -> +/-2V5 | F | x 0-8, y 16-22.5 | same cell; C625 CIN, C619 CCP, C624 C1 |
| beads, LDO output caps | B / F | under the LM27762 cells and east of them | FB602 / C617 / C621 / FB603 / C627 / FB605 / R617 / C629 / FB607 / C628 / C630 / FB606 on B; FB604 on F |
| C632 47u (DNP damper) | B | under U603, on the VBUS input | |
Not placed here: C606, C614, C615, C616, C620, C622 (power sheet, placed at their loads in other blocks per kicad/README.md);
`floorplan.membership` still maps them to "power" (integrator: move them to analog / pstrobe / phase).

## Supply paths
- VBUS: FB601 -> vias (14.0, 17.4 / 18.3) -> B strip (1.1-1.4 mm, x 13-14.2) -> 3 vias (10.45-12.05, 3.3) -> F polygon
  over U603 VIN / C601 and along the top edge to U601 VIN / C603 / C602 (~6 mOhm, 5 mV at 0.75 A).
- +5V1: F polygon C610 / C611 -> 3 vias -> B polygon -> FB602 (B) -> +5V1F to U604 VIN / EN+ / EN- (B 0.4 mm);
  GVA-84+ feed: B 0.5 mm track to the via pair (12.3, 20.9 / 21.7), directly from the output caps, not through FB602.
- +3V3: U601 output polygon (L602 / C604) -> 2 vias to the L4 plane and to U602's input polygon (B).
- In2 (slow / static layer, rule 10) carries two block-internal lines: +1V2 sense R611 -> (8.0, 1.2) -> top edge y 0.4 ->
  x 0.5 -> (1.0, 7.9); PG_5V1 U603.5 -> (10.05, 6.45) -> x 8.3 -> (7.9, 18.6). The integrator's L3 copper must avoid them.

## Regulator input headroom (layout drops included)
| | Vin at the pin | needed | margin |
|---|---|---|---|
| U601 +3V3 0.67 A | 4.59-5.25 V (VBUS minus 5 mV B strip) | 3.53 V (100 % mode) | >= 1.06 V |
| U602 +1V2 30 mA | 3.25-3.38 V | 1.2 V + 0.03 V | >= 2.0 V |
| U603 +5V1 0.34 A | 4.59-5.25 V | buck-boost, any VIN 2.3-5.5 V | n/a |
| U604 +4.80 / -4.64 V 41 mA | 5.03-5.15 V after FB602 (12 mV) | 4.82 V (OUT+), 4.89 V (OUT-, RNEG 4 R) | 0.21 V / 0.14 V |
| U605 +/-2.50 V 50 mA | 3.24-3.37 V after FB605 (8 mV) | 2.54 V / 2.82 V (RNEG 5 R assumed) | 0.70 V / 0.42 V |

## Interfaces (local mm; board = local + (74, 0))
| net | local x, y | layer | note |
|---|---|---|---|
| /USB_DP, /USB_DM | 8.6 / 9.0, 22.5 | F.Cu S, pair | unchanged |
| VBUS | 14.0, 17.85 | via pair | unchanged position; now feeds J501 pin 1 only |
| +3V3 | 8.72, 6.05 | via pair | U601 output |
| +5V | 9.05, 8.77 | via | FB604 output |
| -5V | 0.45, 14.0 | via | FB603 / C627 |
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

## Checks (24 Nov 2026)
- check_board (61 refs = power membership minus the 6 moved capacitors): 0 missing / extra / footprint / value / pad-net,
  0 clearance, 0 corners > 45 deg, 0 off-axis pad exits, 0 USB width / pour-gap faults, 0 courtyard overlaps.
  Unrouted: +3V3 (2) only: R609 sense via and the FB605 +3V3 via are joined by the L4 +3V3 plane (plane-fed).
- Nightly DRC jlc4: 72 = 56 lib_footprint_mismatch + 2 lib_footprint_issues (library version / project library),
  9 via_dangling (supply interface vias, plane-fed), 2 track_dangling (USB pair ends at the S edge), 2 unconnected_items
  (+3V3, plane-fed), 1 invalid_outline (no Edge.Cuts in a block). 0 clearance, courtyard, hole, track-width, silk errors.

## Open points
- Thermal: U601 0.30 W max into its GND polygon (about 8 mm2 on F) + 5 vias + In1 / L4; U603 0.20 W; not simulated.
- U601 / U602 HF input caps (C602 / C607 0402) sit 2 mm from the pins (the 0805 CIN is at the pins).
- LDO output caps of U604 / U605 are on B behind one via each (C617, C621, C628, C630).
- Pair impedance from IPC-2141 only.
