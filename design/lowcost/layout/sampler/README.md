# Layout fragment: sampler (bridge, hold amp, level shifter, sampler-strobe output)
`python3 gen_sampler.py` -> `sampler.kicad_pcb` (KiCad 7, 30.8 x 19.3 mm, own Edge.Cuts), plus the tables below and the checks.
`sampler.png`: top = F.Cu with the top pour hidden (so track widths show), silk, fab. Bottom row = F.Cu with pour, B.Cu (mirrored), In1.
`sampler_detail.png`: bridge, hold node, guard, STRB arms, balun. Values: `sim/sampler`, `sim/strobe`, `sim/phase_array` RESULT.md.

## Stack-up (SPEC decision 9 rev., written into the board setup)
JLC04161H-7628, 1.6 mm (checked on jlcpcb.com/impedance): L1 35 um / 7628 0.2104 mm er 4.4 / L2 In1 = solid GND /
core 1.065 mm er 4.6 / L3 In2 = +3V3 plane / 7628 0.2104 mm / L4 B.Cu (GND pour + slow feeds). Mask er 3.8, 15 um over the trace.
`microstrip()` in the script: Hammerstad-Jensen with Hammerstad thickness correction, plus a first-order mask overlay
(mask fills the air part of the fringing field, coefficient 1.2 c/h; it is an estimate that lands on JLC's 0.36 mm).
| Line | width | Z0 | eps_eff | delay |
|---|---|---|---|---|
| 50 R, all RF nets | **0.36 mm** (exact 0.360) | 50.0 R (51.0 R without mask) | 3.30 | **6.06 ps/mm** |
| neck inside the U402 pins 2/7 pads | 0.25 mm, 0.25 mm long (inside the pad) | 60 R | - | 1.5 ps |
| hold node (not a line, kept thin) | 0.15 mm | 75 R | - | 1.6 + 1.2 mm |
Top pour clearance from every RF trace = 2 w = 0.72 mm (3.4 h; keep-out rule areas per segment and per RF pad).
Coplanar check (Wadell CPWG): side ground only pulls Z below the microstrip value for gaps < 0.33 mm, so the lines are microstrip.

## RF nets (script table, all 0.36 mm / 50 R, F.Cu over In1, no vias, no layer changes)
| Net / segment | length | delay |
|---|---|---|
| BUF_OUT_S X1 -> R201, BRG_IN R201 -> D201.3 (under D201, between pins 1/2) | 0.80 + 3.12 mm | 4.8 + 18.9 ps |
| BRG_A / BRG_K rails (4 pieces, mirror images) | 2.565 mm each | 15.5 ps |
| STRB_A / STRB_K arms 47 pF -> balun (single-ended 50 R each; the bridge deck models no line, so 50 R) | 15.253 / 15.253 mm, mismatch 0 | 92.4 ps |
| STRB_CLIP balun.1 -> tap -> C404; TRF2_OUT C404 -> U402.7; TRF2_RFIN U402.2 -> C403; TRF2_IN C403 -> X2 | 2.97; 1.77; 0.83; 0.88 mm | |
| **Shorted stub**, 80 ps intended: 80 / 6.057 = 13.207 mm, drawn 13.207 mm (tap centre -> NT401) | 13.207 mm | **80.0 ps** |
Pad discontinuities (excess C vs the 0.36 mm line, noted instead of In1 cut-outs): 0402 in-line pads (R201, C403, C404) +28 fF,
R204 shunt pads on the arms +29 fF, balun pads +22 fF, SOT-323 pins +12 fF, D203 cathode +11 fF, X1/X2 +16 fF, WSON pins -11 fF.
All < 0.03 pF (about 1.5 ps of a 50 R line each); no compensation cut-outs needed.

## Placement (local origin = bridge centre, mirror axis y = 0, courtyards touching)
- X1 -> R201 10 R -> D201.3; D201 / D202 BAT15-04W side by side; rails meet at the 24.9 R pads; 47 pF C0G horizontal so the arms leave along the pad axis.
  1 k bias + 10 nF to VBIAS_A/K test pads. Arms: 45-degree chamfers, exact mirror images, R204 1 k on the arm pads at the balun.
- Hold: D202.3 -> U201.3 1.61 mm, C205 2.2 pF branch 1.18 mm. Guard (HOLD_FB, 0.1 mm) from U201 pin 4 under the body, between pins 2/3,
  around D202.3 / hold trace / C205.1 (between the C205 pads) to R208. Ground cut-out on In1/In2/B.Cu under the hold node, no top pour there.
- Supplies: U201 +2V5 pin -> 100 nF along the pad axis (0.6 mm copper), -2V5 pin -> via -> 100 nF on B.Cu under it; U202 +3V3 -> 100 nF (0.6 mm) -> In2 via;
  TRF37D73 VCC -> 1 nF + 100 nF in a row, via to In2.
- **Bias tee (revised, `sim/bias_tee/RESULT.md`, `bias_tee_detail.png` before/after)**: one straight chain perpendicular to the line,
  courtyards touching: FB402 BLM15HD102 with pad 1 centred ON the 50 R line (no stub; +32 fF, no In1 cut-out needed) -> 0.64 mm link
  -> L402 47 uH LQH32CN470K23L 1210 with R416 1 k 0402 beside it (two 45-degree links) -> C411 100 nF across the cold pad, GND via at
  its GND pad -> +3V3 plane via pair beyond C411 (supply enters through the capacitor) -> C412 10 uF on the via row.
  Was: bead 0.3 mm off the line on a 0.3 mm stub, plane vias at the inductor pad, 1 nF / 10 uF beside it on a polygon (-0.55 dB at 5.6 GHz).
  Ground pads: via right at the pad (not in it). U402 EP: 3 vias 0.2/0.45 in the EP (tented), GND pins tied to the EP.
- Strobe out, one straight line on y = -0.435: X2 -> C403 -> U402 TRF37D73 -> FB402 bias tee (bead pad centred on the line) -> C404 -> clip node
  -> T401 pin 1. **BAT15-03W clamp D203 added** (cathode on the clip node / stub tap, anode GND via), as `sim/phase_array/RESULT.md` asks.
- U202 level shifter below the K arm: R211 / C207 and C206 along the pad axes; the 1 k feedback R210 below, its OUT side via B.Cu.

## What changed (vs the JLC04161H-3313 version)
Stack-up 3313 -> 7628; RF width 0.17 -> 0.36 mm; full re-layout: compact courtyard-to-courtyard placement, only 45-degree bends,
wide/polygon supply connections, top pour with 2 w RF clearance, **no via stitching grid and no via fences** (to be added when the
fragments are assembled), clamp D203 added, stub re-computed (13.625 -> 13.207 mm), arms 17.26 -> 15.25 mm, board 31.5 x 22.8 -> 30.8 x 17.7 mm.
Vias left: 19 GND at pads/caps, 2 stub-short, 7 supply, 4 slow-signal (HOLD_OUT, SHIFT_OUT, -2V5 to B.Cu).

## Checks and limits
Script checks: courtyards (top and bottom) no overlap; copper clearance >= 0.1 mm; every bend <= 45 degrees; 0 unrouted after zone fill.
**kicad-cli 7 has no DRC**: run DRC in pcbnew after integration (net tie NT401 shorts the stub to GND on purpose).
Remaining deviations: R201 -> D201.3 is 3.12 mm (target <= 3 mm); BRG_IN passes 0.12 mm from the rail pads under D201; T-junctions at the
rail / R25 pads and at the stub tap / clamp; R210 and the D203 / C205 taps leave their pads sideways (short).
Open: balun pad map vs the Murata DLW21SN drawing; rail values follow the sampler RESULT (25 R / 47 pF); mask model is an estimate
(check with the JLC calculator at order time); integration must merge In2 (+3V3 here) with the board power split.
