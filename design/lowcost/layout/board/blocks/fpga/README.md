# fpga block (U501 GW1NZ-LV1 QN48, U502 MS5351M + Y501, J501 WR-WST, config/decoupling, R407/R411)

STATUS: INCOMPLETE. Not routed out and not DRC clean. Do not merge yet.

Size: an L shape. The main part is 24.5 x 22.0 mm at board (56, 0.5); FLOORPLAN.md gives 18 x 22. A strip at x 24.5-29.6, y 0-7.4 holds the J501 body and the VBUS exit.
So the block reaches board x 85.6 at the top edge and overlaps the power rectangle (x >= 74) by 6.5 / 11.6 mm.
`python3 gen_fpga.py [--render]` writes fpga.kicad_pcb / fpga.ifaces.json / fpga.png / fpga_detail.png. It uses local helpers: a grid router (0.05 mm, F/B, 45-degree moves), `to_east`, and `courtyard_overlaps`.
`prio.json` sets the order in which routing jobs run (empty = default order).

Interfaces (see fpga.ifaces.json):
| net | edge / layer | note |
|---|---|---|
| /S_STROBE_P, /S_STROBE_N | W, F.Cu, y 9.37 / 10.37 | 0.36 mm. P crosses under N on B.Cu with 2 vias and is length-matched by a B meander |
| Net-(C412-Pad1), Net-(C422-Pad1) | S, B.Cu | after R407 / R411 (on B, at U501). 0.36 mm, straight |
| /TAP0-15 | S, B.Cu, x 8.5-23.5 | the router permutes freely; order is not monotonic |
| /COARSE, /ADC_TRIG, /FPGA_DONE, /FPGA_RECONFIG | S, B.Cu, x 1.8-8 | |
| SPI x4, MCU_CLK, I2C, HOST_RX/TX, UC_SWDIO/SWCLK, DBG1, UC_NRST | E (x 24.5), B.Cu, y 11-21.5 | changed from S to E: the S edge could not take them |
| VBUS | E of the strip, B.Cu | J501.1 |
| +3V3, +1V2, GND | via pairs to In2 / vias to In1 | |

Check state (last run):
- check_board: 0 missing / extra / footprint / value / pad-net.
- Unrouted: 5 nets (+1V2, +3V3, DBG2, JTAG_TCK, JTAG_TDI).
- 11 routing jobs failed: SPI x4, MCU_CLK, COARSE, TAP8, U501.37 +1V2, U502.1 +3V3, JTAG_TDI, DBG2.
- 1 clearance (U502.8 / R509.1), 0 corners, about 50 off-axis pad exits.
- 9 courtyard overlaps: R508-R510 against U502 and U501, C509 against U502 and Y501, C504 against R502.
- DRC (nightly, jlc4): 40 errors (18 unconnected, 12 clearance against U502's 0.2 mm pad clearance, 9 courtyards, 1 outline) and 75 warnings.

Open points:
- U502, R508-R510 and C509 need a new placement with more room: move U502/Y501 into the empty bottom-right area (x 15-24, y 13-22).
- The SPI pins (28-31, top side) then get a free path east.
- A TAP permutation is not needed: the TAP pins (9-27) are on the bottom and right sides and fan straight to the S edge.
- The strobe fan-out narrows next to the 0.4 mm pitch pins of U501.38 / .35.
