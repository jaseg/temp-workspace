# Input stage: result (sim)

Script: `input_stage.py` (ngspice AC and transient, about 5 s). Plots: `input_ac.png`, `input_steps.png`. Numbers: `results.json`.
**Behavioural models only.** TI's BUF802 datasheet (SBOS998E) was read for the CL-mode structure. No vendor SPICE models were used.
- BUF802 model: G=0.983 unloaded (0.971 into 100 Ω), two poles giving 3.1 GHz, Cin 2.4 pF behind 0.5 nH, Zout 1.2 Ω + 0.3 nH.
- BUF802 aux path: Ga = 0.26 with an 800 MHz pole. In_Bias connects to the internal source through 100 k (RHF). Output is clamped to CLH/CLL. Input diodes go to CLH and VS-.
- Op amps: gm-C single pole with GBW 10 MHz (OPA197) or 7 MHz (TP2272), 20 V/us, Ccm 6.4 pF and Cdiff 1.6 pF (OPA197 datasheet; the same values are assumed for the TP2272).
- K1 (HFD3) contact inductance is assumed (4 nH per pole) because no RF data was found.

## Final network
```
SIG_IN SMA -- 6 mm 50R -- VIN
VIN -- R50 49.9R 0603 (or 2x100R, one per K1 pole) -- K1 HFD3, BOTH poles in parallel -- GND   (TERM_50 drives coil)
HF path : VIN -- Ctop 1.5 pF C0G 0402 +-0.05 pF 100 V -- GA ; GA -- Cbot 3.3 pF C0G 0402 +-0.1 pF -- GND
          GA -- Rg 10R 0402 -- BUF802 IN ;  IN -- 2 x 4.99M 0402 (series) -- In_Bias
          k = 1.53/(1.53+3.3+2.4+~0.3 pads) = 0.206 ; HF gain = k*G = 0.200
Servo   : VIN -- 3 x 300k 0.1 % 0402 -- TAP -- 100k 0.1 % -- GND   (alpha = 0.100, Rin = 1.000 Mohm)
          TAP -- Cp 18 pF C0G -- GND (tap RC = 90k x 26 pF = Rpar x Cint, cancels the integrator feed-through)
          OPA197 (U, +/-5 V): IN+ = TAP ; IN- = FB ; Cint 470 pF C0G OUT->FB
          FB: Rf1 10.0k from BUF802 OUT pin ; Rf2 16.2k + 10k trimmer (nominal 20.26k) to GND
              Rofs 33.2k from VOFS (DAC 0-3.3 V) ; Rmid 49.9k from -2V5
          OPA OUT -- Raux 1k -- In_Aux ; Caux 100 pF In_Aux-GND ; Aux_Bias to VS- (CL mode)
BUF802 : VS +/-5 V, R_Bias 17.8k, CLH = +1.5 V, CLL = -1.5 V (dividers from +/-2V5, 1 uF each)
OUT -- 49.9R -- BUF_OUT -> splitter (50R input)
```
LF gain = alpha x Rf1 x (1/Rf1 + 1/Rf2 + 1/Rofs + 1/Rmid) = 0.1 x 2.0 = 0.200, the same as the HF path.
Offset (sim): VOFS 0 / 1.65 / 3.3 V gives +0.50 / 0.00 / -0.50 V at OUT, which is +2.5 / 0 / -2.5 V referred to the input.
The servo is a **differential integrator**. Its loop bandwidth is Ga/(2 pi Rf1 Cint) = 8.8 kHz.
- The bandwidth does not depend on the op-amp GBW. In simulation the OPA197 and the TP2272 give identical curves.
- A plain non-inverting servo following TI Fig 8-1 passed the alpha tap through the op amp's unity-gain zero. That gave a +5 % bump at 100 kHz in my first run. Cp (the tap RC) cancels it.

## Key numbers (sim)
| Item | Value |
|---|---|
| Crossover flatness (trimmed, OPA197 or TP2272), 1 Hz-100 MHz | -0.25 % ... +0.67 % (largest near 30 kHz); 1 V step: 0.5 % peak deviation, settled in 50 us |
| HF/LF mismatch untrimmed, Cin +/-0.3 pF | +/-4 % LF-vs-HF step (time constant about 20 us). Trim range of Rf2 (16.2k + 10k trimmer): -5.6 % ... +6.2 % |
| -3 dB, 50 Ω mode (2 K1 poles in parallel, 2 nH) | 3.4 GHz model, set by the ideal BUF802 model; flat to within 0.1 dB up to 1.5 GHz. A real BUF802 gives about 2-2.4 GHz |
| Rise time 10-90 %, 20 ps step | Passive part at the BUF802 die: 56 ps. At the splitter: 120 ps with **13 % overshoot** (ESL/Lin resonance near 4 GHz plus a steep model roll-off) |
| One K1 pole only (4 nH) | +1.7 dB peak at 2 GHz, 25 % overshoot, S11 -5 dB. This is why both poles are used |
| S11, 50 Ω mode | below -16 dB to 1 GHz; -9 dB at 2 GHz |
| 1 MΩ mode | 1.000 MΩ, 3.2 pF at 10 MHz. With a 50 Ω source: 1.1 GHz, 345 ps (source x Cin) |
| Noise referred to the input, 10 Hz-2 GHz | BUF802 0.49 mV; back-termination and splitter 0.28 mV; alpha network 0.04 mV; servo 0.006 mV; **total 0.57 mV rms** |
| Clamp, +20 V 10 us overload (1 MΩ) | Die input clamps at 2.3 V (CLH + diode); OUT limited to 1.5 V. **Recovery is slow (more than 60 us)**: the servo winds up to the rail and the gate re-biases through 10 MΩ |
| Maximum input (my estimate) | 1 MΩ: +/-50 V peak, limited by the 100 V C0G and the 0402 resistor string (3 x 50 V); linear range +/-2.5 V around the offset. 50 Ω: 3 Vrms with 2 x 100 Ω 0603 |

## Choices
- **Trim.** Use a fixed C0G divider plus the Rf2 trimmer: set it once with a 1 kHz square wave so the LF and HF gains match. Software cannot repair an LF/HF mismatch in equivalent-time records. If Rf2 is selected on test instead, the trimmer is not needed. DC gain and offset go into the software calibration.
- **Protection.** No external TVS, because it would add 0.3-1 pF. The internal BUF802 clamps (CLH, 100 mA diodes) handle overdrive. Ctop (1.5 pF) limits the current: 100 V/ns gives 150 mA for less than 1 ns. The 900k string limits the current into the servo input.
- **Clamp levels.** CLH/CLL = +/-1.5 V. This leaves 0.5 V above the largest output (signal +/-0.5 V plus offset +/-0.5 V) and limits the sampler bridge to about +/-0.75 V after the splitter. The datasheet asks for 1.5 V of margin for best THD; that is a small THD cost at the edges of the range.
- **(f) Attenuation: keep the fixed 5:1, with no attenuator relay.**
  - 200 mVpp at the probe gives +/-19 mV at the comparator, and 0.57 mV of noise is 51 dB below it.
  - 10:1 would halve the trigger margin.
  - A relay-switched 1:1 would put a second relay with about 4 nH into the HF path at GHz frequencies, and the result above shows that inductance costs flatness. It would also cost about 2 USD, and the 1:1 range (+/-0.5 V) is too small for 3.3 V logic.
  - If more sensitivity is needed later, add gain in the trigger branch, not at the input.
- **Relay.** Keep the HFD3, use both poles in parallel and keep the stub under 2 mm. A cheaper relay would only be acceptable if its contact inductance is at or below about 2 nH; I checked none.

## Sensitivities
- Cin of the BUF802 (typical value only): +/-0.3 pF gives +/-4 % HF gain. Ctop +/-0.05 pF gives +/-2.6 %. G spread gives +/-1 %. All of these are covered by the trimmer.
- Cp, OPA Ccm: a 20 % change in Ccm gives about 1.3 % on the tap RC, and the residual crossover bump stays below about 0.3 % (estimated, not swept).
- K1 inductance: 1.5-2 nH is flat. 3 nH gives +0.9 dB and 4 nH +1.7 dB at 2 GHz.

## Open points (unproven)
1. The 13 % step overshoot comes from the Cbot/Lin ESL resonance and the idealised BUF802. To try: Rg 22-33 Ω, or a 0201 Cbot. In one AC run with the 4 nH relay, Rg = 33 Ω removed the +1.7 dB peak; the cost was -0.4 dB at 2 GHz and -6 dB at 3 GHz.
2. Overload recovery: clamp the servo output, for example with an output limiter or diodes at In_Aux, and/or lower the bias resistor to 2-5 MΩ as the TI datasheet suggests. Not simulated.
3. HFD3 RF parameters (contact inductance, open capacitance) are assumed. Measure them or find data. S11 is -9 dB at 2 GHz.
4. The BUF802 model has no real aux-path dynamics, no Cin tolerance data, no slew or THD, and no 1/f noise beyond the 18 kHz corner. Validate against the TI EVM or a TINA model if one can be obtained.
5. The noise figure excludes the sampler and hold amplifier. The -2V5 rail drives the offset through Rmid (gain 0.2 at OUT), so it must be clean below 10 kHz.
