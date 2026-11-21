# Main sampler: result (simulation only, nothing built)

Scripts: `bridge.py` (strobe-level deck, 1 ps steps, 60 ns tail, steady state from two runs per
efficiency + one per point), `multistrobe.py` (10 real strobes, checks the steady-state method:
gain 0.709 / eff 71 % vs. 0.716 / 70 %), `chain.py` (hold amp -> level shift -> ADC switch),
`amp.py` (TPH2501 model), `plots.py`. Plots: `bridge_step.png`, `chain.png`. Data: `bridge.json`, `chain.json`.
Diodes: BAT15 Infineon model + SOT323 package from `sim/frontend.py`. **TPH2501 is behavioural**
(no vendor model fetched): GBW 120 MHz, 180 V/us, 2nd pole 300 MHz, 10 ohm out, Cin 1 pF CM each
input + 2.7 pF differential. Strobe = step with 120 ps erf edge minus a copy 130 ps later (what a
shorted stub makes; peak 84 % of the step), "3 V" = step into a matched 50 ohm, then 1:1 balun.

## Final circuit
```
BUF802 out pin --+-- R 10 R (0402, <=3 mm) -- bridge input HS          (sampler leg, BUF_OUT_S)
                 +-- R 49.9 R -- 50 ohm line -- TMUX136 -> TLV3801     (trigger leg, BUF_OUT_T, hi-Z end)
Bridge: 2x BAT15-04W, 25 R per rail at the diodes, rails fed from the balun through 47 pF C0G each,
        bias VBIAS_K / VBIAS_A through 1 k each; 1 k across the balun outputs.
Hold:   2.2 pF C0G + TPH2501 (+in), U1 non-inverting G = +3.0: Rf 1.00 k, Rg 499 R, +/-2.5 V.
Shift:  U2 TPH2501 on 0/3.3 V, 1 k in / 1 k fb, +in 0.725 V (10 nF); Vadc = 1.45 V - U1out.
Pin:    33 R + 220 pF C0G -> PA0 (ADC12_IN1), 6.5-cycle sampling (108 ns) at 60 MHz.
Bias:   STM32G474 DAC1 -> 3.16 k / 6.98 k divider -> TP2272 follower -> VBIAS_K (+1.00 V at code 2048,
        0..+2.0 V, 0.49 mV/code); DAC2 -> TP2272 inverting 10 k / 6.98 k -> VBIAS_A (-1.00 V, 0..-2.0 V).
        100 nF at each buffer output, then the 1 k feeds. No bootstrap.
```
**Gain changed from +5 to +3**: the bridge gain with the hold-amp Cin is 0.69, so +/-0.5 V in gives
+/-0.35 V at the hold node; x5 would drive the level shifter below 0 V. x3 gives 0.41-2.49 V at the pin.

## Key numbers (3 V strobe, final circuit unless stated)
| Item | Value |
|---|---|
| 10-90 % (ideal 1 ps input step) | 65 ps, but 40 % overshoot and ringing to ~600 ps from the 0.5 nH / 10 R / bridge-C input network |
| 10-90 % behind a 2 GHz first-order input (BUF802 stand-in) | 109 ps, 4 % overshoot (input network peaking; system limited by the BUF802) |
| Gain hold/input (steady state), efficiency per strobe | 0.69, 69 % (1 nF/2 k feed: 0.72, 70 %) |
| Without the 1 pF + 2.7 pF amp Cin (earlier deck) | 0.72, 79 % - Cin costs ~10 points of efficiency |
| 2 V strobe, same +/-1 V bias | 0.39, 44 %, distorted response: **bridge barely turns on**; with bias +/-0.6 V: 0.69, 67 %, 66 ps (input range then <= +/-0.4 V) |
| 3x16.7 R splitter after 50 R (3 V / 2 V strobe) | gain 0.30 / 0.18 (incl. the 1/2 divider), eff 59 / 44 %, 74 ps |
| Pedestal (hold node at 0 V input) | +49 mV; 0.29 V per V of rail common mode -> null with -0.17 V rail CM via the DACs |
| Rectified charge per strobe | 1.75 pC (anode rail) / 1.38 pC (cathode): 47 pF rails recover in 47 ns |
| Kick-out, quiet input: bridge input / BUF802 pin / trigger end | 174 / 113 / 19 mVpp (star splitter: 62 / 26 / 17 mVpp) |
| Rail C mismatch 0.30/0.45 pF | kick at trigger end 30 mVpp, pedestal +10 mV more |
| Chain settling (worst 0.5 V hold jump, ADC cap from opposite end) | < 0.02 LSB from 0 ns trigger delay on (U1+U2 settle in ~20 ns, 108 ns window) |
| Droop with the model leakage (7.5 Mohm equiv. to rail CM, + 3 pA) | 1.25 % of the hold voltage per 320 ns; 0.67 LSB per 16 ns at 0.25 V |

Sensitivities (gain / eff): bias 2.4 V 0.65/62 %; 1.6 V 0.76/81 %; edge 150 ps 0.71/69 %; width 160 ps
0.77/90 %; strobe 2 V needs the bias lowered to match (above). Everything in `bridge_step.png` right.

## (b) Memory and bootstrapping
Dominant memory is the 69 % efficiency: v_k = 0.31 v_(k-1) + 0.69 (0.69 x_k + ped). Bias-network memory
is removed by 47 pF / 1 k (tau 47 ns << 320 ns); with 1 nF / 2 k it is tau 2 us and ~2 mV of rail shift,
~0.2 mV at the hold node. Leakage droop (above) is linear and deterministic at a fixed trigger delay.
A rail bootstrap with coefficient 1 (0.29 V/V measured) raises gain to ~1.0 but lowers the effective
efficiency to 0.69 x 0.71 = 0.49: the weight of the new sample (eff x gain = 0.48) is unchanged, so it buys
nothing in noise; a slow (multi-strobe) loop only tracks the average, which the DAC trim already does.
**Recommendation: no bootstrap; deconvolve in software x_k = (v_k - 0.31 v_(k-1)) / 0.48,** with the
coefficients calibrated per board (DC reference steps) and re-checked against strobe amplitude/temperature.

## (d) ADC trigger
Trigger 40 ns after the strobe (window 40-148 ns, conversion to 356 ns, next window from 360 ns at
3.125 MHz). Any delay 0-212 ns settles; earlier = less droop. Use synchronous ADC clock (fixed latency).

## (e) Noise, referred to the bridge input (BUF802 output), per deconvolved point
kT/C + diode shot (3.4 pF): 35 uV rms at hold, innovation 33 uV -> 66 uV at input. U1 33 uV, U2 22 uV,
Rf/Rg 12 uV, ADC 0.48 mV/3 = 160 uV (all at hold) -> 165 uV, x2.08 deconvolution -> 344 uV.
**Total ~0.35 mV rms at the bridge input (~1.75 mV at the probe tip, 5:1)**; 0.23 mV without deconvolution.
ADC dominates; two conversions per strobe would need <= 2 MHz strobe. 1/f of the TPH2501 not included.

## (f) Splitter
Unequal split chosen: sampler leg 10 R from the BUF802 pin (+/-0.5 V full scale at the bridge),
trigger leg 49.9 R source-terminated into an unterminated 50 ohm line: full +/-0.5 V at the TMUX136
after the first round trip (half for ~2x line delay). The 3x16.7 R splitter halves both legs and gives
the bridge a 50 R source: 2.4x less sampler gain. BUF802 only sees transient load.

## Open points
- Strobe kick reaches the trigger comparator: ~19 mVpp, ~100 ps, at the strobe instant; comparable to
  small trigger signals (40 mVpp at 200 mVpp probe). Consider 100 R + ferrite in the trigger leg; unproven.
- 113 mVpp kick at the BUF802 pin depends on its real GHz output impedance (modelled 1.2 R + 0.5 nH).
- Real BAT15 reverse-leakage mismatch and its temperature drift (model uses 15 Mohm per diode).
- 2 V strobe works only with +/-0.6 V bias; the strobe driver result decides bias and input range.
- Ringing of the input network for fast edges; layout must keep the 10 R and trace short.
- TPH2501 vendor model, 1/f noise, overload recovery; balun need still not established.
