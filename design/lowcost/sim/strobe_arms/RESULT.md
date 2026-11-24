# Strobe arms STRB_A / STRB_K: result rev. 2, as built 24 Nov 2026 (simulation only; RF-1, RF-2, RF-3/R204)

Scripts: `wave_gen.py` / `wave_fall.py` (2xTRF chain from `sim/strobe/chain.py`, 152 ps, rising / falling edge,
same 4.30 V scale), `arms.py` (deck; `CASES` rev. 2, `SINGLE` per-diode / falling-edge runs, `OLD_CASES` rev. 1),
`plots.py` (`arms.png`), `amp.py`. Run: `python3 arms.py; python3 arms.py single; python3 plots.py` (about 3 min).
Deck = `sim/sampler/bridge.py` final circuit + chain source, tap, TL401, D401, CLIP 1.6 mm, balun, 50 R arms at
5.925 ps/mm, rails 2.565 mm, hold copper +268 fF, as in rev. 1. **As built (layout/board/blocks/analog/README.md):**
arms 17.827 mm = 105.6 ps each (rev. 1: 16.747 mm, 99 ps); R204 1 k inline on the bridge axis, 4.039 mm from
T401.2 / T401.4 on both arms (no stub); TL401 80.0 ps incl. the via short; D401 on a 0.40 mm tap line.
Aperture = 10-90 % of the held step (clean 35 ps input); system = BUF802 model + 2 GHz edge; kick-out with the
BUF802 model, quiet input. Regression: rev. 1 REC case re-run unchanged (100 ps / 104.8 % / 186 mV).

## Sampling edge, as built (clean input)
| Case | aperture | eff | gain | ped | kick in / BUF / trig (mVpp) | bridge rev. |
|---|---|---|---|---|---|---|
| **bias +/-1.0 V** | **126 ps** | 122 % | 0.60 | +31 mV | **180 / 97 / 21.5** | -3.7 V |
| +/-1.2 V | 109 ps | 112 % | 0.57 | +34 | 189 / 99 / 22 | -4.3 V |
| **+/-1.3 V (recommended)** | **100 ps** | **105 %** | 0.55 | +36 | **187 / 102 / 22** | -4.6 V |
| +/-1.35 V | 96 ps | 102 % | 0.54 | +37 | 185 / 103 / 22 | -4.7 V |
| +/-1.4 V (VBIAS_K limit) | 91 ps | 98 % | 0.53 | +38 | 185 / 106 / 22 | -4.8 V |
| -1.46 / +1.40 V (both range ends) | 88 ps | 96 % | 0.52 | +23 | 157 / 91 / 18 | -4.9 V |

System (BUF802, 2 GHz): +/-1.0 V 186 ps (eff 118 %, gain 0.55); **+/-1.3 V 148 ps (eff 100 %, gain 0.49)**;
+/-1.35 V 141 ps (97 %); +/-1.4 V 133 ps (93 %). No second sampling instant (held value flat to within 1.6 %
before the edge at nominal strobe, `arms.png` left; 2.5-7 % in the strobe -25 % cases with eff <= 71 %). Rev. 1 as built at +/-1 V was 129 ps / 209 mV kick: the symmetric
R204 removes the RF-3 kick-out excess (180 vs 209 mV); the 6.6 ps longer arms change nothing measurable (rev. 1
recommended 100 ps / 105 %; 17.827 mm with R204 at the balun 101 ps / 106 %, same kick-out).

## Strobe amplitude (as built)
| Bias | strobe -25 % | -10 % | +10 % |
|---|---|---|---|
| +/-1.0 V | 90 ps, eff 93 %, gain 0.51 | 114 ps, 114 % | - |
| +/-1.2 V | 66 ps, 71 %, 0.43 | - | - |
| +/-1.3 V | **56 ps, 59 %, gain 0.38** | - | 112 ps, 115 % |
| +/-1.35 / +/-1.4 V | 51 / 47 ps, 51 / 42 % | - | 108 / 104 ps, 112 / 110 % |
| re-trimmed: +/-0.9 V | **103 ps, 103 %, gain 0.54** | - | - |
At a fixed +/-1.3 V a 25 % weaker strobe halves the efficiency; re-trimming to +/-0.9 V restores 103 ps / 103 %.
So the per-board bias trim (target eff ~100 %) is mandatory, not optional. A strobe more than ~10 % above
nominal cannot be fully trimmed back: at the VBIAS_K end (1.40 V) the aperture stays 104 ps (eff 110 %).

## Bias vs control range (kicad/README.md: VBIAS_A -1.46..-0.50 V, VBIAS_K +0.10..+1.40 V)
+/-1.3 V nominal is inside both ranges (K margin 0.10 V). The trim span needed for strobe -25..+10 % is
+/-0.9..>1.4 V: the lower end is inside (A 0.40 V and K 0.80 V above their minimum), the upper end hits VBIAS_K
1.40 V. Asymmetric -1.46 / +1.40 V gains only 3 ps and moves the pedestal (-13 mV) and kick-out.

## Reverse voltage per diode (max over the 4 BAT15-04W diodes, hold node at its sampled steady state)
| Bias | rising edge, input +/-0.5 V / +/-1.5 V | falling edge, +/-0.5 V / +/-1.5 V | falling, +/-1.5 V, strobe +10 % |
|---|---|---|---|
| +/-1.0 V | 1.96 / 2.50 V | 2.63 / 3.63 V | 3.72 V |
| +/-1.2 V | 2.24 / 2.70 | 2.83 / 3.83 | 3.93 |
| **+/-1.3 V** | 2.39 / 2.80 | **2.93 / 3.93** | **4.03** |
| +/-1.4 V | 2.54 / 2.90 | 3.03 / 4.04 | 4.13 |
| -1.46 / +1.40 V | 2.57 / 2.96 | 3.09 / **4.10** | 4.18 |
Input +/-0.5 V = full scale at the bridge, +/-1.5 V = BUF802 CLH/CLL clamp (overload). Over the full-scale range
every case keeps >= 0.9 V margin to the 4 V rating. At overload the falling edge reaches 3.9-4.2 V for any bias
>= +/-1.3 V: about |bias| + 1.5 V + 1.13 V. The kicad/README.md note "VBIAS_K 1.40 V keeps <= 2.9 V at the
-1.5 V clamp" is the static / sampling-edge value only (2.90 V here); the falling edge adds 1.1 V.

## Falling edge (reverse pulse, +160 ns, D401 fitted; `arms.png` right)
- The stub turns the falling edge into a negative pulse; D401 clips the tap at -1.37 V (-1.49 V at +10 %),
  peak 99 mA (111 mA) for ~150 ps, average ~50 uA at 3.125 MHz. The bridge goes further into reverse
  (+/-1.3 V: -2.6 -> -4.8 V) and the ringing afterwards peaks at -2.2 V: **no forward conduction**, so no
  spurious sample at the falling edge.
- **Without D401**: tap -2.85 V, bridge -6.8 to -7.7 V, 4.5 V per diode at overload (over the 4 V rating at any
  bias; 3.5-3.9 V at 0 V input) and the ringing comes back to +0.25 V at +/-1.0 V bias (-0.3 V at +/-1.3 V), 0.25 V from conduction.
  D401 is required.
- Held-value shift from the falling edge: -9.6 mV, independent of the input over full scale (-9.5..-9.7 mV), plus
  a large shift only in overload (+/-150..310 mV at +/-1.5 V). It lands after the ADC window (40-148 ns,
  theory-of-operation); the next sampling edge removes it to within (1 - eff) x 9.6 mV < 0.5 mV. Kick-out at
  the falling edge 9 / 4 / 1.2 mVpp (in / BUF / trig) at 0 V input.

## Findings
1. The as-built arms (105.6 ps, R204 symmetric on the axis, 80 ps stub) behave like the rev. 1 recommendation:
   at +/-1.0 V the bridge is over-driven (126 ps, eff 122 %); **+/-1.3 V restores 100 ps / 105 %** (system 148 ps,
   eff 100 %, gain 0.49, pedestal +36 mV). +/-1.35 V gives 96 ps / 102 %. Kick-out 187 / 102 / 22 mVpp.
2. The nominal setting in kicad/README.md (+/-1.3 V, DAC 0.62 / 2.50 V) stays valid; no change.
3. Amplitude sensitivity is strong (-25 % strobe at +/-1.3 V: eff 59 %); the calibration trim covers -25 % down
   to +/-0.9 V; above +10 % the VBIAS_K 1.40 V limit stops the trim (aperture 104-108 ps).
4. Reverse voltage: full scale OK (<= 3.1 V); overload at the BUF802 clamp with the falling edge is at the
   4 V rating (3.93 V at +/-1.3 V, 4.10 V at the range ends, 4.18 V with +10 % strobe). For a margin either
   limit the trim to |bias| <= 1.25 V in overload-prone use (3.88 V; costs ~5 ps aperture at nominal strobe), or
   tighten CLH/CLL to +/-1.2 V (-0.3 V per diode). Recorded for the schematic / firmware owners; not changed here.
**Recommendation.**
- Keep the as-built geometry. Nominal bias +/-1.3 V, per-board trim for eff ~100 % (expected span +/-0.9..1.4 V).
- Update the VBIAS_K note in kicad/README.md: 2.9 V is static; the falling edge gives 3.9-4.1 V at overload.
- Keep D401 fitted (it halves the falling-edge reverse swing and keeps the ringing 2.7 V below conduction).
- Keep the ADC window before the falling edge (falling-edge shift -9.6 mV, calibrated with the pedestal).

Open: balun as a lumped CM choke; chain amplitude unmeasured (trim covers it); BAT15 VR 4 V from the project
notes (datasheet not re-checked; overload transient ~150 ps wide); hold droop over 160 ns not modelled.
