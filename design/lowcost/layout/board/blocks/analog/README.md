# ANALOG block (input stage + sampler + sampler strobe chain), 56.0 x 21.5 mm at board (0, 1), rot 0
`python3 gen_analog.py` -> `analog.kicad_pcb`, `analog.ifaces.json`, `analog.png`, `analog_detail.png` (balun / stub / TRF #2 / pad).
check_board (102 refs): 0 missing / extra / footprint / value / pad-net / no-net, 0 clearance, 0 corners > 45 deg, 0 RF width, 0 RF gap.
Unrouted only the plane-fed supplies +5V, -5V, +2V5, -2V5, +3V3 (via pairs to In2, the integrator draws In2). 33 off-axis pad exits are left (short 45-degree escapes in the input fragment). kicad-cli 7 has no DRC / ERC.
Geometry: input fragment at block (0, 4.0) (SMA 4.4 mm from the M3 hole centre), bridge centre at (19.84, 10.30), chain on y 9.865.
## Interfaces (block-local mm)
| net | x, y | layer / side | note |
|---|---|---|---|
| /S_STROBE_P, /S_STROBE_N | 56, 9.865 / 10.865 | F.Cu E, 0.36 | FLOORPLAN 8.5 / 9.5: both 1.37 mm lower (strobe line axis); P above N kept |
| /BUF_OUT_T | 15.75, 21.5 | F.Cu S, 0.36 | 0.45 mm right of FLOORPLAN 15.3 (RV101 clearance), now on the S boundary |
| /VOFS, /VBIAS_A, /VBIAS_K, /ADC_IN, /ADC_REF_MID | x 5.9, 15.24, 16.24, 18.9, 21.49; y 21.5 | B.Cu S, 0.2 | VOFS outside the 20-35 window |
| +5V, -5V, +2V5, -2V5, +3V3 | via pairs | In2 | see FLOORPLAN partition |
## RF lengths (0.36 mm, 50 R, F.Cu over In1, no vias; 6.057 ps/mm)
| segment | mm | ps |
|---|---|---|
| SMA pad end -> Ctop pad 1 | 0.89 | 5.4 |
| BUF802 OUT -> R201 10 R pad 1 (<= 3 mm) | 2.79 | 16.9 |
| R201 -> D201.3; rails (4 x, mirror) | 3.12; 2.565 | 18.9; 15.5 |
| STRB_A / STRB_K arms (C201/C202 -> T401) | 16.747 / 16.747 | 101.4, mismatch 0 |
| TL401 shorted stub (tap -> NT401) | 13.207 | 80.0 |
| BUF_OUT_T (R113 -> S boundary) | 9.10 | 55.1 |
| S_STROBE_P edge -> R401 / TRF1 in, pad, TRF1 out, TRF2 out -> clip | 1.51 / 1.08+1.01+1.01+2.02 / 2.02+2.97 | |
## Deviations
- T401 uses the netlist land (Coilcraft 0805USB, 1/4 | 2/3): clip pin 1 and STRB_A pin 2 as in the fragment, but GND (3) and STRB_K (4) swap ends.
  The K arm passes under T401 to pin 4; the arms are mirror images up to x = XV, then differ; the A arm carries a 45-degree bump (h 1.73 mm) so both are 16.747 mm.
- Added to this block (strobe sheet, membership() puts them in pstrobe): C402/C403/C404 (U401) and C407/C408/C409 (U402) decoupling.
  Per sim/bias_tee: 100 nF (C403/C408) at the choke cold pad + plane via pair beyond it; VCC pin: 1 nF + via pair + 10 uF on B.Cu (no second 100 nF in the netlist).
- J102 / R122 (input sheet) left to the phase block (FLOORPLAN). Fragment J2, J3, X1, X2, TP205-207 dropped (not netlist parts).
- TP201-TP204, TP401/TP402, bulk C111/C116, C110/C114/C115, C209 on B.Cu. Single +2V5 / -2V5 vias at the clamp resistors and U201 -2V5.
- Block contains In1 / F.Cu / B.Cu GND zones with the fragment cut-outs (SMA In1 cut, low-C cut at the divider, hold-node cut). merge(skip_planes=True) would lose the In1 cuts.
- Local helpers: Frame.place (boardlib Block.place side="B" flips before Add and segfaults in pcbnew 7.0.11: placed on F, flipped after Add); render() crop offset (SVG origin = board bbox incl. the SMA body, 10 mm left of the block).
## Open points
- Balun pin map: check the Murata DLW21SN drawing; with this land winding 2 is grounded at the arm end (reversed vs the fragment balun). Fix in the schematic/footprint, not here.
- R201 -> D201.3 3.12 mm (> 3 mm, as in the fragment). Integrator: GND stitching, In2 partition, BUF_OUT_T and the S_STROBE pair routing.
