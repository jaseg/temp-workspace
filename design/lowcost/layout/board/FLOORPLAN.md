# scope-fe board floorplan

`floorplan.png` is drawn to scale by `python3 floorplan.py`. That script also prints the block membership and the area table
below. Coordinates are in mm, the origin is the top-left board corner, +x points right and +y points down. The view is the top side.

## Outline decision: 100 x 55 mm (100 x 50 mm is not enough)

| | mm2 |
|---|---|
| sum of the netlist courtyard boxes (454 parts, `floorplan.py`) | 2624 |
| the same x 1.6 (routing allowance for slow / power parts) | 4198 |
| real RF density of the existing fragments: input 269, sampler 594, phase 2670 mm2 for 756 + ~300 mm2 of courtyards | about 3x courtyard |
| needed with the fragments' RF density and x 1.6 elsewhere | about 4900 |
| 100 x 50 minus 4 hole keep-outs (4 x 38) | 4846 |
| 100 x 55 minus the holes | 5346 |

The deciding constraint is height. The analog band needs 21.5 mm (the sampler fragment is 19.3 mm, plus the U401 sampler-strobe section).
The phase band needs 22.5 mm: comparators 15 mm above the tap axis and the PSTRB_K side 7.5 mm below it. That leaves 6 mm at 100 x 50.
J701 alone (2x13, 5.1 mm) fits in 6 mm. The three TP2272 SOIC-8 parts and 38 passives of the DAC scaling would then have to go on B.Cu under the
analog block, which must stay a quiet GND pour, or under the tap row, which is taken by the B.Cu summing jumpers and the VTH rail.
Double-sided placement is already used for power bulk capacitors, ferrites and decoupling, and it does not recover those 5 mm.
**Decision: 100 x 55 mm.** This is within the accepted 110 x 55 mm. The phase block shrinks from 105.1 to 99.5 mm and the pstrobe chains
fit into its left end. If the phase block cannot be built in 22.5 mm (the fragment is 25.4 mm), the fallback is **100 x 57 mm**.

Mounting holes: 4 x M3 (MountingHole_3.2mm_M3) at (3, 3), (97, 3), (3, 52) and (97, 52). Every block keeps copper and parts more than 3.5 mm from
each hole centre. The analog block touches the (3, 3) keep-out, so the input fragment's top-left test header J3 is dropped. J3 is not a
netlist part.

## Blocks (all at rotation 0; block-local origin = top-left of the rectangle)

| block | x | y | w | h | rot | contents (netlist refs) | courtyard mm2 |
|---|---|---|---|---|---|---|---|
| analog | 0.0 | 1.0 | 56.0 | 21.5 | 0 | 1xx, 2xx, and from the strobe sheet U401, U402, R401-R406, C401, C405, C406, C410, C411, FB401, FB402, L401, L402, R415, R416, T401, D401, TL401, NT401, TP401, TP402 (98 parts) | 536 |
| fpga | 56.0 | 0.5 | 18.0 | 22.0 | 0 | 5xx: U501 QFN48, U502 MS5351M, Y501, J501 JTAG (top edge), JP501, decoupling (25 parts) | 206 |
| power | 74.0 | 0.0 | 26.0 | 22.5 | 0 | 6xx: J601 USB-C on the right edge at y 9-18, F601, D601, FB601-603, U601-U607, L601, D602 (52 parts, both sides) | 498 |
| pstrobe | 9.5 | 26.0 | 17.0 | 23.0 | 0 | the rest of 4xx: U403/U405 TRF37D73, 10 dB pads, U404/U406 GVA-84+, chokes, TL402/TL403 stubs, NT402/NT403, DNP clamps (62 parts) | 229 |
| phase | 0.0 | 22.5 | 99.5 | 22.5 | 0 | 3xx (176 parts) and J102 (EXT_CLK SMA, input sheet; R122 next to it). The pstrobe rectangle is cut out of it, except the axis corridor y 34.5-40.5 | 756 |
| mcuif | 27.0 | 45.0 | 66.5 | 10.0 | 0 | 7xx: J701 2x13 at x 52-85 with pins along the bottom edge; U701-U703, references, scaling resistors (41 parts) | 398 |

Inner sub-placements:
- **analog**:
  - Input fragment at block (0, 3.0): SIG_IN J101 on the left board edge at y 12.85.
  - Sampler at board (14.8, 1.4). Its X1 sits on input IF1 (BUF_OUT_S), so the bridge is 3 mm from the BUF802 OUT pin, as the two fragments were designed to abut.
  - U401 + 12 dB pad + input of U402 at x 46-55.5, y 6.5-13.5. The trial merge found one overlap: sampler TP202 (bottom-left) collides with input IF2 (BUF_OUT_T exit). Move TP202 up by 1 mm.
- **phase** (folded):
  - The tap axis (PH_LINE) is at board y 37.5. Tap 0 is at x 27.0, tap 15 at x 94.7, and the far-end 49.9 R terminations at x 96-98.
  - The comparator row and VTH rail are at y 23-29.5. PSTRB_A is at y 33.1 and PSTRB_K at y 41.9.
  - The front chain no longer runs as a 28 mm in-line strip in front of the taps. It is folded as follows: J102 is on the left edge at y 37.5. U301 TMUX136, U302 TLV3801 and the U303 line driver with its bias tee and pad sit on the axis in the corridor x 3-26, y 34.5-40.5, between the two strobe chains.
  - U304 SN65LVDS2, the TLV supplies and the -0.9 V VSW_GND parts go to x 0.5-9, y 23-34. They have no RF timing role.
  - BUF_OUT_T (50 R, F.Cu) comes down from the input block at x 7 into U301.1.
  - Width check: front corridor 26 mm + 16 taps (67.7 mm) + terminations 4 mm = 98 mm, within 99.5 mm.
- **pstrobe**:
  - Chain A at y 26.5-34.5 and chain K at y 40.5-48.5 are exact mirror images about y = 37.5.
  - Each chain runs west to east: TRF37D73, 10 dB pad, GVA-84+, stub tap. The 13.2 mm shorted stub folds back towards the west.
  - The outputs leave the east side at x 26.5, y 33.1 / 41.9, as 50 R, step to 0.16 mm half a pitch before tap 0, and are equal length.
  - Inputs PH_STROBE_P/N enter the chains' north-west (A) and come round the west end on B.Cu (K, mirrored path length). See the table.

## Inter-block nets

Trace classes:
- **rf50**: 0.36 mm F.Cu over In1, pour gap >= 0.72 mm, no vias.
- **pair**: equal-length P/N pair, 0.36 mm 50 R with 33 R series resistors at the FPGA.
- **slow**: 0.2 mm on B.Cu.
- **supply**: In2 plane regions plus via pairs.

| net | from (block, side, approx. board xy, layer) | to (block, side, xy, layer) | class |
|---|---|---|---|
| /BUF_OUT_S | analog-internal (input IF1 = sampler X1, 15.15 / 12.85) | - | rf50 |
| /BUF_OUT_T | analog S, (15.3, 16.6) F.Cu | phase N-W, (7, 34.5) into U301.1, F.Cu | rf50 |
| /EXT_CLK | J102 on the left edge (0, 37.5) | U301.3 / R301 (3, 37.5) | rf50 |
| /S_STROBE_P, /S_STROBE_N | fpga W, (56, 9.5 / 10.5), F.Cu, R401/R405 at the FPGA | analog E, U401 at (55, 10), F.Cu | pair (U501 pins 38 / 35, bank 0 top) |
| /PH_STROBE_P, /PH_STROBE_N | fpga S-W, (56.5, 22) | pstrobe N, (24, 26.5) for A; K mirrored round the west end; 33 R (R407/R411) at the FPGA | pair, equal P/N length |
| /PSTRB_A, /PSTRB_K | pstrobe E, (26.5, 33.1 / 41.9), F.Cu | phase tap 0 (27, 33.1 / 41.9) | rf50, then 0.16 mm |
| /TAP0../TAP15 | phase N (comparator outputs, x 27-95, y 23) | fpga S, (57-73, 22.5); U501 pins 9-11, 13-24, 27 bank 1 (right side), permute freely | slow, B.Cu |
| /COARSE | phase U304 (5, 26) | fpga S, pin 47 | slow, B.Cu |
| /fpga_clock/FPGA_CLK, CLK2 | fpga-internal | - | slow |
| /VBIAS_A, /VBIAS_K, /VOFS, /ADC_IN, /ADC_REF_MID | mcuif N, (30-40, 45), B.Cu | analog S, (20-35, 22.5), B.Cu | slow (DC) |
| /TRIG_LEVEL, /TRIG_SEL | mcuif N-W, (28, 45), B.Cu | phase U302 / U301 (8-10, 40), B.Cu | slow (DC) |
| /VTAP_TH, /VTAP_P, /VTAP_N | mcuif N, (45, 45), B.Cu / In2 | phase VTH rail and VTAP strips, In2 | slow / supply |
| /SPI_*, /ADC_TRIG, /MCU_CLK, /I2C_*, /FPGA_DONE, /FPGA_RECONFIG | J701 (52-85, 50-55) | fpga S (60-73, 22.5); MS5351M I2C | slow, B.Cu, run at x 74-80 between the phase far end and power |
| +3V3, +1V2 | power W, (74, 5-20), In2 | fpga, analog (TRF), pstrobe, phase | supply |
| +5V, -5V | power W, In2, along the top band | analog (input BUF802 / OPA197) | supply |
| +2V5, -2V5 | power, In2 | analog (sampler), phase (TLV, VTAP), mcuif (TP2272) | supply |
| VBUS | power, In2 strip along y 22-24 | pstrobe GVA-84+ chokes (L404, L406), C418-C430 | supply |

## In2 power-plane partition (In1 is a solid GND layer everywhere)

| region (board mm) | In2 net(s) |
|---|---|
| analog x 0-16 (input) | -5V band under U101/U102, +5V elsewhere, GND island under J101 |
| analog x 15-56 (sampler, U401/U402) | +3V3 (TRF, level shifter), +2V5 / -2V5 islands under U201 (and B.Cu polygons) |
| fpga | +3V3 with a +1V2 island under U501 |
| power | VBUS, +5V4F, -5V_LDO local; +5V / -5V feed tongues leave along the top band to the input |
| pstrobe | +3V3 (TRF) and VBUS (GVA chokes), mirrored for A / K |
| phase | +3V3 (U303, U304, COS3502), +2V5 / -2V5 islands at U302, VTAP_P / VTAP_N strips under the taps (as in the fragment), VSW_GND on B.Cu |
| mcuif | +2V5 / -2V5 (TP2272), +3V3 at J701 |

Slow inter-block signals use **B.Cu**, in a corridor at x 74-80 (mcuif to fpga) and at y 44-46 (mcuif to phase / analog, under the phase K side only where no
summing jumpers lie). Switching parts (U603 MT3608, L601, D602, U605 LM27761) go to the far right of the power block, x >= 85, 70 mm from the input stage.

## Open points
- The phase height of 22.5 mm is below the fragment's 25.4 mm. Remove the fragment's edge margins and the VTAP test pads beyond the far end. Otherwise use 100 x 57.
- The pstrobe chain length (TRF + pad + GVA + stub) is estimated at 17 mm. If it is longer, tap 0 moves right; the slack is 1.5 mm.
- The balun land: the netlist footprint (Coilcraft 0805USB, pins 1/4 | 2/3) differs from the sampler fragment's custom land (1/3 | 2/4). Check the Murata DLW21SN drawing first.
