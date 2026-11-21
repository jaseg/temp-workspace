# ADC for the sampler output: STM32G474 internal ADC or an external one

November 2026. Sources: STM32G474xB/xC/xE datasheet DS12288 Rev 3 (LCSC copy of the
STM32G474RCT6 datasheet, read with pdftotext; st.com itself refused the connection, so the
reference manual RM0440 and AN5346 could not be downloaded). LCSC prices from
lcsc.com/product-image/Cxxxx.html, single unit. DigiKey and Mouser were not reached for the
ADCs (one DigiKey fetch landed on a wrong product); those prices are open.
Statements marked (RM, unverified) are from memory of RM0440 or from the STM32G4 HAL headers
as quoted by a web search, not from a document read here.

## Verdict

The G474 internal ADC is adequate. Use it; no external ADC. Strobe rate 1-4 MHz on one
ADC pair, 5 MHz by alternating two ADCs. Its noise (about 0.48 mV rms at the pin) is about
0.2 mV rms referred to the bridge with a hold gain of 5, below the 1 mV target. The external
ADCs that are fast enough cost 6-8 USD and give 1-1.5 dB more SNR, which is not worth it. The
one real argument for an external ADC is that the FPGA could read it directly and attach each
sample to its tap snapshot. With the internal ADC, the MCU has to keep the ADC stream and the
FPGA time-stamp stream aligned by counting (see "Pairing samples with timing").

## STM32G474 ADC facts (DS12288 Table 69-71)

| Item | Value | Source |
|---|---|---|
| ADCs | 5 × 12-bit SAR (ADC1/2 share the ADC12_INx pins; ADC3/4/5) | DS Table 2 |
| fADC | up to 60 MHz single ADC; 52 MHz with all ADCs on at VDDA ≥ 2.7 V | Table 69 |
| Conversion | ts + 12.5 cycles; ts from 2.5 to 640.5 cycles | Table 69 |
| Max rate | 4 Msps at 12 bits (2.5 + 12.5 = 15 cycles at 60 MHz) | DS feature list |
| Sampling cap CADC | 5 pF typ | Table 69 |
| RAIN max, 12 bit, fast channel | 100 Ω at 2.5 cycles (41.7 ns); 330 Ω at 6.5 cycles (108 ns); 680 Ω at 12.5 cycles | Table 70 |
| Fast channels | ADCx_IN1 to IN5 (e.g. ADC12_IN1 = PA0, ADC12_IN2 = PA1, ADC3_IN1 = PB1) | Table 70 note, pinout |
| ENOB / SNR, single-ended, 4 Msps, VDDA = VREF+ = 3 V, 25 °C | 10.6 bits typ (10.4 min); SNR 66.9 dB typ (65 min); THD -73 dB | Table 71 |
| Same, differential | 10.9 bits, SNR 69 dB | Table 71 |
| INL / DNL single-ended | 2.3 / 1.1 LSB typ, 3.4 / 1.9 max | Table 71 |
| Trigger latency | 1.5-2.5 cycles with the asynchronous ADC clock (CKMODE = 00); fixed 2.0 / 2.25 / 2.125 cycles with the synchronous clock HCLK/1, /2, /4 | Table 69 |
| Input range | 0 to VREF+; VREFBUF gives 2.048, 2.5 or 2.9 V; separate VREF+ pin on LQFP64 | 3.20, pinout |
| Triggers | on-chip timers and external signals (EXTI); oversampling unit; DMA | 3.18 |
| Negative injection | to be avoided on any analog pin; ST recommends a Schottky diode to ground | Table 71 note 3 |

Noise at the pin: SNR 66.9 dB at a 3 V reference means a full-scale sine of 1.06 V rms
against 0.48 mV rms of noise plus quantisation (1 LSB = 0.73 mV, 0.71 mV at 2.9 V).

## Signal levels and noise budget

From scope-frontend.md: the bridge input is clamped to ±0.5 V. The simulated sampler
(10 Ω source, fixed bias) has gain 0.46 and an efficiency of 72 % per strobe. The hold
node therefore swings about ±0.23 V. It may reach ±0.3 V with the 0.15 pF variant
(gain 0.53).

| Contribution | At hold node | Referred to the bridge input |
|---|---|---|
| kT/C of 2.2 pF | 43 µV rms | 94 µV |
| G474 ADC, 0.48 mV at the pin, total gain 5 after the hold node | 96 µV | 0.21 mV |
| Same after deconvolving the 72 % efficiency (one independent point per strobe) | - | about 0.3 mV |
| Probe input, through the 5:1 divider | - | about 1.5 mV (ADC) / 0.5 mV (kT/C) |

The 1 mV target is met at the bridge with margin. At the probe tip, behind the 5:1 divider,
the ADC alone contributes 1-1.5 mV. If 1 mV is meant at the probe tip, take two conversions
per strobe (dual interleaved ADC1/ADC2 on the same pin, below) and average them: about
0.75-1.05 mV. Sample-to-sample averaging in the display does the rest. A 14-bit external
ADC would not change the picture much: kT/C and the hold amplifier then dominate.

Resolution: 2.3 V of the 2.9 V span covers 1 V at the bridge, so 1 LSB is about 0.31 mV at
the bridge and 1.6 mV at the probe tip, about 3200 codes over full scale.

## Droop and aperture

dV/dt = I_leak / C_hold, with C = 2.2 pF:

| Net leakage | Droop | In a 108 ns sampling window | Over a 300 ns delay strobe → sample |
|---|---|---|---|
| 1 nA | 0.45 mV/µs | 49 µV | 0.14 mV |
| 10 nA | 4.5 mV/µs | 0.49 mV | 1.4 mV |
| 5 µA (BAT15 datasheet maximum, earlier estimate) | 2.3 V/µs | 0.25 V | unusable |

The leakage that matters is the net current: the mismatch between the upper and lower
diode pairs, plus op-amp bias (pA, negligible). At nA level, droop is harmless as long as
the conversion starts at a fixed delay after each strobe. It is then a small,
voltage-dependent offset that calibration removes. The trigger-latency spread with the
asynchronous ADC clock (1 cycle, 17-24 ns) gives ≤ 11 µV of droop variation at 1 nA. Even
so, use the synchronous clock mode (CKMODE ≠ 00) so the latency is deterministic.
Leakage on the order of µA would need a larger hold capacitor. Measure the real figure on
the first board: convert twice per strobe (below) and the slope is the droop.

The bridge has memory (72 % efficiency): the software model needs the held value
immediately before each strobe. With droop, that is not the value converted right after
the previous strobe. A second conversion just before the next strobe gives the value
directly, and costs nothing at 1-2 MHz strobe rates.

## Timing per strobe

1. Strobe at t = 0. The hold node jumps by up to the full scale.
2. The hold amplifier and level shifter settle: about 100-150 ns to 12 bits (OPA810 or
   TPH2501, see opamps.md), plus the 7 ns RC at the pin.
3. The ADC starts sampling at t ≈ 150-200 ns: 6.5 cycles = 108 ns at 60 MHz (RAIN ≤ 330 Ω).
4. Conversion, 12.5 cycles = 208 ns. The input is free again, so the next strobe can come
   during the conversion.

Minimum strobe period on one ADC: about 250 ns sampling-to-sampling, so 4 MHz.

- **5 MHz:** two ADCs (ADC1 and ADC2 on the same ADC12_IN1 pin) on alternate strobes. Each
  then converts at 2.5 Msps. Their sampling windows (108 ns) do not overlap at 200 ns
  spacing. Converting the same channel on two ADCs simultaneously is not allowed (RM,
  unverified), so the windows must stay apart. In dual interleaved mode the hardware
  handles the alternation (RM, unverified).
- **Recommended:** 2 MHz strobe, with dual interleaved ADC1 + ADC2, two conversions of each
  held value 100-200 ns apart. That gives √2 less ADC noise, plus droop and a pre-strobe
  value. ADC3 or ADC4 stays free for slow housekeeping (supplies, temperature, DAC
  readback).
- **Throughput:** 4 Msps × 2 bytes = 8 MB/s by DMA into SRAM. Process in blocks.
  Fine for 170 MHz.

ADC trigger: the FPGA already generates the strobes, so it should also output an ADC
trigger pulse at a fixed delay after each strobe, to an EXTI pin that is a regular
external trigger for ADC12 (EXTI11 for ADC12; RM, unverified). Alternatively, the FPGA
clocks a timer through ETR and a timer compare starts the ADC. Either way the timing
reference is the strobe, not the MCU clock.

### Pairing samples with timing

The FPGA has the tap snapshot or time stamp for each strobe; the MCU has the ADC result.

1. Both sides start from a common reset (an FPGA "arm" pulse that also enables the ADC
   trigger).
2. The FPGA streams per-strobe records with a sequence number over SPI or QSPI to the MCU.
3. The MCU checks each block by comparing its DMA count with the FPGA sequence count.
4. If the counts disagree, the block is discarded and the system re-arms.

An external ADC read by the FPGA would avoid this. The cost is about 6-8 USD and a few FPGA
pins. It is not needed.

## Drive network (recommended)

The hold amplifier runs on ±2.5 V and the hold node sits around 0 V. The ADC pin must stay
in 0 to VREF+ and must never go negative. So a level shift is needed.

```
hold node ──► U1 hold amp, non-inverting, G = +5 (±2.5 V supply)
              output ±1.15 V around 0 V
          ──► R_in 1.0 kΩ ──┬── U2 (–) ── U2 output ─ 33 Ω ─┬─► PA0 (ADC12_IN1)
                            R_f 1.0 kΩ to U2 output          220 pF C0G to AGND
              U2 (+) = 0.725 V   (VREF+ 2.9 V / 4, divider or DAC; 10 nF to AGND)
              U2: RRIO op amp on VDDA = 3.3 V (second TPH250x, or the G474 opamp is NOT usable here)
```

Vadc = 2·0.725 − Vout1 = 1.45 V − Vout1, so 1.45 ± 1.15 V (0.30-2.60 V) at VREF+ = 2.9 V.

- The inversion is absorbed in software.
- Gain is set by U1 (G = 4-6, to taste). With 1 % resistors the gain is calibrated, not trimmed.
- U2 runs on the ADC's own 3.3 V supply, so it cannot drive the pin above VDDA or below
  ground. No clamp diodes are needed.
- The U2 input pins sit at 0.725 V, inside the common-mode range of an RRIO part.

RC at the pin:

- 33 Ω + 220 pF: τ = 7.3 ns, 9τ = 66 ns to settle a step to 12 bits.
- Kickback charge sharing: 5 pF / 225 pF = 2.2 % of the difference from the previous
  sample, recovered in 14τ within the 108 ns sampling time. 33 Ω is far below the
  330 Ω RAIN limit.
- The RC also limits the noise bandwidth of U1/U2 to about 22 MHz.
- Use 6.5-cycle sampling. 2.5 cycles (100 Ω limit) is possible but leaves no margin.

Alternative with one op amp less:

- Run U1 from +3.3 V / −2.0 V (5.3 V total, inside a 5.5 V CMOS part).
- Return its gain resistor to Vr = −0.36 V instead of ground:
  Vout = G·Vin + (1 − G)·Vr, so 1.45 V at Vin = 0 for G = 5.
- This needs a −2.0 V rail and gives worse supply rejection.
- Not preferred.

The internal OPAMPs (13 MHz GBW, 45 V/µs high-speed mode, 0-VDDA inputs, ±3 mV offset,
500 µA drive, 50 pF max load) cannot do the level shift. Their input pins cannot see the
negative hold-amplifier swing. In inverting PGA mode the input resistor end is a pin, and
it would see ±1.15 V. The internal PGA modes also settle slowly: GBW/2 at gain 2 is
6.5 MHz, so about 220 ns to 12 bits. They are better used as DAC buffers (below).

Differential ADC mode (+0.3 dB SNR, about 0.3 bit) would need a differential driver
with a VREF+/2 ± 0.18 V common mode. Not worth an extra part.

## External ADC candidates

| Part | Price (LCSC, 1 pc) | Stock | Specs | Note |
|---|---|---|---|---|
| TI ADS7883SDBVT, C122523 | 6.28 (3.67 at volume) | 4 pcs | 12 bit, 3 Msps, SPI, SOT-23-6, single supply 2.7-5.5 V | DigiKey not checked |
| ADI AD7276AUJZ-REEL7, C208646 | 7.90 | 167 | 12 bit, 3 Msps, SPI, TSOT-23-6 (rate from memory) | DigiKey not checked |
| LTC2366, C680319 | about 11.3 (web-search snippet) | ? | 12 bit, 3 Msps | too expensive |
| Si-Change XC2362, C23377959 | 1.77 | 987 | 12 bit, **500 ksps**, SNR 72 dB at 100 kHz, LTC2362 pin-compatible (datasheet read) | too slow for ≥ 1 MHz strobes |

None of the fast ones beats the internal ADC by enough to pay 6-8 USD out of an 80 USD
budget. The 3 Msps parts are also slower than the G474 (4 Msps, or 5+ with two ADCs).
Cheap Chinese SPI ADCs found on LCSC (Si-Change XC121S101, XCS7476 = ADC121S101 / ADCS7476
clones, 1 Msps; XC2362 500 ksps) are all ≤ 1 Msps.

## Analog control voltages from the MCU

| # | Voltage | Range and resolution needed | G474 resource |
|---|---|---|---|
| 1 | Trigger / external-clock threshold for the TLV3801, shared by both inputs through the TMUX136 | about ±0.3 V at the comparator, ≤ 1 mV steps; level-shifted to the comparator's shifted supply | DAC1_OUT1 (PA4, buffered, 1 Msps) + external op amp for offset and scale |
| 2 | Vertical offset into the OPA197 servo path | bipolar, about ±0.5 V at the bridge scale; 12 bits; low noise and drift | DAC1_OUT2 (PA5, buffered) + RC filter + summing resistor into the servo |
| 3 | Bridge bias, positive rail trim | about +1 V ± 0.2 V | DAC3_CH1 → OPAMP1 follower → PA2 → external op amp/level shift |
| 4 | Bridge bias, negative rail trim | about −1 V ± 0.2 V; needs inversion | DAC3_CH2 → OPAMP3 follower → PB1 → external inverting op amp |
| 5 | Delay-line tap comparator threshold (COS3502), one common threshold | near the tap common-mode voltage, ±30 mV fine trim | DAC2_OUT1 (PA6, buffered) |
| 6 | ADC level-shift reference (0.725 V) | fixed, ratiometric to VREF+ | resistor divider from VREF+; DAC4_CH1 → OPAMP4 → PB12 if trim is wanted |
| 7 | Spare: strobe-driver bias, delay-line gate bias, or a second tap threshold | - | DAC4_CH2 → OPAMP5 follower → PA8 |

- Count: seven needed or useful, and the G474 has exactly seven DAC channels.
  - Three are buffered to pins: DAC1_OUT1 PA4, DAC1_OUT2 PA5, DAC2_OUT1 PA6. PA6 is shared
    with OPAMP2_VOUT.
  - Four internal channels (DAC3/DAC4, 15 Msps, unbuffered) can reach pins through the
    internal OPAMPs in follower mode. The OPAMP VINP can be DAC3_CH1 (OPAMP1, OPAMP6),
    DAC3_CH2 (OPAMP3), DAC4_CH1 (OPAMP4) or DAC4_CH2 (OPAMP5) (HAL header, unverified).
    Output pins from the datasheet: OPAMP1 PA2, OPAMP3 PB1, OPAMP4 PB12, OPAMP5 PA8,
    OPAMP6 PB11.
- OPAMP limits: 500 µA load, 50 pF max, so use ≥ 1 kΩ in series before any filter
  capacitor. Offset ±3 mV, which calibration removes. Drift 10 µV/°C. A forum report says
  DAC3 → OPAMP1 output sat at 0 V until the DAC and OPAMP self-calibration ran; do that at
  initialisation.
- DAC output range is 0.2 to VREF+ − 0.2 V with the buffer on. All bipolar voltages need
  an external op amp. Spare halves of the dual TPH2502 / TP2272 cover this; about 3-4
  op-amp sections in total, roughly 1 USD.
- No external DAC is needed. Fallbacks, if pins run short:
  - HRTIM or TIM PWM with a two-pole RC (fine for bias rails; filter about 10 Hz).
  - A quad I2C DAC such as MCP4728 (not priced).
- The G474's internal comparators (16.7 ns, 7 of them) are too slow for the trigger path.
  They can serve as an overload / clamp-hit detector on the hold-amplifier output.

## Unverified points

- RM0440 not read (st.com unreachable):
  - dual interleaved mode behaviour per external trigger;
  - the rule against converting the same channel on two ADCs at once;
  - EXTI11 / EXTI2 as regular external triggers for ADC12 / ADC345;
  - the OPAMP VINP ↔ DAC3/DAC4 mapping (from HAL headers via web search).
- AN5346 (ADC tips) not read.
- Internal OPAMP noise density is only a figure in the datasheet; not extracted.
- Real BAT15-04W bridge net leakage at ±1 V bias (nA assumed, 5 µA datasheet maximum).
  Measure it.
- DigiKey and Mouser prices for ADS7883 and AD7276. AD7276 3 Msps rating from memory.
- LTC2366 price from a search snippet.
- STM32G474RET6 at LCSC, C521608: 12.63 at 1 pc, 22 in stock. For reference only; the user
  supplies the MCU.
