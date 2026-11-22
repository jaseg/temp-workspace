# Validation: bias tees (5x TRF37D73, 2x GVA-84+) as built

Validator key `biastee`. This is validation only: no design file was changed. Scratch work, scripts and logs are in
`/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/val/biastee/`. The simulations are copies of
`sim/bias_tee`, `sim/strobe` and `sim/phase` in `sim/`, plus `asb.py`, `asb_ac.py`, `asb_sens.py` and `asb_tran.py`. Plots:
`biastee-layout.png` (L1/L6 geometry of three tee types), `biastee-ac.png` (|Z| and S21, as built against RESULT.md) and
`biastee-tran.png`.

## Method
- Geometry comes from `layout/board/scope-fe.kicad_pcb` through pcbnew: pads, tracks, vias and zones. A copy was refilled
  with ZONE_FILLER and used for the antipad and plane checks. Connectivity was cross-checked against `kicad/export/scope-fe.net`
  and `kicad/gen/gen_strobe.py:381-407`.
- Pad and track capacitance uses the generators' microstrip formula, re-evaluated for the 6-layer stack (L1 to L2 and L6 to L5
  at 0.0994 mm, er 4.1). It is scaled by the fraction of each pad that lies over GND.
- Via inductance uses 0.2 h (ln(4h/d) + 1) with h = 1.54 mm and d = 0.2 mm, giving 1.36 nH. Via capacitance is about
  0.3 pF (0.45 mm pad, 0.9 mm antipad on four inner layers; an estimate).
- The as-built tee subcircuits are in `asb.py`. They were run through the unchanged `ac.py` and `tran.py` machinery:
  - Bead: Murata S2P Foster fit, extrapolated above 3 GHz.
  - Waveforms: 3.0 MHz sampler square, 48 MHz phase square into the 80 ps stub, 3 Gbps PRBS7 and 1 MHz on the line driver.

## The seven tees as built (board coordinates in mm)
| tee | bead (F.Cu, pad 1 on line) | choke / 1 k | hot-node vias | test pad on hot node | cold-end cap, supply |
|---|---|---|---|---|---|
| U303 line drv | FB301 (113.08,137.50), straight line, **no L2 cut** | L302 1210 **B** (pad 2 at 113.08,138.70), R382 B | **2** through (113.08,139.10/139.70), inside L302 pad 2 | none | C313 100n B at 1.32 mm; 2 +3V3 vias to L4 |
| U401 / U402 sampler | FB401 (148.56,110.87) / FB402 (138.60,110.87), L2/L3/L4 cut | L401 / L402 1210 **F**, R415 / R416 F | 1, only to TP401 / TP402 (overlaps the L401 pad by 0.16 mm) | TP401 / TP402 1 mm, B | **C403 / C408** F at 1.34 mm; 2 vias to L4 beyond the cap |
| U403 / U405 phase TRF | FB403 (114.31,129.40) / FB405 (114.31,145.60) at the 90-degree corner of the line, L2 cut | L403 / L405 1210 **B**, R417 / R418 B | **1** (114.31,127.60 / 147.40), at the centre of the L pad | TP403 / TP405 B, 2.59 mm of 0.4 mm track | C434 + **C432** / C435 + **C433** B; 2 vias to L4 |
| U404 / U406 GVA | FB404 (124.10,129.40) / FB406 (124.10,145.60), corner, L2 cut | L404 / L406 0805 **B**, no R | **1** at the centre of the L pad | TP404 / TP406 B | **C418 / C428 1 nF only**. L404: no via, 1.5 mm B.Cu VBUS track. L406: 2 vias to a 1.5 mm L3 VBUS track |

## Checked and found correct
- **Parts and values.** All 7 beads are BLM15HD102SN1D. All 5 TRF chokes are LQH32CN470K23L 47 uH 1210 with a 1 k 0402
  across them (R382, R415-R418). Both GVA chokes are LQM21PN2R2MGHL 0805. Netlist, generator and board agree.
- **Bead on the line.** Every bead pad 1 centre lies on the 0.16 mm RF trace centreline (50.2 R on this stack), so the stub
  length is 0 mm in all seven. U403/U405/U404/U406 put the pad at the line's 90-degree corner, where the pad itself is the
  corner. The six pstrobe and analog tees have L2/L3/L4 cleared under bead pad 1, as `blocks/pstrobe/README.md` states
  (-19 fF).
- **Vias.** Through vias are 0.45 / 0.2 mm, 1.54 mm long. Each has a 0.45 mm radius antipad (0.225 mm clearance) on L2 GND,
  L3 GND pour, L4 +3V3 and L5 GND, with no stub.
- **Cold-end caps.** Every 100 nF / 1 nF cold cap has its own GND via 0.62-0.65 mm from its pad. The +3V3 plane vias are on
  or beyond the cold cap and connect to the filled L4 +3V3 zone.
- **TRF DC.** The worst case is 65 mA x (1.25 bead DCR max + 1.69 choke max) = 0.19 V. With AMS1117 at 3.235 V min, the pin
  sees 3.04 V, at least 3.0 V (TRF37D73 datasheet, Recommended Operating Conditions). This is marginal but meets.
- **Current ratings.** TRF bead at 65/250 mA and choke at 65/170 mA. GVA bead at 130/250 mA and LQM21PN at 130 mA against
  450 mA Isat.
- **Bead DC bias.** Applying the RESULT.md derating (x0.65 GVA, x0.85 TRF) to the as-built tees changes the stub-launch peak
  by 0.8 % (3.599 -> 3.571 V).
- **Time domain.** As built and the RESULT.md "corrected" model behave alike:
  - Sampler, 3.0 MHz into 50 R: step 4.44 vs 4.45 V. Ringing is 48 vs 20 mV pp.
  - Sampler into the stub: 2.51 V either way. FWHM is 229 vs 243 ps.
  - Phase chain, 48 MHz: launch peak 3.60 V either way. The tail is 7 vs 4 mV.
  - Line driver: DDJ 1.09 vs 1.19 ps rms; 1 MHz droop 0.281 -> 0.223 V, the same.

## Findings
**BT-1 (medium, verified numbers / likely conclusion): the GVA-84+ drain is below its 4.8 V minimum. The tee's own drop is the
largest single term.**
- **The tee's drop.** The bead DCR (1.25 R max, Murata datasheet table) plus the LQM21PN DCR (0.16 R max) is 1.41 R. At
  108-130 mA that drops 0.15-0.18 V.
- **Upstream drops.** The PTC F601 (1206L150THWR) is about 0.05-0.1 R (assumed typical, not verified) and the ferrite FB601 is
  0.045 R max. Both carry 0.85 A, which costs about 0.08-0.12 V. The VBUS copper costs under 0.01 V.
- **Resulting Vd.** With VBUS at 5.00 V, Vd is 4.73-4.79 V. With VBUS at 4.75 V (USB minimum), Vd is about 4.50 V. The
  GVA-84+ datasheet table gives 4.8 / 5.0 / 5.2 V, with Id changing 0.058 mA/mV.
- **Fix.** Feed the two GVA chokes from +5V4F (5.32 V, MT3608 boost) instead of VBUS. The pin would then see about 5.15 V. The
  boost budget must be rechecked for +0.22 A. Second choice: a lower-DCR bead in these two tees.
- `docs/theory-of-operation.md` item 8 already notes the supply side. This finding quantifies the tee's share.

**BT-2 (low, verified): six of seven tees do not match their schematic decoupling assignment.**
- `gen_strobe.py:396` assigns the tees' own 100 nF as C432 (U401), C433 (U402), C434 (U403) and C435 (U405).
- On the board, C432 and C433 sit at the L403 / L405 cold ends as second caps (B, 118.48,128.97 / 118.48,146.03).
- L401 / L402 use C403 / C408 instead (`gen_analog.py:725,747`).
- Result: the U401 / U402 VCC pins 1 have no 100 nF within 4 mm, only C404 / C409 1 nF at 1.45 mm and a 10 uF on B at 2.45 mm.
  This breaks RESULT.md rule 3 ("TRF VCC pin keeps its own 1 nF + 100 nF").
- U303 pin 1 has only C309 100n within 4 mm, with no 1 nF.
- Fix: move C432 / C433 to the U401 / U402 VCC pins, or update the schematic and RESULT.md to the as-built assignment.

**BT-3 (low, verified geometry / modelled effect): the as-built node parasitics are 2-4x those simulated in RESULT.md.**
- **Pad capacitance.** At 0.0994 mm a 1210 pad is 1.31 pF (RESULT.md: 0.70) and a 0402 pad is 0.178 pF (0.104).
- **Hot node** (between bead and choke): U303 2.46 pF, U401 2.1 pF + TP 0.48 pF behind the 1.36 nH via, U403 3.4 pF,
  U404 1.5 pF. RESULT.md assumed 0.80 pF.
- **Sources.** The B-side chokes behind a single via, the 1 mm test pads (0.44 pF) and 2.6 mm of B track (U403/U405).
- **Effect in 1 MHz-3 GHz.** The worst S21 is -0.40 to -0.47 dB at 47-50 MHz (-0.51 with the bead derated), against the
  -0.3 dB criterion and RESULT's -0.28. The 48 MHz phase fundamental sits in this dip.
- **Effect at 4.2-6.8 GHz.** Narrow node resonances, model-sensitive because the bead is extrapolated there:
  - U403 -2.1 dB at 5.8 GHz.
  - U404 -1.0 dB at 4.2 GHz (stub stage -0.95 dB).
  - U303 -2.9 dB at 6.8 GHz.
  - With a via pair at U403 the dip is -0.49 dB; with no TP it is -0.86 dB.
- **Time-domain effect:** negligible (see above).
- Fix: none needed for function. Use via pairs at L403/L405/L404/L406 and update RESULT.md to the as-built parasitics.
  Measure S21 on the first board; if the notch is real, apply the 47 R + 22 pF cold-pad damper.

**BT-4 (low, verified): the GVA cold ends are inconsistent and decoupled only by 1 nF.**
- The L404 cold pad (124.10,125.73, B) has no via. It is fed by a 1.5 mm B.Cu VBUS track to the L3 VBUS zone at x 132-134.
- L406 has a via pair (122.78,147.955/148.655) to a 1.5 mm L3 VBUS track.
- The 100 nF / 10 uF (C419/C420, C429/C430) sit about 45 mm (L404) and 15-25 mm (L406) away along the copper. RESULT.md
  specifies 1 nF / 100 nF / 10 uF at the cold end.
- `blocks/pstrobe/README.md` says "VBUS L4 via pair at 1 nF", but L4 is +3V3 and L404 has no via.
- Effect is small, because the GVA chokes sit behind the shorted stub.
- Fix: put C419 / C429 at the cold pads with a GND via each, and correct the README.

**BT-5 (low, verified): the line-driver bead pad FB301 is not compensated.**
- L2 is solid under FB301 pad 1 (100 % GND) and under C311 pad 1. The other six tees have the cut.
- Excess capacitance is +0.108 pF per pad. The as-built U303 S11 is -15.8 dB, against -21.7 dB with the cut.
- 3 Gbps DDJ is unaffected (1.09 ps rms).
- Fix: apply the pstrobe L2 cut rule for consistency, or record it as accepted.

**BT-6 (low, verified): there are open vias inside the choke pads.**
- Two vias sit inside L302 pad 2 on B.
- One via sits at the centre of L403/L405/L404/L406 pad 1.
- TP401/TP402 vias overlap the L401/L402 pad 1 on F by 0.16 mm.
- Without plugged and capped vias (POFV) the 0.2 mm holes wick solder from the choke joints. No fab note in RULES.md asks for
  POFV.
- Fix: order POFV, or offset the vias 0.3 mm off the pad with a short track.
