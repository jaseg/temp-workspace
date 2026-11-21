# Strobe generators: result (simulation, behavioural amplifier models)

Scripts: `chain.py` (FPGA + gain-block chains, edge table), `bridge.py` (re-runs the bridge deck of
`sim/scope_sampler.py`, case D, with the simulated strobe), `extras.py` (AC coupling/choke droop over
real pulse trains, phase-strobe launch, plots). Plots: `chain_edges.png`, `baseline.png`, `bridge_step.png`.

## Models (what is behavioural)
- No vendor models used. GVA-84+ datasheet fetched (gain table, P1dB, Psat); TRF37D73 from the local extract.
- Gain block = 50 R in || 0.2 pF -> filter A -> tanh limiter -> filter B -> 50 R || 0.3 pF out.
  TRF37D73: 22.3 dB, 2 poles at 3.3 GHz; saturates at +/-2.3 V into 50 R (OP1dB 16.5 dBm).
  GVA-84+: 24.1 dB, poles 1.1 / 6.5 GHz + zero 3.75 GHz (fits 24.1...10.5 dB, 0.1-7 GHz); +/-3.6 V (Psat 22.3 dBm).
  "nominal": one pole (TRF) / the 1.1 GHz pole + zero (GVA) before the limiter, the rest after.
  "pess": all filtering after the limiter (stage slews no faster than its small-signal response).
- FPGA pin: 3.3 V ramp, 10-90 % = 300 or 600 ps, 40 R, 3 pF. Symmetric clipping assumed; real
  Darlington stages clip asymmetrically (cut-off side ~Iq x R_L, saturation side ~Vcc - 1 V).

## Key finding: use 50 % duty, not a short pulse
An AC-coupled saturating chain with a low-duty pulse idles in its linear range, so the step is only
~Vsat (2.4 V for TRF finals). With a 50 % square wave both levels saturate and the step is 2 Vsat
(4.6 V TRF, 7.2 V GVA). The stub differentiates both edges; the other edge gives a reverse pulse
half a period later. FPGA patterns: S_STROBE 3.125 MHz 50 % (160 ns / 160 ns), PH_STROBE 50 MHz 50 %.

## Final circuits
**Sampler strobe (STRB_A/STRB_K), one chain + balun, ~3.4 USD:**
S_STROBE_P -> 47 R series -> 100 nF -> TRF37D73 #1 -> 100 nF -> 12 dB pi pad (82 / 91 / 82 R)
-> TRF37D73 #2 -> 100 nF -> shorted stub 80 ps one-way (about 13 mm 50 R microstrip at 6.05 ps/mm)
-> common-mode-choke balun as in the bridge deck -> 1 nF blocks -> rails (10 R at the diodes, +/-1 V bias).
TRF output chokes: 47 uH (with a small high-SRF 0402 section in series, not modelled); 2.2 uH loses 25 %.
S_STROBE_N: terminate 50 R (unused). No logic-gate sharpener needed: the first TRF stage already
turns a 300-600 ps edge into ~250 ps and the second into 133-152 ps.

**Phase strobe (PSTRB_A/PSTRB_K), two chains from PH_STROBE_P / PH_STROBE_N, ~9.2 USD:**
each: 47 R -> 100 nF -> TRF37D73 -> 100 nF -> 10 dB pi pad (100 / 68 / 100 R) -> GVA-84+ (5 V, choke
2.2 uH) -> 100 nF -> shorted stub 40-50 ps one-way (7-8 mm) at the launch point -> strobe line.
Cheaper alternative 2x(2xTRF), 6.3 USD, gives only 2.15 V per line (below the 3 V the taps were simulated with).

## Numbers (simulated)
| Chain (50 % duty) | edge 10-90, FPGA 300 / 600 ps | step into 50 R |
|---|---|---|
| 2xTRF nominal / pess | 133 / 152 ps, pess 180 / 194 ps | 4.59 V |
| 3xTRF nominal | 128 / 130 ps | 4.59 V |
| TRF+GVA nominal / pess | 130 / 148 ps, pess 314 / 324 ps | 7.18 V |
No chain reaches the 120 ps target edge (TRF output pole limits to ~106 ps); a third TRF buys 2-20 ps.

Bridge (deck D, 10 R source, +/-1 V bias, 2.2 pF hold), reference ideal 3 V/40 ps: 73 ps, gain 0.46, 72 %.
| Strobe | aperture | gain | eff/strobe |
|---|---|---|---|
| 2xTRF 50 % duty (4.6 V, 152 ps), 80 ps stub | 84 ps | 0.74 | ~100 % |
| same, 60 ps stub | 70 ps | 0.71 | 93 % |
| same, FPGA 300 ps, 60 ps stub | 72 ps | 0.73 | 98 % |
| same, pessimistic amplifier, 60 / 80 ps stub | 69 / 84 ps | 0.56 / 0.73 | 76 / 102 % |
| step -25 % (3.4 V), 60 / 80 ps stub | 49 / 57 ps (overshoot 57 / 15 %) | 0.17 / 0.56 | 39 / 75 % |
| step -40 % (2.75 V), 80 ps stub, bias +/-0.6 V | 81 ps | 0.70 | 93 % |
| step -40 %, bias +/-1 V | fails (no conduction) | - | 0 % |
| 2xTRF low duty (2.4 V "+/-2 V strobe") | fails | - | 0 % |
| TRF+GVA low duty (4.8 V), 60 ps stub | 73 ps | 0.73 | 97 % |
Efficiency figures near/above 100 % come from the finite-difference estimate; read as "full".

AC coupling (2xTRF, 100 nF everywhere, `baseline.png`): S_STROBE 50 % duty step 4.30 V with 47 uH
chokes, 3.47 V with 2.2 uH; 1/64 duty 2.40 V. PH_STROBE 50 MHz 50 % duty 4.42 V (2.2 uH), 1/20 duty 3.01 V.
Phase launch through the stub: 2xTRF 2.15 V peak, 188 ps FWHM; TRF+GVA 3.0-3.4 V, 166-180 ps FWHM
(pessimistic GVA: 2.0-2.3 V, 240-266 ps).

## Sensitivities
- Strobe amplitude vs bias is the steep one: with +/-1 V bias the bridge stops at ~-35 % amplitude.
  Make VBIAS adjustable (DAC/trimmer, +/-0.5..+/-1.2 V); 80 ps stub preferred over 60 ps for margin.
- FPGA edge 300 vs 600 ps: 20 ps at the chain output, ~2 ps in aperture. Duty cycle: decisive (above).
- Choke value at 3.125 MHz: 2.2 uH -> -25 % step; needs >= 22-47 uH plus a broadband section.

## Open points (unproven)
1. Large-signal edge of both gain blocks in hard saturation (no vendor data; "pess" bracket shown;
   GVA-84+ pessimistic case is far worse). Measure one chain early.
2. Clipping asymmetry and recovery time of the Darlingtons; input abs. max: TRF stage 2 sees
   ~+8.6 dBm square (limit +10 dBm), GVA ~+10 dBm (limit +13 dBm).
3. Reverse pulse from the second edge: up to ~4.6 V step on the bridge rails on top of 2 V bias vs
   BAT15 BV 4 V (two diodes share it) - not simulated; add a clamp or check in the deck.
4. Phase strobe: tap_array.py was not re-run with the 3.0-3.4 V / 170-180 ps pulses (it assumed 3 V/100 ps).
5. Broadband 47 uH bias-tee choke realisation and its SRF; balun as in the earlier deck (choke type).
