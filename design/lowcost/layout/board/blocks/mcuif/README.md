# mcuif block: STM32G474CBT6 (U704, LQFP-48) + control-voltage networks (all 36 /mcu_if/ parts)
Run `python3 gen_mcuif.py [--render]` to write mcuif.kicad_pcb, mcuif.ifaces.json, mcuif.png and mcuif_detail.png (U704 area). The script uses local helpers: a grid router copied from fpga (with point sources, N-edge targets, reserved B.Cu west-bus lanes and a 0.46 mm via-to-via spacing), `bplace`, `tie` and `courtyard_overlaps`. `prio.json` holds the routing order that routes every job. boardlib.py was not edited.
**Size**: 66.5 x 10.0 mm at board (27, 45), the FLOORPLAN rectangle with the bottom edge on the board edge. The only excursion is U704: it is 10.3 mm and fills the full height, so its courtyard reaches board y 44.70 (0.3 mm into phase, where phase is empty below y 41.6) and its pads run from y 44.95 to 54.75 (0.25 mm to the board edge). The N and S pins fan in to two staggered rows of vias under the body and continue on B.Cu.
Parts: U704, U701, the dividers and the LED are on F. Decoupling, VDDA/VREF caps, I2C pull-ups, NRST cap and the VTAP 0 R links are on B (under U704 or in a row along the board edge).

## Checks (final run)
- check_board (36 refs): 0 missing / extra / footprint / value / pad-net / no-net, 0 clearance, 0 corners > 45 deg, RF width 0, RF pour gap 0. Unrouted: only the plane-fed +3V3 (7), +2V5 (1) and -2V5 (2). There are 35 off-axis pad exits (router, at small passives and LQFP corners).
- Courtyard overlaps (BooleanIntersection > 0.005 mm2): 0.
- DRC (nightly 10.99, jlc4): 108 items. 11 errors = 10 unconnected (+3V3 / +/-2V5 only) + 1 missing outline. 97 warnings = 36 lib_footprint_mismatch, 29 track_dangling (= the 29 interface stubs), 19 via_dangling (supply vias to the absent In2), 13 isolated_copper (pour slivers). 0 clearance / courtyard / track-width / hole / silk.

## USB pair (90 R differential, F.Cu over In1)
w 0.295 / s 0.205 mm (edge-coupled microstrip, Hammerstad Z0 = 55.5 R, IPC coupling) gives Zdiff 90.1 R and 6.00 ps/mm. The pitch is 0.5 mm, equal to the pin pitch. DP 7.29 mm, DM 8.12 mm in the block: 0.83 mm / 5 ps skew from the 90-degree turn (irrelevant for USB FS; compensate on the master if wanted). Pour gap 0.59 mm (2 w).

## Interfaces (local x on the N edge y = 0; board = local + (27, 45); B.Cu unless stated)
| group | nets (x) |
|---|---|
| analog / trigger (west) | VOFS 1.10, VNEG_REF 1.60, DAC_TRIG 2.10, TRIG_SEL 2.60, VBIAS_A 3.40, VBIAS_K 4.20, ADC_IN 4.90, ADC_REF_MID 6.60 |
| phase (exact phase iface x) | VTAP_N 17.15 (0.4), VTAP_P 21.66 (0.4), VTAP_TH 35.20 (0.25) |
| fpga / J501 | UC_NRST 42.25, MCU_CLK 42.70, DBG1 46.25, I2C_SDA 47.25, SPI_MOSI 48.25, SPI_MISO 48.75, SPI_SCK 49.25, I2C_SCL 49.75, UC_SWCLK 50.25, UC_SWDIO 50.75, FPGA_RECONFIG 51.60, SPI_CS 51.85, FPGA_DONE 52.10, ADC_TRIG 52.55, HOST_TX 52.80, HOST_RX 56.20 |
| power (USB-C) | USB_DP 57.00 / USB_DM 57.50, **F.Cu**, pair |
| supplies | +3V3, +2V5, -2V5 via pairs to In2; GND vias to In1, In1 / F / B GND pours in the block |

## Deviations / open points
- The ADC_IN RC (R211 / C207) and the dividers R119, R123 and R383-R385 belong to the analog / phase blocks, so ADC_IN leaves as a plain trace. Those blocks must keep their RC next to their iface.
- The analog / trigger nets leave at the west end (board x 28-34) on the N edge, as in FLOORPLAN. The integrator must route them through the phase / pstrobe area to analog y 22.5 (x 1-22) and phase S (x 4.6 / 9.25).
- The fpga ifaces for SPI x4 and MCU_CLK do not exist yet (fpga is incomplete). The fpga bus lands at board x 69-83.
- USB route from J601 (power block) down to board (84, 45): no corridor is defined yet. Use F.Cu or B.Cu over a solid plane with 0.295 / 0.205.
- The integrator must provide In2 regions: +3V3 under U704, and +2V5 / -2V5 islands at U701 (x 52-60) and R725 / R726 (x 43-49).
- West routing is router-made (diagonal runs on F/B). It is functional but not tidy; a hand-drawn bus would look cleaner.
- kicad-cli 7 has no DRC / ERC; the DRC above is from the nightly on a scratch copy.
