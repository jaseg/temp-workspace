# Layout fragment: sampler (bridge, hold amp, level shifter, sampler-strobe output)
`python3 gen_sampler.py` -> `sampler.kicad_pcb` (KiCad 7, 31.5 x 22.8 mm, own Edge.Cuts) + delay table + checks.
`sampler.png`: top = F.Cu/silk/fab, bottom = B.Cu. Values from `sim/sampler/RESULT.md` and `sim/strobe/RESULT.md`.

## Stack-up (SPEC decision 9, written into the board setup)
JLC04161H-3313, 1.6 mm: L1 35 um / 3313 prepreg 0.0994 mm (er 4.1) / L2 In1 = solid GND / core 1.265 mm /
L3 In2 = +3V3 plane / 3313 0.0994 mm / L4 B.Cu (GND pour + slow feeds).
50 R microstrip on L1 (Hammerstad-Jensen, Wheeler thickness correction, no mask): exact 0.172 mm,
drawn **0.17 mm -> 50.4 R, eps_eff 3.10, 5.87 ps/mm**. Solder mask takes ~1-2 R off (still within tolerance).
Hold node 0.15 mm, guard 0.12 mm, bias/control 0.2 mm, supplies 0.3 mm. Clearance >= 0.1 mm; top GND pour 0.3 mm (3h) clear.

## Placement (local origin = bridge centre, mirror axis y = 0)
- X1 (BUF_OUT_S, = BUF802 OUT pin) -> R201 10 R -> D201 pin 3. The trace runs **between D201 pins 1/2 under
  the body**. Planar routing needs this: the two series pairs have the same handedness, so one
  external lead has to enter the rail loop.
- D201/D202 (BAT15-04W) side by side with the same orientation. Rails BRG_A (pins 1) and BRG_K (pins 2) are exact mirror images.
  Each joins at x = -1.0, then goes to 24.9 R -> node (1 k bias to VBIAS_A/K, 10 nF) -> 47 pF C0G -> STRB_A/K.
- T401 balun (0805 CMC) on the axis right of the hold amp, R204 1 k across its outputs. The STRB_A and
  STRB_K arms run around the hold cluster as mirror images: **17.257 mm each (101.3 ps), mismatch 0**.
- Hold node: D202.3 -> U201.3 (TPH2501, G = +3: R207 1.00 k, R208 499) 1.66 mm. C205 2.2 pF branch 1.2 mm.
  The **ground cut-out** (In1, In2, B.Cu) is 2.95 x 1.9 mm under D202.3/trace/U201.3/C205.1, with no top pour near.
  **Guard ring** = U201 -IN net (HOLD_FB, which sits at the hold voltage). It runs between U201 pins 2/3, under D202 and between the C205 pads.
  -IN goes from R207 under the U201 body. U201 OUT drops to B.Cu (outside the cut-out) to the level shifter.
- U202 (TPH2501 on +3V3) inverting 1 k / 1 k, +IN = ADC_REF_MID (10 nF), R211 33 R + C207 220 pF -> ADC_IN.
- Strobe out: X2 (TRF2_IN, from the 12 dB pad) -> C403 100 nF -> U402 TRF37D73 (WSON-8 DSG) -> bias tee
  FB402 bead + L402 47 uH (1210) to +3V3 -> C404 100 nF -> clip node -> T401 pin 1.
  **Shorted stub** from the clip node: 13.625 mm = **80.0 ps**, ends in NT401 (net tie) + 3 GND vias.
  U402 EP: 3 in-pad vias 0.2/0.4 mm (filled/tented), GND pins tied to the EP. VCC pin: 1 nF + 100 nF + via to In2.
- 126 GND vias: stitching both sides of every RF line (about 1 mm pitch, 0.64 mm from the centreline) plus a grid.

## Interface points (silk-labelled)
| Point | Net | Connects to |
|---|---|---|
| X1 (left) | BUF_OUT_S | BUF802 OUT pin (input fragment); place the BUF802 so X1 is its pin, bridge 5 mm away |
| X2 (right) | TRF2_IN | 12 dB pi pad output of the TRF37D73 #1 chain (strobe fragment / user board) |
| TP201 / TP202 | VBIAS_A / VBIAS_K | TP2272 bias buffers (DAC) |
| TP203 / TP204 | -2V5 / +2V5 | hold-amp rails (B.Cu feeds to 100 nF at the pins) |
| TP205 / TP206 | ADC_IN / ADC_REF_MID | MCU PA0 / reference divider |
| TP401, TP207/TP402 | +3V3 (also In2), GND | power |

## Checks and limits
Script checks: no courtyard overlaps, no track/via/pad pair closer than 0.1 mm (pcbnew shape collisions). Result: OK.
Zones are filled by the script. **kicad-cli 7 has no DRC**: run DRC in pcbnew after integration.
Not done: S_STROBE input chain (TRF #1, 12 dB pad, 47 R, dummy load). Integration also has to merge In2 (+3V3 here)
with the board's power split, and connect the B.Cu feeds.
Open points: R201 -> D201.3 is 3.29 mm centre to centre (2.7 mm pad edge to pad edge); the target was <= 3 mm.
Check the balun pad map against the Murata DLW21SN drawing (custom pads: 1/3 input end, 2/4 output end, as in the schematic pins).
The rail values follow the sampler RESULT (25 R / 47 pF), not the strobe RESULT (10 R / 1 nF).
