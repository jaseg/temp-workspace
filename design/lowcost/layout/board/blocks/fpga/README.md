# fpga block (U501 GW1NZ-LV1 QN48, U502 MS5351M + Y501, config pull-ups, decoupling)

STATUS: routed. check_board and the nightly DRC pass (RULES.md); the only DRC error is the missing outline.
Size: 18 x 22 mm at board (56, 0.5), the FLOORPLAN rectangle (nothing beyond x 74). 24 refs = fpga_clock sheet minus
J501 / R511 / R512 (now in mcuif; the UC_NRST 100 nF is C719 on mcu_if). R407 / R411 (PH series 47 R) are placed by pstrobe.
`python3 gen_fpga.py [--render]` takes about 50 s. prio.json sets the router job order.
Layout: U501 rot 90 at (8.6, 9.8). U502, Y501 and R508-R510 are on the top row, the U502 decoupling on B. The pull-ups are on B (W / SW) and JP501 is on B under U501.
Hand-drawn: strobes, supply necks (pad-wide 0.2 mm, then 0.4 mm into via pairs at the U501 corners), and the TAP / JTAG / west buses
(F.Cu 45-degree fan, one via row at y 20.6, B.Cu stubs to the S edge). SPI runs on B down the east edge. A grid router handles the clocks, I2C, caps and ties.
100 nF caps are on B under the pad ring: supply via a 0.4 mm B track to the pin's via pair, GND to its own exposed-pad via.
Planes: In1 GND zone. In2 +3V3 over the block, with a +1V2 island under U501 and a strip leaving east at y 15-16. Merge without skip_planes.

| iface (local; board = +56 / +0.5) | edge / layer | nets |
|---|---|---|
| W, y 10.37 / 11.37 | F.Cu 0.36 | S_STROBE_P / N (analog's points). P (drives the strobe amp) F.Cu only, no vias, 8.01 mm; N (only terminated) pin 35 -> via -> B.Cu (over In2 GND) -> via -> F stub, 15.42 mm. No crossing, no meander (22 Nov) |
| W, y 12.60 / 13.08 | F.Cu 0.36 | PH_STROBE_N / P |
| S, x 0.6-2.4 (0.6 pitch) | B.Cu 0.15 | ADC_TRIG, FPGA_DONE, COARSE, FPGA_RECONFIG (pull-ups R502 / R501 here) |
| S, x 3.0-5.4 | B.Cu 0.15 | JTAG_TCK (R507 pull-down), TMS, TDI, DBG2, TDO (to J501 in mcuif) |
| S, x 6.0-15.0 | B.Cu 0.15 | TAP0 ... TAP15, monotonic west to east (schematic pin map unchanged) |
| S, x 16.1-17.6 (0.25 pitch) | B.Cu 0.12-0.15 | SPI_SCK, MOSI, MISO, CS, MCU_CLK, I2C_SDA, I2C_SCL |
| In2 | - | +3V3 (power W, board 74.45 / 5.5); +1V2 strip at E y 15.5 (power +1V2 at board 75.25 / 21.95) |

Lengths: S_STROBE P 8.011 / N 15.424 mm (no longer matched: N is only a termination); PH_STROBE P = N = 9.403 mm.
The strobes have a 0.2 mm neck inside the 0.4 mm pin row, so they are not in the RF width table.
check_board (24 refs): every count 0 (missing, extra, footprint, value, pad-net, unrouted, clearance, corners, off-axis exits, courtyards).
DRC (nightly 10.99, jlc4): total 61, error 1 (invalid_outline), warning 60. The warnings are 36 track_dangling (the 36 interface stubs) and 24 lib_footprint_mismatch.

Notes for integration:
- The integrator must carry +1V2 on In2 from the E strip (y 15-16) down to the power block's +1V2 at board (75.25, 21.95).
- The SPI lines are 0.12 mm where they pass between the staggered vias at U501 pins 28-31.
- The I2C, MCU_CLK and CLK0 paths over the top row were made by the router. They are DRC clean, but not as tidy as the buses.
