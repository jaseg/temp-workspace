# Inter-block routing topology (six layers) — the plan every block and the integrator follow

Layer use is RULES.md rule 10: L1 RF/analog, L2 GND, L3 slow bias/control, L4 power, L5 GND,
L6 fast inter-block digital + bottom-side parts. Board 100 x 57 mm, origin top-left.
Blocks: analog (0..56, 1..22.5), fpga (56..74, 0.5..22.5), power (74..100, 0..22.5),
phase (0..99.5, 22.5..45; tap axis y 37.5, taps at x 26.71 + 4.514 n), pstrobe (9.5..26.5, 25..50),
mcuif (27..93.5, 45..57). Comparators U305..U312 sit north of the tap row (bodies about y 25..30.5),
outputs on their north pins, inputs on their south pins.

The first six-layer pass failed for one reason: on L6 everything leaving the FPGA's south edge had to
cross the east-west TAP ribbon. The plan below removes every same-layer crossing by ORDERING.

## 1. FPGA south edge (L6), west to east
`COARSE | TAP0 TAP1 ... TAP7 | DBG2 JTAG_TCK JTAG_TMS JTAG_TDI JTAG_TDO MCU_CLK SPI_CS I2C_SDA FPGA_DONE
SPI_MOSI SPI_MISO SPI_SCK I2C_SCL FPGA_RECONFIG ADC_TRIG | TAP8 TAP9 ... TAP15`
- TAP0..7 turn WEST into a staircase ribbon along y about 23..25 (north of the comparators) and drop to
  the comparator output pins U305..U308; TAP0 is the outermost (northmost, furthest west).
- TAP8..15 turn EAST the same way to U309..U312; TAP15 outermost.
- The middle group goes straight SOUTH between the two ribbons (between U308 and U309) to the highway.
- COARSE arrives from the west, north of the TAP0 track.
- This needs the FPGA pins permuted (all are ordinary bank I/O after configuration; the README says TAP
  pins may be permuted; SPI / JTAG pins keep their functions, only their fan-out order at the block
  edge changes). The schematic generator and netlist are updated with the permutation.

## 2. Highway (L6), y about 26..32, under the comparator bodies
East-west bus corridor, about 20 tracks at 0.3 mm pitch, over solid L5 ground.
- The VTH rail that ran here on B.Cu moves to L3 (it is a static threshold voltage); its vias stay.
- From the drop point at x about 60..66 the middle group splits:
  - `DBG2 TCK TMS TDI TDO` go WEST along the highway to x about 37..48,
  - `MCU_CLK SPI_CS I2C_SDA FPGA_DONE SPI_MOSI SPI_MISO SPI_SCK I2C_SCL FPGA_RECONFIG ADC_TRIG` go EAST
    to x about 70..88.
  Bus order is kept west-to-east equal to the target order, so the two turns nest without crossings.

## 3. Tap-row crossings (L6)
Between two tap cells there is one clear lane (about 1 mm: three 0.15 mm tracks at 0.3 mm pitch) between the
node window of one cell and the summing-jumper / tap-branch tracks of the next. Lanes are used straight
north-south from the highway (y 32) to the mcuif north edge (y 45):
- JTAG group: two lanes near x 38..48, landing on the mcuif interfaces above J501
  (DBG2 37.55, TCK 40.09, TMS 42.63, TDI 45.17, TDO 47.72).
- MCU group: four lanes near x 70..88, landing on MCU_CLK 73.35, SPI_CS 77.25, SDA 78.25, DONE 78.75,
  MOSI 79.25, MISO 79.75, SCK 80.25, SCL 80.75, RECONFIG 85.10, ADC_TRIG 85.80 (short jogs in the 3 mm
  between the tap row and the mcuif edge; the mcuif interfaces may be re-spaced to sit under the lanes).
- USB_DP / USB_DM: 90 ohm pair on L6 in its own lane near x 84..88 from the power block (south edge) to the
  mcuif interface at (88.0 / 88.5, 45); the pair crosses the highway band at right angles east of the
  MCU group.
No L6 track may pass under a node window (hold-node cut-outs) of a tap cell.

## 4. L1 inter-block RF
- BUF_OUT_T: analog south edge to the TMUX136, 50 ohm.
- S_STROBE_P: FPGA west edge straight into the analog block's east end (abutting); S_STROBE_N to its
  termination by the shortest path. No vias.
- PSTRB_A / PSTRB_K: pstrobe to the tap row (abutting, mirror images).
- PH_STROBE_P / _N: FPGA west edge, as a pair on L1 westward along y about 23 to the pstrobe block's
  NORTH edge at x about 10.0 / 10.5. Inside pstrobe both lines take the SAME structure to reach their
  chains on either side of the trigger corridor: L1 -> via -> L6 -> via -> L1, equal total length
  (the A-side line gets the detour the K-side needs to pass under the corridor), ground via beside each
  signal via. These are the FPGA's 300-600 ps edges before the amplifiers sharpen them.

## 5. L3 (slow)
VBIAS_A, VBIAS_K, VOFS, VNEG_REF, DAC_TRIG, VTAP_TH / VTH, ADC_REF_MID, TRIG_SEL from the mcuif north edge
(x about 37..72) to the analog block and the trigger front end, flanked by ground pour; never under the
hold node, the divider node or comparator inputs. ADC_IN: analog block to the MCU pin on L6 or L1 inside a
ground-poured corridor away from the highway and the clocks (it is a settled DC level sampled 40 ns after
the strobe: treat as sensitive, not fast).

## 6. L4 (power)
+3V3 is the background zone. Islands, each at least 2 mm wide along its whole run from the regulator:
+5V and -5V (power block to the input stage along the top edge), +2V5 and -2V5 (to hold amp, level
shifter, TLV3801, U701, tap readout), +1V2 (to the FPGA), VBUS (to the GVA-84+ chokes in pstrobe and to
J501 pin 1), VTAP_P / VTAP_N strips under the tap row (fed from +2V5 / -2V5 at the east end). L4 is cleared
under the node windows. Every supply via lands inside its zone; no supply runs as a track.
