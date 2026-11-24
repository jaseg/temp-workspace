# scope-fe KiCad 7 project (generated)

Hierarchical schematic for `design/lowcost/SPEC.md`. **Every `.kicad_sch` here is generated; do not edit
in KiCad and expect it to survive** — change the generator in `gen/` and rerun.

## Regenerate

```
cd design/lowcost/kicad/gen
python3 test_schlib.py        # library self-test (96 pin placements, rotation/mirror, via kicad-cli netlist)
python3 gen_all.py            # all sheets + project files + netlist checks + export/ (PDF, SVG, PNG)
python3 gen_all.py --no-export
```

`gen_all.py` runs `gen_<sheet>.py` for each critical sheet if it exists, otherwise the placeholder from
`gen_placeholders.py` (which never overwrites a non-placeholder file), then `gen_fpga_clock.py`,
`gen_power.py`, `gen_mcu_if.py`, `gen_root.py` (after `gen_footprints.py`, which writes the project footprint library
`lib/scope-fe.pretty`), and collects every embedded `scope-fe:` symbol into
`scope-fe.kicad_sym`. It then exports the netlist (`export/scope-fe.net`), asserts key inter-sheet connections
(FPGA/MCU pins, VBIAS_A/K, STRB_A/K, BUF_OUT_S/T, EXT_CLK, DAC_TRIG/TRIG_LEVEL, VOFS, VNEG_REF, ADC_IN, ADC_REF_MID),
fails on any two-pin part with both pins on one net, lists single-node and NC-flagged nets, writes
`export/scope-fe.pdf` plus one SVG/PNG per sheet (PNG via `gen/svg2png.js`, node + playwright/chromium), and
finally runs `gen_bom.py` (`docs/bom.csv`, `docs/bom.md`). Each critical sheet also has its own check:
`python3 gen_<sheet>.py --check <dir>` (input: always run).

`Sheet.render()` splits every wire at each pin, wire end and label lying on its interior (`split_wires`):
KiCad 7 connects only at wire ends. Before this was in the library, mcu_if had 9 false opens (VOFS, VBIAS_A/K,
TRIG_LEVEL feedback/divider resistors, the since-removed relay gate pull-down) and the split exposed three real shorts that are now
fixed (strobe bias tees drawn with the wire through the bead and choke; crystal XB on the GND symbol).
Requires KiCad 7.0.x `kicad-cli` and `/usr/share/kicad/symbols`.

## Files and ownership

| File | Generator | Owner |
|---|---|---|
| `gen/schlib.py` | library (API in its docstring) | infrastructure |
| `gen/common.py` | sheet table (`SHEETS`: names, ref bases, sheet pins), passive helpers | infrastructure; change sheet pins here only |
| `scope-fe.kicad_sch`, `.kicad_pro`, `scope-fe.kicad_sym`, `sym-lib-table`, `fp-lib-table` | `gen_root.py`, `gen_all.py` | infrastructure |
| `lib/scope-fe.pretty/` | `gen/gen_footprints.py` (KiCad 7 format; library nickname `scope-fe`) | Würth WR-WST 490107671612 debug footprint (re-created from the yanartas sensing board library); TI DLA0010A VSON-HR-10 (TPS63802, TI land pattern 4223750/D); XR0420 4.4 x 4.2 mm inductor (Xiangru land 2 x 1.5 x 2.5 mm, gap 2.2) |
| `input.kicad_sch` | `gen_input.py` | input stage (SMA without termination, 5:1, BUF802, OPA197 servo, splitter, EXT_CLK SMA), refs 1xx (R101-R103, K101 unused since the termination was removed) |
| `sampler.kicad_sch` | `gen_sampler.py` | bridge 2x BAT15-04W, 2.2 pF hold, TPH2501 x2, refs 2xx |
| `trigger_phase.kicad_sch` | `gen_trigger_phase.py` | TMUX136, TLV3801, TRF37D73 line driver, 16 taps, COS3502 x8, SN65LVDS2, refs 3xx |
| `strobe.kicad_sch` | `gen_strobe.py` | sampler strobe (2x TRF37D73, balun, fitted BAT15-03W clamp), phase strobes (TRF + GVA-84+ x2, 80 ps stubs), refs 4xx |
| `fpga_clock.kicad_sch` | `gen_fpga_clock.py` | infrastructure, refs 5xx (J501 programming header, R511/R512 100 R) |
| `power.kicad_sch` | `gen_power.py` | infrastructure, refs 6xx (FB608 and C623 are drawn on fpga_clock at the MS5351M; docs/research/power-tree.md) |
| `mcu_if.kicad_sch` | `gen_mcu_if.py` | infrastructure, refs 7xx (STM32G474CBT6 U704 and its parts C710-C719, R729-R730, FB701, JP701, D701; J701 removed; control voltages: U701 TLV9001, R731-R736, C720-C722; R737 2.0k TRIG_SEL reset pull-down (22 Nov 2026: PA1 floats at reset; keeps the TMUX136 SEL at -1.0 V, the pin at -0.17 V); R701/R702, R705-R722, C701, C703-C708, U702, U703 removed 21 Nov 2026) |
| `gen/gen_placeholders.py` | placeholder sheets (unused now: all four critical generators exist) | infrastructure |
| `gen/gen_bom.py` | `../docs/bom.csv`, `../docs/bom.md` from `export/scope-fe.net`; price table inside | integration |
| `export/` | `scope-fe.net`, `.pdf`, per-sheet `.svg`/`.png` (generated) | - |

A critical-sheet generator must: `sh = common.new_sheet("<name>")`, put one hierarchical label for every
net in `common.hier_pins("<name>")` (same name and shape), draw the signal path with `wire/path`, and
`sh.save()`. The root picks the sheet up unchanged. Need a new inter-sheet net? Add it to `SHEETS` in
`common.py` (both sheets) and rerun `gen_all.py`.

## Conventions

- Units mm, Y down, 1.27 mm grid (`g(n)`). Rotation counter-clockwise, `mirror="x"|"y"` as in KiCad.
- Power: global power symbols: `+5V -5V +3V3 +2V5 -2V5 +1V2 VBUS GND`. `+5V1` (TPS63802 output, GVA-84+ drain supply)
  is a hierarchical sheet pin power -> strobe. Local rails on the power sheet are labels (`+5V1F`, `+3V3_CP`, `+5V_LDO`,
  `-5V_LDO`, `+2V5_LDO`, `-2V5_LDO`, `PG_5V1`); `+3V3_CLK` (MS5351M) on fpga_clock. `VBUS` is the filtered USB 5 V.
- Inter-sheet nets: SPEC names as hierarchical labels; the root connects equal names via local labels at
  the sheet pins. `CMP_P/CMP_N` stay inside `trigger_phase` (TLV3801 -> line driver and LVDS receiver).
- Fields: `Footprint` (KiCad standard library or the project library `scope-fe:` = `lib/scope-fe.pretty`, checked to
  exist at generation), `LCSC` (`NA` for footprint-only parts), optional `MPN`,
  `Price`, `Note`. Passive LCSC numbers are the usual JLC basic parts (verify value/stock before ordering).
- Instance paths `/<root uuid>/<sheet uuid>` are derived from the sheet name, so references are stable
  across regeneration and KiCad opens the project annotated.

## FPGA (GW1NZ-LV1QN48C6/I5, LCSC C5799569, 6.68 USD)

Verified from Gowin UG842-1.6.8E (GW1NZ-1 pinout, xlsx pin list, QN48 column) and UG843-1.8.7E (QN48 view,
recommended land pattern EP 4.3 x 4.3 mm -> footprint `QFN-48-1EP_6x6mm_P0.4mm_EP4.3x4.3mm`), DS841-2.8E.

- Power: VCC (core 1.07-1.26 V) pins 12, 37 = +1V2; VCCX 36, VCCIO0 1, VCCIO1 25 = +3V3 (VCCX >= VCCIO);
  VSS 2, 26, EPAD = GND. 100 nF per pin + 10 uF per rail. Ripple limits VCC 3 %, VCCIO/VCCX 5 %.
- Banks: Bank0 = 3-8, 35, 38-48 (top, IOT), Bank1 = 9-11, 13-24, 27-34 (right, IOR). Both at 3.3 V.
- **No true LVDS on GW1NZ-1** (LVDS column NONE for every pin; DS841: "GW1NZ-1 only supports ELVDS
  output", which needs VCCIO 2.5 V and resistor networks). Strobes are therefore complementary LVCMOS33
  on True/Comp pairs: PH_STROBE_P/N = 39/40 (IOT16B/A; swapped 22 Nov for the board fan-out, which output is called P is a firmware matter), S_STROBE_P/N = 38/35 (IOT17A/B). No LVDS input
  either: COARSE comes from the SN65LVDS2 on trigger_phase, into pin 27 (IOR7A/GCLKT_3; was 47 GCLKT_0).
- FPGA_CLK (MS5351M CLK0) -> 33 (IOR5A/GCLKT_2/RPLL_T_in). CLK2 -> 34 (spare clock).
- Pin permutation for the 6-layer fan-out (22 Nov 2026, layout/board/TOPOLOGY.md section 1; old -> new):
  TAP0..4 9,10,11,13,14 -> 28,29,30,31,32; TAP5 15 -> 41; TAP6 16 -> 47; TAP7 17 -> 6; TAP8..10 18,19,20 -> 9,10,11;
  TAP11..15 21,22,23,24,27 -> 13,14,15,16,17; COARSE 47 -> 27 (GCLKT_3); ADC_TRIG 41 -> 18; DBG2 6 -> 8;
  SPI SCK/MISO/MOSI/CS 28/30/29/31 -> 20/21/22/24 (plain user I/O after internal-flash boot).
  22 Nov, second step (board integration): TAP8..15 reversed on 9,10,11,13,14,15,16,17 (now TAP15..TAP8), PH_STROBE_P / _N
  swapped 40/39 -> 39/40.
  Unchanged: strobes 38/35, FPGA_CLK 33, CLK2 34, DONE 46, RECONFIG 48, READY 45, JTAGSEL 44, MODE 43/42,
  JTAG 3/4/5/7. All moved nets stay on 3.3 V user I/O (both banks at 3.3 V).
- Config: RECONFIG_N 48, DONE 46, READY 45 (4.7k pull-ups; MCU reads FPGA_DONE, drives FPGA_RECONFIG
  open-drain), JTAGSEL_N 44 (4.7k pull-up + solder jumper to GND), MODE0 43 / MODE1 42 (4.7k to GND;
  MODE2 is internally grounded on QN48), JTAG TCK 3 (4.7k pull-down), TMS 4, TDI 5, TDO 7 on the programming
  header J501. DBG2 (debug I/O to J501 pin 5) on pin 8 (IOT10B, Bank0; was 6). TAP7 on pin 6 (IOT9A/SCLK: SCLK is only
  used for SSPI configuration, not for the internal-flash autoboot). Unused: 19, 23 (NC flags).

## Programming header J501 (yanartas sensing board J3: same part and pinout)

Würth WR-WST 490107671612, 2x08 Redfit IDC direct-to-board debug footprint (`scope-fe:Würth_WR-WST_debug_490107671612_2x08_P2.54mm_Vertical`:
16 plated holes 1.85/1.5 mm staggered +/-1.27 mm, two NPTH 2.2 / 2.6 mm). Footprint only: the cable connector plugs
into the board, no part is fitted (LCSC `NA`, BOM line at 0 USD, not counted as a fitted part).

| Pin | Net | | Pin | Net |
|---|---|---|---|---|
| 1 | VBUS (5 V) | | 2 | HOST_RX via 100 R R511 -> STM32 PA10 USART1_RX |
| 3 | +3V3 | | 4 | HOST_TX via 100 R R512 <- STM32 PA9 USART1_TX |
| 5 | DBG2 (FPGA pin 8) | | 6 | GND |
| 7 | JTAG_TCK (FPGA 3) | | 8 | UC_SWDIO (PA13) |
| 9 | JTAG_TMS (FPGA 4) | | 10 | UC_SWCLK (PA14) |
| 11 | JTAG_TDI (FPGA 5) | | 12 | DBG1 (PF1) |
| 13 | JTAG_TDO (FPGA 7) | | 14 | UC_NRST (100 nF C719 at the MCU) |
| 15 | GND | | 16 | GND |

HOST_RX / HOST_TX are named as on the sensing board, where the MCU is the host: HOST_RX is the MCU's UART RX
(there PC0 LPUART1_RX), HOST_TX the MCU's UART TX (there PA2), checked in its schematic. USART1 on PA9/PA10 is also
the STM32 system-bootloader UART.

## Clock

MS5351M (LCSC C1509083, 0.91 USD), Si5351A-B-GT pin-compatible MSOP-10 (library symbol reused), 25 MHz
3225 crystal Y501 (C9006 = YXC X322525MOB4SI, **CL 12 pF**): firmware sets XTAL_CL = 10 pF, the largest internal
setting (with about 2 pF stray; validation PARTS-7). CLK0 -> FPGA_CLK 24 MHz, CLK1 -> MCU_CLK 24 MHz (STM32 HSE
bypass, PF0), CLK2 -> FPGA pin 34, 33 R series each. I2C from the MCU (pull-ups on mcu_if). VDD / VDDO (pins 1 / 7)
on `+3V3_CLK`: FB608 (BLM18KG601SN1D) from +3V3, C509 / C508 100 nF at pins 1 / 7, C623 1 uF and C510 10 uF.

Clock plan (SPEC decision 18, 24 Nov 2026; was 960 Mbit/s, above the PLL limit): FPGA rPLL from FPGA_CLK 24 MHz on
pin 33 (RPLL_T_in): IDIV 1, FBDIV 16, ODIV 2 -> VCO 768 MHz (400-800 MHz), CLKOUT = FCLK 384 MHz (<= 400 MHz;
DS841-2.8E table 3-20, LV C6/I5), CLKDIV /5 -> PCLK 76.8 MHz. OSER10 (strobes) and IDES10 (COARSE) run DDR at
768 Mbit/s (<= 1100 Mbit/s, table 3-16): 1.302 ns per bit. PH_STROBE 48 MHz = 16 bits, S_STROBE 3.0 MHz = 256 bits.

## Power tree (24 Nov 2026; `docs/research/power-tree.md`, LCSC prices read 24 Nov 2026)

| Rail | Regulator | From | Vout | Load typ / max | VIN at the part, dropout margin | Price |
|---|---|---|---|---|---|---|
| VBUS | USB-C 16P, F601 PTC 1.5 A, D601 SMAJ5.0A, FB601 220R 2 A | USB | 4.60-5.25 V | 0.75 / 0.97 A | - | ~0.3 |
| +3V3 | U601 TPS62A01ADRLR buck 2.4 MHz FPWM, L602 1 uH, R609 100k / R610 22.1k | VBUS | 3.315 V (3.25-3.38) | 0.51 / 0.67 A | 4.60-5.25 V; 100 % mode needs 3.53 V: >= 1.07 V | 0.197 |
| +1V2 | U602 TPS62A01ADRLR, L603 1 uH, R611 / R612 100k | +3V3 | 1.200 V | 20 / 30 mA | 3.25-3.38 V: 2.1 V | 0.197 |
| +5V1 | U603 TPS63802DLAR buck-boost FPWM, L601 0.47 uH, R603 459k / R604 49.9k (0.1 %) | VBUS | 5.10 V (5.04-5.16) | 0.29 / 0.34 A | regulates above and below VOUT | 0.951 |
| +5V / -5V | U604 LM27762DSSR (pump + LDOs) via FB602; FB604 / FB603 at the outputs | +5V1 | +4.80 / -4.64 V | 37 / 41 mA each | 5.03-5.15 V (<= 5.5 V); OUT+ and OUT- >= 0.14 V | 0.960 |
| +2V5 / -2V5 | U605 LM27762DSSR via FB605; FB606 / FB607 at the outputs; EN = PG_5V1 | +3V3 | +2.500 / -2.501 V (0.1 % dividers) | 40-48 / 42-50 mA | 3.24-3.37 V; OUT+ 0.70 V, OUT- 0.42 V (RNEG 5 R assumed) | 0.960 |

Totals: 3 regulator types, 5 ICs, BOM +0.9 USD against the 7-type tree. +5V / -5V keep their net names (4.80 / -4.64 V):
BUF802 VS >= 9.30 V (min 9 V). GVA-84+ drain 4.86-5.10 V at any USB voltage (+5V1, own track from C610 / C611).
Sequencing: +3V3 1 ms soft start, +1V2 from +3V3 (1.2 mV/us), +/-5V with +5V1, +/-2V5 after the TPS63802 power good.
Hottest part U601: 0.19 / 0.30 W, +27 / +45 K. Open: USB hot-plug ringing vs the 6.0 / 6.5 V abs max (C632 DNP damper),
TMUX136 supply ramp, LM27762 RNEG at 3.3 V, XR0420 stock 65 (second source C49232844, land not checked).

## MCU (STM32G474CBT6, LQFP-48, U704; on board since 21 Nov 2026)

User decision (SPEC 12): the MCU is on the board; the 2x13 header J701 to an external STM32 board is gone. Part:
STM32G474CBT6 (128 KB flash, LCSC C730123, 2.64-4.11 USD at 1 pc in the LCSC listings, about 3-5k in stock; BOM uses
4.11). STM32G474CET6 (512 KB, C730125) is pin-compatible but about 11 USD; RET6 LQFP-64 (C521608, not priced) is the
fallback if more pins are needed. Symbol `MCU_ST_STM32G4:STM32G474CBTx`, footprint `LQFP-48_7x7mm_P0.5mm`; pin numbers
as in DS12288 (LQFP48: PG10 = NRST, PB8 = BOOT0, VREF+ separate pin 20).

| Pin | Port | Net | Function |
|---|---|---|---|
| 8 | PA0 | ADC_IN | ADC12_IN1 (fast channel) |
| 10 | PA2 | DAC_TAPTH | OPAMP1_VOUT (DAC3_CH1 follower) -> 30k/1k VTAP_TH divider |
| 12 | PA4 | DAC_TRIG (sheet pin) | DAC1_OUT1, buffered -> TRIG_LEVEL network at the TLV3801 (trigger_phase) |
| 13 | PA5 | VOFS (sheet pin) | DAC1_OUT2, buffered -> Rofs into the OPA197 servo node (input) |
| 14 | PA6 | DAC_BIAS_A | DAC2_OUT1, buffered -> 7.5k / 4.7k divider to -2V5 -> VBIAS_A |
| 17 | PB1 | DAC_BIAS_K | OPAMP3_VOUT (DAC3_CH2 follower) -> 5.1k -> VBIAS_K (100k pull-down) |
| 20 | VREF+ | VREFP | VREFBUF 2.9 V (1 uF + 100 nF); feeds ADC_REF_MID divider and the VNEG_REF inverter (0.27 mA) |
| 25 | PB11 | ADC_TRIG | TIM2_CH4 (AF1) output, frame mark to FPGA pin 18; ADC1/2 triggered internally by TIM2_TRGO (MMS = OC4REF); EXTSEL code to check in RM0440 (validation IO-6) |
| 5 | PF0 | MCU_CLK | OSC_IN, HSE bypass from MS5351M CLK1 (PF1 free, used as DBG1) |
| 40 / 41 / 42 / 46 | PB3 / PB4 / PB5 / PB9 | SPI_SCK / MISO / MOSI / CS | SPI1 master AF5, CS as GPIO (layout swap: was PB10) |
| 39 / 44 | PA15 / PB7 | I2C_SCL / I2C_SDA | I2C1 AF4 (pull-ups R727/R728) |
| 43 / 27 / 9 | PB6 / PB13 / PA1 | FPGA_DONE / FPGA_RECONFIG / TRIG_SEL | GPIO in / open-drain / out (layout swaps: were PB0 / PB2 / PB6) |
| 33 / 34 | PA11 / PA12 | USB_DM / USB_DP | USB FS (internal D+ pull-up) to J601 on the power sheet |
| 37 / 38 / 7 | PA13 / PA14 / PG10 | UC_SWDIO / UC_SWCLK / UC_NRST | SWD + reset to J501 (NRST 100 nF C719) |
| 31 / 32 | PA9 / PA10 | HOST_TX / HOST_RX | USART1 TX / RX to J501 pins 4 / 2 via R512 / R511 |
| 6 | PF1 | DBG1 | GPIO to J501 pin 12 (layout swap: was PB9) |
| 45 | PB8 | BOOT0 | 10k R729 to GND, JP701 to +3V3 (bootloader: USB DFU or USART1) |
| 28 | PB14 | LED | green LED D701 + 1k R730 from +3V3, active low (layout swap: was PC13) |
| 1, 24, 36, 48 / 21 / 23, 19 | VBAT, VDD / VDDA / VSS, VSSA | +3V3 / VDDA / GND | 4x 100 nF + 10 uF; VDDA via BLM15HD102 FB701, 1 uF + 10 nF |
| 2, 3, 4, 11, 15, 16, 18, 22, 29 | PC13, PC14, PC15, PA3, PA7, PB0, PB2, PB10, PB15 | NC | spare |
| 30 / 26 | PA8 / PB12 | NC | reserved: OPAMP5 / OPAMP4 follower outputs (spare analog, ADC_REF_MID trim) |

**Control voltages (21 Nov 2026, user instruction "generate what can be generated in software directly and only use
op-amps where necessary").** The three TP2272 packages (VMID buffer, four difference amplifiers, one spare section)
are gone. DAC pins (from the ST open pin-data XML for STM32G474C(B-C-E)Tx LQFP48 and the HAL OPAMP header): buffered
external outputs exist only for DAC1_OUT1 PA4, DAC1_OUT2 PA5, DAC2_OUT1 PA6; DAC3/DAC4 reach pins only through an OPAMP
follower (VINP = DAC3_CH1 for OPAMP1 and OPAMP6, DAC3_CH2 for OPAMP3, DAC4_CH1 for OPAMP4, DAC4_CH2 for OPAMP5), whose
outputs on LQFP-48 are OPAMP1 PA2, OPAMP2 PA6, OPAMP3 PB1, OPAMP4 PB12, OPAMP5 PA8, OPAMP6 PB11 (PB11 is ADC_TRIG).
Limits used (DS12288 values from `docs/research/adc.md` and the task brief; st.com refused the PDF download): buffered
DAC RL >= 5k, CL <= 50 pF, output 0.2..VREF+ - 0.2 V; OPAMP follower <= 500 uA, CL <= 50 pF. Vdac below = 0.2..2.7 V.
Only VOFS keeps an op-amp: U701 TLV9001IDBVR (LCSC C398363, 0.080 USD) on +/-2V5 makes VNEG_REF = -VREF+ x
R732/R731 = -1.973 V (10.0k/14.7k, 0.1 % 25 ppm/K, 100 nF C722 across R732: 160 Hz), which drives only Rmid.

| Voltage | Source pin | Network | Transfer | Range | Resolution | Reset state (DAC/OPAMP off, VREFBUF off) |
|---|---|---|---|---|---|---|
| TRIG_LEVEL | PA4 DAC1_OUT1 | trigger_phase: R383 5.1k from DAC_TRIG, R384 8.87k from -2V5, R385 2.0k shunt, C304 10 nF at U302.4 (Rpar 1.24k, 13 kHz) | 0.242 Vdac - 0.139 x 2.5 V | -0.30..+0.31 V | 0.17 mV/LSB | -0.34 V (PA4 high-Z) |
| VOFS | PA5 DAC1_OUT2 | input: Rofs R119 24.9k into FB, Rmid R123 34.0k from VNEG_REF, Rf2 22.1k + RV101 | OUT offset = 0.580 - 0.402 Vdac (sim) | +/-0.50 V at OUT = +/-2.5 V input | 0.28 mV/LSB at OUT, 1.4 mV at the input | 0 (VNEG_REF 0 V, PA5 high-Z) |
| VBIAS_A | PA6 DAC2_OUT1 | R733 7.5k from DAC, R734 4.7k to -2V5 (Thevenin 2.89k) + sampler 1k / 10 nF (5.5 kHz) | 0.385 Vdac - 0.615 x 2.5 V | -1.46..-0.50 V (-1.54..-0.42 V at 0..2.9 V) | 0.27 mV/LSB | about -1.7 V (PA6 clamped near -0.4 V by its substrate diode, 0.17 mA): reverse bias |
| VBIAS_K | PB1 OPAMP3 (DAC3_CH2) | R735 4.7k series, R736 5.1k VBIAS_K to GND (+ sampler 1k / 10 nF); 24 Nov 2026, PARTS-4 | 0.520 Vdac | +0.10..+1.40 V | 0.37 mV/LSB | 0 V (R736) |
| VTAP_TH | PA2 OPAMP1 (DAC3_CH1) | R723 30k / R724 1k, C709 100 nF (unchanged) | Vdac / 31 | 3..90 mV | 0.02 mV/LSB | 0 V |
| VNEG_REF | VREF+ | U701 inverter (see above) | -0.680 VREF+ | -1.973 V fixed | - | 0 V |

DAC loads: TRIG 5.1k + 8.87k||2.0k = 6.7k (>= 5k, max 0.47 mA); VOFS 24.9k to a virtual ground; VBIAS_A 12.2k to -2V5
(max 0.43 mA at 2.7 V); VBIAS_K 9.8k (OPAMP3 <= 0.28 mA at 2.7 V); VTAP_TH 31k. Bridge at reset: anode rail about -1.7 V,
cathode rail 0 V, never forward-biased; with the DACs at code 0 -1.54 V / +0.0 V (OPAMP3 low limit). Nominal bias
+/-1.3 V (VBIAS_A DAC 0.62 V, VBIAS_K DAC 2.50 V; sim/strobe_arms), trimmed per board for efficiency ~100 %; the
VBIAS_K limit 1.40 V keeps the BAT15-04W reverse voltage <= 2.9 V at the -1.5 V input clamp (VR 4 V). Firmware: enable VREFBUF, DAC1/2/3 and OPAMP1/3 (with their self-calibration)
before the strobes; DAC_TRIG and VNEG_REF also before trusting the trigger.

**-2V5 rail dependence** (24 Nov 2026: U605 LM27762, FB- reference -1.22 V +/-1.5 % with a 0.1 % divider: +/-1.7 % =
+/-43 mV; noise 22 uV rms 10 Hz-100 kHz; pump ripple 1-2.5 mV pp at 1.7-2.3 MHz, below 1 uV after FB607 + 2.2 uF; was LM337
+/-4 % and 75 uV rms). Sensitivities as before: TRIG_LEVEL 0.139 V/V -> +/-6 mV initial (calibrated), 3 uV rms;
VBIAS_A 0.615 V/V -> +/-26 mV, pedestal 0.089 V/V -> +/-4 mV (calibrated), 2 uV rms at the hold node (0.6 % of the
0.35 mV floor). Strobe-rectified charge at 3.0 MHz: 5.3 uA through 2.89k + 1k on VBIAS_A (20 mV), 4.3 uA x 3.45k on
VBIAS_K (15 mV), calibrated per strobe setting. VOFS: VNEG_REF (U701) as before, independent of -2V5.
VTAP_TH = DAC/31. VTAP_P/N = +2V5/-2V5 through 0 R links.
ADC_REF_MID = VREF+ x 1/4 = 0.725 V.

USB: J601 is now a 16-pin USB 2.0 Type-C receptacle (HRO TYPE-C-31-M-12, LCSC C165948, price estimate) with both
D+/D- pairs tied, 5.1k CC pull-downs as before, and a USBLC6-2SC6 ESD array U608 (LCSC C7519, may be left unfitted).
+3V3 budget: 0.51 A typ / 0.67 A max (power-tree.md section 1), U601 buck 0.19 / 0.30 W.

## Decoupling (24 Nov 2026: existing capacitors moved first; layout placement)

Moved within the power block: C603 10u + C602 100n -> U601 VIN (3) / GND (1) < 1 mm, IC layer; C604 22u -> U601
output; C609 10u + C607 1u -> U602 VIN; C605 22u + C608 1u -> U602 output; C601 22u -> U603 VIN (10) / GND (8);
C610 / C611 22u -> U603 VOUT (6) / GND (8), both loops tight on the top side; C613 100n (closest) + C612 22u -> U604
pin 3 on the IC layer (DECOUPLING-4); C618 1u 0603 -> U604 C1+ / C1- (10 / 9); C626 10u -> U604 CP (5); C617 10u ->
U604 OUT+ (11); C621 10u -> U604 OUT- (6); C625 10u -> U605 pin 3; C624 1u -> U605 C1; C619 4.7u 0603 -> U605 CP;
C628 10u -> U605 OUT-; C630 10u (new) -> U605 OUT+. CIN and CCP grounds join at LM27762 pin 4; R1-R4 at the FB pins.

Moved to load pins on other sheets (drawn in the power sheet box "at the loads", net unchanged unless stated):

| Cap | Value | Net | Place at | Finding |
|---|---|---|---|---|
| C614 | 10n 0402 | -5V (was BP_5V) | BUF802 U101 pin 10 (VSO-), top side, between the pin and R112, GND via to L2 | DECOUPLING-1 |
| C616 | 2.2u 0402 | +5V | U101 pins 1 / 12, beside C108 (10 V part preferred) | PDN-6 |
| C620 | 2.2u 0402 | -2V5 (was -5V_LDO) | TLV3801 U302 pin 3 (VEE), beside C307 | PDN-6 |
| C615 | 1u 0402 | +2V5 (was +5V4F) | between U302 pin 6 and U301 pin 10 | PDN-6 |
| C606 | 100n 0402 | +3V3 | TRF37D73 U401 pin 1 (VCC), beside C404, top side | PDN-7 |
| C622 | 100n 0402 | +3V3 (was -5V) | TRF37D73 U402 pin 1 (VCC), beside C409, top side | PDN-7 |
| C627 | 1u 0402 | -5V | FB603 output | - |
| C629 | 100n 0402 | -2V5 | FB607 output | - |
| C508 / C509 | 100n | +3V3_CLK (was +3V3) | MS5351M U502 pin 7 (VDDO) / pin 1 (VDD), top side | DECOUPLING-5 |
| C623 / C510 | 1u / 10u | +3V3_CLK | after FB608, near U502 | power-tree.md |

Reference changes for the layout (24 Nov 2026, against `layout/board/scope-fe.kicad_pcb`):
- Removed: D602 (SOD-123), U606 (SOT-23-5), U607 (SOT-223).
- Added: C630 10u 0805; C631 120p 0402 DNP; C632 47u CP_EIA-3528-21_Kemet-B DNP; FB604-FB608 0603
  (BLM18KG601SN1D); L602, L603 1u L_1008_2520Metric; R609-R617 0402.
- New footprint / part on an existing ref: U601, U602 SOT-563 (TPS62A01A); U603 `scope-fe:Texas_DLA0010A_VSON-HR-10_2x3mm_P0.5mm`;
  U604, U605 WSON-12-1EP_3x2mm_P0.5mm_EP1x2.65 (LM27762); L601 `scope-fe:L_XR0420_4.4x4.2mm`; FB602, FB603 0805 -> 0603;
  R402, R408, R412 0402 -> 0603.
- Value / net only: R603-R608 (0.1 % dividers), R378 / R379 43 R, R735 4.7k, R736 5.1k now VBIAS_K to GND (was at
  PB1), U502 pins 1 / 7 on +3V3_CLK, L404 / L406 and C418-C420 / C428-C430 on +5V1 (was VBUS), plus the moved
  capacitors above.

DECOUPLING-2 / -3 (TLV3801 HF caps, TMUX136 C301 / C303 within 1 mm of pins 10 / 5) are placement items for the layout;
no part is added. Only new capacitor: C630. DNP footprints: C631 120 pF (U601 Cff across R609), C632 47 uF 10 V tantalum
(VBUS hot-plug damper, at U601 / U603 input).

## BOM

`docs/bom.md` (generated): **63.76 USD for one board** (24 Nov 2026 power tree; 62.85 before) (MCU included, PCB
excluded) against the 80 USD budget, 6.1 USD of it estimates. Largest lines: TRF37D73 x5 7.50, GW1NZ-1 6.68, BAT15-04W x18 6.58, GVA-84+ x2 5.98, BUF802 5.89,
TLV3801 5.13, STM32G474CBT6 4.11. J501 (WR-WST footprint) is a 0 USD footprint-only line, not counted as a part.
First order with LCSC minimum quantities ~88 USD. LCSC numbers that pointed at other parts were corrected (power LDOs,
TVS, PTC) or removed (several resistor values) on 21 Nov 2026.

## Open points

Integration (21 Nov 2026):
- Root netlist (24 Nov 2026): 265 nets, 0 failed checks, no single-node nets; 20 NC-flagged pins, all intended (BUF802 NC
  9/13/16, FPGA 19/23, STM32 spares PA3/PA7/PA8/PB0/PB2/PB10/PB12/PB15/PC13-15, USB-C SBU1/2, PG of U601/U602).
  ERC (`tools/run_erc.sh`, KiCad nightly): 0 errors, 16 warnings (SMA footprint link and Conn_Coaxial library copy).
- STM32 (21 Nov 2026; ADC trigger revised 24 Nov): ADC1/2 from TIM2_TRGO, PB11 = TIM2_CH4 frame mark (EXTSEL code in
  RM0440 not read, verify); the OPAMP/DAC3-4
  mapping is from the ST HAL OPAMP header (stm32g4xx_hal_opamp.h). PB4 (SPI1_MISO) and PB6 (FPGA_DONE, an input) carry the UCPD dead-battery pull-downs until
  firmware sets PWR_CR3.UCPD_DBDIS. USB-C 16P, USBLC6-2SC6 and the LED are price estimates; check the STM32G474CBT6
  price on the LCSC page (only search snapshots read).
- Stock: BAT15-03W (C5310874) 0 at LCSC; TRF37D73 25 at LCSC (Mouser has stock); SMA
  edge connectors not sourced (2 x ~2 USD estimate). TP2272 no longer used (U701 is a TLV9001IDBVR, LCSC C398363).
- LCSC numbers missing (BOM `est`): 1.5p, 2.2p, 3.3p, 100p, 470p, 220p, 2.2u 0402, 4.7u 0603, 1% values (4.99M,
  300k, 17.8k, 22.1k, 24.9, 499, 82, 91, 68, 47, 470, 49.9, 24.9k, 34.0k, 14.7k, 7.5k, 8.87k, 2.0k, 30k, 78.7k, 499k,
  1.54M, 18k, 2.7k), 600R beads, 47 uH 1008, 120 nH 0402, 4.7 uH SRN4018, 50k trimmer.
- Control voltages (21 Nov 2026): DS12288 DAC/OPAMP load limits and the VREFBUF reset state (high-Z) taken from
  adc.md / the brief, PDF not re-read; PA6 sees about -0.4 V / 0.17 mA substrate injection while the DAC is off
  (reset, bootloader): within the absolute maximum as remembered, check IINJ in DS12288; the input_stage layout fragment
  needs R119 24.9k and the new R123 (Rmid, VNEG_REF); trigger_phase fragment needs R383-R385. VBIAS_A / VBIAS_K ranges
  (-1.46..-0.50 / +0.2..+2.7 V) cover the strobe RESULT window 0.5..1.2 V; the 40 / 75 ps re-simulation is still open.
- Tap hold caps are 0.5 pF (nearest stocked C0G value, LCSC C1544) instead of 0.47 pF.
- Power tree (24 Nov 2026): LCSC numbers to assign for the 0.1 % 0402 divider resistors (class price 0.02 USD), 1u 0603
  25 V (C618), 4.7u 0603 (C619), 2.2u 0402 10 V (C616); the C618 field carried an 0402 part number before.
- Sampler ADC must sample before the S_STROBE falling edge (+167 ns at 3.0 MHz) - FPGA/MCU firmware timing.
- Phase strobe stubs now 80 ps (13.2 mm) per sim/phase_array (strobe sheet; not part of the phase_trigger fragment,
  which takes PSTRB_A/K from its X2/X3 interfaces); signal-line meander drawn 70 ps per tap for 75 ps, strobe lines 40 ps per tap (layout pitch 4.514 mm).
- Remaining cosmetic text overlaps: power sheet value/power-symbol labels, COS3502 power units, MS5351M
  +3V3 pair.

Earlier:
1. Prices marked "~" and the passive/crystal/USB LCSC numbers were not re-checked in this session.
2. (Closed 21 Nov 2026) TP2272 was specified 2.7-36 V (datasheet Rev D.1), so +/-2.5 V was legal; it is no longer used.
   U701 TLV9001: 1.8-5.5 V, RRIO, Vos 0.4 mV typ / 1.6 mV max, 0.6 uV/K (TI SBOS833R), run at +/-2.5 V.
3. MODE[1:0] = 00 for autoboot from internal flash is from memory of Gowin UG290; verify. Verify in Gowin
   EDA that OSER10 can be placed on IOT16/IOT17 and IDES on pin 47 (GW1NZ-1 IO logic placement rules).
4. USB power 0.75 A typ / 0.97 A max exceeds a default USB port (0.5/0.9 A): needs a 1.5 A-capable USB-C supply (no PD
   negotiation on board). (AMS1117 dissipation: closed, buck since 24 Nov 2026.)
5. (Closed 24 Nov 2026) LM337 replaced by the LM27762 U605 (ceramic-stable).
6. MS5351M exact equivalence to Si5351A (register map, crystal load) assumed from its datasheet claim.
7. GVA-84+ chains (strobe sheet) are on +5V1 via their own chokes (24 Nov 2026; was VBUS).
