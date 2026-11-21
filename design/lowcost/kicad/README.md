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
| `lib/scope-fe.pretty/` | `gen/gen_footprints.py` (KiCad 7 format; library nickname `scope-fe`) | Würth WR-WST 490107671612 debug footprint, re-created from the yanartas sensing board library (KiCad 9/10 format there) |
| `input.kicad_sch` | `gen_input.py` | input stage (SMA without termination, 5:1, BUF802, OPA197 servo, splitter, EXT_CLK SMA), refs 1xx (R101-R103, K101 unused since the termination was removed) |
| `sampler.kicad_sch` | `gen_sampler.py` | bridge 2x BAT15-04W, 2.2 pF hold, TPH2501 x2, refs 2xx |
| `trigger_phase.kicad_sch` | `gen_trigger_phase.py` | TMUX136, TLV3801, TRF37D73 line driver, 16 taps, COS3502 x8, SN65LVDS2, refs 3xx |
| `strobe.kicad_sch` | `gen_strobe.py` | sampler strobe (2x TRF37D73, balun, fitted BAT15-03W clamp), phase strobes (TRF + GVA-84+ x2, 80 ps stubs), refs 4xx |
| `fpga_clock.kicad_sch` | `gen_fpga_clock.py` | infrastructure, refs 5xx (J501 programming header, R511/R512 100 R) |
| `power.kicad_sch` | `gen_power.py` | infrastructure, refs 6xx |
| `mcu_if.kicad_sch` | `gen_mcu_if.py` | infrastructure, refs 7xx (STM32G474CBT6 U704 and its parts C710-C719, R729-R730, FB701, JP701, D701; J701 removed; control voltages: U701 TLV9001, R731-R736, C720-C722; R701/R702, R705-R722, C701, C703-C708, U702, U703 removed 21 Nov 2026) |
| `gen/gen_placeholders.py` | placeholder sheets (unused now: all four critical generators exist) | infrastructure |
| `gen/gen_bom.py` | `../docs/bom.csv`, `../docs/bom.md` from `export/scope-fe.net`; price table inside | integration |
| `export/` | `scope-fe.net`, `.pdf`, per-sheet `.svg`/`.png` (generated) | - |

A critical-sheet generator must: `sh = common.new_sheet("<name>")`, put one hierarchical label for every
net in `common.hier_pins("<name>")` (same name and shape), draw the signal path with `wire/path`, and
`sh.save()`. The root picks the sheet up unchanged. Need a new inter-sheet net? Add it to `SHEETS` in
`common.py` (both sheets) and rerun `gen_all.py`.

## Conventions

- Units mm, Y down, 1.27 mm grid (`g(n)`). Rotation counter-clockwise, `mirror="x"|"y"` as in KiCad.
- Power: global power symbols only: `+5V -5V +3V3 +2V5 -2V5 +1V2 VBUS GND`. Local intermediate rails on the
  power sheet are labels (`+5V4`, `+5V4F`, `-5V_LDO`). `VBUS` is the filtered USB 5 V (GVA-84+).
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
  on True/Comp pairs: PH_STROBE_P/N = 40/39 (IOT16A/B), S_STROBE_P/N = 38/35 (IOT17A/B). No LVDS input
  either: COARSE comes from the SN65LVDS2 on trigger_phase, into pin 47 (IOT10A/GCLKT_0).
- FPGA_CLK (MS5351M CLK0) -> 33 (IOR5A/GCLKT_2/RPLL_T_in). CLK2 -> 34 (spare clock).
- TAP0..15 -> 9, 10, 11, 13-24, 27 (Bank1; may be permuted for routing). SPI slave SCK/MOSI/MISO/CS ->
  28/29/30/31 (dual-purpose MSPI/SSPI config pins, free after internal-flash boot). ADC_TRIG -> 41.
- Config: RECONFIG_N 48, DONE 46, READY 45 (4.7k pull-ups; MCU reads FPGA_DONE, drives FPGA_RECONFIG
  open-drain), JTAGSEL_N 44 (4.7k pull-up + solder jumper to GND), MODE0 43 / MODE1 42 (4.7k to GND;
  MODE2 is internally grounded on QN48), JTAG TCK 3 (4.7k pull-down), TMS 4, TDI 5, TDO 7 on the programming
  header J501. DBG2 (debug I/O to J501 pin 5) on pin 6 (IOT9A/SCLK, Bank0, next to the JTAG pins; SCLK is only used
  for SSPI configuration, not for the internal-flash autoboot). Unused: 8, 32 (NC flags).

## Programming header J501 (yanartas sensing board J3: same part and pinout)

Würth WR-WST 490107671612, 2x08 Redfit IDC direct-to-board debug footprint (`scope-fe:Würth_WR-WST_debug_490107671612_2x08_P2.54mm_Vertical`:
16 plated holes 1.85/1.5 mm staggered +/-1.27 mm, two NPTH 2.2 / 2.6 mm). Footprint only: the cable connector plugs
into the board, no part is fitted (LCSC `NA`, BOM line at 0 USD, not counted as a fitted part).

| Pin | Net | | Pin | Net |
|---|---|---|---|---|
| 1 | VBUS (5 V) | | 2 | HOST_RX via 100 R R511 -> STM32 PA10 USART1_RX |
| 3 | +3V3 | | 4 | HOST_TX via 100 R R512 <- STM32 PA9 USART1_TX |
| 5 | DBG2 (FPGA pin 6) | | 6 | GND |
| 7 | JTAG_TCK (FPGA 3) | | 8 | UC_SWDIO (PA13) |
| 9 | JTAG_TMS (FPGA 4) | | 10 | UC_SWCLK (PA14) |
| 11 | JTAG_TDI (FPGA 5) | | 12 | DBG1 (PB9) |
| 13 | JTAG_TDO (FPGA 7) | | 14 | UC_NRST (100 nF C719 at the MCU) |
| 15 | GND | | 16 | GND |

HOST_RX / HOST_TX are named as on the sensing board, where the MCU is the host: HOST_RX is the MCU's UART RX
(there PC0 LPUART1_RX), HOST_TX the MCU's UART TX (there PA2), checked in its schematic. USART1 on PA9/PA10 is also
the STM32 system-bootloader UART.

## Clock

MS5351M (LCSC C1509083, 0.91 USD), Si5351A-B-GT pin-compatible MSOP-10 (library symbol reused), 25 MHz
3225 crystal (C9006, ~0.07, CL 8 pF via internal load caps). CLK0 -> FPGA_CLK, CLK1 -> MCU_CLK (STM32 HSE
bypass, PF0), CLK2 -> FPGA pin 34, 33 R series each. I2C from the MCU (pull-ups on mcu_if).

## Power tree (LCSC 1 pc; "~" = estimate from memory, not re-checked in this session)

| Rail | Part | From | Load | Price |
|---|---|---|---|---|
| VBUS | USB-C 16P (C165948 ~0.20), PTC 1.5 A (C118413, 0.08), SMAJ5.0A (C353442, 0.03), 2 A ferrite | USB | ~0.85 A total | ~0.2 |
| +3V3 | AMS1117-3.3 (C6186) | VBUS | 0.49 A (TRF37D73 x6, FPGA, MS5351M, COS3502, LVDS rx, STM32G474) | ~0.06 |
| +1V2 | AP2112K-1.2 (C460310) | +3V3 | 0.03 A | 0.24 |
| +5V4 | MT3608 boost 5.32 V (C84817) + 4.7 uH + SS14, ferrite/22 uF pi -> +5V4F | VBUS | 0.2 A | ~0.15 |
| +5V | LP2985-50DBVR (C74511), 10 nF bypass | +5V4F | 0.04 A (BUF802, OPA197) | 0.29 |
| -5V | LM27761 (C129351), -4.99 V, + ferrite/10 uF | +5V4F | 0.09 A incl. -2V5 | 1.23 (verified, prices.md) |
| +2V5 | LP5907MFX-2.5 (C165132) | +5V4F | 0.05 A | 0.34 |
| -2V5 | LM337 SOT-223 (C19267471, XBLW), 120/120 R, 10 uF ADJ bypass | -5V | 0.04 A | 0.44 |

Total about 2.5 USD plus passives. Why the boost: LM27761 needs VIN >= |VOUT| + 2 ohm x I + 30 mV;
from 4.75 V USB it cannot hold the BUF802's -4.5 V minimum. The boost also gives the +5V LDO headroom.

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
| 25 | PB11 | ADC_TRIG | EXTI11 = ADC12 regular external trigger (EXTI11 on port B; PA11 is USB) |
| 5 | PF0 | MCU_CLK | OSC_IN, HSE bypass from MS5351M CLK1 (PF1 NC) |
| 40 / 41 / 42 / 22 | PB3 / PB4 / PB5 / PB10 | SPI_SCK / MISO / MOSI / CS | SPI1 master AF5, CS as GPIO |
| 39 / 44 | PA15 / PB7 | I2C_SCL / I2C_SDA | I2C1 AF4 (pull-ups R727/R728) |
| 16 / 18 / 43 | PB0 / PB2 / PB6 | FPGA_DONE / FPGA_RECONFIG / TRIG_SEL | GPIO in / open-drain / out |
| 33 / 34 | PA11 / PA12 | USB_DM / USB_DP | USB FS (internal D+ pull-up) to J601 on the power sheet |
| 37 / 38 / 7 | PA13 / PA14 / PG10 | UC_SWDIO / UC_SWCLK / UC_NRST | SWD + reset to J501 (NRST 100 nF C719) |
| 31 / 32 | PA9 / PA10 | HOST_TX / HOST_RX | USART1 TX / RX to J501 pins 4 / 2 via R512 / R511 |
| 46 | PB9 | DBG1 | GPIO to J501 pin 12 |
| 45 | PB8 | BOOT0 | 10k R729 to GND, JP701 to +3V3 (bootloader: USB DFU or USART1) |
| 2 | PC13 | LED | green LED D701 + 1k R730 from +3V3, active low |
| 1, 24, 36, 48 / 21 / 23, 19 | VBAT, VDD / VDDA / VSS, VSSA | +3V3 / VDDA / GND | 4x 100 nF + 10 uF; VDDA via BLM15HD102 FB701, 1 uF + 10 nF |
| 9, 11, 15, 3, 4, 6, 27-29 | PA1, PA3, PA7, PC14, PC15, PF1, PB13-15 | NC | spare |
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
| VBIAS_K | PB1 OPAMP3 (DAC3_CH2) | R736 100k pull-down at PB1, R735 5.1k series to VBIAS_K (+ sampler 1k / 10 nF) | Vdac | +0.2..+2.7 V | 0.71 mV/LSB | 0 V (pull-down) |
| VTAP_TH | PA2 OPAMP1 (DAC3_CH1) | R723 30k / R724 1k, C709 100 nF (unchanged) | Vdac / 31 | 3..90 mV | 0.02 mV/LSB | 0 V |
| VNEG_REF | VREF+ | U701 inverter (see above) | -0.680 VREF+ | -1.973 V fixed | - | 0 V |

DAC loads: TRIG 5.1k + 8.87k||2.0k = 6.7k (>= 5k, max 0.47 mA); VOFS 24.9k to a virtual ground; VBIAS_A 12.2k to -2V5
(max 0.43 mA at 2.7 V); VBIAS_K 100k DC, 5.1k transient (OPAMP3: change VBIAS_K in steps of <= 1 V, 0.2 mA);
VTAP_TH 31k. Bridge at reset: anode rail about -1.7 V, cathode rail 0 V, never forward-biased; with the DACs at code 0
-1.54 V / +0.0 V (OPAMP3 low limit). Firmware: enable VREFBUF, DAC1/2/3 and OPAMP1/3 (with their self-calibration)
before the strobes; DAC_TRIG and VNEG_REF also before trusting the trigger.

**-2V5 rail dependence** (LM337 + 120/120 R: reference 1.213-1.287 V at 25 C, i.e. +/-2.9 %, about +/-4 % = +/-0.1 V
with 1 % resistors and Iadj 65 uA x 120 R; output change 0.6 % typ over 0-125 C, about 48 ppm/K, i.e. 3.6 mV over 30 K;
noise 0.003 % = 75 uV rms 10 Hz-10 kHz; 2 MHz ripple from the LM27761 (its output ripple about 1 mV, assumed not
reduced by the LM337 at 2 MHz) taken as <= 1 mV pp):

| Voltage | Sensitivity | Initial tolerance (calibrated) | 30 K drift (regulator typ) | Noise / ripple after the node filter | What it means |
|---|---|---|---|---|---|
| TRIG_LEVEL | 0.139 V/V | +/-14 mV | 0.5 mV | 10 uV rms (13 kHz); 0.9 uVpp at 2 MHz | vs TLV3801 Vos +/-0.5 mV typ / 5 mV max, 2 mV hysteresis, Ib x 1.24k = 2.5 mV typ / 12 mV max, 19 mV minimum signal: negligible |
| VBIAS_A | 0.615 V/V; pedestal 0.089 V/V (0.29 V per V of rail CM, CM = VA/2) | +/-62 mV on VBIAS_A, +/-9 mV pedestal | 2.2 mV on VBIAS_A, 0.32 mV pedestal at the hold node = 2.3 mV referred to the input (/0.69, x5) | 43 uV rms on VBIAS_A (5.5 kHz) -> 6 uV rms pedestal vs 35 uV kT/C (+0.5 uV RSS); 2 MHz ripple 0.25 uVpp | invisible in noise; drift below the 5 mV/30 K limit |
| VBIAS_A, strobe charge | 1.75 pC x 3.125 MHz = 5.5 uA through 2.89k + 1k | 21 mV (op-amp version: 5.5 mV) toward 0 V; VBIAS_K 4.3 uA x 6.1k = 26 mV | follows strobe rate and amplitude | - | static; net rail CM -2.9 mV -> pedestal -0.8 mV; calibrated per strobe setting |
| VOFS if passive (Rmid to -2V5, rejected) | 1.16 V/V at the input (Rf1/Rmid x 5) | +/-116 mV | 4.2 mV + set-resistor tracking (1 % thick film up to 200 ppm/K ratio: +17 mV) | 87 uV rms LF at the input | at or above the 5 mV/30 K limit: hence U701 |
| VOFS with VNEG_REF (built) | 0 | - | U701 drift 0.6 uV/K: 0.04 mV; R731/R732 ratio 25 ppm/K worst: 4.4 mV, same-reel tracking typically < 1 mV; VREF+ drift only away from mid-scale | - | |

Consequence for the regulator: fit the LM337 set pair (120 R / 120 R) as 0.1 % 25 ppm/K thin film (cents) so the
resistor tracking does not dominate the TRIG_LEVEL and VBIAS_A drift; no extra -2V5 filtering is needed (the node
capacitors give 5.5 kHz and 13 kHz corners and the residual noise is far below kT/C and the comparator offset).
VTAP_TH = DAC/31. VTAP_P/N = +2V5/-2V5 through 0 R links.
ADC_REF_MID = VREF+ x 1/4 = 0.725 V.

USB: J601 is now a 16-pin USB 2.0 Type-C receptacle (HRO TYPE-C-31-M-12, LCSC C165948, price estimate) with both
D+/D- pairs tied, 5.1k CC pull-downs as before, and a USBLC6-2SC6 ESD array U608 (LCSC C7519, may be left unfitted).
+3V3 budget: AMS1117 load about 0.49 A with the MCU (~35 mA), ~0.84 W dissipation.

## BOM

`docs/bom.md` (generated): **62.85 USD for one board** (64.3 before the control-voltage simplification) (MCU included, PCB excluded) against the 80 USD budget, 6.0 USD of it
estimates. Largest lines: TRF37D73 x5 7.50, GW1NZ-1 6.68, BAT15-04W x18 6.58, GVA-84+ x2 5.98, BUF802 5.89,
TLV3801 5.13, STM32G474CBT6 4.11. J501 (WR-WST footprint) is a 0 USD footprint-only line, not counted as a part.
First order with LCSC minimum quantities ~88 USD. LCSC numbers that pointed at other parts were corrected (power LDOs,
TVS, PTC) or removed (several resistor values) on 21 Nov 2026.

## Open points

Integration (21 Nov 2026):
- Root netlist (after the control-voltage simplification): 251 nets, 0 failed checks, no single-node nets; 21 NC-flagged pins, all intended (BUF802 NC 9/13/16,
  FPGA 8/32 unused, STM32 spares PA1/PA3/PA7/PA8/PB12-15/PC14/PC15/PF1, USB-C SBU1/2, NC pins of
  AP2112K/MT3608/LP5907). Not a KiCad ERC: run ERC in eeschema.
- STM32 (21 Nov 2026): ADC12 external trigger EXTI11 from PB11 is from adc.md (RM0440 not read, verify); the OPAMP/DAC3-4
  mapping is from the ST HAL OPAMP header (stm32g4xx_hal_opamp.h). PB4 (SPI1_MISO) and PB6 (TRIG_SEL) carry the UCPD dead-battery pull-downs until
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
- LM337S (XBLW) SOT-223 pinout to check against the TI pinout used in the symbol.
- Sampler ADC must sample before the S_STROBE falling edge (+160 ns) - FPGA/MCU firmware timing.
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
4. USB power ~0.85 A exceeds a default USB port (0.5/0.9 A): needs a 1.5 A-capable USB-C supply (no PD
   negotiation on board). AMS1117 dissipates ~0.8 W.
5. LM337 output-capacitor stability with ceramics, minimum-load 10 mA: check; a low-noise negative LDO
   (e.g. TPS7A30) would be better but costs ~2 USD more.
6. MS5351M exact equivalence to Si5351A (register map, crystal load) assumed from its datasheet claim.
7. GVA-84+ chains (strobe sheet) are expected on VBUS via their own chokes.
