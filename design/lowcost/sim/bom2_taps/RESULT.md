# BOM-2 tap capacitors C314-C345 on the as-built phase array (simulation, behavioural models)

Scripts: `deck_ab.py` (imports `sim/phase_array/deck.py` unchanged; `build_ab()` is a modified copy of its `build()`),
`taps.py` (`survey` and `sweep`, reusing `sim/phase_array/run.py` for the tap fit and the single-shot estimator).
Outputs: `survey.json`, `sweep.json`, `taps.png`. Run `python3 taps.py all` (about 6 min, 4 processes).

## What the capacitor does
C314-C345 are **not** hold capacitors to ground. Each one is in series between PSTRB_A (or PSTRB_K) and a hold node
(netlist: C314 pad 2 = Net-(D301-A)). The strobe reaches the BAT15 gate only through this capacitor, and the held
charge sits on it. If the part is not fitted, the only path left is the empty 0402 pad pair, about 0.03 pF.

## As-built deck (layout/board/blocks/phase/README.md, six layers)
- Strobe lines: 62 R, 26.25 ps per 4.514 mm section unloaded, a 0.110 pF strobe-side pad at each gate, 43 R ends,
  80 ps stub.
- PH_LINE: 62 R, 56.46 ps per 9.707 mm cell unloaded, a 0.095 pF pad-3 excess per tap, 49.9 R end.
- Readout: 2.2 k / 2 x 1 k, comparator Cin 3 pF (assumed, as before).
- **Hold-node capacitance to ground, c_node = 0.40 pF.** This was extracted from scope-fe.kicad_pcb with pcbnew,
  using L2 fill coverage per pad and track:
  - the 1 k node pad (R315 etc., 0.54 x 0.64 mm) lies fully over solid L2: about 0.17 pF
  - 0.95 mm of 0.15 mm node track over L2: 0.10 pF
  - the 2.2 k pad, about one third over L2: 0.05 pF
  - the copper in the L5-referenced cut-out (diode pad, C pad 2, tracks, about 1 mm2): about 0.05 pF
  - fringe to the L1 pour: 0.03-0.05 pF
  - estimate +/-30 %; the original deck had none
- Diode capacitance: in the BAT15 model.

## Survey (comparator input; "swing" = edge passed minus edge not yet arrived; min / mean over the 16 taps)
| cc | c_node | swing at 3 ns | at 5 ns | at 12 ns | threshold mid (3 / 5 ns) | feed-through | strobe ps/tap, tap-15 peak |
|---|---|---|---|---|---|---|---|
| 0.03 pF (DNP pads) | 0.40 | **-6.3 / -6.0 mV** | -5.5 / -5.1 | -1.8 | 21 / 16 | 38.5 mV | 30.4, 3.72 V |
| 0.10 pF | 0.40 | -5.9 / -5.7 | -5.4 / -5.0 | -1.8 | 21 / 16 | 38.0 | 31.9, 3.74 V |
| 0.20 pF | 0.40 | -4.8 / -3.7 | -5.0 / -3.7 | -1.7 | 20 / 15 | 37.2 | 33.7, 3.73 V |
| 0.30 pF | 0.40 | 14.0 / 32.0 | 9.0 / 22.8 | 3.0 | 18 / 14 | 36.3 | 36.2, 3.59 V |
| **0.50 pF (as built)** | 0.40 | **47.2 / 55.7** | 35.1 / 41.2 | 12.6 | **16.7 / 13.5** | 34.5 | **39.3, 3.36 V** |
| 0.80 pF | 0.40 | 38.5 / 49.4 | 28.7 / 37.1 | 11.1 | 15.6 / 13.5 | 31.5 | 42.5, 2.76 V |
| 0.20 pF | 0.12 | 7.0 / 25.0 | 4.3 / 17.1 | 1.2 | 20 / 15 | 39.3 | 34.2 |
| 0.30 pF | 0.12 | 45.6 / 51.6 | 31.7 / 36.4 | 9.7 | 18 / 14 | 38.6 | 36.0 |
| 0.50 pF | 0.12 | 43.3 / 50.3 | 30.9 / 35.9 | 10.2 | 18 / 14 | 36.9 | 38.9, 3.02 V |
| 0.47 pF, c_node 0 (old deck values) | 0 | 42.5 / 49.1 | 30.1 / 34.6 | 9.4 | 18 / 14 | 38.2 | 38.1 |

- **DNP:** the hold node peaks at -0.65 V (bias -0.78 V), so the diode never conducts. The output is only
  feed-through. No capture at any tap. Up to 0.2 pF also fails.
- Capture starts at about 0.3 pF. The output is flat from 0.4 to 0.8 pF.
- Droop from 3 to 12 ns is 71-80 % in every case. The COS3502 output follows its input (4.5-7 ns delay), so the
  FPGA latch at +12 ns sees the input at about 5-7.5 ns. At 0.5 pF that is 35 mV of swing at the weakest tap.
- The threshold midpoint is 16.7 mV at 3 ns and 13.5 mV at 5 ns, inside VTAP_TH 6-79 mV.
- Tap-to-tap spread of the midpoint is 1.3-2.4 mV.

## Full edge sweeps (25 ps steps; spacing, window and rms as in sim/phase_array)
| Case | spacing mean +/- sd (min-max) | window | half swing min-max | 10-90 width | single-shot rms (offsets 3.7 / 6.5 mV) |
|---|---|---|---|---|---|
| **as built, 0.5 pF, c_node 0.40** | **33.7 +/- 5.1 ps (26.9-46.6)** | 506 ps | 23.6-50.6 mV | 272 ps | **16.8 / 19.3 ps** |
| 0.25 pF (C1544 -0.25 pF corner) | 33.4 +/- 4.5 (18.8-38.2) | 501 | **0.4-10.4 mV** | 374 | **60 / 74 ps (fails)** |
| 0.45 pF (Murata W -0.05 pF corner) | 34.4 +/- 4.0 | 516 | 24.2-48.6 | 272 | 17.1 / 19.6 |
| 0.5 pF, L2 cut enlarged (c_node 0.12) | 32.7 +/- 3.3 | 490 | 21.7-43.8 | 287 | 17.7 / 20.2 |
| printed 0.5 pF (strobe pad 0.16 pF), c_node 0.12 | 31.8 +/- 3.5 | 477 | 21.6-43.9 | 290 | 17.6 / 20.0 |
| printed -15 % (0.43 pF) | 31.8 +/- 3.9 | 477 | 23.9-41.6 | 335 | 18.0 / 20.5 |
| printed +15 % (0.58 pF) | 31.8 +/- 3.0 | 477 | 19.9-46.3 | 260 | 17.2 / 19.8 |
| DNP (0.03 pF) | no transitions | - | -3.0 mV | - | no stamps |

- As built, taps 3-11 are 29.8-31.7 ps apart: the "about 30 ps effective" of SPEC decision 4 is confirmed. Taps 12-15
  are irregular (46.6 / 26.9 / 41.0 ps), as before (pulse widening), and calibrated by code density.
- Strobe: 39.3 ps/tap (layout target 39.40). Tap-15 peak 3.36 V (>= 2.0 V needed).
- Compared with the 4-layer deck (34.7 +/- 3.1 ps, 19 / 22 ps rms), the as-built board is slightly better in rms.

## Conclusions
1. DNP relying on parasitics is impossible: the series coupling capacitance must be at least about 0.35 pF.
2. The fitted part C1544 (FH 0402CG0R5C500NT, "C" = +/-0.25 pF) is a risk: its low corner (0.25 pF) gives
   0.4-10 mV half swings and 60 ps rms.
3. Two fixes work:
   - Murata GJM1555C1HR50WB01D (+/-0.05 pF, LCSC C76912, extended, 121k in stock).
   - A printed L1/L2 capacitor of 0.5 pF: 0.43 / 0.58 pF corners give 17-18 ps rms.
4. Enlarging the L2 cut under the 1 k node pad (c_node 0.40 -> 0.12 pF) brings nothing at 0.5 pF: not recommended.

Open: c_node and the printed-capacitor value are estimates (no field solver run); COS3502 Cin assumed 3 pF;
behavioural strobe chain as in sim/phase_array.
