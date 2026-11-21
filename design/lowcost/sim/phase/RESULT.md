# Phase-recovery path at 50 MHz strobe rate: result (simulation, behavioural models)

Scripts: `common.py` (models, runner), `line_drive.py` (a), `gate50.py` (b, d), `feedthrough.py`,
`neutralise.py` (b), `tdc_mc.py` (c, reuses `sim/snapshot_tdc.run`). Plots: `line_drive.png`, `gate50.png`.
No vendor models: TLV3801 = ±3.5 mA current-steering output, 135 ps 20-80 %; TRF37D73 = 50 R in/out,
22.3 dB, 2 x 3.3 GHz poles, tanh limit ±2.3 V, flat to DC behind the external parts (datasheet: 1 MHz-6 GHz).
Diodes: BAT15 model + package from `sim/frontend.py`. Line = LC ladder. TMUX136 not in the decks.

## Final circuit
- **TMUX136 (f)**: local switch GND = -0.9 V from a divider (1.5 k to GND, 2.7 k to -2V5, 100 nF + 1 nF at
  the pin), VCC = +2V5 (3.4 V across, in 2.3-4.8 V). Signal ±0.5 V = 0.4..1.4 V above the switch GND (spec
  0..3.6 V). EN to the local -0.9 V. SEL from a 3.3 V GPIO: 10 k series, 18 k to -2V5 -> -0.89 V / +1.23 V
  = 0.0 / 2.1 V above switch GND (VIL 0.6, VIH 1.3, max VCC). EXT_CLK on B: 50 R to GND, same range.
  Ron is specified only at 0-0.4 V; at 1.4 V above GND it is unspecified (NMOS-type switch): open point.
  Power sequencing: VCC-GND ramp must be 100-1000 us/V.
- **TLV3801**: VCC +2V5, VEE -2V5, GND pin to GND, trigger DAC on IN-. Output pair: **100 R across CMP_P/CMP_N**
  at the pins (DC path, 350 mV VOD as specified); each leg then sees 25 R at HF.
- **Line driver (a)**: CMP_P -> **1 uF** -> TRF37D73 (3V3, output choke **47 uH** + small high-SRF section)
  -> **1 uF** -> **12 dB pi pad 82 / 91 / 82 R** -> line. CMP_N -> 1 uF -> **49.9 R** dummy (equal load).
  Line: ±0.21 V for data, steps of 0.42 V for isolated edges; edge at the taps 225-250 ps 10-90, 151-162 ps
  20-80, overshoot < 1 %.
- **Line**: 16 taps, 35.1 ps/tap simulated (35 target), trace between taps **73 R, 24 ps** (about 3.5 mm on
  the stack-up of `frontend.py`), loaded to 50 R by each gate (~0.37 pF); 50 R end termination.
- **Gate**: BAT15-04W, 2 x 0.47 pF C0G hold caps to PSTRB_A/PSTRB_K. **Readout 2.2 k to VTAP_N/VTAP_P,
  2 x 1 k to the comparator IN+**. **VTAP_P/N = +2V5 / -2V5** (hold nodes at ±0.78 V; 0.78 mA per tap,
  12.5 mA per rail for 16 taps). Comparator COS3502 on 3V3/GND (inputs at 0 V are inside its range),
  IN- = VTAP_TH (DAC, range 0..+80 mV, 0.5 mV steps, through 1 k + 100 nF per group).
- **Coarse receiver (e)**: GW1NZ-1 has no differential inputs (DS841 rev 1.3E note) -> **SN65LVDS2DBVR**
  (LCSC C38204, about 0.54 USD @1, snapshot) at 3V3, bridged by **2 x 470 R** from CMP_P/CMP_N (Rx Cin ~3 pF
  assumed). Receiver sees 175 mV (HF) / 350 mV (LF) differential, above its ±100 mV threshold; TRF input
  drops < 5 % at the edge, 0 % after. RC 1.4 ns: the coarse path is good to ~100-150 MHz edges only.

## Key numbers
| Item | Result |
|---|---|
| 3 Gbps PRBS7 at the line | ±0.26 V peak, zero-crossing DDJ 1.8 ps rms / 7.8 ps pp; baseline wander nil (tau ~2 us) |
| 1 MHz square | 0.29 V after the edge, 0.23 V at the end of the half period (choke tau 1.9 us) |
| 1 kHz square | 0.43 V step from 0 V, decays (0.25 V at 1 us, 0.01 V at 5 us), undershoot +0.016 V at 20 us; line sits at 0 V between edges |
| Comparator input, strobe 2.0 V, line ±0.21 V, Cin 3 / 6 pF | 34 / 20 mV at 1 ns, 30 / 22 at 3 ns, 21 / 18 at 5 ns, 13 / 14 at 8 ns |
| Residue of the previous snapshot (20 ns earlier) | -1.6 mV (3 pF), -0.25 mV (6 pF) at 2 ns: 5 % / 1 % |
| **Line feed-through** (line edge after the strobe, no strobe) | **-34 mV for a 0.42 V step (3 pF)**: as large as the captured value |
| Single-shot rms, 16 taps x 35 ps (code-density cal.) | 20 ps (3 pF), 28 ps (6 pF); offsets 6.5 mV rms: 24 / 39 ps; amplitude -30 % vs cal: 25 ps |

**Feed-through finding (b)**: out ≈ 0.16·V(line at strobe) + 0.08·(V(line now) − V(at strobe)), both decaying
with the readout. Taps the edge reaches 0-560 ps after the strobe therefore read about 0 mV (−1.4 mV), taps it
has passed read +32 mV (3 pF). The decision threshold is not 0 V but half-way, and its sign follows the edge
polarity: **use one edge polarity (rising) and set VTAP_TH ≈ +15 mV (data, 3 pF) / +10 mV (6 pF)**; isolated
slow edges (step 0 -> 0.42 V) need ≈ +50 mV (before-taps read +34 mV, after-taps +68 mV). VTAP_TH is found per
signal class by a threshold sweep (code density). This also removes the AC-coupling problem: on a slow
clock the line idles at 0 V, which reads 0 with a positive threshold. Hit rate halves (one polarity).
A neutralising 0.27 pF from each hold node to a complementary line (`neutralise.py`) cancels the
feed-through but also cut the useful difference to < 1 mV in this quick test: rejected, not understood.

## Latch timing (FPGA)
Comparator input peaks 1-2 ns after the strobe; COS3502 4.5 ns typ / 7 ns max (5-7.5 ns at 12-20 mV).
Output valid from strobe + ~9 ns (worst case) until strobe + 20 ns + 4 ns. **Sample TAP[15:0] at strobe
+ 12 ns (window 10-22 ns)**, same delay for all bits, i.e. 8 ns before the next phase strobe.

## Strobe requirement (d) (to the driver agent)
Per gate, per side: **≥ 2.0 V unloaded (Thevenin 25 R, i.e. a 50 R line passing the gate and terminated),
opposite polarity on PSTRB_A/PSTRB_K, FWHM 150-250 ps** (150 vs 250 ps: no difference), imbalance < 5 %.
1.5 V gives only 10 mV (fails), 2.5 V gives 48 mV (+27 %). Peak diode reverse voltage 1.3-1.5 V (BV 4 V).
Each gate presents ~0.4 pF (0.47 pF in series with the diode path) and draws its charge at the strobe; 16
gates = ~6.5 pF per polarity. Distribution: the strobe must reach all 16 gates nearly simultaneously (skew is
calibrated, but must be stable). A strobe line travelling along the taps does not work at 35 ps: loaded with
0.4 pF/tap it is slower than 35 ps/tap, co-propagation cancels the spacing and counter-propagation doubles it.
Proposal (not simulated): per polarity 1:4 split into four short 4-gate segments, each a 50 R line ending in
50 R right behind its 4 gates; the driver then has to deliver ≥ 2.0 V into each of 4 x 50 R (≈ 4 V into
12.5 R, or 4 driver outputs). Above the 3.0-3.4 V single-line pulse of `strobe/RESULT.md` divided four ways.

## Sensitivities
Strobe amplitude (steep below 2 V); Cin of COS3502 (3 -> 6 pF: signal -40 %, rms 20 -> 28 ps); VTAP_TH
must be re-found per signal class; TLV3801 VOD 250-450 mV and TRF gain move the line ±30 % (calibrated).

## Open points (unproven)
1. Feed-through model rests on the BAT15 package capacitance (0.16 pF) and ideal hold caps; measure on board.
2. Strobe distribution to 16 gates (above); full 16-tap deck with strobes and readout not run (time).
3. TRF37D73 below 1 MHz and its saturation behaviour; TMUX136 Ron at 0.4-1.4 V above its GND.
4. COS3502 Cin, hysteresis and delay at 10-30 mV overdrive; SN65LVDS2 input capacitance and max rate.
