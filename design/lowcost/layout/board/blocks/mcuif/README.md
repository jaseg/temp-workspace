# mcuif block: STM32G474 U704, control-voltage networks, U701, J501 + R511 / R512 (39 refs)
`python3 gen_mcuif.py [--render]` writes mcuif.kicad_pcb / .ifaces.json / .png / _detail.png. Hand-drawn, explicit coordinates, no router.
Block 66.5 x 12 mm at board (27, 45); copper >= 0.5 mm from y 57; only interface stubs reach y 45. J501 at board x 31..53, courtyard to y 56.5.
The integrator must move J501, R511 and R512 into mcuif in floorplan.py / boardlib.

## Pin-escape plan (U704 rot 0, centre board (79, 51.3))
- N: 39-44, 46 inward vias (two staggered rows), B.Cu straight north = FPGA bus. 37 / 38 SWD outward onto two F.Cu lanes (y 45.7 / 46.05) to J501.8 / .10 from above.
  45 BOOT0 inward via, then the top B lane to JP701 / R729 (B). 47 GND via; 48 + 1 into C713 (NW notch), C710 on B.
- E: 33 / 34 USB east then north (w 0.295 / s 0.205, 90.1 R, DP = DM 9.572 mm). 25 / 27 east to vias, B.Cu north. 28 LED east to R730 / D701.
  31 / 32 UART inward vias. 35 GND via, 36 into C711 (NE notch).
- W: 5 CLK, 8 ADC_IN, 9 TRIG_SEL go F.Cu west then north in columns. 10 TAPTH runs F.Cu west to its divider column. 12 DAC_TRIG has a via onto a B lane.
  6 DBG1 / 7 NRST inward vias (C719 on F at pin 7).
- S: 13 / 14 / 17 DACs, 20 VREF+ and 21 VDDA inward vias. C717 / C718 (VREF+) and C715 / C716 / FB701 (VDDA) on B at the vias. 24 into C712 (SE notch).
- B lanes leaving W (N->S): BOOT0, RX, TX, DBG1, NRST, VREFP, BIAS_K, BIAS_A, VOFS, DAC_TRIG. No same-layer crossings.
  The J501 bus jogs up 0.85 at x 60 and drops into the north-row pins from above. R511 / R512 sit inline on B. JTAG leaves the south row on F.Cu, then via + B stub.
- Analog on F west of U704: one column per output (series R inline, shunt parts hanging west, via + B stub at the top).
  VREFP: B lane to the R703 column, then along the bottom channel (y 56.1, under J501) to U701 / R731 / R732 / C722 / C720 at board x 28..37 (C721 on B).
- R725 / R726 (VTAP links) and C714 are east of the USB pair.

## Swaps (gen_mcu_if.py, gen_all.py checks, kicad/README.md; gen_all: 0 failed checks, 0 single-node nets)
TRIG_SEL PB6->PA1 (9), FPGA_DONE PB0->PB6 (43), SPI_CS PB10->PB9 (46), DBG1 PB9->PF1 (6), FPGA_RECONFIG PB2->PB13 (27), LED PC13->PB14 (28).

## Interfaces (N edge y 45, board x, B.Cu unless noted)
| group | nets |
|---|---|
| U701 / J501 JTAG | VNEG_REF 36.95, DBG2 37.55, TCK 40.09, TMS 42.63, TDI 45.17, TDO 47.72 |
| analog | ADC_REF_MID 55.29, DAC_TRIG 58.60, VOFS 59.50, VBIAS_A 63.00, VBIAS_K 66.50, VTAP_TH 70.30 (w 0.25), TRIG_SEL 71.00, ADC_IN 71.50 |
| fpga bus | MCU_CLK 73.35, SPI_CS 77.25, I2C_SDA 78.25, FPGA_DONE 78.75, MOSI 79.25, MISO 79.75, SCK 80.25, I2C_SCL 80.75, FPGA_RECONFIG 85.10, ADC_TRIG 85.80 |
| USB / VTAP | USB_DP 88.00 / USB_DM 88.50 F.Cu 90 R pair; VTAP_P 90.60, VTAP_N 92.45 (w 0.4, class supply) |
| supplies | +3V3, +2V5, -2V5, VBUS to In2 (via pairs, J501 THT pins); GND In1 + F / B pours |

## Checks (last run)
- check_board (39 refs): 0 missing / extra / footprint / value / pad-net, 0 clearance, 0 corners, 0 off-axis, 0 courtyard, RF 0. Unrouted: only +3V3 (8), +2V5 (1), -2V5 (2) (plane-fed).
- DRC nightly jlc4: total 101, error 12 (11 unconnected +3V3 / +-2V5, 1 outline), warning 89 (38 lib_footprint_mismatch, 1 lib issues,
  28 track_dangling = the 28 interface stubs, 14 via_dangling = supply plane vias, 8 isolated GND fill). 0 hole / clearance / courtyard / width / silk.

## Open points
- TRIG_SEL reset pull-down R737 2.0k (schematic gen_mcu_if.py): on B under the TRIG_SEL column (local 43.3, 3.35), GND pad into the B pour. Floating PA1 -> pin -0.17 V, SEL -1.00 V (switch ground -0.89 V). 5.1k as first asked would leave the pin at -0.39 V (beyond the -0.3 V limit) and SEL at -1.14 V. Its TRIG_SEL pad is entered at 45 deg for the last 0.2 mm (1 off-axis exit; no room between R729 / JP701).
- C721 moved 0.88 mm east of its two vias (B tracks, no via-in-pad). Pour islands: island removal 'always' (0 isolated copper). C719 GND reaches its via through a 0.3 mm F track.
- VNEG_REF / ADC_REF_MID moved west (36.95 / 55.29), RECONFIG / ADC_TRIG / USB / VTAP moved east. The integrator routes to these.

## Integration changes (24 Nov 2026)
- VBIAS_K divider: R735 4.7k inline (U704.17 -> VBIAS_K), R736 5.1k now from VBIAS_K to GND at the output node (B row y 2.05,
  GND via at 36.75). check_board: 0 apart from the plane-fed supplies and the known R737.1 entry (fixed on the board).

- TIGHTEN (24 Nov): C716 / C715 (VDDA, B) GND pad gets its own plane via 0.9 mm south-east (clear of the F pin row and the board edge); the return no longer goes only to the via at pin 23.

## REPAIR (24 Nov, recheck RF2-3)
- U704 pin 24: the +3V3 plane via moved from the pin's inner end to just north of C712's +3V3 pad (pin -> C712 -> via).
  Pins 48 / 1: the inner via stays (it is C710's via on B; no room behind C713). Pin 36: the nearest +3V3 via is R727's
  pull-up feed, not a decoupling via. Render: `mcuif_netview_u704.png`.
