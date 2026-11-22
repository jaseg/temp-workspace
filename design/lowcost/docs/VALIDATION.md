# Design validation (22 Nov 2026)

Independent validation of the six-layer board and its documents at commit `af4a1b9`. Eight reviewers each took one
area and wrote a note with method and evidence (`validation/<area>.md`, plots and crops beside them). Every high or
medium finding was then given to a second reviewer whose task was to refute it from the primary files; the severity
below is the one left after that check. Findings first rated low were not re-checked. Nothing in the design was
changed by the validation.

Result in one paragraph: no finding says the board cannot work and none is rated high. Seven medium findings remain;
one is a timing-plan error (the 960 Mbit/s serialiser needs a 480 MHz clock, above the 400 MHz PLL limit of the
GW1NZ-1), the others are layout or power items worth fixing before fabrication. Pinouts and footprints of all 66
non-passive parts match their datasheets.

## Medium findings (confirmed by the second reviewer)

### RF-1: Sampler balun 99 ps from the bridge on uncoupled arms; arms missing from the simulation
- Where: T401 (32.94, 11.30) -> STRB_A/K -> C201/C202 (19.96, 7.23 / 15.37), L1
- Evidence: Each arm is 16.75 mm long (99 ps), as two separate 50 R lines about 8 mm apart. gen_strobe.py lines 250-256 ask for the balun 'within 5 mm of the bridge; STRB_A/K a coupled 100 R pair'. sim/scope_sampler.py lines 62-78 (used by sim/strobe/bridge.py) put the lumped balun directly on the blocking caps, with no arm lines.
- Impact: The bridge end is high impedance while the diodes are off, and the balun end is about 25 R, then a short. The strobe residue therefore rings with a 198 ps round trip: a reverse pulse at +198 ps and a same-polarity pulse at +396 ps. Aperture, kick-out and efficiency have not been verified with this geometry; there is a risk of a second strobe or a wider aperture.
- Suggested fix: Re-run bridge.py with two 99 ps 50 R lines. If needed, move T401 and R204 next to C201/C202 as the schematic note requires.
- Second reviewer (confirmed): Reproduced: STRB_A 16.747 mm and STRB_K 17.512 mm, both single 0.16 mm L1 traces (about 50 R on the 0.0994 mm prepreg), 8.1 mm apart. T401 sits 13.5 mm from C201/C202, against the schematic's 'within 5 mm, coupled 100 R pair'. scope_sampler.py puts Lb1/Lb2 straight into cblk with no arm lines. The ~200 ps round-trip ringing has not been simulated.

### PDN-2: AMS1117: no dropout margin at USB minimum; 0.7-0.88 W on 61 mm2 of copper with 2 vias
- Where: U601; +3V3 B.Cu tab zone bbox 174.2-185.2 x 100.0-108.3 mm (60.9 mm2), 2 vias to L4; F601, FB601
- Evidence: At 0.86 A: 4.75 V - PTC (0.05-0.11 ohm) - FB601 0.045 ohm - 4 mOhm track = 4.61-4.66 V at U601.3, so headroom 1.31-1.36 V against 1.3 V max dropout (ds1117 EC table). P = (VIN-3.3) x 0.45 A = 0.70 W at 5.0 V, 0.88 W at 5.25 V. theta-JA 90 K/W gives Tj 88-104 C at 25 C ambient. gen_power.py:102 asks for >= 2 cm2 of copper.
- Impact: +3V3 in or near dropout with a low USB supply (PSRR lost, boost and USB ripple on the TRF37D73 and comparators); hot regulator, close to its 125 C limit in an enclosure
- Suggested fix: Use a low-dropout regulator, or put the 5 TRF37D73 (about 0.3 A) on their own regulator; enlarge the tab copper and add >= 8 vias to L4 and an L6 pour
- Second reviewer (partly): Thermal part confirmed: the B.Cu +3V3 tab zone fills 60.9 mm2 with 2 vias, against the >= 2 cm2 the schematic asks for. 0.7-0.88 W gives Tj about 90-105 C at 25 C ambient. Dropout part overstated: the 1.3 V maximum is specified at 0.8 A, and at 0.45 A it is lower, so 1.31 V of headroom at 4.75 V is marginal, not in dropout. The theory doc already lists AMS1117 dissipation as open.

### PDN-3: LM337 U607 with ceramic-only output caps and 2.49 V headroom (specified only from 3 V)
- Where: U607 (B.Cu 182.15, 116.7); C628 10u MLCC, C629 100n on -2V5; 10u on ADJ_N25
- Evidence: TI SLVS047L section 8: '1-uF solid tantalum or 10-uF aluminum electrolytic capacitor is required on the output pin for stability'; a bypassed ADJ raises the requirement. |VI-VO| = 4.99 - 2.50 = 2.49 V, and all EC parameters are given for |VI-VO| >= 3 V.
- Impact: Possible oscillation or poor regulation on -2V5, which sets TRIG_LEVEL, VBIAS and the TLV3801 VEE
- Suggested fix: Put a 10 uF tantalum, or 1 ohm in series with C628, at U607.3; check the XBLW clone's dropout at 50 mA, or use a ceramic-stable negative LDO
- Second reviewer (confirmed): SLVS047L verified: '1-uF solid tantalum or 10-uF aluminum electrolytic is required on the output pin for stability'. The -2V5 net has only C628 10u MLCC and 4x100n, and ADJ_N25 has a 10u bypass. |VI-VO| is about 2.49 V, below the 3 V the parameters are specified from. The part is an XBLW clone. The theory doc lists this as an open item ('LM337 stability with ceramics').

### PDN-4: LM27761 capacitors too small after DC-bias derating
- Where: U605 (188.85, 102.25 F.Cu): C620 2.2u 0402 (-5V_LDO), C623 1u 0402 (VIN), C619 4.7u 0603 (CPOUT)
- Evidence: C620 at 5 V is about 0.8-1 uF; SNVSA85D 7.2.2.5.4 'requires 2.2-uF ceramic output capacitor for stable operation', and FB603 isolates C621 behind it. C623 at 5.3 V is about 0.4 uF against 4.7 uF recommended (7.2.2.5.2); the next bulk, C612, is 24 mOhm / 4.2 nH away (extracted). C619 is about 2 uF, equal to the 2 uF anti-toggle minimum (7.2.2.5.1).
- Impact: Marginal LDO stability and larger 2 MHz ripple / PFM toggling on -5V (BUF802, LM337) and on +5V4F, which feeds LP5907/LP2985
- Suggested fix: C620 to 4.7-10 uF 0603/0805 16 V X7R; C623 to 4.7-10 uF 0603/0805; C619 to 10 uF 0805 10-16 V
- Second reviewer (partly): C620 (2.2u 0402, no voltage rating given) drops to about 1 uF at 5 V, below the 2.2 uF LDO-stability figure: this is the main issue. C623 (1u 0402 10 V) is far below the 4.7 uF recommendation, but the 2 uF minimum is stated for a 250 mA load and the load here is about 90 mA. C619 at about 2 uF effective meets the anti-toggle example exactly, so it is not a defect.

### DECOUPLING-1: BUF802 VSO- (U101.10) is decoupled only by the bottom-side C115
- Where: U101.10 (12.21, 11.80) L1; via (12.5, 12.05); C115 (13.25, 13.12) B
- Evidence: The copper path from pin 10 is 2.01 mm: 0.25 mm on L1, then a through via, then 0.4/0.6 mm on L6 to C115.1. The top-side C113 is reachable only through L3 (5.8 mm). Estimated loop is about 1.8 nH, against about 0.7 nH for C108, C109 and C112 at the other supply pins. BUF802 datasheet 8.4.1: put the bypass capacitors 'as close to the supply pins as possible and on the same side of the PCB as the BUF802'; 8.3 asks for individual capacitors on every supply pin.
- Impact: The output-stage supply sees 11-23 Ohm at 1-2 GHz. This can degrade output transient response and flatness, and couple output current into -5V.
- Suggested fix: Add a top-side 0402 (10n or 100n) at U101.10, between the pin and R112, with its GND pad on the L1 pour and a via to L2. Alternatively, connect C113 to pin 10 on L1. Keep C115 as a second capacitor.
- Second reviewer (confirmed): Pin 10 (-5V VSO-) runs 0.89 mm on L1 (not 0.25 mm), then a via at (113.0, 112.05), then about 1.1 mm on B.Cu to C115. There is no top-side cap at pin 10. C112 and C113 serve pins 5/6/8 on top. The BUF802 datasheet explicitly asks for individual caps per supply pin on the same side as the part. The ~1.8 nH, 11 R at 1 GHz estimate is plausible.

### DECOUPLING-3: TMUX136 (U301) VCC capacitor and switch-ground RF bypass are 3.6 mm and 8 mm from the part
- Where: U301 (8.9, 27.8); C301 (10.4, 24.48) B; C303 (14.4, 23.52) B; C302 (13.0, 23.52) B
- Evidence: VCC (pin 10) runs on a 0.3 mm L1 track to C301 on the bottom. The VSW_GND return goes from pin 5 over 0.15 mm stubs to the via (8.04, 27.8), then 4.5 mm on L6 at 0.3 mm. Estimated loop is about 3 nH, so the 100 nF resonates near 9 MHz. C303 (1 nF, VSW_GND to GND) carries the schematic note 'C0G, at U301.5' (gen_trigger_phase.py line 165) but sits 7.97 mm from U301.5. TMUX136 datasheet 9.3/9.4: bypass 'as close to VCC pin as possible'.
- Impact: The switch's internal capacitances return through 3-4 nH (about 20 Ohm at 1 GHz) to signal ground. This degrades trigger-path bandwidth, isolation and crosstalk between BUF_OUT_T and EXT_CLK.
- Suggested fix: Move C301 and C303 to the top side within 1 mm of pins 10 and 5. Replace the 0.15 mm VSW_GND stubs with a solid copper island under U301.
- Second reviewer (confirmed): Reproduced. VSW_GND leaves U301 over 0.15 mm stubs to a single via, then a 4.55 mm, 0.3 mm B.Cu run to C301 (+2V5 to VSW_GND), C302 and C303. C303, noted 'C0G, at U301.5', sits about 8 mm from pin 5. +2V5 reaches C301 over 3.0 mm of 0.3 mm L1 plus a via. The switch's ground is therefore poorly bypassed to signal GND.

### DECOUPLING-4: LM27761 (U605) input has only a 1 uF 0402 on the bottom side
- Where: U605 pins 1/6 (88.85, 2.25)/(90.75, 3.25); C623 (88.98, 1.50) B; via (87.85, 2.25)
- Evidence: C623 is 1u 0402 10 V X5R (BOM C52923). From pin 1 the path is 1.0 mm on L1 at 0.25 mm, a via, then L6 at 0.4 mm; pin 6 needs about 3 mm of L6. The next +5V4F capacitor (C615) is about 10 mm away. At 5.3 V the effective capacitance is about 0.4-0.5 uF (DC-bias estimate). LM27761 datasheet 7.2.2.5.2 recommends 4.7 uF, at least 2 uF effective, and its layout guideline says 'CIN on the top layer, as close as possible'.
- Impact: Charge-pump input ripple and spikes go onto +5V4F, which feeds the LP2985 (BUF802 +5V) and the LP5907 (+2V5 for the TLV3801 and TMUX136). Input droop can also affect charge-pump regulation.
- Suggested fix: Add a 4.7 uF 0603/0805 16 V capacitor on L1 between U605 pins 1/6 and pin 2, with short wide copper. Keep C623.
- Second reviewer (confirmed): Reproduced. From pin 1: 1.0 mm on L1, a via at (187.85, 102.25), then about 3.3 mm on B.Cu to C623 (1u 0402, C52923). Pin 6 needs about 6 mm. No other +5V4F cap lies within 12 mm. The LM27761 layout section says 'Place CIN on the top layer ... as close as possible'. This overlaps PDN-4 (the same C623 undersizing).

### THEORY-1: 960 Mbit/s serialiser clock exceeds GW1NZ-1 PLL limit
- Where: docs/theory-of-operation.md section 6 table; SPEC decision 17; U501 GW1NZ-LV1QN48C6/I5
- Evidence: OSER10 at 960 Mbit/s needs FCLK 480 MHz (PCLK 96 MHz x5, DDR) -> rPLL CLKOUT 480 MHz, VCO >= 960 MHz. DS841-2.8E table 3-20 (GW1NZ-1 LV C6/I5): VCO 400-800 MHz, CLKOUT max 400 MHz. Gearbox limit FMAXOSERx 1100 Mbps (table 3-16) is not the constraint. The COARSE IDES at 960 Mbit/s is affected in the same way.
- Impact: The documented synchronous time base cannot be built within spec. All derived numbers (48 MHz, 3.0 MHz, 1.04 ns bins) are affected.
- Suggested fix: Re-plan at 800 Mbit/s, e.g. 20 MHz FPGA_CLK/MCU_CLK x40, PH 40 MHz (20 bits), S 2.5 MHz (320 bits = 24 ADC clocks at 60 MHz, MCU 20 MHz x6 = 120 MHz). Only the clock and firmware change; then update the ToO and SPEC.
- Second reviewer (confirmed): UG289: f_PCLK = f_FCLK/5 for OSER10, so 960 Mbit/s needs FCLK 480 MHz. DS841-2.8E Table 3-20 (GW1NZ-1 LV C6/I5) gives CLKOUT max 400 MHz and VCO 400-800 MHz. ToO l.220 states '24 MHz x 40, OSER10 at 96 MHz'. Out of spec; this duplicates IO-1. The fix is clock and firmware only.
- Also reported as IO-1.

## Findings reduced to low by the second reviewer

Real, but smaller than first stated, already listed as open in the documents, or covered by calibration.

- **RF-2: Stub shorted ends add about 5 ps (stubs about 85 ps instead of 80 ps)** (NT401 (42.62, 17.635-18.635), NT402 (10.597, 33.25-34.25), NT403 (10.597, 40.75-41.75)). Geometry holds: TL401-403 are 13.503 mm long and end at NT pad 1, and GND is reached across the 1 mm tie plus a 0.3-0.6 mm track and a via. That is about 0.25-0.3 nH, or about 5 ps per end. But the stub delay was set with the old 6.05 ps/mm figure and is itself uncertain by a similar amount. The schematic treats the pulse width as a trim item, and the phase sim showed no difference between 150 and 250 ps FWHM. Fix: Put a GND via in or at NT pad 2 next to the stub end, or shorten each stub by about 0.85 mm. Make all three terminations alike.
- **RF-3: Tap spacing 30 ps as drawn vs 35 ps in SPEC; strobe terminations mismatched** (PSTRB_A/K, PH_LINE (Net-(D301-common)), R378/R379). The numbers (39.4 / 69.4 ps, 30 ps effective, 41.3 R into 49.9 R) are the design's own documented open points (board README items 4 and 124, theory section 375); I did not recompute them. The spacing is calibrated per tap anyway (the theory doc gives 31-44 ps). The impact is a window about 14% narrower (fewer hits per sweep), not a functional failure. A re-sim is still warranted. Fix: Re-run sim/phase_array with the six-layer section values, set the meander from the result, and fit 43 R terminations.
- **PDN-1: AMS1117 U601 output is all MLCC; the datasheet requires 22 uF tantalum for stability** (U601 pin 2 (+3V3), B.Cu at 175.85-182.15, 104.6; C604/C605 22u 0805, C606 100n, plus about 7x10u and about 30x100n on the L4 plane). Quote verified: '22uF solid tantalum ... will ensure stability'. The datasheet states no minimum ESR, though, and also says smaller capacitors work when ADJ is not bypassed (fixed 3.3 V has no ADJ cap). +3V3 is all MLCC (2x22u, 7x10u, 30x100n, 4x1n). Oscillation is a plausible risk, not a documented requirement violation. Cheap hedge: a 22 uF polymer cap. Fix: Add a 22-47 uF tantalum or polymer (ESR 0.1-1 ohm) at U601.2, or replace it with a ceramic-stable 1 A low-dropout LDO (also fixes PDN-2)
- **DECOUPLING-2: TLV3801 (U302) has a single 100 nF per rail, both on the bottom, with no low-value HF capacitor** (U302 pins 6/7 (+2V5) -> C305 (7.43, 29.3) B; pins 3/9 (-2V5) -> C307 (7.40, 31.74) B). Placement confirmed: C305 and C307 are single 100n caps on B.Cu, about 0.5-1 mm through a via, with nothing else within 5 mm. But a 100 pF cap in the same 0402 package has the same ESL, so the missing low value matters little. Only a top-side cap with a shorter loop would help. The datasheet wording ('a good combination would be') is a suggestion, not a requirement. Fix: Add 100 pF (or 1 nF C0G) 0201/0402 capacitors on L1 at pins 6/7 and at pin 3, each with its own L2 GND via, plus 1 uF per rail nearby.
- **BIASTEE-1: GVA-84+ drain voltage below 4.8 V minimum; tee DCR is the largest single drop** (U404/U406 tees: FB404/L404, FB406/L406 on VBUS; F601, FB601 upstream). The 4.8/5.0/5.2 V range and the 1.25 R max bead are verified. Reaching 4.73 V at a 5.00 V VBUS requires maximum DCR everywhere. With typical values (bead about 0.8 R, PTC about 0.07 R) Vd is about 4.8 V. sim/bias_tee/RESULT.md and the theory doc already flag the 0.15-0.18 V tee drop and Vd of about 4.6 V at 4.75 V USB as a known risk. Fix: Feed the GVA chokes from +5V4F (5.32 V boost rail), which gives about 5.15 V at the pin; recheck the MT3608 budget for +0.22 A. Second choice: a lower-DCR bead in these two tees.
- **ZONES-1: L3 GND webs under the tap row are unstitched and grounded only at their far ends** (L3 (In2.Cu), x 28-67 / y 34.6-41 (east part x 67-98); L finger x 31-57 / y 25-29.2; sliver x 35.5-56 / y 30.5). Reproduced on a refilled copy: L3 band max 23.2 mm, 135 mm2 over 5 mm; east 11.6; finger 22.6; sliver 24.8 mm. This breaks RULES.md. But the webs sit 0.109 mm above the solid L4 +3V3 plane on a slow-only layer, so the plane pair loads them heavily. Cell-to-cell coupling is claimed, not shown. Fix: Put one GND via in each 1 mm web between node windows (about x 30.9 + 4.514 n, y 37.5), or neck the VTAP tracks so stitching can get in. Otherwise keep L3 copper out of the band. Remove the 0.3 mm sliver and the L finger (raise the minimum width to 0.5 mm or add a keep-out).
- **ZONES-2: L6 GND fingers between tap-row lanes and single-via islands are longer than lambda/10** (L6: x 40-44 / y 25-41; x 58.2-61.7 / y 35-43; x 62.7-66.2 / y 36-42; x 80.8-84.4 / y 31-40; top-edge sliver x 35-59 / y 0.5-0.9. Single-via islands: L1 (0.5-6.6, 21.2-22.5), L1 (71.8-73.5, 46.3-51.8), L3 (6.0-6.9, 34.0-41.2), L3 (84.5-87.0, 17.3-25.9), L6 (17.5-22.2, 22.7-24.7)). Fingers reproduced: 19.3 / 16.2 / 15.7 / 13.2 mm, top sliver 28.5 mm. The islands are only 3-7 mm from their via, which is marginal. The lanes next to them (JTAG, RECONFIG) are static in operation. U311A+ to I2C_SCL is 0.39 mm c-c, but the run within 0.7 mm is about 3.5 mm, not 7.7 mm. SPI_SCK is 0.62 mm over about 3 mm. Fix: Add a GND via every 3-4 mm along each finger (2-4 mm wide, so there is room). Delete the 0.4 mm top-edge sliver. Add a second via at the far end of each single-via island. Consider a wider gap between U311A+ and I2C_SCL / SPI_SCK.
- **THEORY-2: Phase-detector figures belong to the simulated 35/70 ps line, not the built 39.4/69.4 ps one** (ToO lines 28, 30, 38, 54, 156-166, 200-203; layout/board/blocks/phase/README.md lines 46-55; sim/phase_array/RESULT.md section 2). Numbers hold (30 ps gives about 0.023 f, 10 k/s from about 430 kHz). The ToO already says this itself: section 3 text ('effective 30 ps, 39.4/69.4, not re-simulated') and open risk 3. What remains is that the summary table, the 560 ps window and the rates were not updated. Tap positions come from code-density calibration anyway. Fix: Re-run sim/phase_array/deck.py with the built parameters (62 R / 26.25 ps sections, 0.5 pF, pad loads, 49.9 R terminations, 69.4 ps signal). Update the table, section 1 diagram, window and rate figures from that run.
- **THEORY-4: 3.0 MS/s is a burst rate; SPI, SRAM, USB and CPU budget not addressed** (ToO sections 1, 5 (snapshot reduction), 6 (MCU)). The ToO says the MCU 'builds the equivalent-time record' on board. Raw samples are not streamed, so the SRAM-fill and USB 0.25 MS/s claims assume an architecture the document does not describe. SPI 48 of 60 Mbit/s fits. What is real: there is no firmware or data-flow budget, and 40 cycles per sample at 120 MHz is tight (open risk 7). Fix: Document burst length, duty and sustained rate. Pack or decimate records in the FPGA (send only valid stamps) and specify the processing as off-line.
- **THEORY-5: Strobe kick-out into the trigger is phase-locked to the strobe grid (systematic stamp error)** (ToO section 5 'Minimum signal levels', risk 4; R113 0 R position). The 19 mVpp comes from the sampler deck with an ideal strobe, and the final chain was not re-run at the trigger node. The kick is already open risk 4. The strobe-to-phase offset is swept and the signals are mostly asynchronous, so kick toggles are outliers rather than bias, except for commensurate signals. TLV3801 response to a 100 ps pulse was not simulated. Gating the S_STROBE-coincident phase strobe in firmware is trivial. Fix: Re-simulate the kick with the final chain. In the FPGA, discard stamps from the phase strobes coincident with S_STROBE, or fit the 100 R/ferrite at R113.
- **IO-2: TAP0-3, TAP8-11 and ADC_TRIG are on IOR6 pins without I/O logic** (U501 pins 28, 29, 30, 31, 14, 15, 16, 17, 18 (IOR6I/E/C/A/B/D/F/G/H)). Netlist pin functions confirm TAP0-3 on IOR6I/E/C/A, TAP8-11 on IOR6G/F/D/B and ADC_TRIG on IOR6H. DS841 and UG289 say IOR6 has no IO logic. But a 48 MHz capture into fabric FFs with a 10.8 ns valid window (strobe +10 to +20.8 ns) tolerates ns-level skew, and the latch point can move to mid-window. COARSE (IDES) is on IOR7A, so it is unaffected. Fix: Either constrain the fabric capture timing and let the per-tap calibration absorb the skew, or move the critical TAPs to non-IOR6 pins. The only free one is 23 (IOR8B); otherwise swap with SPI 20/22/24 or DBG2 8 and keep slow nets on IOR6.
- **PARTS-1: Input shunt resistors of the saturated pi pads run at or above the 0402 rating** (R402 82R (46.18,9.47); R408/R412 100R (15.27,30.53)/(15.27,44.47); also R404, R410, R414). Topology is confirmed (R402 82R shunt at the TRF output, 0402). But +/-2.3 V is a behavioural-model clip. The TRF37D73 OP1dB is 16.5 dBm (2.1 Vpk sine), and a real Psat of about 18 dBm gives a square of about +/-1.9 V, so R402 sees about 44 mW (70 % of 62.5 mW) and R408/R412 about 36 mW. Only marginal at 70 C ambient. Fix: Use 0603 (100 mW) or 0402 high-power parts (ERJ-PA2 type) for R402, R404, R408, R410, R412 and R414. Measure the TP401/TP403/TP405 swing on the first board.

## Low findings (not re-checked)

- **RF-4: R204 loads the two balun arms differently (arms not mirror images)** (R204 pad 1 (30.65, 10.865) / pad 2 (30.65, 11.885); STRB_K stub (30.65, 11.885-12.65)). Small differential/common-mode imbalance of the strobe at the bridge, adding to the pedestal and kick-out. Fix: Rotate R204 so that both pads sit in their lines symmetrically, or give both arms equal stubs.
- **RF-5: BUF_OUT_T runs close to PH_STROBE_P** (L1 y about 22.35 / 22.85 near the analog south edge). Deterministic, strobe-synchronous disturbance on the trigger path, about 2 ps. Fix: Increase the gap to at least 3 h edge with a stitched GND finger between, or reroute the pair.
- **RF-6: Pad-compensation cuts reference L5, not L3 as the README states** (For example R113.2 (13.8, 14.6), R204.1 (30.65, 10.865), T401.2 (32.1, 10.865)). The residuals are more negative than the tabulated -12 to -31 fF; under 1 % reflection at 2 GHz. Documentation / model correction. Fix: Correct the README table, or restore the L3 pour under the cuts as intended.
- **RF-7: S_STROBE_N pour gap 0.20 mm; +2V5 via antipad undercuts BUF_OUT_T** (S_STROBE_N near (56.40, 8.21); +2V5 via (9.32, 24.70) next to BUF_OUT_T x 8.79, y 24.38-24.99). Minor local impedance dips and coupling from a supply via. Fix: Open the pour; move the via 0.3 mm away.
- **PDN-5: +5V4F worst case 5.53 V exceeds the 5.5 V VIN max of the LM27761 and LP5907** (U603 MT3608 feedback R603 78.7k / R604 10k; +5V4F feeds U605 and U606). Out of the recommended operating range at worst-case tolerance (abs max 6 V not exceeded) Fix: Set -5V to about -4.8 V (R605 about 1.43M; the BUF802 needs >= 4.5 V) and the boost to about 5.15 V to centre both windows
- **PDN-6: -2V5 TLV3801 VEE and +5V BUF802 have only 100 nF locally behind 8.6-12 nH of track** (U302.3 with C307 only (107.79, 132.05); U101.1/12 with C108/C109 only; +2V5 U302.6/U301.10 behind 0.35 ohm / 28 nH). Marginal against a ~1 ohm target for comparator / buffer transients; supply noise couples into the trigger timing and the BUF802 Fix: Add 1-2.2 uF 0402 at U302.3 (beside C307), beside C108 at U101 +5V, and at U302.6 / U301.10
- **PDN-7: TRF37D73 VCC decoupling 1 nF + 10 uF with no near 100 nF: 3.4 ohm anti-resonance at about 146 MHz** (U401/U402 pin 1 (151.58/141.62, 111.36): C404/C409 1n at 1.4 mm, C402/C407 10u B.Cu at 2.5 mm; C403/C408 100n at 7.6 mm). Probably small, because most device current flows through the RFOUT bias tee Fix: Add a 100 nF 0402 next to C404/C409 if space allows
- **PDN-8: GVA-84+ supply shares VBUS with the MT3608 input, which probably pulse-skips** (VBUS: U603 pins 4/5 and L404/L406 pin 2 (GVA bias tees)). Strobe amplitude modulation, which reaches the sampler efficiency and pedestal Fix: Measure on the first build; if needed, add an RC/LC filter (for example 1 ohm + 47 uF) ahead of L404/L406
- **DECOUPLING-5: MS5351M VDDO capacitor C508 is on the bottom through a via; C509 GND via is 1.3 mm away** (U502.7 (64.90, 2.20) -> C508 (66.72, 1.95) B; C509 GND pad, nearest GND via 1.32 mm). Supply noise on VDDO adds jitter to FPGA_CLK and MCU_CLK. Fix: Move C508 to L1 next to pin 7, and add GND vias within 0.5 mm of the C508 and C509 GND pads.
- **DECOUPLING-6: FPGA capacitors C502 and C506 share one GND via; C505's GND via is 1.74 mm away** (GND via (59.55, 8.65) for C502 (+1V2, U501.37) and C506 (VCCX, U501.36); C505 GND pad (68.78, 7.40)). Each loop gains about 0.3-0.5 nH, and the shared via couples core and VCCX noise. This is minor at the FPGA's clock rates. Fix: Give each capacitor GND pad its own via.
- **DECOUPLING-7: U303 TRF37D73 pin 1 has only a bottom-side 100 nF (C309), unlike the other four TRF37D73** (U303.1 (10.05, 37.00); C309 (10.05, 36.2) B). Small: pin 1 is the DC bias pin, and the main current flows through the choke, which is decoupled (C313 at 1.32 mm). Fix: Add 1 nF 0402 on L1 at pin 1, as on U401-U405.
- **DECOUPLING-8: USBLC6-2SC6 (U608) VBUS pin has no local capacitor** (U608.5 (88.14, 13.50); nearest capacitor C601 22u B at 6.76 mm). The clamp's VBUS reference is inductive during ESD events, so clamping is less effective. Fix: Add a 100 nF 0402 next to pin 5.
- **BIASTEE-2: Tee cold-cap assignment differs from the schematic; U401/U402 VCC pins lack 100 nF** (C432/C433 at (118.48,128.97)/(118.48,146.03) B; C403/C408 at the L401/L402 cold pads; U401/U402 pin 1 (151.58/141.62, 111.37)). Breaks RESULT.md rule 3 ('TRF VCC pin keeps its own 1 nF + 100 nF'). Documentation and BOM refs no longer match intent; there is a mid-frequency decoupling gap at the U401/U402 VCC pins. Fix: Place C432/C433 at the U401/U402 VCC pins, or update the schematic and RESULT.md to the as-built assignment; add a 1 nF at U303 pin 1.
- **BIASTEE-3: As-built tee node parasitics are 2-4x the simulated values (47-50 MHz dip -0.47 dB; 4-7 GHz notches)** (Hot node bead-choke: U303 (2 vias into L302 B), U403/U405 and U404/U406 (1 via into B choke, plus TP on 2.6 mm of B track), U401/U402 (L401 1210 on F plus TP via)). Small loss at the 48 MHz phase fundamental and possible narrow notches in the TRF band. Above 3 GHz the bead model is extrapolated, so the notches are uncertain. Fix: Use via pairs at L403/L405/L404/L406 and update RESULT.md with the 6-layer parasitics. Measure S21 on the first board; if a notch shows, apply the planned 47 R + 22 pF cold-pad damper.
- **BIASTEE-4: GVA tee cold ends are inconsistent and decoupled only by 1 nF locally** (L404 cold pad (124.10,125.73) B; L406 cold pad (124.10,149.27) B; C419/C420, C429/C430). Choke ripple returns through long VBUS copper. The effect is minor because the GVA tees sit behind the shorted stub; the documentation is wrong. Fix: Place C419/C429 at the cold pads with their own GND vias, give L404 the same via pair as L406, and correct the pstrobe README.
- **BIASTEE-5: Line-driver bead FB301 and C311 pads uncompensated (no L2 cut), unlike the other six tees** (FB301 pad 1 (113.08,137.50) and C311 pad 1, F.Cu over L2 GND). A small return-loss degradation on the 3 Gbps line driver output; an inconsistency with the pstrobe rule. Fix: Apply the same L2/L3 cut under FB301.1/C311.1, or record it as accepted.
- **BIASTEE-6: Open 0.2 mm vias inside choke pads (solder wicking) without a POFV fab note** (L302 pad 2 (vias 113.08,139.10/139.70, B); L403/L405/L404/L406 pad 1 centre vias; TP401/TP402 vias overlapping L401/L402 pad 1 by 0.16 mm (F)). Solder may wick into the holes and starve the choke joints. This is an assembly-yield risk on 7 tees. Fix: Specify resin-plugged, capped vias (POFV) for the order, or move the vias 0.3 mm off the pads with a short track.
- **ZONES-3: Merged via antipads form 4-5 mm slots in L2/L5 under the FPGA fan-out** (L2+L5: diagonal row (63.6-67.8, 4.8-8.2); column (67.8-69.6, 8.2-12.3); cluster (69.6-73.9, 20.8-23.7); mcuif row (76.8-81.2, 47.9-49.3)). All affected nets are MHz-class, so the SI effect is small. The slots raise loop inductance and emissions, and grow with any larger antipad. Fix: Space or stagger the fan-out vias to at least 0.95 mm pitch, or reduce the plane clearance on those vias, so that a 0.15 mm web of L2 / L5 survives between them.
- **ZONES-4: Most fast-net layer transitions have no GND via within 1 mm, including S_STROBE_N at 3.16 mm** (S_STROBE_N vias (56.4, 11.86) and (56.4, 7.8); U501 fan-out (68.2-68.75, 9.46-11.86); TAP vias (70-72, 21.25-21.9), (28.98, 23.92), (75.39, 27.0); U502 CLK1 (63.85, 3.2)). The return current has to move from L5 to L2 up to 3-4 mm away, which adds loop inductance at each transition. This matters most for S_STROBE_N (the complement of the sampler strobe pair) and the comparator TAP edges. The SPI / I2C cases are benign. Fix: Add a GND via within 0.7 mm of each S_STROBE_N via and of the TAP output vias. In the FPGA fan-out, move or add GND vias next to the signal via groups.
- **THEORY-6: Sampler and input simulations use smaller node parasitics than built** (layout/board/blocks/analog/README.md line 44; sim/input/input_stage.py lines 47, 84, 95; ToO key-figures table). Input C '2.0 pF', S11 -3.4 dB at 2 GHz and 1.7 GHz unterminated bandwidth are optimistic. The HF ratio shifts about 1.5 %, which is within the trim range. Fix: Re-run the input and sampler decks with the as-built node capacitances and quote those figures.
- **THEORY-7: Deconvolution noise factor and key-figure noise refer to the wrong case** (ToO section 3 last paragraph; key figures 'Noise'). The noise figure is misstated (pessimistic for the final strobe chain). Fix: State which strobe case the noise refers to and correct the factor.
- **THEORY-8: Stale or inconsistent text in ToO, kicad/README and SPEC** (ToO lines 135, 160-164, 180-181, 280, section 10; kicad/README lines 106, 128, 250-252, 261; SPEC decisions 4 and 9). Misleads bring-up and review. Fix: Update the listed lines to the six-layer, 3.0 MHz, as-built state.
- **IO-3: CLK2_FPGA is on a pin that is not a clock pin** (U501 pin 34 (IOR3B), net /fpga_clock/CLK2_FPGA via R510). The spare / beat-mode clock reaches the clock tree through general routing, with extra jitter and skew. Fix: Swap TAP6 (47) and CLK2_FPGA (34), after checking the L6 fan-out.
- **IO-4: UCPD dead-battery Rd on PB6 can pull FPGA_DONE to about 1.7 V when PA9 is high** (U704 PB6 (pin 43, UCPD1_CC1, FT_c) on FPGA_DONE with R502 4.7k; PA9 (pin 31, UCPD1_DBCC1) = HOST_TX). The MCU reads FPGA_DONE as low, and an external low on DONE delays the FPGA wake-up (UG842 DONE definition). This applies until firmware sets DBDIS, and also in the ST system bootloader. Fix: Set UCPD_DBDIS before enabling USART1. Otherwise move FPGA_DONE to a non-UCPD spare such as PB10 or PB15, and document the PA9/PA10 gating in the README.
- **IO-5: Independent OSER10 + IODELAY on both pins of each strobe pair is unproven** (U501 pins 35/38 (IOT17B/A) and 39/40 (IOT16B/A); IDES10 on 27). If placement fails, the complementary strobes or the fine-delay sweep would need a re-pin. Fix: Run a short Gowin EDA place-and-route (OSER10 + IODELAY on 35/38/39/40, IDES10 on 27, plain inputs on the IOR6 pins) before ordering.
- **IO-6: Out-of-date pin references for DBG2 and the ADC_TRIG function** (kicad/README.md J501 table; kicad/gen/gen_fpga_clock.py l.137 and l.165; README MCU table PB11 vs theory l.228). Confuses firmware and bring-up. Fix: Correct the DBG2 text. Specify PB11 as TIM2_CH4 (AF1) and trigger ADC1/2 from TIM2_TRGO (OC4REF); verify the EXTSEL code in RM0440.
- **PARTS-2: Stage-1 TRF37D73 input is 0.4-1.4 dB from its 10 dBm abs max, depending on FPGA drive** (R401/R407/R411 47R, U401/U403/U405 RFIN). At high drive-strength settings the stage-1 input sits at or slightly above its abs max. Fix: Set DRIVE=8 mA for the strobe pins, or use 100 R series resistors (6.5 dBm, still 2.6x the saturation drive).
- **PARTS-3: T401 uses the Coilcraft 0805USB land, which is outside Murata DLW21SN land limits** (T401 pads (32.105/33.775, 10.865/11.735)). Assembly yield risk (shorts between lines or a rotated part). Electrical mapping is correct. Fix: Make a DLW21SN footprint (0.8x0.4 pads on a 1.8x0.8 centre grid) or trim the pads to 0.4 mm width.
- **PARTS-4: BAT15-04W bridge diodes can exceed VR = 4 V at the top of the VBIAS_K DAC range** (D201 common->K diode (D201.3 on the input via R201; K node = VBIAS_K)). Reverse breakdown or leakage at DAC extremes or in overload; possible errors in the held value. Fix: Clamp VBIAS_K to about 1.5 V in firmware, or rescale R735/R736.
- **PARTS-5: TMUX136 A1 goes 0.3 V below its abs max during input overload** (U301 (8.04,27.80) pin 1 BUF_OUT_T via R112 49.9R + R113 0R). Clamp-diode conduction pulls VSW_GND (964 R Thevenin) down during overload. Damage is unlikely. Fix: Document it, or set CLL to about -1.1 V if the full +/-1.5 V overload range is not needed.
- **PARTS-6: LM337 -2V5 runs at its 2.5 V minimum differential; the PDN-5 fix (-5V to -4.8 V) would push it to 2.3 V** (U607, R607/R608 120/120, -5V from U605). Lower rejection of the LM27761 2 MHz ripple on -2V5 (TLV3801 VEE, VNEG_REF, U201). Fix: Choose the -5 V and -2V5 set-points together: -2.4 V (R608 110 R), or a low-dropout negative LDO (for example TPS7A30).
- **PARTS-7: Y501 is a 12 pF crystal but the MS5351M is set for 8 pF load** (Y501 (C9006) / U502). Estimated +20..+30 ppm frequency offset, i.e. a time-base scale error. Fix: Set XTAL_CL = 10 pF and correct the README, or buy an 8 pF crystal.
- **PARTS-8: Tap comparator inputs go slightly below the COS3502 common-mode range** (U305-U312 +IN (tap nodes), VTH1/VTH2). Possible recovery or delay skew after low inputs. Logic is correct because VTH > 0. Fix: Accept, or offset VTAP_P/N slightly positive together with VTAP_TH.
- **PARTS-9: DNP and footprint-only status exists only in the schematic and BOM, not on the board** (D402 (25.52,32.90), D403 (25.52,42.10), R122 (6.11,25.99), J501 (42.0,53.2); D602 value). A board-derived CPL/BOM would place DNP parts and order a connector that should not be fitted. Fix: Set exclude-from-pos/BOM on these footprints or filter them in the assembly export. Change the D602 value to B5819W.

## Checked and found correct

### RF layout (`validation/rf.md`)
The L1 RF geometry is mostly built as designed. My own finite-difference solver gives 49-50 R for the 0.16 mm lines (boardlib: 50.2 R), and the effect of the pour gap actually present is negligible. L2 is continuous under every RF track except the intended cuts. The 16 delay-line cells are identical, A and K strobe paths are equal, and the three stubs are 13.503 mm each. Main risks:
- The sampler balun sits 99 ps from the bridge on uncoupled arms; the schematic note asks for within 5 mm and the bridge simulation has no arms at all.
- The stub shorted ends add about 5 ps each.
- The tap spacing as drawn is 30 ps, against 35 ps in SPEC.
- Smaller items: the asymmetric R204 stub, BUF_OUT_T crosstalk from PH_STROBE_P, and a pad-cut reference that differs from the README.
Note: design/lowcost/docs/validation/rf.md

- 50 R 0.16 mm: FD 49-50 R vs boardlib 50.2 R; eps_eff within 1-3 %
- 0.10 mm strobe / PH_LINE lines 62-63 R; pour-gap coplanar effect <= 1.2 R
- Pour gap >= 2w on all L1 RF nets except S_STROBE_N
- L2 continuous under all RF tracks except intended pad cuts, windows and antipads; no RF over a plane split
- No vias in critical RF paths; no bends >45 deg outside pads and tees
- PH_LINE 16 cells x 9.707 mm identical; launch 10.087 mm (0.16) + 2.600 mm (0.10); far end 1.849 mm
- PSTRB_A = PSTRB_K = 71.934 mm (0.10) + 5.877 mm (0.16), mirror images
- Hold-node copper identical in all 16 tap cells
- TL401/402/403 stubs 13.503 mm each
- Bridge rails 4 x 2.565 mm, mirror-symmetric about y 11.30
- STRB_A / STRB_K 16.747 / 16.748 mm
- PH_STROBE_P/N FPGA pin -> TRF pin 2 equal (64.569 + 30.512 mm each, 2 vias each with GND vias)
- Sampler chain RFIN / RFOUT segments equal (1.08 / 2.02 mm)

### PDN impedance (`validation/pdn.md`)
I built the PDN model from the board itself. pcbnew extracted each rail's tracks, vias and refilled zones, and I solved R and L from each regulator pin to each load pin. A numpy |Z|(f) model (derated MLCC, the +3V3 L4 plane at 1.4 nF) shows every load at or under about 1 ohm up to 100 MHz. The weakest points are -2V5 at TLV3801 VEE (1.0 ohm at 5 MHz, only C307 locally) and the BUF802 +5V (0.48 ohm, 100 nF only). DC IR drops are small; +2V5 on its 147 mm, 0.35 ohm track drops about 9 mV. The main risks are the regulators. AMS1117 and LM337 have all-ceramic outputs where their datasheets ask for tantalum. AMS1117 has no dropout margin at 4.75 V USB, runs at 0.7-0.88 W on 61 mm2 of copper with 2 vias, and the LM27761 capacitors are too small after DC-bias derating. Note: docs/validation/pdn.md.

- Extracted R/L from regulator to load on every minor rail (+2V5 351 mOhm / 28 nH to U302; +5V 140 mOhm / 12 nH to the BUF802; -5V 145 mOhm / 15 nH; -2V5 62 mOhm / 8.6 nH; +1V2 20 mOhm / 2.4 nH)
- +3V3 L4 plane: 4710 mm2 in one island; 15-70 mOhm up to 20 MHz at the FPGA, TRF37D73 and MCU
- IR drop: +2V5 at TLV3801 about 9 mV, leaving VCC-GND >= 2.44 V (2.4 V min); +/-5V to the BUF802 about 5 mV each
- Load budget: +3V3 about 0.43 A typ / 0.52 A max; VBUS about 0.86 A, within the PTC hold; the docs say 6 TRF37D73 but the board has 5
- AP2112, LP5907, LP2985 output capacitance meets stability after derating
- LM27761 headroom and 250 mA rating OK (about 85 mA); LM337 min-load divider 10.4 mA OK; LDO dissipations of AP2112/LP5907/LM337 small
- GVA-84+ 2.2 uH bias tees isolate the GVA RF current from VBUS, so the 121 MHz VBUS peak is not seen by the amplifiers
- VREFP 64 mm of 0.15 mm track (0.23 ohm) carries only mA divider loads: OK
- Minor-rail track R damps the 100 nF / track-L resonances (Q < 1 on +2V5)

### Decoupling capacitor placement (`validation/decoupling.md`)
I measured 65 supply pins on 34 ICs (pcbnew copper-path extraction on a zone-refilled copy of the board). 59 pins have their closest capacitor within 2 mm of copper path. In 16 cases the closest capacitor is on the bottom side, which gives about 1.6 to 2 nH of loop inductance against about 0.7 to 0.9 nH for a top-side 0402. The L4 plane adds only about 1.4 nF, so every IC depends on its local capacitor above about 20 MHz.

Four medium issues:
- The BUF802 output-stage negative supply (VSO-) is decoupled only on the bottom.
- The TLV3801 has a single 100 nF per rail, both on the bottom, with no 100 pF or 10 nF.
- The TMUX136 VCC capacitor and the switch-ground RF bypass sit 3.6 mm and 8 mm from the part.
- The LM27761 input has only a 1 uF 0402 on the bottom.

The rest are low. Note: docs/validation/decoupling.md, with plots decoupling-*.png next to it.

- Every one of the 65 supply pins has a capacitor on its own net to GND (the TMUX136 one goes to VSW_GND by design)
- COS3502 x8: 100n on the top side at 1.30 mm copper path, 0.5 mm track, GND via 0.62-0.91 mm
- TRF37D73 U401/U402/U403/U405: 1n on the top side at 0.97-1.56 mm, plus 100n and 10u; choke cold ends each have 100n within 1.4 mm
- BUF802 VS+, VSO+ and VS- each have their own top-side 100n at 1.1-1.4 mm (VSO- does not, see DEC-1)
- STM32G474: 4x100n plus 10u on VDD/VBAT; VDDA has FB701 + 1u + 10n; VREF+ has 1u + 100n (about 0.7 uF effective, inside the VREFBUF 0.5-1.5 uF range)
- GW1NZ: 100n on all 5 VCC/VCCIO/VCCX pins at 1.1-2.4 mm, plus 10u on +1V2 and on +3V3
- Feed order: C504, C501, C509 and C628 sit between the plane via and the pin; no HF capacitor is fed only through the L4 plane
- No supply track narrower than 0.2 mm (0.25 mm or more outside the FPGA fan-out)
- LDO in/out capacitors (AP2112, LP2985, LP5907, LM337, AMS1117) are within 1.6-2.9 mm, with bulk capacitance nearby
- OPA197, TPH2501, TLV9001 and SN65LVDS2 decoupling is adequate for their bandwidths
- GVA-84+ have no supply pin; the VBUS choke cold end has 1n at 1.32 mm with its GND via in the pad

### Bias tees (`validation/biastee.md`)
I traced all seven bias tees (5x TRF37D73, 2x GVA-84+) on the board and re-simulated them with the as-built 6-layer parasitics. Parts match the schematic and RESULT.md. Every bead pad sits on the 50 R line with no stub. Worst-case TRF pin voltage is 3.04 V, so it meets 3.0 V but only just. The hot node between bead and choke is 1.5-3.4 pF against the 0.8 pF simulated. This pushes the 47-50 MHz dip to -0.40..-0.47 dB and adds narrow notches at 4-7 GHz (-1 to -2.9 dB), but the time-domain effect is negligible. The main issue: GVA-84+ drain is 4.50-4.79 V, below its 4.8 V minimum, and the tee's 1.41 R is the largest single drop. Feeding the GVA chokes from +5V4F would fix it. The rest are cap-assignment, consistency and fab items. Note: docs/validation/biastee.md

- All 7 beads BLM15HD102SN1D, 5 TRF chokes LQH32CN470K23L 1210 with 1k across (R382, R415-R418), 2 GVA chokes LQM21PN2R2MGHL 0805: netlist = generator = board
- Bead pad 1 centred on the 0.16 mm (50.2 R) trace in all 7 tees: stub length 0 mm
- L2/L3/L4 cut under bead pad 1 in the 6 pstrobe/analog tees (as stated in pstrobe README)
- Through vias 0.45/0.2 mm, 1.54 mm, antipad radius 0.45 mm on L2..L5, no stubs; ~1.36 nH single
- Cold caps have their own GND via 0.62-0.65 mm away; +3V3 via pairs at or beyond the cold cap connect to the filled L4 zone
- TRF pin DC: 65 mA x 2.94 R max = 0.19 V -> 3.04 V worst at AMS1117 3.235 V min (meets 3.0 V)
- Current ratings: TRF bead 65/250 mA, LQH32CN 65/170 mA; GVA bead 130/250 mA, LQM21PN 130 mA vs 450 mA Isat
- Time domain as built vs RESULT model: sampler 3.0 MHz step 4.44 vs 4.45 V; stub pulse 2.51 V; phase 48 MHz launch 3.60 V; line driver PRBS7 3 Gbps DDJ 1.09 vs 1.19 ps rms; 1 MHz droop identical
- Bead DC-bias derating (x0.65 GVA) changes the phase launch peak only 0.8 %
- U403/U405, U401/U402 and U404/U406 pairs are exact mirror/translation copies (identical track lengths)

### Zone splits and return paths (`validation/zones.md`)
I refilled a copy of the board and checked every zone. L2 and L5 GND are each one polygon, as is the L4 +3V3 plane (no edge strip, no tracks, no neck under 0.3 mm). Every L1 RF sample without L2 under it is an intended pad cut, a node or SMA window, or the net's own via antipad, and no RF net crosses a slot. The boost and charge-pump switch nodes sit over solid L2 and L5, 26.8 mm from the nearest slow line.

Main problems:
- The L3 GND webs between the tap-row node windows have no stitching: up to 24 mm from a GND via.
- L6 GND fingers between tap-row lanes are grounded at one end only (13-19 mm).
- Merged via antipads form 4-5 mm slots under MHz digital nets in the FPGA fan-out.
- 50 of 72 fast signal vias have no GND via within 1 mm, including S_STROBE_N at 3.16 mm.

Note: docs/validation/zones.md plus 3 crops (zones-*.png).

- Zone table on refilled copy: L2 GND 4999.9 mm2 / 1 piece, L5 GND 5206.9 mm2 / 1 piece, L4 +3V3 4710.5 mm2 / 1 piece (no other net, 0 tracks on L4)
- L4 +3V3 plane: no +5V edge strip, no neck under 0.3 mm (a 0.3 mm opening leaves no orphan piece)
- Under all 116 L2 windows, L3 and L4 are empty and L5 is GND (9/9 sample points each); no via of any net lies inside an L2 window
- L1 RF nets (strobes, PSTRB, STRB, delay line, BUF_OUT, EXT_CLK, front chain, TAP8/9 hop, USB) sampled every 0.25 mm at centre and +/-w, 2w, 3.5w: every miss is a deliberate pad cut, node/SMA window or own-via antipad; worst detours 0.53-0.54 mm (U401/U402 RFOUT, STRB_A)
- PH_STROBE_P/_N: GND via within 1 mm at all 4 layer transitions
- SW_BOOST copper (MT3608/L601/D602) and LM27761 flying-cap loop: 100 % / 98.9 % solid L2 and L5 under them, L3 GND below; nearest slow / bias line 26.8 mm away; analog block at least 22 mm away
- L3 slow bias lines: no L4 plane edge to cross (L4 has none)
- L2/L5 single pieces: no isolated plane islands; small single-via L3 islands (<0.6 mm2) are just via annular rings

### Theory of operation (`validation/theory.md`)
Most of the theory of operation checks out. I recomputed the control-voltage networks, hold-chain levels, correction formula, strobe and reverse-pulse timing, ADC window, minimum trigger level, power budget and every FPGA/MCU pin in its tables against the netlist, and all of these hold. The main problems: (1) the 960 Mbit/s serialiser needs FCLK 480 MHz, but the GW1NZ-1 C6 PLL tops out at 400 MHz (DS841 table 3-20). (2) The phase-detector figures (34.7 ps spacing, 560 ps window, stamp rates) come from the simulated 35/70 ps line, not the built 30 ps one, and the simulation does not itself support the 'line minus strobe delay' rule. (3) The GVA-84+ supply is below its 4.8 V minimum even on a nominal 5.0 V USB supply. (4) 3.0 MS/s is a burst rate. (5) Strobe kick-out is phase-locked to the strobe grid. Some figures and text are stale. Note: docs/validation/theory.md.

- TRIG_LEVEL network 0.2424 Vdac - 0.139x2.5 V, -0.300..+0.306 V, 0.172 mV/LSB
- VBIAS_A -1.46..-0.50 V, 0.273 mV/LSB; VBIAS_K = Vdac; VTAP_TH Vdac/31 6.5-87 mV
- VNEG_REF -1.973 V, ADC_REF_MID 0.725 V, VOFS 0.580-0.402 Vdac
- TMUX136 local GND -0.893 V, SEL +1.23 / -0.89 V
- Hold chain G=3, 0.415-2.485 V at PA0
- Efficiency correction x=(v_k-0.31v_k-1)/0.476 consistent with RESULT
- Bit 1.0417 ns, PH 20.83 ns, S 333.3 ns, reverse pulses +10.42 / +166.7 ns
- ADC 19 of 20 cycles, window 40-148.3 ns ends 18.3 ns before reverse pulse; variant 175.4 vs 208.3 ns
- PH reverse pulse reaches COS3502 output >=14.9 ns, after +12 ns latch
- COS3502 CM range and Vos compatible with sum-node levels
- Min trigger 200 mVpp tip -> +/-20 mV at TLV3801
- Stamp-rate arithmetic consistent for a 560 ps window
- All ToO FPGA and MCU pin assignments and J501 pinout match netlist
- Strobe/line pads, chokes, terminations, readout values, DNP clamps D402/D403, fitted D401 polarity, R122 DNP
- Power budget 0.83-0.95 A total consistent with 0.85-0.9 A

### FPGA and MCU I/O assignment (`validation/io.md`)
I checked every pin of U501 and U704 against Gowin UG842/DS841/UG289 and DS12288 Rev 3 (pin table, AFs, VREFBUF, injection tables), plus the ST pin XML and the HAL OPAMP header. Pin names and numbers, supplies, straps, clock pins, strobe pairs, AF assignments, reset-state injection and J501 are correct. Two medium issues: 960 Mbit/s needs a 480 MHz FCLK, but the GW1NZ-1 rPLL tops out at 400 MHz (use 768 Mbit/s). Nine permuted inputs (TAP0-3, TAP8-11, ADC_TRIG) are on IOR6 pins, which have no I/O logic on the GW1NZ-1. Low issues: CLK2 is on a pin that is not a clock pin, the UCPD dead-battery Rd can hold FPGA_DONE near 1.7 V, the serialiser placement on both pins of each pair is unproven, and some pin references in the docs are stale. Note: design/lowcost/docs/validation/io.md.

- U501 all 48 pins + EPAD match UG842 QN48 names/numbers
- FPGA supplies: VCC 12/37 +1V2 (1.07-1.26 V), VCCX 36 / VCCIO0 1 / VCCIO1 25 +3V3, VSS 2/26/EPAD GND
- MODE0/1 4.7k to GND, MODE2 internally GND -> mode 000 AUTO BOOT; RECONFIG_N/DONE/READY/JTAGSEL_N 4.7k pull-ups, TCK 4.7k pull-down; JTAG pins not reused
- FPGA_CLK on 33 GCLKT_2/RPLL_T_in, 24 MHz within CLKIN 3-400 MHz
- COARSE on 27 IOR7A/GCLKT_3 has IO logic (IDES possible)
- Strobe pairs 39/40 (IOT16B/A) and 38/35 (IOT17A/B) are true/comp pairs in bank 0 with IO logic; IODELAY 0.5 ns + 30 ps x 0..127
- All TAP/user nets on 3.3 V banks; COS3502, SN65LVDS2, MS5351M, STM32 levels compatible (3.3 V LVCMOS)
- Dual-purpose SSPI/MSPI pins unused in AUTO BOOT (need 'as regular IO' options)
- U704 symbol numbers match DS12288 LQFP48 column and ST XML
- PA0 ADC1/2_IN1; PA4/PA5 DAC1_OUT1/2; PA6 DAC2_OUT1; PA2 OPAMP1_VOUT / PB1 OPAMP3_VOUT with internal DAC3_CH1/CH2 VINP
- SPI1 PB3/4/5 AF5; I2C1 PA15/PB7 AF4; USART1 PA9/PA10; USB PA11/12; SWD PA13/14; NRST 100 nF; PB11 TIM2_CH4 AF1 + ADC12_EXTI11
- BOOT0 PB8 10k down + jumper; no negative injection on PB8
- HSE bypass PF0 24 MHz <= 48 MHz, VHSEH 0.7 VDD met
- VREFBUF 2.9 V: CL 1.1 uF in 0.5-1.5 uF, load 0.27 mA, VDDA >= 3.135 V met with 0.1 V margin
- Reset-state pins: PA1 -0.17 V, PA4 about -0.35 V / 16 uA, PA6 0.17 mA injection: within TT_a -5 mA / total 25 mA
- J501 pinout and pad geometry identical to the sensing-board J3

### Pinouts, footprints and ratings (`validation/parts.md`)
Checked all 66 non-passive parts. Every pin in the netlist matches its datasheet, including the parts flagged for review: BUF802, TMUX136, TLV3801, COS3502 (correct COS3502 pinout, not TLV3502), GW1NZ QN48 (all 48 pins), LM27761, and the XBLW LM337 SOT-223 (1 ADJ, 2 VIN/tab, 3 VOUT). The T401 DLW21SN pad map on the 0805USB footprint was open; it is now closed: topology and polarity are correct. The land patterns for DSG0008A, RSE0010A, RGT0016C and Gowin QN48 match. Main new issue (medium): the input shunt resistors of the saturated pi pads run at 53-65 mW against the 62.5 mW rating of an 0402. The low findings are: TRF stage-1 drive near its abs-max, T401 land outside Murata's limits, BAT15 VR at the VBIAS_K extreme, TMUX136 overload below its abs-max, LM337 headroom, crystal CL mismatch, COS3502 common-mode margin, and DNP status missing on the board. Note: docs/validation/parts.md.

- BUF802 RGT pinout, CL-mode strapping, EP isolated->GND, CLH/CLL +/-1.5 V within mid-supply..rail
- TRF37D73 DSG pinout (NC to GND, PWDN to GND), EP; DSG0008A EP 0.9x1.6 land
- GVA-84+ SOT-89 pins 1 IN / 3 OUT+DC / 2 tab GND; input 10.6 dBm < 13 dBm; pin-3 DC < 5.8 V
- TRF #2 input 8.4 dBm < 10 dBm abs max
- TMUX136 pinout and RSE0010A land (board pads match exactly); VCC-local GND 3.39 V; SEL levels 2.12/0 V local
- TLV3801 pinout, EP to VEE; VCC-VEE 5.0 V <= 5.5; VCC-GND 2.5 V >= 2.4
- SN65LVDS2 DBV pinout
- COS3502 SOP-8 pinout (OUTA pin 7 = even TAP, OUTB pin 6 = odd TAP)
- GW1NZ-LV1 QN48: 48/48 pins vs UG842, EPAD GND, land vs UG843 Fig 4-18
- MS5351M MSOP-10 and 3225 crystal pin map
- STM32G474CBT6 LQFP48 power/VREF/NRST/BOOT0 pins
- AMS1117, AP2112K, MT3608 (5.32 V), LP2985, LP5907, LM27761 (-4.985 V), USBLC6 pinouts
- XBLW LM337 SOT-223 pinout (datasheet fetched) and 10.4 mA min load
- T401 DLW21SN on 0805USB footprint: windings 1-2 / 4-3 with dots on the same end; balun polarity correct
- Op-amp supplies: TLV9001, TPH2501, OPA197 within ratings
- BLM15HD102 / LQH32CN470 / LQM21PN2R2 / B5819W current and voltage ratings
- 47 R series, dummy-load and PSTRB termination dissipation < 20 mW
