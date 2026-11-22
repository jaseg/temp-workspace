# RF layout validation (key: rf)

Board: layout/board/scope-fe.kicad_pcb, loaded with pcbnew 7. Zones were refilled in a scratch copy.
Coordinates are board mm (pcb coordinates minus 100, 100). Scripts are in scratchpad/val/rf/: dump.py, ana.py
(pour gap and L2/L5 under each track sample), walk.py (path lengths), cells.py, stub.py, par.py and nbr.py
(coupling), fd.py (2-D finite-difference quasi-static solver).

## Method
- Impedance: my own FD Laplace solver. Cross-section: 0.0994 mm, er 4.1; t 35 um; solder mask er 3.8, 15 um on the
  copper and 25 um on the substrate; optional coplanar ground at gap g. Grid 2.5 and 1.25 um, Richardson
  extrapolation. Results are compared with boardlib.microstrip.
- Every F.Cu / B.Cu segment of the RF nets was sampled every 0.1 mm for three things: the edge gap to the filled
  F.Cu GND; whether the L2 (or L5) GND fill is under the centre and at +/-(w/2 + 0.1 / 0.3); and what lies on L3 / L4.
- Path lengths were walked node by node. Tap-cell copper was compared cell by cell against cell 0. Parallel runs
  with an edge gap under 0.45-0.6 mm were listed for every RF net.

## Checked and found as designed (verified)
- 50 R width 0.16 mm: FD gives 50.8 R (2.5 um grid) and 49.8 R (1.25 um), so about 49-50 R extrapolated;
  boardlib gives 50.2 R. eps_eff from FD is 3.04-3.11, against 3.155 in boardlib: 1-3 % less delay (80 ps
  stub -> 78-80 ps). The 0.10 mm line is 62-63 R (boardlib 62.0).
- Coplanar effect of the pour gap actually present: 0.16 mm with g 0.32-0.35 mm gives -0.1 R; 0.10 mm with
  g 0.20 mm (PSTRB, 242 samples) gives -1.2 R. Negligible.
- Pour gap >= 2w on every L1 RF net: BUF_OUT_T, BUF_OUT_S, STRB_A/K, bridge, S_STROBE_P, PH_STROBE, EXT_CLK,
  CMP, RFIN/RFOUT and the stubs (minimum 0.32-0.35 mm). Exception: S_STROBE_N (RF-7).
- L2 is under every RF track along its whole length, except the intended pad-compensation cuts, the SMA and node
  windows, and via antipads. L4 (+3V3) lies under L2 throughout. No RF net crosses a plane split.
- No vias in the critical RF paths. No bend over 45 deg except the T junctions at the stub tees and the line
  leaving the tap pads.
- PH_LINE: 16 cells of 9.707 mm each (walked, spread 0.001 mm). Launch: 10.087 mm at 0.16 mm, then 2.600 mm at
  0.10 mm. Far end D316.3 -> R377: 1.849 mm.
- PSTRB_A and PSTRB_K: 4.224 + 15 x 4.514 = 71.934 mm at 0.10 mm each, plus 5.877 mm at 0.16 mm each.
  Identical, true mirrors about y 37.5.
- Hold-node copper (pads and track lengths, 3.803 mm A / K) is identical in all 16 cells.
- Stubs TL401 / TL402 / TL403: 13.503 mm each (footprint copper). TL402 and TL403 are mirror images.
- Sampler bridge: the 4 rails are 2.565 mm each, mirror-symmetric about y 11.30. C201 / C202 sit at +/-4.07 mm.
  R201 -> D201.3 is 3.12 mm and BUF802 OUT -> R201 is 2.947 mm.
- STRB_A and STRB_K, C20x.1 -> T401: 16.747 / 16.748 mm.
- PH_STROBE_P / _N, FPGA pin -> TRF pin 2: the outside parts are 64.569 / 64.569 mm, and the pstrobe parts are
  30.512 / 30.512 mm. Both have 2 vias, each with a GND via beside it.
- Sampler-chain RFIN / RFOUT 1.08 / 2.02 mm for both TRFs.
- PSTRB lines and VTAP_N/P: 12.8 mm parallel at 0.31 mm. Effect on delay is under 0.1 ps.

## Findings
RF-1 (medium, likely): the sampler strobe arms are 99 ps long and are not modelled.
- Layout: T401 sits at (32.94, 11.30). STRB_A and STRB_K run 16.75 mm each (99 ps) to C201 / C202. They are two
  separate 50 R lines about 8 mm apart.
- gen_strobe.py lines 250-256 ask for the balun "within 5 mm of the bridge; STRB_A/K a coupled 100 R pair".
- The deck behind every sampler number (sim/scope_sampler.py lines 62-78, used by sim/strobe/bridge.py) puts the
  lumped balun straight onto the 1 nF blocking caps, with no arm lines.
- What happens on the board: the bridge end is high impedance while the diodes are off. The balun end is about
  25 R, then a short once the stub reflection returns. The residue of the strobe therefore rings with a 198 ps
  round trip: a reverse pulse at +198 ps and a same-polarity pulse at +396 ps.
- Aperture, kick-out and efficiency have not been simulated with this geometry.
- Fix: re-run bridge.py with two 99 ps 50 R lines between the balun and the caps. If the ringing re-strobes or
  widens the aperture, move T401 / R204 next to C201 / C202.

RF-2 (medium, likely): the shorted ends of the stubs are about 5 ps electrically long.
- TL401 / TL402 / TL403 end at the centre of NT pad 1.
- The current then crosses the 1.0 x 0.5 mm net-tie bridge, then 0.4 mm tracks to the GND vias:
  - NT401: 0.76 mm to (41.92 / 43.32, 18.935);
  - NT402: 0.64 mm to (10.597, 32.61);
  - NT403: 0.64 mm to (10.597, 42.39).
- Estimate: about 0.14 + 0.10 + 0.03 nH = 0.27 nH, which is L/Z0 = +5 ps. The stubs are therefore about 85 ps, and
  the strobe pulses about 170 ps instead of 160 ps (aperture about +6 %).
- NT401 pad 1 also has an L2 cut (rule area 42.37-42.87, 17.39-17.89); NT402 / NT403 have none.
- Fix: put a GND via in NT pad 2 (or in the pad 1 end), or shorten each stub by about 0.85 mm. Treat the three
  stubs alike.

RF-3 (low, verified): R204 (1 k across the balun) loads the two arms differently.
- Pad 1 at (30.65, 10.865) sits on the STRB_A line.
- Pad 2 at (30.65, 11.885) hangs on a 0.765 mm stub off STRB_K at y 12.65: about 4.5 ps and about 0.1 pF with
  the pad.
- With T401's diagonal pads 2 / 4 at (32.105, 10.865) / (33.775, 11.735), the arms are equal in length but not
  mirror images (rule 5).
- Fix: rotate R204 so that both pads sit in the lines symmetrically, or give both arms the same stub.

RF-4 (medium, verified): the tap spacing misses SPEC by 14 %.
- As drawn, the strobe is 39.40 ps per tap and the signal 69.40 ps per tap, an effective 30.0 ps.
- SPEC.md item 4 says 35 ps; the window is 480 ps instead of 560 ps.
- The loaded strobe line is 41.3 R into 49.9 R terminations R378 / R379 (Gamma +0.094).
- The array was simulated only for 35 / 70 ps. The sim bias of the lumped model (signal 75.7 ps simulated vs 70 ps
  designed, theory section 5) could move the real spacing anywhere from about 30 to 36 ps.
- Fix: re-run sim/phase_array with the 6-layer section values (62 R 0.10 mm, 26.25 / 56.46 ps unloaded), then
  set the meander. Fit 43 R terminations.

RF-5 (low, verified): BUF_OUT_T runs close to PH_STROBE_P.
- Parallel run: 5.06 mm at a 0.34 mm edge gap (0.50 mm centre to centre = 5 h, no pour between), along
  y about 22.35 / 22.85.
- Estimated backward crosstalk: about 1 % saturated, about 0.2 % for 300 ps edges, i.e. about 7 mV at the
  unterminated TMUX136 end.
- This is a deterministic, strobe-synchronous trigger disturbance of about 2 ps.
- S_STROBE_P / PH_STROBE_P: 3.1 mm at 0.24 mm.
- Fix: spread to 3 h edge gap with a stitched pour finger, or move the pair.

RF-6 (low, verified): the pad-cut reference does not match the README.
- Under the compensated pads, L3 and L4 are cleared as well, so the pads see L5 at 1.35 mm, not L3 at 0.665 mm
  as analog/README says. Examples: R113.2 (13.8, 14.6), R204.1, T401.2 (32.1, 10.865).
- The residual will be more negative than the -12 to -31 fF tabulated. Effect is under 1 % reflection at 2 GHz;
  this is a documentation / model correction.

RF-7 (low, verified): two local clearance faults.
- S_STROBE_N pour gap is 0.20 mm (< 2w) over 33 samples near (56.40, 8.21).
- The +2V5 via at (9.32, 24.70) has an L2 antipad reaching within about 0.03 mm of the BUF_OUT_T edge over
  y 24.38-24.99 (x 8.79).
- Fix: open the pour and move the via 0.3 mm.

## Not checked / out of scope
- USB is full speed (12 Mbit/s), so impedance is irrelevant.
- The bias-tee details and the T401 pad map against the Murata drawing (already an open point) belong to other keys.
