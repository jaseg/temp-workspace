# Sampling scope front end: summary

Target: 2 GHz analog bandwidth, eye diagrams on NRZ data up to 3 Gbps including
spread-spectrum links. Triggering from the data itself works from 200 mV peak-to-peak
at the probe point; smaller signals use the external clock input. One comparator serves
both, with switched inputs. Details, sources and simulations are in
[scope-frontend.md](scope-frontend.md). Nothing here has been built; figures are from
simulation, datasheets or arithmetic, and prices are single-unit, November 2026.

## Fixed parts of the design

| Block | Choice | Result |
|---|---|---|
| Input | BUF802 in composite loop with a precision op amp, 1 MΩ, 5:1 divider | Sets the bandwidth: about 2 GHz, 175 ps rise time |
| Sampler | Four-diode BAT15-04W bridge, fixed ±1 V bias, driven through 10 Ω, 2.2 pF hold, gain made up by an op amp | 73 ps, gain 0.46, 72 % per strobe |
| Strobe | Fast limited edge, amplified to 2–3 V, clipped to 100–160 ps by a shorted stub | Needs an edge under about 120 ps; unproven |

## Options

**Timebase**

| Option | For | Against |
|---|---|---|
| Si5344, two outputs at a beat frequency | 1 ps time axis, cleans jitter, locks 8 kHz–750 MHz | About 30; cannot follow spread spectrum or lock to data |
| Si5351C, same scheme | About 5 | Locks only to 10–100 MHz; follows jitter |
| FPGA (GW1NZ-1), free-running strobe plus time stamps | Any signal incl. data and spread spectrum; strobe placement in 30 ps steps | No beat mode; delays need self-calibration; PLL jitter and edge rate unpublished |

**Time stamping (needed with a free-running strobe)**

| Option | Precision per stamp | For | Against |
|---|---|---|---|
| FPGA input-delay converter, 16 pins | 31 ps (assumed tolerances) | Free; stamps every edge | Needs edges at least about 1.5 ns apart, so fast data needs a divider |
| Tapped delay line with 16 diode gates | 23–38 ps | Measured against the real strobe; no fast logic; speed limit is the gate (55–70 ps) | 27–41 plus five strobe amplifiers; large; strobe distribution unproven; catches few edges below a few hundred Mbps |
| TDC7200, several armed in turn | 35 ps (specified) | About 1.50 each; self-calibrating | 0.3 million stamps per second per chip; 8 chips for 1.25 Gbps with spread spectrum; 3 Gbps with spread spectrum not solved |

**Edge conditioning for data and triggers**

| Option | For | Against |
|---|---|---|
| TLV3801 comparator + AD9508 divider, TMUX136 input switch | About 22; LVDS couples to the divider down to DC; 5 ps dispersion at ±19 mV; divider also fans out and passes plain triggers at ÷1 | AD9508 limits at 303 ps pulses (3.3 Gbps, no margin); comparator and switch need a −2.5 V rail; FPGA bank at 1.8 V |
| ADCMP572 or TLV3901 instead | Faster than needed | 10–30; CML output must be AC-coupled, so no plain triggers |
| Limiter (amplifier chain) + AD9508, AC coupled | AD9508 sensitivity (360 mV differential) is no obstacle | No DC coupling, no trigger level; no cheaper than the TLV3801 |
| Slow comparators only (TLV3602) | Cheap | Clocks to about 300 MHz, data to a few hundred Mbps |
| Hardware clock-recovery ICs | – | Expensive, hard to buy, or cannot follow spread spectrum |

Clock recovery itself is a software fit over the time stamps: 9–12 ps rms at 1.25 Gbps,
with or without spread spectrum.

## Recommended builds

| | Best performance | Lowest cost |
|---|---|---|
| Input and sampler | as above, OPA140, OPA656 | as above, OPA197, OPA810 |
| Strobe driver | ADCMP572 edge into GVA-84+ finals | FPGA CMOS output into two amplifier stages (TRF37D73, then GVA-84+) |
| Timebase | FPGA, free-running strobe | FPGA, free-running strobe |
| Phase recovery | Tapped delay line with a limiter for data, plus TLV3801 + AD9508 into the FPGA converter for the external input and slow signals | FPGA input-delay converter behind TLV3801 + AD9508 |
| Why | Only option with headroom at 3 Gbps and timing referred to the actual sampling instant | Fewest parts; 3 Gbps is at the divider's limit |
| Main risk | Strobe distribution to 16 gates | Strobe edge from CMOS; AD9508 with irregular edges |

For clock-like signals where a 1 ps time axis matters more than data, the Si5344 beat
timebase is the better instrument and can be fitted alongside.

## Recommended parts

Prices are single-unit (DigiKey unless marked LCSC). "–" means the same part in both builds.

| Function | Best performance | Lowest cost | Note |
|---|---|---|---|
| Input buffer | BUF802, 6.77 | – | Sets the 2 GHz bandwidth |
| Low-frequency amplifier | OPA140, 4.29 | OPA197, 0.82 | Crossover must be re-trimmed for the OPA197 |
| Bridge diodes | 2 × BAT15-04W, 0.52 | – | Cheaper diodes have too much capacitance |
| Hold amplifier | OPA656, 14.45 | OPA810, 3.29 | OPA810 just settles in a 10 MHz strobe period |
| Strobe edge source | ADCMP572, 30.18 | FPGA output, none | TLV3901 is an alternative, about 10 but reel only |
| Strobe amplifiers | GVA-84+, 2.60–3.70 (LCSC) | TRF37D73 pre-driver, GVA-84+ final | TRF37D73 alone gives about ±2 V, short for the delay-line strobe |
| Main-sampler balun | TCM1-83X+, 8.70 | common-mode choke, DLW21S type, 0.29 | Choke raises overshoot from 12 % to 26 % in simulation |
| Timebase and time stamps | GW1NZ-LV1QN48 FPGA | – | Price not checked |
| Trigger comparator | TLV3801, 5.20 | – | Needs a −2.5 V rail |
| Trigger divider and fan-out | AD9508, 15.83 | – | 3.3 Gbps limit; 1.8 V outputs |
| Trigger input switch | TMUX136 | – | On a shifted supply; to be verified. Price not checked |
| Delay-line gate diodes | 16 × BAT15-04R pair, 0.38 | not fitted | 0.20 at 100 pieces |
| Delay-line limiter | 2 × GVA-84+ | not fitted | 3 × TRF37D73 as alternative |
| Delay-line comparators | 8 × COS3502 dual, 0.36 (LCSC) | not fitted | TLV3502 (2.91) is the pin-compatible original; MX7219T (0.40) as single-channel alternative. Input capacitance near 6 pF halves the signal |
| Split supply | LTC3261 + TPS7A39, 13.40 | TPS60403 with LC filters, 1.04 | |

Optional: Si5344 (about 30) for a 1 ps beat timebase on clock-like signals; TDC7200
(about 1.50 at LCSC) as a specified reference time stamper on a first board.

## Open before layout

1. Strobe driver: edge and amplitude from a saturating amplifier chain.
2. FPGA: output edge rate, PLL jitter, delay-step tolerance.
3. Delay line: strobe distribution, comparator input capacitance.
4. AD9508: behaviour with irregular edges. TMUX136 and TLV3801 on a shifted supply.
5. Spread spectrum at 3 Gbps with the TDC7200 bank.
