# Zones, splits and return paths (key: zones)

Board: layout/board/scope-fe.kicad_pcb, zones refilled with pcbnew.ZONE_FILLER in a scratch copy (pcbnew 7.0.11).
Coordinates are board mm (pcb minus 100, 100). Scripts and outputs are in scratchpad/val/zones/:
- z2.py: zone table.
- rast.py: rasterises the filled polygons at 0.025 mm.
- rp.py / rp2.py / det.py: return-path sampling, void labelling and the geodesic detour per crossing.
- isl.py: islands and the vias inside them.
- pen.py: geodesic distance from every pour cell to the nearest GND via or GND PTH, on a 0.1 mm grid.
- neck.py: morphological opening at 0.3 mm. vias.py: GND via next to each signal via. win.py: the stack under each L2 window.

## Zone inventory (verified)
| layer | net | filled mm2 | pieces | note |
|---|---|---|---|---|
| L2 In1 | GND | 4999.9 | 1 | 116 rule-area windows: 32 tap-node, hold node, divider/BUF802 strip, 2 SMA, 78 pad cuts, 2 corner holes |
| L3 In2 | GND | 3091.9 | 78 | between the minor-rail corridors (+2V5 6 pieces, -2V5 5, +5V 4, -5V 2, +1V2 4, VBUS 2; min width 0.5) |
| L4 In3 | +3V3 | 4710.5 | 1 | no other net on L4, 0 tracks; 80 `L4_window` areas |
| L5 In4 | GND | 5206.9 | 1 | via antipads only |
| L1 F | GND | 3238.6 | 24 | + small local pours: SW_BOOST 6.6, +5V4 / +5V4F, VBUS, +3V3, +/-5V pads |
| L6 B | GND | 3654.2 | 23 | + +3V3 60.9 and VBUS 28.5 under the power block |

- The L4 +3V3 plane is one polygon. There is no +5V edge strip any more (TOPOLOGY section 8 supersedes section 6).
  A 0.3 mm opening leaves no orphan piece of 0.5 mm2 or more, so the plane has no neck under 0.3 mm.
- L2 and L5 are each a single polygon. Their holes are via antipads, the 0.85 mm ring of each 0.45 mm via, plus the
  windows listed above.

## Checked and found correct
- Under every L2 window, L3 and L4 are empty and L5 is GND on all 9 sample points (win.py).
  - This holds for the node windows and for the 78 pad cuts.
  - Pad cuts therefore reference L5 at 1.35 mm, not L3 at 0.665 mm. This is already reported as RF-6, so it is not repeated here.
- No via of any net lies inside an L2 window.
- No stitching via sits on a track (DRC is clean).
- RF return paths on L1 (strobes, PSTRB_A/K, STRB_A/K, delay line D301-common, BUF_OUT_T/S, EXT_CLK, front chain
  RFIN/RFOUT, TAP8/9 hop, USB) were sampled every 0.25 mm. Points were taken under the trace and at +/-w, 2w, 3.5w.
  - Every sample without L2 lies in one of three places: an intended pad cut, a node / SMA window, or the antipad of
    the net's own via.
  - Geodesic detours across neighbouring antipads are 0.53-0.54 mm, at U401/U402 RFOUT (48.54 / 38.58, 10.86) and STRB_A (30.63, 10.86).
  - No L1 RF net crosses a slot.
- The SW_BOOST copper (78.4-81.6, 2.5-5.6) and the LM27761 flying-cap loop (90.5-93.2, 0.5-3.0) have solid L2 and L5
  under them (100 % / 98.9 %), and L3 is GND there.
  - The nearest slow / bias line is ADC_IN at (66.55, 28.0) on L3, 26.8 mm away.
  - The analog block (x < 56) is at least 22 mm from the switch node.
- L3 slow lines do not run over any L4 edge, because L4 has none.
- PH_STROBE_P/_N have a GND via within 1 mm at all 4 vias.

## Findings
ZONES-1 (medium, verified): the L3 GND webs under the tap row have no stitching. They are grounded only at their far ends.
- In x 28-67, y 34.6-41, the L3 pour between the 32 node windows is fenced north by VTAP_P (y about 34) and south by
  VTAP_N (y about 41.5).
- Every GND via of the tap row (rows at y 33.6 / 41.3) lies outside that fence.
- The geodesic path from the pour to the nearest GND via is up to **23.9 mm**, and 131 mm2 is further than 5 mm.
  East part (x 67-98): 11.9 mm, 45 mm2.
- Two more pieces nearby:
  - an L-shaped finger at x 31-57, y 25-29.2: 22.4 mm;
  - a 0.3 mm x 20 mm sliver at y 30.5, x 35.5-56: 25.4 mm.
- Quarter-wave of a 24 mm one-end-grounded strip in the core (er 4.1): about 1.5 GHz. lambda/10 at 3 GHz is about 4.9 mm.
- RULES.md L3: "Unused L3 area is ground pour stitched to L2 / L5" is not met.
- These webs form the side walls of every hold-node window (L5-referenced). They are a shared, poorly grounded
  conductor running the full length of the 16 cells, so they couple the cells and add a cell-dependent ground.
- Fix:
  - GND vias in the 1 mm webs between windows (one per cell gap, about x 30.9 + 4.514 n at y 37.5), if L1 / L6 allow it;
  - otherwise let the VTAP tracks neck to give the vias a way in;
  - or keep the L3 copper out of the band;
  - delete the 0.3 mm sliver and the L finger (minimum width 0.5 mm, or a keep-out).
- Figure: zones-L3-taprow.png.

ZONES-2 (medium, verified): L6 GND fingers between the tap-row lanes are grounded at one end only.
The worst geodesic lengths to a GND via:
- **19.3 mm** at x 40-44, y 25-41. Neighbours: JTAG_TCK 39.86, U306B+ 40.27 / 41.07, JTAG_TMS 43.97, TDI 44.27.
- **16.9 mm** at x 58.2-61.7, y 35-43.
- **16.3 mm** at x 62.7-66.2, y 36-42.
- **13.1 mm** at x 80.8-84.4, y 31-40, between U311A+ (81.69) and FPGA_RECONFIG / ADC_TRIG (84.5-84.9).
- **28.4 mm** for the 0.4 mm sliver along the top edge, x 35-59, y 0.5-0.9.

Single-via islands longer than lambda/10:
- L1 (0.5-6.6, 21.2-22.5), 6.1 mm;
- L1 (71.8-73.5, 46.3-51.8), 5.4 mm;
- L3 (6.0-6.9, 34.0-41.2), 7.2 mm;
- L3 (84.5-87.0, 17.3-25.9), 8.6 mm;
- L6 (17.5-22.2, 22.7-24.7), 4.7 mm.

Impact:
- lambda/4 on L6 (eps_eff about 3) is 15-19 mm, which resonates at about 2.3-2.9 GHz.
- These fingers are the intended guards between digital lanes and the comparator summing inputs (Net-(U3xxA/B-+),
  R363 / R364, on L6 for 7.7 mm). At GHz they guard poorly and can couple more.
- Related, verified: U311A+ (x 80.9-81.69, 0.2 mm) runs at 0.40 mm centre-to-centre from I2C_SCL (80.5) and 0.63 mm from SPI_SCK (80.27).

Fix:
- one GND via every 3-4 mm along each finger (the fingers are 2-4 mm wide);
- delete the top-edge sliver;
- give each single-via island a second via at its far end.

Figure: zones-L6-fingers.png.

ZONES-3 (low, verified): merged via antipads form slots in L2 / L5 in the FPGA fan-out. Fast nets cross them.
| slot | size | crossed by (layer) | geodesic detour |
|---|---|---|---|
| diagonal row, (63.6-67.8, 4.8-8.2) | 5.4 mm | COARSE, TAP0-3 (L6); FPGA_CLK at (63.6, 7.73), CLK2_FPGA (L1) | FPGA_CLK 0.04 mm (edge) |
| column (67.8-69.6, 8.2-12.3) | 4.05 mm | I2C_SDA (68.17, 9.86), I2C_SCL (68.2, 11.46), MCU_CLK, SPI_MISO, ADC_TRIG (L6); TAP8/9 (L1) | SDA +4.7 mm, SCL +1.8 mm |
| cluster (69.6-73.9, 20.8-23.7) | 4.35 x 2.85 | ADC_TRIG, TAP9-15 (L6), TAP8 (L1) | side intrusions |
| mcuif row (76.8-81.2, 47.9-49.3) | 4.35 x 1.45 | SPI_CS, MOSI, SCK, I2C_SDA (L6) | edge only |

- Other crossing: USB_DM, L1, at (90.68, 14.25): +2.5 mm (full speed, harmless).
- Every listed net is MHz-class, and detours of 5 mm or less matter little. The slots will grow with any larger antipad.
- Fix: stagger or space the fan-out vias to at least 0.95 mm pitch, or reduce the plane clearance on those vias, so
  that a 0.15 mm web of L2 / L5 survives between them.
- Figure: zones-L5-fpga-slots.png.

ZONES-4 (low, verified): many signal-layer transitions have no GND via within 1 mm.
- 50 of 72 vias on fast nets (L1 to L6, crossing both planes) have none.
- Worst cases:
  - SPI_MOSI / MISO / SCK / CS and ADC_TRIG at U501: 2.5-3.9 mm, (68.2-68.75, 9.46-11.86);
  - TAP15 / 13 / 11 / 14 at (70-72, 21.25-21.9): 2.3-3.4 mm;
  - TAP0 (28.98, 23.92): 2.5 mm;
  - TAP11 (75.39, 27.0): 2.7 mm;
  - **S_STROBE_N (56.4, 11.86): 3.16 mm**, and (56.4, 7.8): 1.10 mm;
  - U502 CLK1 (63.85, 3.2): 1.89 mm.
- README claims ground vias "beside every inter-block signal via". That is true only for the 27 board-level vias.
  The block-internal fan-out vias were not covered.
- S_STROBE_N is the complement of the sampler strobe pair. Its return current has to jump L5 to L2 about 3 mm away,
  which lengthens the loop in a strobe edge.
- Fix: add a GND via within 0.7 mm of the S_STROBE_N vias as a minimum. The FPGA fan-out can use the U501 GND / EP
  vias if they are moved closer.

## Not done / limits
- Detour is the 2-D geodesic on the rasterised plane (0.05 mm grid). It does not include the fact that a return
  current can also use the opposite plane through stitching vias.
- No EM simulation of the finger resonances. The figures above are lambda/4 estimates.
- The L1 pour between the comparator pins (x 36-47, y 28-34.5) reaches up to 12 mm from a via, and joins the rest
  only through webs under 0.3 mm. It is noted, not rated.
