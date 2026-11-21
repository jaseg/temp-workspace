# Timing architecture without the AD9508

Study notes, November 2026. Goal: remove the AD9508 divider from the low-cost front end
by running the phase-recovery (delay-line snapshot) strobe at a multiple of the sampling
strobe, and handle slow triggers and external clocks with a coarse FPGA path.
Status markers: **[V]** checked against a datasheet or distributor page in this session,
**[S]** search-engine snapshot of a distributor page (the LCSC pages render prices in
JavaScript, so WebFetch returned no prices; the numbers come from indexed snapshots and
can be stale), **[U]** unverified (from memory or my estimate), **[R]** taken from
`docs/scope-frontend.md`, **[sim]** simulated here.

## 1. Result in one paragraph

Run the delay-line strobe ("phase strobe") continuously at **50 MHz**. Generate it and the
main sampling strobe from the same FPGA serializer clock, with the main strobe at
**f_p / 16 = 3.125 MHz** (the STM32G474 ADC rate, 4 Msps max), placed half a phase period
away from the nearest phase strobe. The phase strobe time is then known exactly on the
PLL grid, every snapshot that contains an edge is an absolute time stamp, and no divider
is needed: at 3 Gbps about 69 % of snapshots hold an edge (34 M stamps/s). For slower
signals, add a coarse path: the TLV3801 LVDS output into an FPGA LVDS input sampled by a
deserializer (1–2 ns bins). The coarse stamp only counts cycles and identifies edges; the
fine stamp from the delay line carries the time. For periodic signals below about 1 MHz,
the FPGA aims phase strobes at the predicted edge using the coarse/fine history. Lower the
readout resistors from 10 k / 2 × 4.7 k to **2.2 k / 2 × 1 k** so the tap readout recovers
between strobes. The TLV3502/COS3502 comparator (80 MHz toggle at 50 mV overdrive [V])
and the readout recovery set the 50 MHz limit; 100 MHz is not sensible with this
comparator class.

## 2. Hit statistics (a)

Window W = 16 taps × 35 ps = 560 ps. A snapshot holds an edge if one passes the window
during the aperture; both comparator edge polarities count (the snapshot shows the
polarity), so a clock of frequency f gives 2f edges per second. For free-running strobes
uncorrelated with the signal:

- clock: P(hit) = min(1, 2 f W)
- NRZ data at bit rate B with 50 % transition density: P(hit) = 1 − 0.5^(W·B) for W·B ≥ 1,
  else 0.5 W B.

Stamps per second = f_p × P(hit):

| Signal | 5 MHz | 25 MHz | 50 MHz | 100 MHz | 200 MHz |
|---|---|---|---|---|---|
| 1 kHz clock | 6 | 28 | 56 | 112 | 224 |
| 10 kHz clock | 56 | 280 | 560 | 1.1 k | 2.2 k |
| 100 kHz clock | 560 | 2.8 k | 5.6 k | 11 k | 22 k |
| 1 MHz clock | 5.6 k | 28 k | 56 k | 112 k | 224 k |
| 10 MHz clock | 56 k | 280 k | 560 k | 1.1 M | 2.2 M |
| 100 MHz clock | 560 k | 2.8 M | 5.6 M | 11 M | 22 M |
| ≥ 893 MHz clock | 5 M | 25 M | 50 M | 100 M | 200 M |
| 10 Mbps data | 14 k | 70 k | 140 k | 280 k | 560 k |
| 100 Mbps data | 140 k | 700 k | 1.4 M | 2.8 M | 5.6 M |
| 1 Gbps data | 1.4 M | 7 M | 14 M | 28 M | 56 M |
| 3 Gbps data | 3.4 M | 17 M | 34 M | 69 M | 138 M |

Lowest clock frequency meeting the criteria (unaimed, random hits):

| Criterion | 5 MHz | 25 MHz | 50 MHz | 100 MHz | 200 MHz |
|---|---|---|---|---|---|
| ≥ 10 k stamps/s (mean) | 1.79 MHz | 357 kHz | 179 kHz | 89 kHz | 45 kHz |
| gap > 100 µs with probability < 10⁻³ (≥ 69 k/s, Poisson) | 12.3 MHz | 2.5 MHz | 1.23 MHz | 616 kHz | 308 kHz |

Notes:

- **Commensurate signals are the real risk, not the mean.** Strobes on a fixed grid and a
  periodic signal give a fixed set of relative phases. If the signal period is a simple
  ratio of the strobe period (10 MHz signal, 50 MHz strobe), the hits are all or nothing.
  The strobe phase must be dithered so that the set of strobe phases modulo the signal
  period has spacing below W/2 ≈ 280 ps. Options: pseudo-random coarse offset per strobe
  in serializer bits (1 ns) plus a slowly swept fine offset (Gowin IODELAY, 30 ps steps,
  or a PLL dynamic phase step). The offset is chosen by the FPGA, so it is known; the fine
  sweep is calibrated by code density like the taps. 1 ns steps alone are not enough:
  a 100 MHz clock would only see 10 phases, which leaves gaps.
- **Aiming.** Once a periodic signal's phase and frequency are known, the FPGA places
  strobes inside a predicted edge window. Then stamps ≈ min(2f, f_p) × aiming success, so
  ≥ 10 k/s from about 5 kHz upward for crystal-derived sources. Aiming fails for sources
  with large period jitter (RC oscillators: 10⁻⁴ of 1 ms = 100 ns); those fall back to the
  random rates above.
- **Spread spectrum at 3 Gbps (5000 ppm, 33 kHz).** At 50 MHz the mean gap between stamps
  is 29 ns. A 5000 ppm frequency error drifts 145 ps in that time against a half-UI of
  167 ps, so the tracking loop must follow frequency (type-2 loop). With frequency
  tracking, the residual from the SSC slope over 29 ns is negligible. At 5 MHz (290 ns
  gaps) the residual frequency error would have to stay below about 575 ppm, which is
  where the 10 MHz-strobe design was fragile. Higher f_p helps directly here.
- **Spread-spectrum clocks** (100 MHz PCIe refclk): P(hit) 0.11, 5.6 M stamps/s at 50 MHz,
  about 170 stamps per SSC period. Enough without a model. Below about 1 MHz signals with
  SSC are unusual; a parametric SSC model (triangle depth, period, phase) would cover them
  with sparse stamps.
- **Throughput.** 16 bits × 50 MHz = 800 Mbit/s of snapshots. The FPGA reduces each
  snapshot to (strobe index, tap transition position, polarity) and runs the tracking loop
  in fabric. Only the phase estimate at each main strobe goes to the MCU (3.125 M per
  second, about 16 bits each). The MCU cannot take raw stamps at 34 M/s.

## 3. What limits the phase strobe rate (b)

| Limit | Numbers | Allowed rate |
|---|---|---|
| Tap comparator | TLV3502: 4.5 ns delay, 80 MHz toggle at 50 mV overdrive, 1.5 ns rise and fall [V, TI SBOS321 datasheet]. COS3502 is the clone, 4.5 ns typ / 7 ns max at 20 mV [R]; toggle rate not stated. At ±12–20 mV overdrive the delay is 5–7.5 ns [R] | The output may change on every strobe, so f_p ≤ 2 × f_toggle in principle (160 MHz). In practice the held value must last longer than the delay: one period ≥ about 15–20 ns, so **≤ 50–65 MHz** |
| Readout recovery | 10 k bias, 2 × 4.7 k, Cin 3 pF: peak 15 % at 5.6 ns, still 14 % at 10 ns and 10 % at 20 ns [sim] | 10 ns period leaves 90 % of the previous snapshot: **≤ 10–15 MHz** as drawn |
| Strobe amplifiers, AC coupling | Pulse 100–160 ps, so duty 0.5–0.8 % at 50 MHz; baseline shift 0.8 % of amplitude. Chokes sized for 10 MHz (10 µH, 100 nF [R]) are more than adequate at 50 MHz | Not limiting. Keep f_p constant so the self-bias of the gates is constant |
| FPGA capture | 16 inputs, SDR, one sample per strobe at a fixed delay after it (about 8–12 ns: driver plus gate plus comparator) | Not limiting at 50 MHz on any candidate |
| Main sampler hold amp / ADC | OPA810 settles within 100 ns [R]; G474 ADC 4 Msps [U, from memory] | main strobe ≤ 4 MHz, independent of f_p |

Readout network trade-off, one gate, ideal strobe, swing at the comparator input in % of
the line voltage (array taps get about half) [sim, `sim/readout_load.py` cases via
scratch script, same models]:

| Bias / summing / Cin | Peak | 5 ns | 10 ns | 20 ns | 40 ns |
|---|---|---|---|---|---|
| 10 k / 2 × 4.7 k / 3 pF (as drawn) | 15.4 % at 5.6 ns | 15.3 | 14.0 | 9.9 | 4.8 |
| 4.7 k / 2 × 2.2 k / 3 pF | 14.9 % at 2.7 ns | 13.4 | 9.2 | 4.3 | 1.0 |
| **2.2 k / 2 × 1 k / 3 pF** | 14.2 % at 1.3 ns | 8.3 | 3.6 | 0.7 | 0.1 |
| 1 k / 2 × 470 / 3 pF | 12.5 % at 0.6 ns | 2.8 | 0.5 | 0.0 | 0.0 |
| 2.2 k / 2 × 1 k / 1.5 pF | 22.1 % at 1.0 ns | 8.3 | 2.2 | 0.2 | 0.0 |
| 4.7 k / 2 × 1 k / 1.5 pF | 26.2 % at 1.2 ns | 16.6 | 8.5 | 2.3 | 0.2 |

Proposed changes:

- **2.2 k bias, 2 × 1 k summing.** The peak hardly drops (14 % vs 15 %), the signal is
  still at 60 % of the peak after 5 ns (comparator decision), and only 5 % of the peak is
  left at 20 ns, i.e. one 50 MHz period. The remainder is a known linear memory of the
  previous snapshot; like the hysteresis it can be corrected with the previous bit
  known [R, offset calibration section].
- Rails: the divider ratio is unchanged (about ±1.56 V for ±0.5 V on the nodes), but the
  current rises about 4.5×: roughly 1.4 mA per tap per rail, about 23 mA per rail for 16
  taps [U, arithmetic]. Bias-current threshold shift drops from 7.35 to 1.6 mV/µA.
- Hold capacitors stay at 2 × 0.47 pF.
- Comparator input capacitance dominates. If the COS3502's Cin is nearer 1.5 pF than 3 pF,
  4.7 k / 2 × 1 k is better (26 % peak, 8.5 % at 10 ns). Measure Cin on the first board
  and fit the resistors then; lay out for 0402 so either set fits.
- 100 Ω series resistors in the 16 comparator outputs to slow the edges seen by the
  analog section; 16 outputs switching at up to 50 MHz next to a 35 ps line is the main
  layout risk.
- Fire the main strobe half a phase period (10 ns) away from the nearest phase strobe, so
  the comparator outputs and the delay-line gate transients do not coincide with the main
  sampler's aperture. The offset is an integer number of serializer bits, so it is known.
- 100 and 200 MHz are not sensible: 1 k / 470 leaves 2.8 % (about ±6 mV in the array) at
  the comparator decision time, below the comparator offsets. It would need a latched
  comparator (ADCMP-class, ten times the cost) or 2.5 ns parts (TLV3601, 4.25–4.65 per
  channel [R]), which breaks the budget for 16 channels.

## 4. Slow triggers and external clocks below the fine-hit range (c)

Coarse path: TLV3801 LVDS output, split (the delay-line driver TRF37D73 is AC coupled and
already loads it) into one FPGA LVDS input, deserialized at the serializer rate.

- **Coarse stamp**: 1 ns bins with a Gowin IDES at 1 Gbps [R], 1.25–2.5 ns with a
  MachXO2/iCE40 DDR or ×4 gearing [U]. Precision about 0.3 × bin rms.
- **Combining coarse and fine is trivial.** The fine stamp is absolute: it is the known
  phase strobe time minus the tap position. The coarse stamp only has to identify which
  edge (cycle count, polarity) the fine stamp belongs to, so its error has to be below
  half the signal period, not below the 560 ps window. Consistency check:
  |t_fine − t_coarse − latency| < bin. The coarse latency is calibrated against fine
  stamps on any signal that produces both.
- **Range**: pulses must be wider than about two bins to be captured, so the coarse path
  works for edges up to about 200–300 MHz. Above that it is not needed (fine hits are
  dense, section 2) and is ignored.
- **Down to 1 kHz**: periodic → coarse stamps give period and phase within a few ns; the
  FPGA aims phase strobes into the predicted window (needs sub-560 ps placement: serializer
  bit plus IODELAY on Gowin, or PLL dynamic phase on Lattice). After a few hits the fine
  history predicts better than the coarse one. Rate is then limited by the signal itself:
  at most 2 stamps per period, 2 k/s at 1 kHz.
- **Non-periodic triggers** (one edge, no prediction): the FPGA cannot react within the
  560 ps window, so only random hits are possible: P = W × f_p = 2.8 % of events at 50 MHz.
  For that mode, a TDC7200 (3.69 single, 2.29 at 100, DigiKey [R]) started by the coarse
  path and stopped by a phase strobe gives 35 ps on every event; optional footprint.
- **No second comparator needed** if the FPGA has an LVDS input. With the GW1NZ-1 (CMOS
  inputs only [R]) an LVDS receiver is needed instead (SN65LVDS2-class, roughly 1 [U, not
  priced]); a second cheap CMOS comparator would add its own trigger level and offset and
  is worse.

## 5. External clock mode (d)

The TMUX136 feeds the external clock to the same TLV3801, so the fine and coarse paths are
unchanged. Nothing else is required. Notes:

- The AD9508's job (divide fast clocks so the FPGA can count them) disappears: above
  about 300 MHz the fine path alone stamps every strobe (P = 1 from 893 MHz), and cycle
  counting comes from the tracking loop, whose frequency estimate is good enough with
  stamps 20 ns apart.
- The trigger-level DAC and hysteresis stay as before; for an external clock set the
  level to its midpoint.
- Optional: lock the FPGA PLL to the external clock (Gowin rPLL input 3–400 MHz [R]).
  Not recommended; it adds PLL jitter and the free-running scheme already handles it.

## 6. FPGA choice (e)

Needs: 16 SDR inputs at 50 MHz, 1 LVDS input with a deserializer for the coarse path,
2 strobe outputs with serializer and fine delay, MCU interface, about 1–2 k LUTs for edge
extraction, the tracking loop (shifts, no multipliers needed) and FIFOs.

| Part | Price, source | LVDS in | PLL | Input/output delay | Serializer | Package | Logic |
|---|---|---|---|---|---|---|---|
| GW1NZ-LV1QN48C6/I5 | 5.56 (1), 3.90 (100), LCSC C5799569, 489 in stock [S] | no, CMOS only [R] | 1 rPLL, integer [R] | IODELAY 30 ps × 128 [R] | IDES10/OSER10 1.1 Gbps [R] | QFN-48 0.4 mm | 1152 LUT, tight [R] |
| GW1N-LV1 / GW1N-LV4 (non-Z) | not found at LCSC in this session | true LVDS listed in DS100 tables [U, datasheet blocked] | 1–2 [U] | IODELAY [U] | yes [U] | QFN-48/LQFP | 1152 / 4608 |
| GW1NSR-LV4CQN48P | 14.47 (1), LCSC C2908250 [S] | yes [U] | 2 [U] | yes | yes | QFN-48 | 4608 + Cortex-M3; too expensive |
| ICE40UP5K-SG48I | 6.58–8.07 (1), LCSC C2678152, 430–530 in stock [S]; €9.56 DigiKey IE [S] | differential inputs, bank restriction [U] | 1, integer [U] | none (PLL output phase only) [U] | DDR only, about 2.5–4 ns bins [U] | QFN-48 0.5 mm | 5280 LUT, 8 DSP |
| LCMXO2-1200HC-4TG100C | 2.55–3.47 LCSC C453479, 42 in stock [S]; 11.95 DigiKey [S] | true LVDS inputs [U] | 1, fractional-N, dynamic phase [U] | DELAYE/DELAYD coarse [U] | IDDRX2/X4 gearing [U] | **TQFP-100 0.5 mm**, single 3.3 V supply (HC) [U] | 1280 LUT |
| Efinix T8F81C2 | 4.90 (JLC, out of stock) / about 6 DigiKey [S] | [U] | [U] | [U] | [U] | BGA-81, not hand-solderable | 7384 LE |
| Anlogic EF2/EG4, AGM AG1K | not checked | – | – | – | – | – | documentation and toolchain risk |

Assessment:

- **GW1NZ-1** stays workable: its IODELAY and 1 Gbps serializers are the best fit for strobe
  placement and the coarse TDC, it is in stock and verified at 5.56. Against: no LVDS input
  (one LVDS receiver needed), 1152 LUTs is tight for the tracking loop, needs 1.2 V core.
- **MachXO2-1200HC in TQFP-100** is the attractive alternative if the LCSC price holds:
  hand-solderable, LVDS inputs, single 3.3 V supply, fractional PLL. Its fine output delay
  is weaker, so strobe aiming would use PLL dynamic phase. LCSC stock is low and DigiKey is
  four times the price. Not verified against the datasheet in this session.
- **iCE40UP5K** has more logic but no input delays and slower I/O; it only wins if logic is
  the bottleneck.
- **STM32G474 HRTIM** (184 ps output resolution [U]): it cannot replace the strobe
  generation, because the main strobe needs a fixed, known relation to the phase strobe,
  and the MCU's PLL and GPIO edges (ns, MCU PLL jitter) are a second, unrelated time base.
  It is useful to start the ADC conversion a fixed time after each main strobe (feed the
  MCU's HSE from the same oscillator, or from an FPGA output, so this stays synchronous) and
  as a slow event counter. Its capture units are not high-resolution [U].

## 7. Time base (strobe generation)

- One crystal oscillator (25 MHz class, about 0.3–1 [U, not priced]) into the FPGA PLL.
  PLL → serializer bit clock 1 GHz (Gowin, 1 ns bits) and fabric clock 100 MHz (OSER10).
- Phase strobe: one serializer output pin, one pulse every 20 ns (50 MHz), with the
  pseudo-random 0–9 bit offset plus slow fine sweep from section 2.
- Main strobe: a second serializer pin, one pulse every 16th phase strobe (3.125 MHz),
  10 bits after the selected phase strobe. Both pins share the serializer clock, so their
  relative timing is an integer number of bits plus a constant set by the board (driver
  and line delays), calibrated once by measuring the same edge with both samplers.
- MCU clocked from the same oscillator (HSE bypass) or from an FPGA clock output, so the
  ADC trigger is synchronous to the main strobe.
- MS5351M / Si5351: not needed. Keep a footprint only if a beat-frequency mode for the
  instrument's own stimulus is wanted later.

## 8. Recommended architecture

| Function | Choice | Rate / value |
|---|---|---|
| Edge conditioning | TMUX136 → TLV3801 (unchanged); AD9508 removed | – |
| Fine phase | TRF37D73 → 16-tap delay line, BAT15-04R gates, 2 × 0.47 pF, readout 2.2 k / 2 × 1 k, 8 × COS3502 (TLV3502 footprint) | phase strobe 50 MHz, dithered |
| Coarse phase | TLV3801 LVDS → FPGA LVDS input (or SN65LVDS2-class receiver for GW1NZ) → deserializer | 1–2.5 ns bins, edges up to about 200 MHz |
| Main sampler | unchanged | main strobe = phase strobe / 16 = 3.125 MHz, 10 ns offset |
| ADC | STM32G474 internal 12-bit ADC | 3.125 Msps |
| FPGA | GW1NZ-LV1QN48 (verified price and stock) or LCMXO2-1200HC-4TG100C if LCSC price confirmed | tracking loop in fabric |
| Time base | one XO → FPGA PLL; MCU from the same XO | 1 GHz serializer |
| Non-periodic triggers | optional TDC7200 footprint | 35 ps per event |

Coverage: 3 Gbps data with SSC at 34 M stamps/s; clocks from about 1.2 MHz with no aiming
(robust criterion), from about 5 kHz with aiming; 1 kHz periodic triggers at 2 k stamps/s;
non-periodic triggers at 2.8 % yield, or every event with the TDC7200.

## Unverified points

- COS3502 toggle rate and input capacitance (the readout values depend on Cin).
- Gowin GW1N (non-Z) LVDS input, its LCSC stock and price (Mouser datasheet download was
  blocked: the server returned a script page instead of the PDF).
- MachXO2-1200HC: LVDS input, fractional PLL, gearing rates and the low LCSC price.
- iCE40UP5K: LVDS input bank restriction.
- G474 ADC rate and HRTIM capture resolution (from memory).
- Increased readout rail current (arithmetic only); comparator behaviour with a decaying
  input of ±12–20 mV at 50 MHz (not simulated with a comparator model).
- Strobe dithering and aiming are design arithmetic, not simulated.
