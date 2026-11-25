# Recheck of the BOM-2 round (25 Nov 2026)

Independent check of SPEC decisions 27-34 against the primary files: `kicad/export/scope-fe.net`, the generators,
`layout/board/scope-fe.kicad_pcb` (refilled copy in scratch), the bom2 studies and their simulations, datasheets fetched
fresh (TI TLV3801 / TPS63802 / LM27762 / TPS62A01 / BUF802, Infineon BAT15-04W, JSCJ SS8550 / MMBT3904, 3PEAK TPH2501,
Cosine COS3502, Murata DFE252012F via LCSC). No design file was changed. Findings B2-1 ... B2-12 at the end.

## 1. Circuit changes
**Trigger switch (D317-D320, Q301 / Q302).** BAT15-04W pinout read from the datasheet figure: pin 1 = D1 anode, pin 3 =
D1 cathode / D2 anode, pin 2 = D2 cathode (series 1 -> 3 -> 2). Netlist: P_a pin 1 T, 3 X, 2 B; P_b pin 1 T, 3 Y, 2 B, so
T -> X -> B and T -> Y -> B: a correct four-diode gate. SS8550 / MMBT3904 SOT-23: 1 B, 2 E, 3 C (both datasheets) = netlist.
- SIG (TRIG_SEL low): Q301 base 0.13 mA with PA1 high-Z (R386 10k + R737 3.3k, pin +0.43 V), 0.18 mA driven low; collector
  load R387 4.9 mA + bridge 1 2.06 mA + R388 0.42 mA = 7.4 mA: forced beta 57 against hFE 200-350 (C8542 is rank Y2):
  saturated. Q302: base 0.21 mA, collector 6.9 mA: saturated. S +2.43 V, SB -2.32 V. +2V5 draw 12.3 mA.
- EXT (TRIG_SEL 3.3 V): Q301 EB reversed 0.8 V (VEBO 5 V); bridge 2 current (5 - 0.6) / 4k = 1.1 mA, S -1.38 V, SB +1.38 V;
  Q302 Vbe 0.28 V (off).
- TLV3801 (DSG pins 1 OUT-, 2 GND, 3 VEE, 4 IN-, 5 IN+, 6 / 7 VCC = netlist). Split supply VCC - VEE 4.84-5.09 V (<= 5.25),
  VCC - GND >= 2.44 V (>= 2.4). VCM range VEE + 1.5 = -0.88 V worst ... VCC. TRIG_LEVEL -0.332 / +0.466 V guaranteed
  (R383 5.1k / R384 10k / R385 3.3k, DAC 0.2-2.7 V, -2V5 +/-2.5 %; Rth 1.67k, DAC load 7.6k): inside. EXT_CLK lower limit
  -0.9 V sits on the VCM edge, as stated in SPEC 27. IB 10 uA max x 1.67k = 17 mV (calibrated).
- Off-bridge reverse voltage: SIG mode, Y at the BUF802 clamp (line end -1.36 V): B2 - Y up to 2.535 + 1.36 = 3.9 V vs 4.0 V
  abs max (B2-7). EXT on SMA +1.0 / -0.9 V in SIG mode: 3.45 / 3.44 V. EXT mode, bridge 1 off: <= 2.9 V.
- Hand estimate of the off-bridge leak (0.2 pF diode, 1k feeds, ~50 R at Y): -57 dB at 100 MHz, -24 dB at 1 GHz; the sim
  gives -48.8 / -22.4 dB: same order. Isolation below 48 dB above ~100 MHz is documented (operating rule).
- Power-up: U605 rails follow PG_5V1, MCU in reset with PA1 high-Z -> R737 selects SIG; no ramp condition. EXT_CLK open:
  X2 held at 0 V by R301 49.9 R; no floating node. With +/-2V5 off and PA1 high, both Q301 junctions are reversed (no
  current; the study's 0.3 mA remark is harmless but wrong in direction).
**COARSE (U313 COS3502).** Datasheet pin figure: 1 +INA, 2 -INA, 3 +INB, 4 -INB, 5 Vs-, 6 OUTB, 7 OUTA, 8 Vs+ (the pin
table's "OUT 7, 8" is a datasheet typo). Netlist: 1 / 2 via R311 / R312 470 R from CMP_P / CMP_N, 3 GND, 4 +3V3 (OUTB low),
6 open, 7 COARSE, 8 +3V3 with C313 1.5 mm. TLV3801 VOCM 0.92-1.29 V (VCC - GND < 2.6 V) inside -0.2 ... 3.5 V. Speed: 90 MHz
toggle is specified at 5 V only; requirement "< 100 MHz", firmware ignores COARSE above 60 MHz (B2-8).
**Input servo without RV101.** U102 OPA197: +IN = TAP, -IN = FB, C106 1n C0G FB -> OUT. FB DC level in overload (BUF_OUT_S
at +/-1.5 V clamp, VOFS 0.2-2.7 V, VNEG_REF -1.93 V): -1.0 ... +1.1 V; VOFS pin current <= 0.4 mA DC through R119 10k
(transients via C106 bounded by the OPA197 input diodes, <= 0.5 mA at -5 V, within the STM32 5 mA injection). VOFS
0.2 / 2.7 V -> OUT +0.512 / -0.663 V (sim) reproduced by hand. Flatness claim: see B2-9.
**Tap hold node.** Extracted on the refilled copy (pcbnew polygons, L1 net copper intersected with the L2 GND fill, 0.0994 mm
3313, er 4.1, 0.08 mm fringe per edge, rest to L5): 1.61 mm2 per node, 0.53 mm2 over L2, **0.37 pF**, identical for all 32
nodes, plus 0.03-0.05 pF fringe to the L1 pour -> 0.40-0.42 pF against **0.40 pF** simulated. Coupling parts stay fitted
(C76912 0.5 pF +/-0.05 pF, SPEC 29): inside the 0.4-0.8 pF flat region.
**Rails** (datasheet limits: TPS63802 VFB 0.5 V +/-1 %, IFB 100 nA, OVP 5.5 V min, abs 6.0 V; LM27762 VFB+ 1.182-1.218 V,
VFB- -1.202 ... -1.238 V, R2 / R4 >= 50k, output range 1.5-5 V):
| Rail | min / nom / max | check |
|---|---|---|
| +5V1 (20k / 2.2k) | 4.906 / 5.045 / 5.191 V (+2 mV IFB) | <= 5.20 V; 0.31 V below OVP |
| U604 OUT+ (470k / 150k) | 4.812 / 4.960 / 5.111 V setpoint | dropout possible, B2-4 |
| U604 OUT- (510k / 200k) | -4.206 / -4.331 / -4.459 V | CP headroom 0.22 V (41 mA x 4.5 R) |
| BUF802 VS total at pins | 9.008 / 9.29 / 9.57 V | >= 9.0 V ROC: 8 mV margin (B2-5) |
| +2V5 / -2V5 (U605) | 2.456-2.585 / -2.380 ... -2.500 V | TLV3801 sum 5.085 <= 5.25 V |
| GVA-84+ drain | 4.71 / 4.92 / 5.19 V | 4.8-5.2 V operating range, low corner 0.09 V out (B2-6) |
**USB plug-in** (own ngspice deck, 5.25 V ideal step, cable 1.0-1.5 uH / 0.05-0.1 R, FB601 0.05 R + 0.05-0.2 uH, Cin 12-20 uF,
damper 4 x (1 R + 12 / 16 / 25 uF), TVS absent): undamped 8.55 V; damped worst **5.78 V** (1.5 uH, Cin 20 uF, 12 uF per
damper cap), 5.33 V at a realistic 18 uF per 47 uF / 10 V 1206 at 5 V; study 5.27-5.57 V. A 5.5 V (vSafe5V max) step gives
6.05 V in the worst corner (B2-3). Limit TPS63802 VIN 6.0 V; TPS62A01A 6.5 V. An SMAJ5.0A (9.2 V clamp) would not help.
**Inductors.** DFE252012F-1R0M: Isat 4.7 A, Itemp 3.3 A, 40 mR (datasheet) vs TPS62A01 ILIM 1.8 A max: no saturation; it is
TI's own 1 uH part (table 8-2), 1 uH + 22 uF is the table 8-3 standard. L601 0.47 uH unchanged. Bias tees 53-130 mA. L302 /
L401 47 uH 170 mA at 53-65 mA. FB601 BLM18PG121SN1D 2 A at 0.97 A.
**Attenuators** (ABCD, 50 R): sampler 100 / 120 / 100: 12.46 dB, RL 20.4 dB; line 100 / 100 / 100: 11.48 dB, 23.5 dB; phase
120 / 100 / 120: 10.69 dB, 18.4 dB (old 11.97 / 9.63 dB, 40-50 dB). Terminations R378 / R379, R401-R411 49.9 R as stated.
**Op amp.** TPH2501 SOT-23-5: 1 OUT, 2 V-, 3 +IN, 4 -IN, 5 V+ (datasheet) = netlist U701; +/-2V5 within 2.5-5.5 V; VNEG_REF
= -VREF+ x 10k / 15k = -1.933 V, 0.45 V above V- worst; C722 100 nF feedback makes it a follower at HF, no capacitive load.
**Half BAT15-04W clamp.** D401 pin 2 (D2 cathode) on the stub node, pins 1 and 3 GND: D1 shorted, D2 clamps negative
excursions. D402 (PSTRB_A, pin 2) / D403 (PSTRB_K, pin 1 = D1 anode) are mirrored correctly; both DNP.

## 2. Footprints
SOT-323 (D317-D320, D401-D403), SOT-23 (Q301 / Q302), SOIC-8 (U313), L_1008_2520 (1.25 x 2.2 mm pads, 2.14 mm pitch, for
the 2.5 x 2.0 mm DFE), 0603 (R107, R114-R116, R408 / R412, R605 / R613-R615, FB601-FB607), 0402 FB608, 1206 (R618-R621,
C632-C635, F601) are consistent with the datasheets' pin numbering and body sizes. TLV3801 / TPH2501 / COS3502 pin maps
verified above.

## 3. BOM (docs/bom.csv, JLC parts API queried 25 Nov 2026 for all 80 LCSC numbers)
Every fitted line has an LCSC number (J501 is footprint-only, not ordered). JLC class of all 80 numbers matches the CSV.
80 fitted lines, 52 basic / 28 extended lines = **27 extended part numbers** (J101 / J102 share C5199907), 450 parts, **0.1 %
parts: 0**, **70.39 USD** (budget 80). Stock drift: **BAT15-04W C5380972 865** (CSV 1465): 23 fitted per board = 37 boards;
TRF37D73 25 (5 boards, unchanged); GVA-84+ 99, TLV3801 113, BUF802 146 (low, unchanged). All changed basic parts in stock
>= 155k (C17928 1 R 1206 the lowest).

## 4. Board regressions (copy, refilled)
- DRC jlc4 + parity (KiCad nightly): **0 errors, 0 unconnected**, 451 warnings: 199 field, 199 library, 31 attribute (5 DNP:
  KiCad 7 boards carry no DNP flag; all five DNP footprints are excluded from the position file, attr 6), 10 net_conflict
  (TL401-403, J601 shell), 11 library, 1 silk_edge_clearance (D319). Courtyard overlaps 0.
- ERC: 0 errors, 18 warnings (library / footprint-link only).
- via_in_pad.py: FAIL 0, 23 near, 31 in allowed exposed pads (1018 vias).
- RF widths: BUF_OUT_T, EXT_CLK, TRIG_IN, CMP_P / N, PH_STROBE_P / N, S_STROBE_P / N all 0.16 mm. L2 under them: the
  samples without L2 are the listed cut-outs at D317-D320 pin 3, the J102 launch, and via antipads of the T / B feed vias;
  TRIG_IN (Y) has no via. No real holes found.
- decap_audit.py: 77 capacitors, D1 1, D2s 8, D2g 1, D2p 10 (= README, no regression); U313.8 -> C313 0.69 mm, U302 all 0.0
  mm; Q301 / Q302 emitters 6-7 mm from the nearest +/-2V5 capacitor (static switches).

## Findings
| Id | Sev | Finding | Fix |
|---|---|---|---|
| B2-1 | medium | `docs/theory-of-operation.md` is pre-BOM-2: diagram and text still show TMUX136, SN65LVDS2, RV101, BAT15-03W clamp, EXT_CLK +/-0.5 V; calibration item 1 says "adjust RV101 ... software cannot" | rewrite sections 2, 5, 9 for decisions 27-33 (LF/HF firmware fit, EXT_CLK -0.9..+1.0 V) |
| B2-2 | medium | BAT15-04W stock 865 now (CSV 1465): 37 boards at 23 per board; TRF37D73 25 = 5 boards | refresh bom.csv stock; order the diodes early |
| B2-3 | low | USB hot-plug worst 5.78 V (study 5.57 V); 6.05 V for a 5.5 V step, above the 6.0 V TPS63802 abs max | accept for 5.25 V legacy sources or note it; a 5th branch gives 5.89 V at 5.5 V |
| B2-4 | low | U604 OUT+ setpoint (max 5.111 V) can exceed +5V1F - 20 mV (min 4.877 V): LDO in dropout on an estimated 1 in 6 boards; max setpoint above the 5.0 V range. "regulates at every corner" checks only the low corner | document; 9.0 V total still met; FB604 + caps carry the ripple then |
| B2-5 | low | BUF802 total 9.008 V worst vs 9.0 V: no room for any added drop | keep FB603 / FB604 and their tracks as built |
| B2-6 | low | GVA-84+ drain 4.71 V worst corner < 4.8 V operating range (accepted in SPEC 30) | none |
| B2-7 | low | off-bridge diode reverse voltage up to 3.9 V vs 4.0 V abs max with BUF_OUT_T at the clamp and +2V5 at max | accept or move CLL / CLH to +/-1.3 V |
| B2-8 | low | COS3502 toggle (90 MHz) and delay drift not specified at 3.3 V; COARSE latency must stay inside a 1.3 ns bin | measure on the first board; recalibrate over temperature |
| B2-9 | low | flatness 0.34-0.78 % simulated with R105 / R106 4.99 M; as built 1 M adds a 1.05 % bump near 10 kHz (third time constant) not in the fit; correction worsens the +0.1 % board (0.62 -> 0.78 %) | re-run sim/bom2_input correction with 1 M; skip correction for small eps |
| B2-10 | nit | README: +2V5 column feed "a few mA"; it carries 12.3 mA (switch) + up to 26.6 mA (TLV3801), about 5 mV drop | correct the text |
| B2-11 | nit | D319 silkscreen clipped at the board edge | trim silk |
| B2-12 | nit | SPEC.md header (parts list, prices, decisions 6 / 18) still names TMUX136, TLV9001 | mark superseded |
