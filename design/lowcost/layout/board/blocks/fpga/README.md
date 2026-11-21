# fpga block (U501 GW1NZ-LV1 QN48, U502 MS5351M + Y501, config pull-ups, decoupling)

STATUS: INCOMPLETE (re-placed and mostly routed, not DRC clean). Do not merge yet.

Size: 18 x 22 mm at board (56, 0.5), the FLOORPLAN rectangle; nothing beyond x 74. J501, R511, R512 moved to mcuif
(the UC_NRST 100 nF is C719 on mcu_if, never here); R407 / R411 are placed by pstrobe. Block refs (24) = fpga_clock
sheet minus J501 / R511 / R512 (`REFS` in gen_fpga.py). `python3 gen_fpga.py [--render]` (about 50 s), prio.json = job order.
U501 rot 90 at (8.6, 9.8). U502 / Y501 / R508-R510 on the top row, 33 R and caps U502 VDD on B. Pull-ups / JP501 on B (SW).
Supplies: hand-drawn pad-wide neck + 0.4 mm + via pair at each U501 corner, 100 nF on B at the pair; In2 +3V3 zone
over the block, +1V2 island under U501 with a tongue to the SE corner; In1 GND zone. Merge without skip_planes.

| iface (local) | edge / layer | nets |
|---|---|---|
| W, y 10.37 / 11.37 | F.Cu 0.36 | S_STROBE_P / N (matches analog). N dips to B under P (2 vias) |
| W, y 12.6 / 13.4 | F.Cu 0.36 | PH_STROBE_N / P (series 47 R in pstrobe) |
| S, x 1.15-4.6 | B.Cu 0.15 | FPGA_DONE, COARSE, FPGA_RECONFIG |
| S, x 6.8-8.2 | B.Cu | JTAG_TMS, JTAG_TDI, DBG2, JTAG_TDO (TCK missing, see below) |
| S, x 8.6-14.65 | B.Cu | TAP12, 14, 0, 1, 2, 11, 9, 7, 3, 4, 5, 6, 8, 10 (router order; TAP13 / TAP15 missing) |
| S, x 15.1-17.6 | B.Cu | SPI_SCK, MOSI, MISO, CS, MCU_CLK, I2C_SDA, I2C_SCL |
| In2 | - | +3V3 (power W, board 74.45 / 5.5), +1V2 at the SE corner (power 75.25 / 21.95) |

Last run (check_board, 24 refs): 0 missing / extra / footprint / value / pad-net, 0 clearance, 0 off-axis exits,
0 courtyard overlaps, 1 corner (U501.25 supply neck, 90 deg at local 10.8 / 6.1).
Unrouted: +3V3 (U502.7), GND (U502.8, C503), FPGA_MODE1 (U501.42-R506), JTAG_TCK (U501.3, R507), CLK1 (U502.9-R509).
Not routed and without iface: TAP13 (U501.23), TAP15 (U501.27), ADC_TRIG (U501.41).
DRC (nightly, jlc4): 8 errors = 7 unconnected + 1 missing outline; 0 clearance / courtyard / hole / track width / silk.

Open points (in order):
- Strobe length: S_N 15.99 mm vs S_P 7.75 mm (the crossing forces N round the 36/37 supply corner); needs about
  8.2 mm of meander on S_P or a shorter N path (move the pin 36 / 37 via pairs). PH: N 9.21 / P 9.49 mm (0.28 mm).
- Strobes have a 0.2 mm neck inside the 0.4 mm pin row (not in the RF table for that reason).
- U502.7 / .8 need hand fan-outs (0.2 mm clearance on 0.5 mm pitch defeats the grid router); route CLK1 on B.
- Left pins 41 / 42 and 3 (TCK): hand fan-out or staggered vias; TAP13 / TAP15 after re-ordering the TAP jobs.
- TAP order at the S edge is not monotonic; a permutation (schematic unchanged) can be chosen after routing.
