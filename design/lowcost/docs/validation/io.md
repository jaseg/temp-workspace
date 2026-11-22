# Validation: I/O assignment at the FPGA (U501) and the MCU (U704)

Validator key `io`, 22 Nov 2026. Validation only: no design file was changed. Scratch: `/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/val/io/`
(`pins.py` netlist pin dump, `nodes.json`, `j.py`).

## Method

- Every U501 and U704 pad was dumped from `kicad/export/scope-fe.net` and compared with:
  - the Gowin UG842-1.6.8E QN48 pin list (xlsx extract `scratchpad/dl_gowin/qn48_pins.txt`, ug842.txt),
    DS841-2.8E (`dl_gowin/ds841.txt`), UG289-2.2.1E and UG286-2.0.2E (`scratchpad/gowin/`);
  - the ST open pin-data XML for STM32G474C(B-C-E)Tx LQFP48 (`dl_st/g4.xml`), DS12288 Rev 3 (text in
    `scratchpad/dl/ds.txt`: Table 12 pin table, Table 13 AFs, Tables 14/15/56, VREFBUF and HSE tables) and the HAL
    OPAMP header (`dl_st/opamp.h`).
- I computed the reset-state pin voltages and injected currents of the DAC/GPIO networks by hand from the netlist values.
- J501 was compared pad by pad with J3 on `/home/user/yanartas-sensors/sensing/yanartas-pillowbox-sensing.kicad_pcb`. The
  local KiCad cannot load that board (it is a newer file format), so I parsed the S-expression text.
- Not available: RM0440 and AN5225 (ST UCPD dead battery). The dead-battery behaviour comes from ST community FAQ
  pages and is marked as such.

## Checked and found correct

- U501 symbol: all 48 pins plus EPAD match the UG842 QN48 names and numbers. Power: VCC 12/37 = +1V2 (DS841 Table 3-2
  LV: 1.07-1.26 V). VCCX 36, VCCIO0 1 and VCCIO1 25 = +3V3. VSS 2/26 and EPAD 49 = GND.
- Configuration: MODE0 43 / MODE1 42 have 4.7k (R505/R506) to GND, which overrides the internal weak pull-ups.
  MODE2 is internally GND on QN48 (UG842), so mode[2:0] = 000 (AUTO BOOT; DS841 2.13.2 note: "reset mode[2:0] to 000").
  The remaining straps are 4.7k pull-ups to +3V3: RECONFIG_N 48 (R501), DONE 46 (R502), READY 45 (R503) and JTAGSEL_N 44
  (R504, + JP501). TCK 3 has a 4.7k pull-down (R507). TMS 4, TDI 5 and TDO 7 go only to J501, and none of these pins is
  reused as GPIO, which DS841 p.2 forbids together with JTAGSEL_N.
- Clock input: FPGA_CLK goes to 33 = IOR5A/GCLKT_2/RPLL_T_in, the dedicated rPLL input. 24 MHz is inside CLKIN 3-400 MHz
  (DS841 Table 3-20, C6/I5).
- COARSE goes to 27 = IOR7A/GCLKT_3. IOR7 has I/O logic, so IDES can be placed there.
- Strobe pairs are true/complement pairs: PH_STROBE_P/N = 39/40 = IOT16B/IOT16A and S_STROBE_P/N = 38/35 = IOT17A/IOT17B.
  Bank 0 has I/O logic. IODELAY exists on every I/O (DS841 2.3: 0.5 ns + 30 ps x 0..127, not for input and output at once).
- All 16 TAP inputs and every other user net are on Bank 0/1 at 3.3 V. The COS3502 (push-pull, +3V3/GND), SN65LVDS2
  (+3V3), MS5351M (VDDO +3V3) and STM32 outputs are all 3.3 V LVCMOS: levels match, and no 5 V reaches either device.
- Dual-purpose pins in use (SCLK 6, SSPI_CS_N 27, DIN 28, FASTRD_N 29, MCS_N 30, MI 31, MO 14, MCLK 15, SI 22, SO 24)
  carry no function in AUTO BOOT. They need "use SSPI/MSPI as regular IO" in the Gowin EDA dual-purpose options.
  Unused: 19 and 23.
- U704: the symbol pin numbers match the DS12288 LQFP48 column (for example PB0 16, PB3 40, PB6 43, PB12 26) and the XML.
  The alternate functions check out:
  - PA0 = ADC1_IN1 / ADC2_IN1 (TT_a; the hold amplifier U202 runs on 0..3V3, so PA0 never sees a negative voltage);
  - PA4 = DAC1_OUT1, PA5 = DAC1_OUT2, PA6 = DAC2_OUT1;
  - PA2 = OPAMP1_VOUT and PB1 = OPAMP3_VOUT. Their internal VINP = DAC3_CH1 / DAC3_CH2 (opamp.h l.216);
  - SPI1 is PB3/PB4/PB5 on AF5 (Table 13);
  - I2C1 is PA15 SCL / PB7 SDA on AF4 (XML; Table 13);
  - USART1 is PA9 TX / PA10 RX;
  - USB is PA11/PA12, SWD is PA13/PA14, and NRST is PG10 with 100 nF;
  - PB11 = TIM2_CH4 (AF1, Table 13) and ADC1/2_EXTI11 (XML).
- BOOT0: PB8 has 10k to GND and JP701 to +3V3. PB8-BOOT0 must not take negative injection (Table 56: -0 mA), and none
  occurs.
- MCU_CLK: PF0 takes 24 MHz in HSE bypass. Table 42 allows up to 48 MHz and needs VHSEH >= 0.7 VDD; the MS5351M output
  swings to 3.3 V.
- VREF+: C717 1 uF + C718 100 nF = 1.1 uF (VREFBUF CL 0.5-1.5 uF). The static load is 2.9/14.7k + 2.9/40k = 0.27 mA
  (max 6.5 mA). VRS = 10 (2.9 V) needs VDDA >= 3.135 V; AMS1117-3.3 gives 3.235 V min, so there is a 0.1 V margin.
  VBAT = +3V3, VSSA = GND.
- Reset-state voltages with the pins floating:
  - PA1 TRIG_SEL: R737 2.0k to GND against R302 10k + R303 18k to -2V5 gives -2.5 x 2/30 = -0.17 V, which is above -0.3 V.
  - PA4: Thevenin -0.46 V / 1.63k behind R383 5.1k; the pin clamps at about -0.35 V with roughly 16 uA.
  - PA6: R733 7.5k + R734 4.7k to -2V5 gives (2.5 - 0.45)/12.2k = 0.17 mA.
  - All are TT_a pins, inside the -5 mA per-pin and 25 mA total injection limits (Tables 15 and 56).
  - PB1: 100k to GND. PA5: into a virtual ground. So both sit at 0 V.
- J501 matches the sensing-board J3 pad for pad: 1 5 V, 2/4 UART via 100R, 3 3V3, 5 DBG2, 6/15/16 GND, 7/9/11/13
  TCK/TMS/TDI/TDO, 8 SWDIO, 10 SWCLK, 12 DBG1, 14 NRST. The stagger (+/-1.27 mm, 1.27 mm step) is the same.

## Findings

**IO-1 (medium, verified): the planned 960 Mbit/s serialiser rate is impossible with the GW1NZ-1 rPLL.**
- OSER10/IDES10 run at serial rate = 2 x FCLK, with PCLK = FCLK/5 (UG289 4.3.5).
- At 960 Mbit/s this needs FCLK = 480 MHz. DS841 Table 3-20 (LV, C6/I5) limits the rPLL to CLKOUT 400 MHz max and
  VCO 400-800 MHz, so the plan "24 MHz x 40" (theory l.220) is outside the PLL range.
- The gearbox limit (FMAXOSERx = 1100 Mbit/s, Table 3-16) is not the binding limit.
- The ceiling is therefore 800 Mbit/s. An integer plan at 24 MHz: 768 Mbit/s (FCLK 384 MHz, ODIV 2 -> VCO 768 MHz,
  PCLK 76.8 MHz). That keeps PH_STROBE = 48 MHz (16 bits) and S_STROBE = 3.0 MHz (256 bits).
- Effect: the coarse bins and bit slips grow from 1.04 ns to 1.30 ns, and the stated rate in the theory of operation,
  SPEC and the README is wrong.
- Fix: re-plan at 768 Mbit/s (or 800 Mbit/s with a 25 MHz FPGA_CLK) and update the documents and the coarse-window
  analysis.
- Also unverified: whether an LVCMOS33 buffer gives a usable eye at more than 700 Mbit/s. DS841 gives no I/O toggle
  rate. Confirm with a Gowin EDA build plus a bench test.

**IO-2 (medium, verified): nine permuted inputs sit on IOR6, which has no I/O logic on the GW1NZ-1.**
- Sources: UG289 ch. 4 note ("IOL6 and IOR6 pins of ... GW1NZ-1 do not support IO logic") and DS841 section 2.3, ds841.txt l.1575 ("Pins IOR6
  (A,B,C...J) of GW1NZ-1 do not support IO logic").
- Affected: TAP0 28 (IOR6I), TAP1 29 (IOR6E), TAP2 30 (IOR6C), TAP3 31 (IOR6A), TAP11 14 (IOR6B), TAP10 15 (IOR6D),
  TAP9 16 (IOR6F), TAP8 17 (IOR6G), and ADC_TRIG 18 (IOR6H).
- These pins have no IREG, IDDR/IDES or I/O-register-based capture. The +12 ns TAP latch (window 10-20.8 ns,
  theory l.181) must use fabric flip-flops, with pin-to-flop delays that differ per bit by an unconstrained amount.
  The window has about 2 ns of margin on the early side.
- COARSE (27), the strobes and the other seven TAPs are fine.
- Fix: either accept fabric capture, with timing constraints and the per-tap calibration absorbing the skew, or move
  the most timing-critical TAP lines to non-IOR6 pins. The only free one is 23 (IOR8B; 19 is IOR6J), so this means
  swapping TAPs with slow nets on IOL-capable pins (SPI 20/22/24, DBG2 8) and keeping ADC_TRIG on IOR6.
- The theory "open point 6" (input-capture placement on the permuted pins) is answered by this: it is not available
  on IOR6.

**IO-3 (low, verified): CLK2 (spare / beat-mode clock) is on a pin that is not a clock pin.**
- Pin 34 is IOR3B, a plain I/O. UG842 note 2: GCLKC_x is a global clock only with a differential input. That leaves
  the single-ended GCLKs on QN48 as 47 GCLKT_0, 33 GCLKT_2 and 27 GCLKT_3 (GCLKT_1 is not bonded).
- 47 carries TAP6. A clock on 34 reaches the clock tree through general routing, with extra jitter and skew.
- Fix: swap TAP6 and CLK2_FPGA (47 <-> 34). Both are fan-out lanes on the same south/east side, so re-check the
  routing first.

**IO-4 (low, likely): the UCPD dead-battery Rd can hold FPGA_DONE at about 1.7 V.**
- PB6 (FPGA_DONE) and PB4 (SPI_MISO) are UCPD1_CC1/CC2 (FT_c, DS12288 Table 12). ST's community FAQ says their Rd is
  switched on by a high level on PA9 (DBCC1) and PA10 (DBCC2) until PWR_CR3.UCPD_DBDIS = 1.
- PA9 is the MCU's own USART1_TX, which idles high once the UART is enabled; this includes the system bootloader on
  USART1/DFU.
- DONE is then 3.3 x 5.1/(5.1+4.7) = 1.72 V. That is below the FPGA LVCMOS33 VIH of 2.0 V, so a low DONE delays the
  FPGA wake-up (UG842 DONE definition), and the MCU reads "not configured".
- A UART adapter driving HOST_RX high loads SPI_MISO with 0.65 mA, which is harmless.
- Fix: set UCPD_DBDIS as the very first firmware action and before enabling USART1. Otherwise move FPGA_DONE to a
  non-UCPD pin such as PB10 or PB15 (both NC), or document that FPGA_DONE is not valid in the bootloader.
  The README already notes the pull-downs but says they are controlled by DBDIS only; it misses the PA9/PA10 gating.

**IO-5 (low, suspected): the strobe serialisers and IODELAY on both pins of each pair are still unproven.**
- Pairs 39/40 and 38/35 each need two independent OSER10 instances plus an output IODELAY on IOT16/IOT17 A and B.
- Gowin documents I/O logic "per pin" (DS841 2.3) but gives no placement table for using both pins of a pair
  independently.
- Fix: run a 10-minute Gowin EDA place-and-route of OSER10 + IODELAY on 35/38/39/40, IDES10 on 27 and plain inputs on
  the IOR6 pins before ordering. This closes theory open point 6.

**IO-6 (low, verified, documentation): pin references are out of date in several places.**
- kicad/README.md J501 table says "DBG2 (FPGA pin 6)", and gen_fpga_clock.py l.137 and l.165 say "DBG2 = FPGA pin 6".
  The netlist has DBG2 on pin 8 (IOT10B). Pin 6 is TAP7.
- The ADC_TRIG direction is documented two ways. README calls it "EXTI11 = ADC12 regular external trigger"; theory
  l.228 calls it "MCU PB11 -> FPGA pin 18" (a TIM2_CH4 output). Both work, because EXTI reads an AF output pin.
- Simpler: trigger ADC1/2 from TIM2_TRGO (MMS = OC4REF) and keep PB11 as TIM2_CH4 on AF1. The EXTSEL code for EXTI11
  in RM0440 was not verified.

## Not verified

- RM0440 EXTSEL codes; the PF1 GPIO use under HSE bypass (normal per RM0440 from memory, not read); simultaneous-
  switching limits for Bank 0 (four strobe outputs: no SSO table in DS841); the J501 pin 1 5 V direction (source or
  sink on the probe side).
