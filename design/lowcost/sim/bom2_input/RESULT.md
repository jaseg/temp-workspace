# BOM-2 input stage: no trimmer, Cint 1 nF, C101 50 V (simulation, behavioural models)

Scripts (sim/input is copied, not edited): `input_stage_bom2.py` (copy of `sim/input/input_stage.py`, library part;
adds a two-capacitor Ctop option and alpha-string tolerance hooks), `bom2_input.py` (all input runs, `results.json`,
`bom2_ac.png`, `bom2_steps.png`, about 3 min), `hold_cap.py` (imports `sim/strobe_arms/arms.py` unchanged and only
overrides its C_HOLD; `hold_cap.json`), `chain_bom2.py` (copy of `sim/sampler/chain.py` with the ADC pin capacitor as a
parameter; `chain_220p.json`, `chain_100p.json`, `chain_47p.json`). Same behavioural BUF802 / op-amp / BAT15 models as
the originals.

## Proposed values
| Ref | As built | Proposed | Why |
|---|---|---|---|
| RV101 | 50k trimmer (3314J, extended) | **removed** (pads deleted) | LF/HF match by firmware calibration |
| R120 Rf2 | 22k + RV101 | 22k (basic C25768) | LF gain 0.19970 = HF gain 0.19971 (nominal eps -0.001 %) |
| R118 Rf1 | 10k | **4.7k** (basic C25900) | Rf1 x Cint kept (4.7 us): loop and tap-RC cancellation unchanged |
| R119 Rofs | 24.9k (extended C25874) | **10k** (basic C25744) | VOFS span: OUT = 0.606 - 0.470 Vdac |
| R123 Rmid | 33k | **15k** (basic C25756) | mid-scale from VNEG_REF -1.933 V |
| C106 Cint | 470p C0G (extended C75274) | **1n C0G** (C53547, the C303 line) | 1/Rpar x Cint = 2.35 us = tap RC (Cp 18p unchanged) |
| C101 Ctop | 1.5p +/-0.1 pF 100 V (C2179899, 48 in stock) | **1.5p +/-0.05 pF 50 V** Murata GJM1555C1H1R5WB01D (C76901, extended, 17.5k in stock) | same footprint; 50 V is enough (below) |
| C207 ADC pin | 220p C0G (extended C39122) | **100p C0G** (basic C1546) | settling unchanged |
| C205 hold | 2.2p | **2.2p, unchanged** | 3.3p costs 26-32 ps of aperture |

## Results
| Item | As built (RV101 trimmed) | Proposed (no trimmer) |
|---|---|---|
| LF / HF gain (10 MHz) | 0.19971 / 0.19971 | 0.19970 / 0.19971 |
| -3 dB at splitter, ext. 50 R / none | 3.29 / 1.71 GHz | 3.29 / 1.71 GHz (identical HF network) |
| 20 ps step, ext. 50 R: rise / overshoot | 130 ps / 12.3 % | 130 ps / 12.7 % |
| VOFS 0.2 / 1.289 / 2.7 V -> OUT | +0.51 / 0 / -0.50 V (computed) | **+0.512 / -0.000 / -0.663 V** (+/-2.5 V at the input covered) |
| +20 V 10 us overload, recovery to 10 mV | 48.3 us | 48.3 us |
| Flatness 1 Hz-100 MHz | 0.67 % (trimmed) | raw: eps of the board; **after firmware correction 0.34-0.78 %** |

**LF/HF mismatch without any trim** (60 boards each, uniform within tolerance: Ctop, Cbot +/-0.1 pF (Ctop
+/-0.05 pF proposed), BUF802 Cin 2.4 +/-0.3 pF (typical only, assumed), pads +/-40 %, G +/-1 %, Ga +/-20 %, all
resistors +/-1 %, Cint / Cp +/-5 %): as-built network with RV101 replaced by its nominal **eps -6.5 ... +9.1 %**
(sd 3.8 %); proposed **-7.1 ... +6.0 %** (sd 3.4 %). Cin dominates; tighter parts cannot remove it (option 3 rejected:
a Cin-insensitive divider needs about 2x Ctop and halves the unterminated bandwidth).
**Where it shows**: the error is a pole-zero doublet at the servo crossover (median tau 18.6 us, 8.6 kHz). A step
jumps to the HF gain and moves to the LF gain over about 2-150 us, with an undershoot of about 0.17 x |eps| near
70 us (`bom2_steps.png`), so the LF part needs two terms, not one exponential. In equivalent-time records far shorter than tau
(periodic signals above about 100 kHz) the doublet is invisible as a tilt: the AC part of the waveform is scaled by
1/(1+eps) about its true mean.

## Firmware correction (simulated)
Calibration: any square wave of 0.2-2 kHz with flat tops at SIG_IN (no amplitude reference: eps is a ratio), 64
edges averaged from the 3.0 MS/s real-time ADC stream (2 mV rms per sample at the input assumed), fit
y = a [1 + e1 (1 - exp(-t/t1)) + e2 (1 - exp(-t/t2))]; correction C(s) = (1 + e1 + e2) / (1 + e1/(1 + s t1) + e2/(1 + s t2)),
unity at DC, so the result carries the LF (resistor-ratio) gain.
| Board eps | raw flatness | corrected | raw step deviation (1-500 us) | corrected |
|---|---|---|---|---|
| -7.1 % | 7.7 % | **0.34 %** | 7.1 % | **0.19 %** |
| -6.8 % | 7.5 % | 0.49 % | 6.9 % | 0.27 % |
| -2.9 % | 3.5 % | 0.73 % | 3.0 % | 0.35 % |
| +0.1 % | 0.62 % | 0.78 % | 0.44 % | 0.36 % |
The two-term fit is ill-conditioned (e1 and e2 come out large with opposite signs) but the corrected response is
right; firmware may fit the fixed loop shape (measured once per design) with one free eps instead.
Application: records longer than about 5 us or the real-time stream -> C as an IIR at 3 MS/s; short records of
periodic signals -> x = (1+eps) y - eps m with m the mean over all phases (record covering a period, or a per-phase
accumulator over all strobe samples).

## Rejected electronic trims
- Shunt R switched by an open-drain PWM pin: FB and TAP sit at the input/10 (+/-0.5 V in range, about -0.75 V in
  overload with the OPA197 saturated). Below -0.3 V the pin's clamp conducts: the shunt turns on for negative inputs
  (gain depends on polarity). An NMOS has the same body diode, and gate charge (about 15 pC per edge) into the summing
  node gives about 30 mV steps at the servo output.
- DAC-driven JFET or diode as a variable R: no JFET on the BOM; a diode is nonlinear over +/-0.5 V.
- STM32 OPAMP/PGA in the servo path: single 0-3.3 V supply against a bipolar node, plus offset and drift x10 at the input.

## Hold capacitor C205 (as-built arms deck, `hold_cap.json`)
| C205 | bias | aperture clean / system | eff (system) |
|---|---|---|---|
| 2.2 pF (as built) | +/-1.30 V | 100 / 148 ps | 100 % |
| 3.3 pF | +/-1.30 V | 100 / 144 ps | 84 % (too low) |
| 3.3 pF | +/-1.00 V (re-trimmed to 100 %) | **126 / 180 ps** | 100 % |
| 1.65 pF (2 x 3.3 pF series) | +/-1.40 V | 91 / 136 ps | 104 % (needs VBIAS above the 1.30 V firmware limit) |
Kept at 2.2 pF.

## ADC pin capacitor C207 (`chain_bom2.py`, worst 0.5 V hold jump, trigger 36 ns)
220p: -11.04 LSB at the end of the window (pin -10.83); 100p: -10.87 (-10.66); 47p: -10.80 (-10.59). The error is the
modelled hold droop. Pin-to-sample-cap settling is 0.21 LSB in all three cases. **100p (basic) is equivalent.**

## Open points
BUF802 Cin spread is assumed (+/-0.3 pF), not specified. The correction was checked on 4 simulated boards. Calibration
needs one square-wave connection in production (as RV101 did). Firmware for the fit and the correction does not exist yet.
