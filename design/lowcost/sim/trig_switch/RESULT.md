# Trigger source switch without the TMUX136: result (simulation)

Script: `switch.py` (ngspice, about 10 min), numbers in `RESULT.json`. Decision and schematic:
`docs/research/bom2-trigger.md`.

## Circuit simulated
Two four-diode bridges on the TLV3801 IN+ node Y, each made of 2 x BAT15-04W (package 1: pin 1 = T,
pin 3 = X, pin 2 = B; package 2: pin 1 = T, pin 3 = Y, pin 2 = B). Bridge 1: X1 = BUF_OUT_T end
(BUF802 EMF -> 49.9 R -> 50 R line). Bridge 2: X2 = EXT_CLK (50 R source -> 50 R line -> 49.9 R to GND).
Bias: T1 -Rf- S, B1 -Rf- SB, T2 -Rf- SB, B2 -Rf- S. S = collector of a PNP (emitter +2V5, base 10k from
TRIG_SEL) with R2 to -2V5; SB = collector of an NPN (emitter -2V5, base 10k from S, 3.3k base to -2V5)
with R5 to +2V5. TRIG_SEL low: S = +2.43 V, SB = -2.32 V hard -> bridge 1 on, bridge 2 off with its T / B
nodes on the hard rails. TRIG_SEL high: both transistors off -> bridge 2 on through R5 / R2, bridge 1 off
at -1.38 / +1.38 V. Y carries 1.2 pF (TLV3801 C_IC 1 pF + pad) and 1 uA bias current.
Models: BAT15 chip model + SOT-323 share (`sim/frontend.py`), MMBT3904 standard model, SS8550 as a
2N3906-type model with 15 pF Cjc, 1 nH per transistor lead. TMUX136 reference: 5.7 R, Con 1.6 pF split,
Coff 1.6 pF, 0.265 pF off coupling (fitted to the datasheet -34 dB at 240 MHz into 50 R; above 240 MHz
the reference is an extrapolation, not data).

Variants: A Rf = R2 = R5 = 1k (chosen); B all 2.2k; C as A but 100 R feeds on bridge 2.

## Results (gain referred to the unloaded source: EMF for SIG, open-circuit termination voltage for EXT)
| Quantity | A (chosen) | B (2.2k) | C (100 R) | TMUX136 ref |
|---|---|---|---|---|
| SIG on: 100 MHz / 1 GHz / 2 GHz / 3 GHz (dB) | -1.1 / -3.2 / -6.4 / -9.1 | -0.7 / -4.3 / -8.5 / -11.5 | -1.1 / -3.6 / -7.1 / -9.6 | -0.05 / -3.4 / -7.6 / -10.6 |
| SIG on -3 dB | 1.26 GHz | 0.89 GHz | 1.13 GHz | 0.93 GHz |
| BUF_OUT_T end loading (DC) | -0.80 dB (Rin 500 R) | -0.37 dB | -0.80 dB | 0 |
| EXT on: 100 MHz / 1 GHz / 2 GHz (dB), -3 dB | -0.6 / -3.1 / -6.3, 1.13 GHz | -0.6 / -5.5 / -9.8, 0.66 GHz | -1.0 / -5.2 / -7.1, 0.56 GHz | -0.02 / -1.3 / -3.6, 1.79 GHz |
| EXT leak into Y, SIG selected: 100M / 240M / 1G / 2G (dB) | -48.8 / -36.0 / -22.4 / -19.4 | -40.7 / -30.6 / -20.6 / -18.8 | -67.4 / -52.6 / -30.5 / -22.8 | -40.7 / -33.4 / -24.5 / -23.7 |
| SIG leak into Y, EXT selected: same points (dB) | -45.8 / -37.7 / -22.8 / -19.8 | -40.6 / -29.8 / -20.1 / -19.0 | -39.8 / -36.2 / -27.0 / -21.6 | -45.9 / -38.4 / -28.6 / -27.7 |
| SIG DC: offset Y - EMF, gain, nonlinearity +/-0.4 V | +6.4 mV, 0.88, 0.1 mVpp | +3.7 mV, 0.93 | as A | - |
| SIG offset drift 0-70 C | +0.47 mV (6.7 uV/K) | +0.34 mV | as A | - |
| 10 % Is mismatch between the two packages | +0.05 mV | +0.05 mV | | |
| EXT DC: offset, gain, Y at X2 = +/-0.9 V | -0.04 mV, 0.97, +/-0.87 V (0-70 C) | -1.2 mV, 0.97 | fails at 70 C (+0.9 V) | - |
| Y moved by SIG at +/-1.5 V DC (BUF802 clamp), EXT selected | < 0.2 mV | < 0.3 mV | 24 mV | - |
| Y moved by EXT at +/-1.0 V DC, SIG selected | 0 | 0 | 0 | - |
| EXT return loss, EXT selected: 100M / 1G / 2G / 3G | -26 / -12.8 / -10.1 / -9.1 dB | -28 / -15 / -13 / -11 | -19 / -9 / -8 / -7.5 | - |
| EXT return loss, SIG selected: 100M / 1G / 2G | -39 / -22 / -16 dB | -40 / -22 / -17 | | - |
| Kick-back 50 fC (assumed) into Y: peak, back to 10 % | 12.9 mV, 0.32 ns | 13.1 mV, 0.46-0.57 ns | 12.6 mV | 7.2 mV, 0.44 ns |
| Switch time to 2 mV (SIG->EXT / EXT->SIG) | 0.42 / 0.47 us (0.37 V spike) | 0.48 / 0.43 us | | - |
| Rail current, SIG / EXT selected | 12.5 / 1.1 mA | 6 / 0.5 mA | | 0.05 mA |

## Reading
- Bandwidth: the open 50 R line end with 1.2-2.5 pF on it sets the limit for both switches (tau = 50 R x C).
  Variant A is at least as wide as the TMUX136 reference on the signal path; the EXT path is narrower
  (1.13 vs 1.79 GHz), because the EXT source impedance (25 R) plus the bridge (about 2 x 18 R) drives Y.
- Offset: cancels to 6 mV (the bias imbalance between +2.43 V and -2.32 V drawing 90 uA through the 49.9 R
  source), drift 7 uV/K: calibrated with item 9 like the TMUX136 path. A package-to-package Is
  mismatch and a temperature difference between the two packages of a bridge cancel (each package holds
  one diode of each polarity pair).
- DC isolation is structural: the diode directions of an off bridge do not let a DC path form, even with
  the SIG leg at the BUF802 clamp; leakage is capacitive only (2 x 0.26 pF in series per path).
- Variant C (hard AC ground on the EXT bridge) gives 67 dB at 100 MHz but halves the EXT bandwidth and lets
  an overloaded signal into Y in EXT mode: rejected. Variant B loads the line less but loses 0.35 GHz.
- Kick-back: the TLV3801 input charge is not specified; 50 fC is a placeholder. The bridge node is 1.8 x
  more sensitive than the TMUX136 node (higher source impedance) and settles in 0.3 ns.

## Open points
TLV3801 kick-back charge; BAT15 package capacitance at reverse bias (model 0.16 pF fixed); the SS8550 model
is generic; layout parasitics at Y (0.2 pF pad assumed); TMUX136 reference above 240 MHz extrapolated.
