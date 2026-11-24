# Recheck: power tree after the fix round (independent, 24 Nov 2026)

Primary files only: `kicad/export/scope-fe.net`, `layout/board/scope-fe.kicad_pcb` (zones refilled on a scratch copy,
pcbnew 7.0.11), TI datasheets fetched fresh: SLUSEG9E (TPS62A0x), SLVSEU9D (TPS63802), SNVSAF7C (LM27762); BUF802 and
GVA-84+ datasheets already in the project. No design file changed. Scripts and outputs: scratch `close/recheck-power/`.

## 1. Pinout and footprint, pad by pad
| Ref | Datasheet pins | Netlist | Land pattern (DS example vs board) | Result |
|---|---|---|---|---|
| U601/U602 TPS62A01A DRL | 1 GND 2 SW 3 VIN 4 EN 5 FB 6 PG | same; EN = VIN; PG open (allowed) | 6 x 0.67 x 0.3, row c-c 1.48 vs 0.70 x 0.34, 1.50 | OK |
| U603 TPS63802 DLA | 1 EN 2 MODE 3 AGND 4 FB 5 PG 6 VOUT 7 L2 8 GND 9 L1 10 VIN | same; EN, MODE = VBUS (FPWM) | 1-5: 0.6 x 0.25 at -0.9; 6/7/9/10: 0.9 x 0.25 at +0.75; 8: 1.3 wide at +0.55: identical | OK |
| U604/U605 LM27762 DSS | 1 PGOOD 2 FB+ 3 VIN 4 GND 5 CP 6 OUT- 7 FB- 8 EN- 9 C1- 10 C1+ 11 OUT+ 12 EN+, EP GND | same; PGOOD to GND (DS: allowed) | 12 x 0.5 x 0.25 at +/-0.95, EP 1.0 x 2.65: identical | OK |

## 2. Set points (reference tolerance from the EC tables, resistor tolerance included)
| Rail | Divider | Nominal | Worst case | Note |
|---|---|---|---|---|
| +3V3 U601 | 100k / 22.1k (1 %, no tolerance in value) | 3.315 | 3.21-3.42 | docs state 3.25-3.38 (reference only) |
| +1V2 U602 | 100k / 100k | 1.200 | 1.17-1.23 | GW1NZ +/-5 % OK |
| +5V1 U603 | 459k / 49.9k 0.1 %, VFB 500 mV +/-1 % | 5.099 | 5.04-5.16 | <= 5.2 V ROC, OVP 5.5 min |
| OUT+ U604 | 300k / 100k, VFB+ 1.182-1.218 | 4.800 | 4.72-4.88 | |
| OUT- U604 | 280k / 100k, VFB- -1.202..-1.238 (eq. 3) | -4.636 | -4.56..-4.71 | |
| +/-2V5 U605 | 130k/120k, 105k/100k | +2.500 / -2.501 | 2.46-2.54 each | |

## 3. Headroom and absolute maxima
- U601: VIN 4.59-5.25 V vs 100 % mode need about 3.6 V at 0.67 A: >= 1 V. Abs max 6.5 V, ROC 5.5 V: OK at 5.25 V.
- U603: buck-boost, VIN 1.3-5.5 V ROC, abs max 6.0 V. VIN OVP 5.5 V min is only 0.25 V above USB 5.25 V.
- U604 (the 0.14 V claim): VIN min = 5.039 - 82.5 mA x 0.15 R (FB602) - 3 mV = 5.02 V. Fig. 5-4 gives RCP about 4.5 ohm at
  41 mA (25 C and -40 C; 2.6 ohm at 85 C); 2.5 ohm is the 100 mA / 5.5 V point. 5.5 ohm assumed for VIN 5.0 V. LDO- dropout
  Fig. 5-3: about 13 mV at 41 mA (26 mV allowed hot). Need 4.711 + 0.19..0.23 + 0.013..0.026 = 4.91-4.97 V.
  **Worst-case margin 0.06-0.11 V** (typical 0.26 V), smaller than the stated 0.14 V but positive. If the corner is ever
  reached, OUT- follows CP (about -4.77 V): BUF802 supply stays legal, only pump ripple passes.
- U604 OUT+: 5.02 - 4.88 = 0.14 V against about 20 mV dropout at 41 mA: OK. VIN 5.16 V < 5.5 ROC / 5.8 abs max: OK.
- U605: VIN 3.20 V min (with the 1 % +3V3 divider); -2V5 needs about 2.54 + 0.4 (RCP at 3.3 V, unspecified) = 2.95 V: >= 0.25 V.
- **BUF802** (ROC +/-4.5 V or 9 V single): worst +4.715 V / -4.555 V after FB603/FB604 (6 mV) = 9.27 V. Met, 55 mV on VS-.
- GVA-84+ Vd (DS 4.8-5.2 V): 5.04 - /+5V1 trunk <= 30 mV (L3 0.5 oz, 100 squares, upper bound) - tee 0.13 A x
  (1.25 R BLM15HD102 max + 0.125 R LQM21PN2R2) = **4.84 V min**; max 5.16 - about 0.07 = 5.09 V. In range.

## 4. Capacitors (DC bias), inductors, frequency
- U601 CIN C603 10u (>= 4.7 uF DS); COUT C604 22u + plane caps: above the 2 x 22 uF proven cell (DS table 8-3), known.
- U602 COUT C605 22u + C608 + C503: meets 22 uF nominal for 1.2 V. U603 CI >= 4 uF eff.: C601 22u 25 V 0805 about 5-6.5 uF
  at 5 V (thin); CO >= 7 uF eff.: C610 + C611 about 10-13 uF: OK. LM27762 CIN/CCP/COUT >= 2 / 2 / 2.2 uF: OK for 0805 10u;
  C619 4.7u 0603 and C618 1u 0603 have no part number, so the >= 2 uF CCP at 3.3 V is unverified.
- L602/L603 1 uH: dIL 0.39-0.51 A pp (0.73 A at -30 % L), peak <= 1.03 A < 1.3 A min HS limit. L601 0.47 uH +/-20 % =
  0.376-0.564 uH inside the 0.37-0.57 uH window (just); peak eq. 2 at VIN 4.59 V, 1.4 MHz, L min: 0.91 A (doc 0.65 A);
  Isat 9.5 A also covers the 5.75 A limit. Dissipation: all < 0.3 W, Tj rise < 50 K.
- Frequencies: TPS62A01A 2.4 MHz x 20 = 48.0 MHz and LM27762 2.0 MHz x 24 = 48.0 MHz at nominal; TPS63802 1.4-2.1 MHz
  puts its 2nd harmonic on 3.125 MHz. Free-running, so a slow beat with the strobes is possible; levels see section 5.
- Sequencing: U601 1 ms soft start; U602 EN = +3V3; U604 EN = VIN; U605 EN = U603 PG (100k to its own VIN, EN max = VIN OK).

## 5. Board
Hot loops (pad-centre polygon; copper path on the IC layer, raster shortest path, 0.03 mm grid):
| Loop | Area mm2 | Supply side mm | GND side mm | Vias |
|---|---|---|---|---|
| U601 in (C603 straddle) / U602 mirrored (B) | 2.3 | 1.8 | 1.8 | GND/VBUS/+3V3 vias 1.1 mm from the cap pads |
| U601 out L602-C604-GND | 4.9 | 2.3 | 2.2 | +3V3 pair 1.3/1.6 mm behind C604 |
| U603 in C601 / out C610 | 2.8 / 2.8 | 1.8 | **3.6** (0.45 mm channel to pin 8) | VBUS x3 behind C601, +5V1 x2 behind C611, GND at caps |
| U604 in C612 22u / C613 100n | 3.1 / 0.8 | 2.9 / 1.3 | 2.9 / 1.3 | at caps |
| U604 CCP C626 / U605 CCP C619 | 2.8 / 2.1 | 2.6 / 2.4 | **4.0 / 3.6** | at caps |
| U605 in C625 | 1.8 | 1.8 | 1.8 | at cap |
Via rule (plane vias at the capacitors): met for all three switchers; no power via within 1 mm of a switcher pin
(only signal ties: U603 EN/MODE 0.89 mm, FB 0.80, PG 0.89). **Not met on the LM27762s**: OUT- vias 0.55 mm from
U604.6 / U605.6, and all four LDO output capacitors (C617, C621, C628, C630) are on B.Cu behind vias; EP has 2 GND vias each.
Switch nodes: U601 SW 3.95 mm track, 3.9 mm2 incl. L602 pad; U602 the same on B; U603 L1/L2 4.5 / 4.4 mm2 (pads and pour,
no track); pump nodes 0.6-1.9 mm2. Under every switch node: solid GND on L2 and L5, +3V3 on L4, GND on L3 except U605
C1+/C1-/CP over +5V / +2V5 L3 tracks (L2 GND between). U601 SW (L1) overlaps U602 SW and U602 FB (L6) by about 0.7 mm2,
four planes between. No switch-node via.
Distance switch node / inductor to: ADC_IN (L3) >= 12.2 mm (U605 pump), 16.8 (U604), 24.5 (U602); hold nodes D201/D202
>= 51 mm; VREF+ >= 30 mm; SMA J101/J102 >= 73 mm; MS5351M U502 6.2 mm, crystal Y501 3.0 mm (U602 SW / L603 on B, Y501 F).

## 6. USB budget
+3V3 0.667 A max / 0.88 + +5V1 0.343 A / 0.90 = 4.45 W -> 0.97 A at 4.60 V (0.75 A typical): above default USB 0.5 / 0.9 A.
CC1/CC2 only have 5.1k Rd (not sensed), so the board cannot tell a 1.5 A source from a default port. F601 1.5 A hold at 23 C.

## 7. Findings
- RP-1 (medium) LM27762 output capacitors on B.Cu through vias at OUT- pins (DS 7.4.1: top layer, no vias; user via rule).
- RP-2 (medium) U604 OUT- worst-case headroom 0.06-0.11 V, not 0.14 V; BUF802 minimum still met (VS- 4.555 V).
- RP-3 (medium) VBUS hot plug: SMAJ5.0A clamp about 9 V vs U603 6.0 V abs max; damper C632 DNP; OVP 0.25 V above 5.25 V.
- RP-4 (medium, known) USB current 0.75-0.97 A with no CC sensing.
- RP-5 (low) U603 PGND return 3.6 mm and LM27762 CCP returns 3.6-4.0 mm, twice the supply side.
- RP-6 (low) +3V3 3.21-3.42 V with 1 % divider (docs 3.25-3.38); +1V2 1.17-1.23 V.
- RP-7 (low) 20th / 24th harmonics of the buck / pump at 48.0 MHz; TPS63802 2nd harmonic on 3.125 MHz (documented).
- RP-8 (low) U602 SW / L603 3.0 mm from Y501 (opposite side, 4 planes between).
- RP-9 (low) C618 / C619 without part numbers; CCP >= 2 uF effective at 3.3 V not verifiable.
