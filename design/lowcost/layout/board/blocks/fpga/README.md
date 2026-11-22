# fpga block, six layers (U501 GW1NZ-LV1 QN48, U502 MS5351M + Y501, config pull-ups, decoupling)

STATUS (22 Nov 2026): native 6L (JLC06161H-3313). Every escape is drawn with explicit coordinates (TOPOLOGY.md section 1),
and each layer is planar. The router handles only local support ties. `python3 gen_fpga.py [--render]` (about 60 s).
Block 18 x 22 mm at board (56, 0.5). Layers: L1 parts + strobes, L2 GND, L3 GND pour + the 5 static config lines,
L4 +3V3 with a +1V2 island (pins 12 / 37, C501-C503), L5 GND, L6 fan-out. U501 rot 90 at (8.6, 11.165).

Pin permutation (old -> new; schematic gen_fpga_clock.py, kicad/README.md): TAP0..4 9,10,11,13,14 -> 28..32;
TAP5 15 -> 41; TAP6 16 -> 47; TAP7 17 -> 6; TAP8..10 18,19,20 -> 9,10,11; TAP11..15 21,22,23,24,27 -> 13..17;
COARSE 47 -> 27 (GCLKT_3); ADC_TRIG 41 -> 18; DBG2 6 -> 8; SPI SCK/MISO/MOSI/CS 28/30/29/31 -> 20/21/22/24.
Fixed: strobes 40/39/38/35, FPGA_CLK 33, CLK2 34, DONE 46, RECONFIG 48, READY 45, JTAGSEL 44, MODE 43/42, JTAG 3/4/5/7. NC: 19, 23.

| iface (local; board = +56 / +0.5) | layer | nets |
|---|---|---|
| S edge y 22, x = 2.0 + 0.5 k | B.Cu 0.12 | k 0 COARSE, 1-8 TAP0..7 (2.5-6.0), 9 DBG2 6.5, TCK 7.0, TMS 7.5, TDI 8.0, TDO 8.5, MCU_CLK 9.0, SPI_CS 9.5, I2C_SDA 10.0, FPGA_DONE 10.5, SPI_MOSI 11.0, SPI_MISO 11.5, SPI_SCK 12.0, I2C_SCL 12.5, FPGA_RECONFIG 13.0, ADC_TRIG 13.5, TAP8..15 14.0-17.5 |
| W (0, 9.365) | F.Cu 0.16 | S_STROBE_P: one straight line from pin 38, 5.65 mm, no vias (pin row aligned to the analog iface) |
| W (0, 10.365) | F.Cu 0.16 | S_STROBE_N: pin 35 N, W at y 6.9 (F), via (0.4, 7.3), L6 down, via (0.4, 10.365), 0.4 mm F stub; 11.23 mm |
| W (0, 21.35) / (0, 21.70) | F.Cu 0.16 | PH_STROBE_N / P: pair down the W margin (x 0.9 / 1.26), equal length 16.766 / 16.766 mm |
| E (18, 5.0) / (18, 15.35) | In3 | +3V3 zone / +1V2 island strip (y 13.8-16.1) |

Routing plan: COARSE + TAP0..4 go from a via stair N of the top pads west on L6, then down the W margin with TAP5/6
(vias W of pins 41 / 47), and fan to their slots. TAP7 / DBG2 run F south, then W over the JTAG L6 lanes to vias. JTAG
gets vias at the pins and runs L6 straight S. MCU_CLK, SPI x4, I2C x2 and ADC_TRIG run as L6 lanes under U501
(entering from the E pins' vias / the NE corner) and fan to their slots. DONE / RECONFIG run F down the W side, then E
over the bundle to vias. TAP8..15 run F to staggered vias (y 20.75 / 21.4), then short L6 stubs.
Clocks: CLK0 -> R508 -> pin 33 and CLK2 -> R510 -> pin 34 on F (about 5 mm). MCU_CLK goes CLK1 -> via -> R509 (B) -> L6 over L5.
Decoupling sits at the pins with vias into L4 (C506 / C502 NW, C505 NE, C504 SW, C501 SE, C503 on B, C508 on B under U502).
Config pull-ups R502-R506 and JP501 sit on F in the NW corner. The pins reach them through vias and L3 lines. R501 and R507 sit SW.

Checks: check_board (24 refs) all 0 (unrouted, clearance, corners, off-axis, RF width / gap, courtyards).
DRC nightly jlc4: total 61: error 1 (invalid_outline), warning 60 = 36 track_dangling (the 36 iface stubs) + 24 lib_footprint_mismatch.
Notes: The S_STROBE_N L6 hop and the TAP / clock vias have no dedicated GND via beside them (only the plane vias nearby).
The IDES / OSER10 placement on the new pins (COARSE on 27) is not yet checked in Gowin EDA.
