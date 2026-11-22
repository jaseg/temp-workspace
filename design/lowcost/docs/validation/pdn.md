# Validation: PDN impedance, regulators, IR drop, thermal (key `pdn`)

Validator run 22 Nov 2026. Validation only: no design file was changed.
Scripts: `/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/val/pdn/` (`ext.py`, `zones.py`, `graph.py`, `near.py`, `zac.py`).

## Method
1. **Extraction from the board:** pcbnew on a copy of `layout/board/scope-fe.kicad_pcb`, with the zones refilled. For each rail it collects
   the tracks per layer and width, the vias, the filled zone islands, and the pads.
   `graph.py` builds a resistor and inductor network from it: track segments are split at T-joins, and via barrels, zone islands and pads are nodes.
   It then solves the two-terminal R and L from the regulator output pin to each load pin.
   Copper: 35 um outer and 15.2 um inner (stackup in the board file). L' comes from a microstrip / embedded model against the nearest plane:
   L1 over L2 at 0.0994 mm, L6 under L5 at 0.0994 mm, and L3 over **L4 (+3V3)** at 0.1088 mm. Mutual inductance is ignored.
2. **Plane:** +3V3 on L4 has 4710 mm2 filled in 1 island. Its capacitance to L5 (0.55 mm, er 4.6) is 0.35 nF, and to the L3 GND fill
   (3092 mm2 in 78 islands, 0.1088 mm, er 4.16) at most 1.0 nF. The model uses 1.4 nF in total.
3. **AC model** (`zac.py`, numpy, 1 kHz to 1 GHz): each LDO is R0*(1+jf/fbw). Capacitors are modelled as C, ESR and ESL, with ESL 0.7 nH for 0402
   and 1.2 nH for 0805 including mounting, plus extra L for distance. The capacitance is derated for DC bias:
   0402 1u at 5 V x0.4, 0402 2.2u at 5 V about 0.8 uF, 0805 10u at 3.3 V x0.6 and at 5 V x0.45.
   Target Zt = allowed ripple / dynamic current. The result is plotted in `pdn-z.png`.

## Extracted distribution (regulator pin to load pin, VERIFIED from the board)
| Rail | From | To | R | L | Local caps at the load (distance) |
|---|---|---|---|---|---|
| +2V5 | U606.5 | U302.6/7 TLV3801 VCC | 351 mOhm | 28 nH | C305 100n (0.9 mm), C301/C306 100n (6-7 mm); no bulk |
| +2V5 | U606.5 | U301.10 TMUX136 | 363 mOhm | 30 nH | as above |
| +2V5 | U606.5 | U201.5 / R108 / U701.5 | 146 / 170 / 122 mOhm | 15 / 20 / 10 nH | C208 / - / C720 100n |
| -2V5 | U607.3 | U302.3 VEE / U201.2 / U701.2 / R726 | 62 / 43 / 44 / 91 mOhm | 8.6 / 4.3 / 7.1 / 11 nH | C307 100n only (0.5 mm) |
| +5V | U604.5 | U101.1 / U101.12 BUF802 / U102.5 | 140 / 140 / 189 mOhm | 12 / 12 / 17 nH | C108, C109 100n only; C110 at U102 |
| -5V | FB603.2 | U101.5 / U101.10 / U102.2 | 145 / 147 / 152 mOhm | 15 nH | C112, C113, C115 100n + C116 10u (3.7 mm) |
| +1V2 | U602.5 | U501.12 / U501.37 | 20 / 27 mOhm | 2.4 / 3.1 nH | C501 / C502 100n, C503 10u |
| VBUS | FB601.2 | L404.2 / L406.2 (GVA tees) / U601.3 / U603.5 | 15 / 37 / 4 / 7 mOhm | 2.7 / 6.0 / 0.7 / 1.2 nH | C418/C428 1n, C419/C429 100n (6 mm), C420/C430 10u (7.6 mm) |
| VREFP | U704.20 | R731 / R703 | 227 / 98 mOhm | 25 / 11 nH | sources only mA: no issue |
The +2V5 track totals are L3 0.3 mm: 112 mm, L6 0.3 mm: 35 mm, plus 0.4-0.8 mm sections. This matches the 147 mm given in the brief.

## DC budget (VERIFIED arithmetic on datasheet currents)
+3V3: 5 x TRF37D73 (U303, U401, U402, U403, U405; 53 mA typ / 65 mA max, SLASE43 table 6.5) = 265/325 mA.
8 x COS3502 at 2 x 3.3 mA = 53 mA. STM32G474 about 40 mA, MS5351M about 20 mA, FPGA about 20 mA, SN65LVDS2 about 8 mA, AP2112 load about 20 mA.
That gives **about 0.43 A typ / 0.52 A max**. The power-sheet note and gen_strobe say "6 x TRF37D73": the board has 5.
Boost input: +5V4 load 0.17 A at 5.32 V (LP2985 37 mA for the BUF802 at 35.5 mA, LM27761 about 85 mA, LP5907 about 45 mA)
draws about 0.21 A from VBUS. The GVA-84+ pair draws 0.22 A. **VBUS about 0.86 A**, under the PTC 1.5 A hold and over 0.9 A USB3
(already open point 4).
IR drops: +2V5 to the TLV3801 about 9 mV. That leaves VCC-GND >= 2.44 V worst case against the 2.4 V minimum for split supplies
(TLV3801 ROC, txt l.290): OK, 40 mV margin. +5V and -5V to the BUF802 about 5 mV each, +1V2 under 1 mV: OK.

## Checked and found correct
- Track R/L on the minor rails gives series damping. With the local 100 nF it holds |Z| <= 0.43 Ohm (+2V5 @U302), 0.48 Ohm (+5V @BUF802),
  0.67 Ohm (-5V, bead resonance 47 kHz) and 0.12 Ohm (+1V2) up to 100 MHz. These are under the targets (about 1 Ohm) for the actual dynamic currents.
- The +3V3 plane is 15-70 mOhm up to 20 MHz at the FPGA, the TRF37D73s and the MCU. Above about 150 MHz only on-die and package capacitance help (lumped plane / ESL peak about 520 MHz).
- +1V2 (AP2112K, 1u + 2 x 10u, Cout >= 1 uF ceramic OK), LP5907 (C624 1u + C625 10u) and LP2985 (C616 + C617 10u at 1.4 nH): stability capacitance met after derating.
- The LM27761 charge-pump headroom at 5.32 V input meets VIN >= |VOUT| + 2 Ohm x I + 30 mV. LM27761 at about 85 mA of its 250 mA rating; LM337 dissipation 0.12 W; LP5907 0.14 W.
- VREFP (64 mm of 0.15 mm L6) at 0.23 Ohm carries only resistor-divider currents: no impact. VTAP_P is 30-166 mOhm across the 16 taps.
- The GVA-84+ bias tees (2.2 uH) isolate the GVA RF current from VBUS above about 1 MHz. The 8 Ohm VBUS peak at 121 MHz (C418 1n against the far 100n / 10u) is therefore not seen by the amplifier.

## Findings
**PDN-1 (medium, likely) AMS1117 U601 has an all-MLCC output; the datasheet asks for 22 uF tantalum.** U601.2 has C604/C605 22u 0805 + C606 100n,
plus about 7 x 10u and about 30 x 100n MLCC on the L4 plane: ESR a few mOhm. AMS ds1117 "Stability": "the circuit design ... requires the use
of an output capacitor as part of the device frequency compensation. The addition of 22 uF solid tantalum on the output will ensure
stability". That is the LM1117-type architecture, which needs ESR in the zero. Risk: oscillation or ringing on the rail that feeds 5 TRF37D73, the FPGA I/O and the MCU.
Fix: add a 22-47 uF tantalum or polymer (ESR 0.1-1 Ohm) at U601.2, or replace U601 with a ceramic-stable 1 A LDO with a low dropout, which also fixes PDN-2.

**PDN-2 (medium, verified) AMS1117: no dropout margin at USB minimum, and a thermal pad too small.** The VBUS chain at 0.86 A:
USB-C vSafe5V min 4.75 V, minus PTC F601 (1206L150, about 0.05-0.11 Ohm), minus FB601 DCR about 0.045 Ohm, minus 4 mOhm of track. That leaves
4.61-4.66 V at U601.3, a headroom of 1.31-1.36 V against the dropout of 1.1 V typ / **1.3 V max** (ds1117 EC table, 0.8 A). With no margin,
PSRR collapses in dropout and the boost and USB ripple pass onto +3V3. Dissipation (VIN-3.3) x 0.45 A = 0.70 W at 5.0 V and 0.88 W at 5.25 V.
The tab zone is +3V3 on B.Cu, **60.9 mm2** (bbox 174.2-185.2 x 100.0-108.3), with only **2 vias** to L4. The note in gen_power.py:102 asks
for >= 2 cm2. With the ds1117 theta-JA of 90 K/W, Tj = 88-104 C at 25 C ambient (125 C max).
Fix: a low-dropout part, or move the 5 TRF37D73 (about 0.3 A) to a separate regulator. Enlarge the tab copper and add >= 8 vias to L4 and to an L6 pour.

**PDN-3 (medium, likely) LM337 U607 has ceramic-only output capacitors and runs below its specified headroom.** The output is C628 10u MLCC + C629 100n, with 10u on ADJ.
TI SLVS047L section 8: "1-uF solid tantalum or 10-uF aluminum electrolytic capacitor is required on the output pin for stability". A bypassed ADJ
raises that requirement. |VI-VO| = 4.99-2.50 = 2.49 V, while every LM337 parameter is specified at |VI-VO| >= 3 V (EC table).
The minimum load is 10 mA max against 10.4 mA in the 120/120 divider: OK. Fix: a 10 uF tantalum, or 1 Ohm in series with C628, at U607.3. Check the XBLW
clone's dropout at 50 mA, or use a ceramic-stable negative LDO (open point 5).

**PDN-4 (medium, likely) LM27761 U605 capacitors are too small once DC bias is counted.**
- LDO output C620 2.2u 0402 at -5 V is about 0.8-1 uF effective. SNVSA85D 7.2.2.5.4: "requires ... 2.2-uF ceramic output capacitor for stable operation",
  and FB603 isolates the C621 10u behind it.
- Input C623 1u 0402 at 5.3 V is about 0.4 uF, against the 4.7 uF recommended (7.2.2.5.2). The next bulk, C612, is 24 mOhm / 4.2 nH away.
- CPOUT C619 4.7u 0603 is about 2 uF at 5.3 V, which equals the 2 uF anti-toggling minimum (7.2.2.5.1).
Fix: C620 4.7-10 uF 0603/0805 16 V X7R; C623 4.7-10 uF 0603/0805; C619 10 uF 0805 10-16 V.

**PDN-5 (low, verified arithmetic / suspected MT3608 VFB tolerance) +5V4F can exceed the 5.5 V VIN max of the LM27761 and LP5907.**
Nominal 0.6 x (1+78.7k/10k) = 5.32 V. With VFB 0.612 V max (MT3608 typ 0.6 V +/-2 %) and 1 % resistors it reaches **5.53 V**, plus boost ripple.
The LM27761 recommended VIN is 2.7-5.5 V (abs max 6 V). The low end must stay >= 5.2 V for the LM27761 headroom, so the window is only +/-2.7 %.
Fix: set -5V to about -4.8 V (R605 about 1.43M; the BUF802 needs >= 4.5 V) and the boost to about 5.15 V, which centres both windows.

**PDN-6 (low, verified) Two minor-rail loads have only 100 nF locally behind 8-30 nH of track.** -2V5 at U302.3 (TLV3801 VEE) has C307 alone,
with 8.6 nH back to U607: **1.0 Ohm at 5 MHz**. +5V at the BUF802 (U101.1/12) has C108/C109 alone, with 12 nH / 0.14 Ohm: 0.48 Ohm at 2.7 MHz.
The +2V5 TLV3801/TMUX136 branch (28 nH, 0.35 Ohm) is damped by the track R: 0.43 Ohm. These meet the targets now, but local capacitance alone carries
the 1-10 MHz band. Fix (cheap): add 1-2.2 uF 0402 at C307/U302.3, at U101 +5V (beside C108), and at U302.6/U301.10.

**PDN-7 (low, suspected) TRF37D73 VCC pins.** U401/U402 pin 1 has C404/C409 1 nF at 1.4 mm and C402/C407 10u (B.Cu, 2.5 mm). The 100 nF
C403/C408 is 7.6 mm away at the L401/L402 cold end. Model: anti-resonance **3.4 Ohm at about 146 MHz**, which is the 3rd harmonic of the 48 MHz strobe.
Most of the device current flows through the RFOUT bias tee, so the impact is probably small. If space allows, add a 100 nF next to C404/C409.

**PDN-8 (low, suspected) VBUS shares the GVA-84+ supply with the MT3608 input.** At 4.75-5.1 V in and 5.32 V out, D is about 0.04-0.1 at 1.2 MHz:
probably pulse skipping, which draws burst current at kHz rates. The low-frequency VBUS source impedance (cable, PTC, bead) is about 0.2 Ohm,
so 0.2-0.4 A bursts give 40-80 mV on the GVA Vd through the 2.2 uH, which shifts the strobe amplitude. Measure on the first build;
fallback: an RC or LC filter (for example 1 Ohm + 47 uF) ahead of L404/L406.
