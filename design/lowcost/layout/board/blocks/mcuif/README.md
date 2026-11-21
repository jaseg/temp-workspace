# mcuif block: STM32G474 U704 + control-voltage networks (36 /mcu_if/ parts) + J501, R511, R512 (from fpga_clock)
Run `python3 gen_mcuif.py [--render]` to write mcuif.kicad_pcb, mcuif.ifaces.json, mcuif.png and mcuif_detail.png. The routing order is in prio.json.
Block membership: J501, R511 and R512 are in this script's REFS. The integrator must also move them in floorplan.py / boardlib.
**Size**: 66.5 x 12 mm at board (27, 45), with the bottom edge on the board edge y 57. Copper stays >= 0.5 mm from y 57, and only interface stubs reach the N edge.
Placement:
- J501 at board (42, 53.2), rotation 90: pin 1 west, odd row (FPGA and supplies) south. Its courtyard ends at y 56.5.
- R511 / R512 on B.Cu above J501.2 and J501.4.
- U704 at (75, 51). Its courtyard is fully inside the block (y 45.85..56.15).
- VDD decoupling caps sit in the LQFP courtyard notches on F.Cu, with pad-wide copper to the pins and via pairs: C713 / C710 at pins 1 / 48, C711 at pin 36, C712 at pin 24.
- VREF+ (C718 / C717) and VDDA (C716 / C715, FB701) on B.Cu directly above the pin-20 / pin-21 vias.
- Divider columns: inputs on the east pads, outputs on one west column joined by straight verticals.
- I2C pull-ups R727 / R728 on B.Cu beside their own lanes.
West routing, drawn by hand:
- JTAG and DBG2 run straight north on B.Cu between the J501 pins.
- The MCU bus (HOST_RX/TX, SWDIO, SWCLK, DBG1, NRST) runs on F.Cu lanes y 47.9..49.9 at 0.4 mm pitch, steps to B.Cu at x 49.6 / 50.2 and runs to x 67.4. The router does the last hop.
USB: w 0.295 / s 0.205 mm, Zdiff 90.1 R. DP 9.272 mm and DM 9.272 mm in the block (a 1 mm bump on DP); pour gap 2 w.

## Interfaces (N edge y 45, board x; B.Cu unless stated)
| group | nets (board x) |
|---|---|
| fpga JTAG (J501) | DBG2 37.55, TCK 40.09, TMS 42.63, TDI 45.17, TDO 47.72 |
| phase VTAP (0 R links, w 0.4) | VTAP_N 44.15, VTAP_P 48.66, VTAP_TH 62.22 (w 0.25) |
| analog dividers | VBIAS_A 50.90, VBIAS_K 51.60, ADC_REF_MID 56.30 |
| analog / trigger from U704 / U701 | VNEG_REF 60.05, VOFS 60.50, DAC_TRIG 60.90, ADC_IN 61.15, TRIG_SEL 61.40 |
| fpga bus | MCU_CLK 71.60, I2C_SDA 74.25, SPI_MOSI 75.25, SPI_MISO 75.75, SPI_SCK 76.25, I2C_SCL 76.75, FPGA_DONE 78.60, FPGA_RECONFIG 78.85, SPI_CS 79.10, ADC_TRIG 79.70 |
| power (USB-C) | USB_DP 84.00 / USB_DM 84.50, F.Cu, 90 R pair |
| supplies | +3V3, +2V5, -2V5, VBUS: via pairs to In2 (In2 regions by the integrator); GND to In1 and the F / B pours |

## Checks (last run)
- check_board (39 refs): 0 missing / extra / footprint / value / pad-net, 0 clearance, 0 corners, 0 courtyard overlaps, RF width / gap 0.
  2 off-axis exits (U701.3, C722.2).
  Unrouted: the plane nets, plus HOST_TX, UC_SWCLK, UC_SWDIO, BOOT0, VREFP (C717 -> R703 / R731) and 1 GND.
- DRC (nightly, jlc4): total 130, error 18 (17 unconnected, 1 outline), warning 112. 0 hole / clearance / courtyard / silk.

## Open points
- NOT DONE: the router cannot reach the NE-side SWD vias (pins 37 / 38) or pin 31 (TX) through the area under the body.
  Planned fix: a hand-drawn B.Cu bus below the S pads (y 54.4..55.1) up the east side, with TX entering pin 31 from a via at x 80.6.
- VREFP to R703 / R731 and the BOOT0 jumper tie are still open. The 2 off-axis exits at U701 / C722 are still open.
- The router-routed analog interfaces sit at x 60.05..61.40, east of the accepted 49.6..56.4 range: the integrator must route them from there.
- The J501 silk outline is redrawn (clipped at the NPTH pegs). The U704 pin-1 silk wedge is removed; F.Fab keeps the pin-1 marker.
