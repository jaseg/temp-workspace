# Block "power": USB-C, protection, boost, LDOs, LM27761, LM337 (refs 6xx, 53 parts, both sides)
Run `python3 gen_power.py [--norender]` -> `power.kicad_pcb`, `power.ifaces.json`, `power.png`, `power_detail.png` (USB fan-out / U608). KiCad 7.0.11; DRC with the nightly (`tools/run_drc.sh --rules jlc4`).
**Size: 26.0 x 22.5 mm at board (74, 0), as in FLOORPLAN.** J601 on the right board edge (board y 8.2-18.8). M3 hole (97, 3): 3.5 mm keep-out (rule area, all layers).
Placement: boost top-left (L601 / U603 / D602 / C610 / C611; hot loop SW -> D602 -> C610 -> GND -> U603.2 about 4 x 2.5 mm, SW copper is a 3 x 3 mm F polygon), LM27761 top-middle (flying cap C618 north-east, C619 / C620 at the pins), LDO stack U604 / U606 / U602 left (inputs east on a +5V4F / +3V3 F polygon, outputs west), USBLC6 U608 flow-through between J601 and the pair, PTC / TVS / FB601 along the bottom edge. B side: U601 AMS1117 (tab = +3V3 B polygon, heat sink), U607 LM337, all 0805 bulk caps, CC pull-downs, ADJ divider.
## Checks
- check_board (53 refs of the power membership): 0 missing / extra / footprint / value / pad-net / no-net, 0 clearance, 0 corners > 45 deg, 0 off-axis pad exits, 0 USB width deviations, 0 pour-gap hits (2 w around the USB lines). Unrouted: only the plane-fed outputs +3V3, +5V, +2V5, +1V2, -5V (1 link each, see open points). VBUS, GND and all /power/* nets are routed in the block (In1 GND zone drawn in the block; the board plane replaces it).
- Courtyards (F.CrtYd / B.CrtYd, BooleanIntersection > 0.005 mm2): **0**; all courtyards inside the block.
- Nightly DRC (jlc4): 71 = 5 unconnected_items (the plane-fed nets above), 14 via_dangling (In2 supply vias), 2 track_dangling (USB pair ends at the S edge), 1 invalid_outline (no Edge.Cuts in a block), 47 lib_footprint_mismatch + 1 lib_footprint_issues (library version), 1 silk_overlap warning (L601 / U603 library silk lines touch; not silk over pad). 0 courtyard, clearance, hole, track-width, silk-over-pad, text errors. Refdes on F.Fab / B.Fab.
## USB (90 R pair, F.Cu over In1, w 0.25 / s 0.15 = 91 R by IPC-2141, Z0 60 R single)
| route | mm |
|---|---|
| J601 B6 (DP outer) -> U608.6 / B7 (DM outer) -> U608.4 | 3.75 / 3.75 |
| inner A6 (DP): 1.11 F + 1.41 B.Cu hop (2 vias, crossing of the C receptacle's two rows) ; inner A7 (DM) 3.02 F | |
| flow-through U608.6-1 / 4-3 under the body | 2.28 / 2.28 |
| U608.1 / .3 -> S edge (pair) DP / DM | 12.30 / 11.64 (0.66 mm = 4 ps skew, irrelevant at 12 Mb/s) |
## Interfaces (local mm; board = local + (74, 0))
| net | local x, y | layer / side | note |
|---|---|---|---|
| /USB_DP, /USB_DM | 8.6 / 9.0, 22.5 | F.Cu S, pair | to U704.34 / .33 (mcuif). FLOORPLAN had no entry (USB added later). |
| VBUS | 14.0, 17.4-18.3 | via pair, In2 S | at FB601; VBUS also on a B.Cu polygon (U601, C601/C602, boost) |
| +3V3 | 0.45, 5.0 / 6.0 | via pair, In2 W | from the U601 tab polygon (B) |
| -5V | 15.72, 9.3 + 16.8, 8.46 | via pair, In2 W | at FB603 |
| +5V / +2V5 / +1V2 | 0.45, 12.6 / 0.45, 16.2 / 1.25, 21.95 | via, In2 W | at C616 / C624 / C608 |
| -2V5 | 9.75, 18.0 / 19.0 | via pair, In2 S | at R607 / C628 (B) |
## Deviations / local helpers
- VBUS_IN joins the two connector VBUS pad pairs on B.Cu (0.6/0.3 vias beside the pads, under the shell, 0.7 mm track), one via per side (~1 A). A4/B9 -> F601 on F.
- Local helpers: `bplace` (B placement + flip), `two`, `diff90`, `courtyard_overlaps`, `render`. boardlib.py not edited.
## Open points
- Plane-fed inside the block (need In2 copper in the power region, the integrator draws it): +3V3 (U601 polygon <-> U602 input / C607), -5V (FB603 <-> U607 tab vias at board (76, 14.5)), +5V / +2V5 / +1V2 (LDO output <-> B bulk C617 / C625 / C609, via in / beside the pad). FLOORPLAN's power In2 list (VBUS, +5V4F, -5V_LDO) must therefore become: -5V and +3V3 regions under x 74-90, plus tongues W for +5V / +2V5 / +1V2.
- USB pair leaves S into the phase block; the integrator must carry it to U704 (90 R, keep F.Cu over In1 or change layer with GND vias).
- 0.85 A through single 0.6/0.3 VBUS_IN vias; AMS1117 dissipates ~0.8 W into the B +3V3 polygon (about 50 mm2) plus In2: check the temperature.
- Pair impedance from IPC-2141 only (no field solver); JLC calculator check advised.
