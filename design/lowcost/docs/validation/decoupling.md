# Validation: decoupling capacitor placement (key `decoupling`)

Validator run 22 Nov 2026. Validation only: no design file was changed. Scripts and data are in
`/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/val/decoupling/`:
`ext.py` (pin-to-capacitor extraction, output in `pins.json` / `summ.txt`), `feed.py` (pin-to-plane feed via),
`choke.py` (bias-tee cold ends), `share.py` (shared vias) and `plot.py` (crops).
Board coordinates are in mm from the top-left corner (pcbnew minus 100/100). Layers: L1 = F.Cu, L6 = B.Cu.

## Method
- pcbnew on a zone-refilled copy of `scope-fe.kicad_pcb`: for every IC pad on a supply net (+3V3, +1V2, +/-2V5, +/-5V, VBUS,
  VDDA, VREFP, +5V4F, CPOUT, -5V_LDO, BP_5V), every capacitor from that net to GND; Dijkstra copper path pin pad -> cap pad over
  same-net tracks / vias / pads / filled-zone islands (zone hop = straight line); track widths, vias, GND vias within 4 mm of
  the cap GND pad, feed-via order. Crops `decoupling-*.png` looked at. Datasheets: BUF802 8.4.1, TLV3801 SNOSDD7C 8.3/8.4,
  TRF37D73 SLASE43 9/10, TMUX136 SCDS367E 9.3/9.4, LM27761 7.2.2.5 + layout, Si5351 7.1, COS3502, kicad/README (STM32, GW1NZ).
- **Loop model** (L1 track over L2 at 0.0994 mm: L' about 0.30 / 0.26 / 0.23 / 0.17 nH/mm for w 0.2 / 0.25 / 0.3 / 0.5 mm;
  0402 body 0.4 nH; through via pair L1-L5/L6, h 1.3-1.5 mm, s 0.8 mm: (mu0 h / pi) ln(s/r) about 1.1 nH):
  **top-side 0402 at 1-1.5 mm with GND on the L1 pour + L2 via: about 0.7-0.9 nH; bottom-side cap behind one via: about
  1.6-2 nH** (its GND hop to L5 is short, but the loop must close L1 to L5 through the board). The L4 +3V3 plane (0.66 mm below
  L2, 0.55 mm above L5) adds about 1 nH of feed via + cavity spreading and only about 1.4 nF plane capacitance (`pdn.md`):
  **above about 20 MHz every IC depends on its local capacitor**; no IC relies on the plane for HF decoupling (verified below).

## Table: every supply pin, its closest capacitor by copper path
Columns: centre-to-centre distance and copper path (mm), the track width on the path, the vias in the path, and the distance
from the capacitor's GND pad to its nearest GND via (mm). F / B = top / bottom side.

| pin | part | net | cap | ctr / copper | width | vias | GND via | verdict |
|---|---|---|---|---|---|---|---|---|
| U101.1 / .12 | BUF802 VS+ / VSO+ | +5V | C108 / C109 100n F | 1.20/1.14, 1.17/1.43 | pour / 0.25 | 0 | 0.67 / 0.77 | OK |
| U101.5,6 / .8 | BUF802 VS- / Aux_Bias | -5V | C112 / C113 100n F | 1.14 to 1.32 | pour | 0 | 0.68 | OK |
| U101.10 | BUF802 VSO- | -5V | C115 100n **B** | 1.68 / 2.01 | 0.25-0.6 | 1 | 0.79 | **DEC-1** |
| U102.2 / .5 | OPA197 | -5V / +5V | C114 / C110 100n B | 1.99 / 1.61 | 0.5 | 1 | 0.85 / 0.91 | OK (10 MHz op-amp) |
| U201.2 / .5 | TPH2501 | -2V5 / +2V5 | C209 B / C208 F 100n | 1.54 / 1.34 | 0.5 / 0.6 | 1 / 0 | 0.6 / 0.72 | OK |
| U202.5 | TPH2501 | +3V3 | C210 100n F | 1.34 | 0.6 | 0 | 0.62 | OK |
| U301.10 | TMUX136 VCC | +2V5 | C301 100n **B** (to VSW_GND) | 3.6 / about 5 + 4.5 return | 0.3 | 2 | n/a | **DEC-3** |
| U302.6,7 | TLV3801 VCC | +2V5 | C305 100n **B** | 0.86-0.92 / 0.96 | 0.25-0.3 | 1 | 0.6 | **DEC-2** |
| U302.3,9 | TLV3801 VEE | -2V5 | C307 100n **B** | 0.50-0.66 / 0.75 | 0.3-0.6 | 1 | 0.0 (via in pad) | **DEC-2** |
| U303.1 | TRF37D73 (trigger) | +3V3 | C309 100n **B** only | 0.80 / 0.81 | 0.25 | 1 | 0.62 | DEC-6 |
| U401.1 / U402.1 | TRF37D73 | +3V3 | C404 / C409 1n F (+10u B 2.8 mm) | 1.45 / 1.56 | 0.25 | 0 | 0.6 | OK |
| U403.1 / U405.1 | TRF37D73 | +3V3 | C415 / C425 1n F, C414 / C424 100n F 1.9 mm | 0.97 | 0.25 | 0 | 0.55 | OK |
| U304.1 | SN65LVDS2 | +3V3 | C310 100n B | 0.55 | 0.5 | 1 | 0.43 | OK |
| U305-U312.8 | COS3502 x8 | +3V3 | C346-C353 100n F | 1.44 / 1.30 each | 0.5 | 0 | 0.62-0.91 | OK |
| U501.1 / .25 / .36 | GW1NZ VCCIO0 / VCCIO1 / VCCX | +3V3 | C504 / C505 / C506 100n F | 1.11 / 1.91 / 2.38 | 0.2-0.3 | 0 | 0.62 / **1.74** / 0.5 shared | DEC-5 |
| U501.12 / .37 | GW1NZ VCC | +1V2 | C501 / C502 100n F (+C503 10u B) | 1.58 / 1.25 | 0.2 | 0 | 0.77 / 0.5 shared | DEC-5 |
| U502.1 / .7 | MS5351M VDD / VDDO | +3V3 | C509 F / C508 **B** | 1.67 / 1.93 | 0.25 | 0 / 1 | 1.32 / 1.31 | DEC-4 |
| U601.3 / .2 | AMS1117 in / out (B) | VBUS / +3V3 | C602 100n, C601 22u / C605, C604 22u, C606 | 1.83 / 2.51 | pour L6 | 0 | 0.5-1.0 | OK |
| U602.1,3 / .5 | AP2112 in / out | +3V3 / +1V2 | C607 1u / C608 1u (+C609 10u) | 1.97 / 1.60 | pour / 0.6 | 0 | 1.56 / 2.4 (F pour to pin 2) | OK |
| U603.4,5 | MT3608 VIN | VBUS | C603 10u F, C601 22u B | 2.16 / 2.84 | pour | 0/1 | 1.32 | OK |
| U604.1,3 / .4 / .5 | LP2985 in / BP / out | +5V4F / BP / +5V | C615 1u / C614 10n / C616 2.2u (+C617 10u) | 1.97 / 1.60 / 1.60 | pour / 0.25 / 0.6 | 0 | F pour | OK |
| U605.1,6 | LM27761 VIN | +5V4F | C623 1u **B** only | 0.76 ctr; pin 6 about 3 mm | 0.25 / 0.4 | 1 | 1.0 | **DEC-4b** |
| U605.3 / .4 | LM27761 CPOUT / LDO out | CPOUT / -5V_LDO | C619 4.7u 0603 F / C620 2.2u F | 1.38 / 1.40 | 0.25 | 0 | 0.93 / 0.53 | OK |
| U606.1,3 / .5 | LP5907 in / out | +5V4F / +2V5 | C613 100n / C624 1u (+C625 10u B 4.9 mm) | 1.97 / 1.60 | pour / 0.6 | 0 | F pour | OK |
| U607.2 / .3 | LM337 (B) in / out | -5V / -2V5 | C621 10u / C628 10u + C629 100n | 2.05 / 4.04 | 0.5 | 0 | 1.35 / 2.85 | OK (LDO) |
| U608.5 | USBLC6-2 VBUS | VBUS | C601 22u B | 6.76 / 8.94 | 0.25-0.6 | 1 | 0.53 | DEC-7 |
| U701.2 / .5 | TLV9001 | -2V5 / +2V5 | C721 B / C720 F 100n | 1.79 / 1.48 | 0.3 | 1 / 0 | 0.88 / 0.85 | OK |
| U704.1,48 / .24 / .36 | STM32 VBAT, VDD | +3V3 | C713 (+C710 B) / C712 / C711 100n F, C714 10u 6.2 mm | 0.87-1.50 | 0.3 | 0 | 0.72-0.8 | OK |
| U704.21 | STM32 VDDA | VDDA | C716 10n B (under pin), C715 1u B, FB701 | 2.42 | 0.25-0.3 | 1 | 1.83 | OK (low-rate ADC) |
| U704.20 | STM32 VREF+ | VREFP | C718 100n + C717 1u B | 2.52 / 3.47 | 0.25-0.3 | 1 | 0.7 | OK (see note) |

GVA-84+ (U404 / U406) has no supply pin: it is biased through its output tee. The cold end of L404.2 / L406.2 (VBUS, B) has
C418 / C428 1n on B at 1.32 mm with the GND via in the pad. The 100n C419 / C429 is at 6.2 mm and the 10u C420 / C430 at 7.6 mm.
The TRF37D73 chokes L401 / L402 / L403 / L405 / L302 have a 100n capacitor at 1.32-1.37 mm from the cold pad. These are
acceptable as built; the tee geometry is left to the bias-tee key.

## Checked and found correct
- 65 supply pins on 34 ICs: every pin has a capacitor on its own net to GND, except the TMUX136, whose capacitor goes to the
  switch ground by design.
- 59 of the 65 pins have their closest capacitor within 2.0 mm of copper path. The exceptions are U301.10, U501.36 (2.38),
  the AMS1117 / MT3608 / LM337 bulk capacitors, U608 and the STM32 VDDA / VREF+ pair, which reach their capacitors through a via.
- No supply track narrower than 0.2 mm, and none narrower than 0.25 mm outside the FPGA fan-out.
- Feed order (`feed.py`): C504, C501, C509, C628 sit between plane / corridor via and pin; at the COS3502 the plane via is
  2.1 mm from the pin and the cap branches 0.8 mm from it; no HF capacitor is fed only through the plane.
- BUF802: there are separate capacitors for VS+, VSO+ and VS- (datasheet 8.3: individual capacitors per pin), on the same side.
  Exception: VSO-, see DEC-1.
- STM32G474: 4 x 100 nF and 10 uF on VDD/VBAT. VDDA has FB701 plus 1 uF and 10 nF. VREF+ has 1 uF and 100 nF:
  - C717 is a 10 V X5R 0402 at 2.9 V, about 0.6 uF effective. Total about 0.7 uF, inside the VREFBUF CL range 0.5-1.5 uF.
- GW1NZ: there is 100 nF on every VCC / VCCIO / VCCX pin (5 pins), plus 10 uF on +1V2 (C503) and on +3V3 (C510).
- COS3502: 100 nF at 1.3 mm on the top side with a GND via 0.62 mm away (datasheet: 0.1 uF close to VS).
- Shared vias: only the FPGA GND via (DEC-5), C113 / C115 sharing a -5V via, and C302 / C303 sharing a GND via. No capacitor
  shares a via with another net's path.

## Findings
**DEC-1 (medium, verified): BUF802 output-stage negative supply VSO- (U101.10, at 12.21 / 11.80) is decoupled only on the
bottom side.**
- Path: from the pin, 0.25 mm on L1 to a via at (12.5, 12.05), then 0.4 / 0.6 mm on L6 to C115.1 at (13.25, 13.12) B.
  The path is 2.01 mm long with 1 through via.
- C113 (top, 2.39 mm away) is reachable only through L3 (5.8 mm).
- Datasheet 8.4.1: "mount the bypass capacitors as close to the supply pins as possible and on the same side of the PCB as
  the BUF802". The estimated loop is about 1.8 nH, against about 0.7 nH at the other three supply pins.
- VSO- carries the output-stage load current into the 50 R BUF_OUT_S path. At 1-2 GHz, 1.8 nH is 11-23 Ohm.
- Fix: add a top-side 0402 (100 nF or 10 nF) between U101.10 and R112, with its GND pad on the L1 pour and a via to L2.
  Alternatively, connect C113 to pin 10 on L1. Keep C115 as the second capacitor.

**DEC-2 (medium, verified): TLV3801 (U302) has a single 100 nF per rail, both on the bottom.**
- +2V5: C305 at (7.43, 29.3) B, fed by a via 0.11 mm from its pad.
- -2V5: C307 at (7.40, 31.74) B, with a via in the EP pad.
- There is no 100 pF / 10 nF capacitor and no top-side capacitor. SNOSDD7C 8.3 asks for "100 pF, 10 nF and 1 uF with the
  lowest value capacitor closest to the comparator".
- A 100 nF 0402 behind about 1.6 nH has its self-resonance near 13 MHz. The 225 ps comparator draws its switching current
  at GHz frequencies, so the supply bounce goes into the trigger timing (trigger jitter).
- Fix: add a 100 pF (or 1 nF C0G) 0201 / 0402 on L1 at pins 6/7 and at pin 3, with a direct L1 GND via, plus a 1 uF per rail.

**DEC-3 (medium, verified geometry / likely impact): TMUX136 (U301) supply and switch ground are bypassed far from the part.**
- The VCC capacitor C301 (+2V5 to VSW_GND) is on B at (10.4, 24.48), 3.6 mm from U301.10 (8.94, 27.80).
  - Supply: 0.3 mm L1 track north to (9.32, 24.7), then east to a via.
  - Return: from U301.5 over 0.15 mm stubs to the via (8.04, 27.8), then 0.3 mm on L6 for 4.5 mm north to C301.2.
  - The loop is about 3 nH, so the 100 nF resonates near 9 MHz.
- The RF bypass of the switch ground to GND, C303 1 nF, carries the schematic note "C0G, at U301.5" (`gen_trigger_phase.py`
  line 165). It is placed at (14.4, 23.52) B, 7.97 mm from U301.5. C302 100n is at 6.75 mm.
- The trigger signal (BUF_OUT_T / EXT_CLK, GHz content) is referenced to GND, but the switch's internal capacitances return to
  VSW_GND. That return then sees about 3-4 nH (about 20 Ohm at 1 GHz) before it reaches GND, which degrades the trigger-path
  bandwidth, isolation and crosstalk.
- Datasheet 9.3/9.4: "bypass capacitor as close to VCC pin as possible".
- Fix: put C301 and C303 on the top side within 1 mm of pins 10 / 5, and use a solid VSW_GND copper island under U301 instead
  of 0.15 mm stubs. See the crop `decoupling-tmux136-tlv3801.png`.

**DEC-4 (low, verified): the MS5351M VDDO (U502.7, 64.90 / 2.20) capacitor C508 is on the bottom, through a via.**
- Si5351 sec. 7.1: "as close to the VDD and VDDOx pins as possible without using vias".
- C509 (pin 1) has its GND via 1.32 mm from the pad.
- Supply noise on VDDO becomes clock jitter on FPGA_CLK / MCU_CLK.
- Fix: move C508 to L1 next to pin 7, and add a GND via within 0.5 mm of the C509 / C508 GND pads.

**DEC-4b (medium, verified): the LM27761 (U605) input has only C623, 1 uF 0402 (C52923, 10 V X5R) on the bottom.**
- C623.1 is at (88.98, 1.50) B. From pin 1 the path is 1.0 mm L1 at 0.25 mm, a via at (87.85, 2.25), then L6 at 0.4 mm.
  Pin 6 is reached over about 3 mm of L6.
- The next +5V4F capacitor (C615) is about 10 mm away.
- At 5.3 V, the 0402 X5R keeps about 0.4-0.5 uF (manufacturer DC-bias curves: suspected value).
- Datasheet 7.2.2.5.2: 4.7 uF recommended and at least 2 uF after DC-bias derating. The layout guideline asks for "CIN on the
  top layer ... as close as possible ... short, wide traces to VIN and GND".
- Consequence: the input ripple of the charge pump goes onto +5V4F, which feeds the LP2985 (BUF802 +5V) and the LP5907
  (+2V5: TLV3801, TMUX136). The LP5907 / LP2985 PSRR at the switching frequency (about 2 MHz) removes most of it, but it is
  avoidable.
- Fix: use 4.7 uF 0603 / 0805 (16 V) on L1 between pins 1/6 and pin 2. Keep C623.

**DEC-5 (low, verified): FPGA capacitor ground vias.**
- C502 (+1V2, U501.37) and C506 (+3V3 VCCX, U501.36) return through one GND via at (59.55, 8.65), 0.5 mm from each pad.
  The next GND via is 3.7 mm away.
- C505 (VCCIO1, U501.25) has its nearest GND via 1.74 mm from its GND pad (68.78, 7.40), joined by a 0.3 mm L1 track.
- About 0.3-0.5 nH is added to each loop. This is harmless at the FPGA's I/O rates, but the shared via couples the core and
  VCCX noise.
- Fix: one GND via per capacitor pad.

**DEC-6 (low, verified): U303 (TRF37D73 trigger line driver) pin 1 has only 100 nF C309 on B (via, about 1.5 nH)**, while
the four strobe TRF37D73 have 1 nF on top at about 1 mm (SLASE43 sec. 9: higher-SRF capacitor closest). Pin 1 is the DC bias
pin, so the impact is small. Fix: add 1 nF on L1 at pin 1, as on U401-U405.

**DEC-7 (low, suspected relevance): USBLC6-2SC6 (U608) VBUS pin 5 has no local capacitor** (nearest C601 22 uF at 6.8 mm,
through a via). Fix: add 100 nF 0402 next to pin 5.

Not a finding: 16 of 65 primary capacitors are on the bottom (about 1.6-2 nH each); acceptable for the op-amps, TPH2501,
TLV9001, STM32 analog pins and LDOs (bandwidths below 50 MHz).
