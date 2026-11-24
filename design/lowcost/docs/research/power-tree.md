# Power tree redesign (findings PDN-1..8, DECOUPLING-4, BIASTEE-1, PARTS-6)

Research note, 24 Nov 2026. Datasheets read: TI SLUSEG9E (TPS62A0x), SLVSEU9D (TPS63802), SNVSAF7C (LM27762), SBVS263B (TPS7A39),
Diodes AP2112 rev, plus the load datasheets already in the project (TRF37D73, TLV3801, TPH2501, COS3502, Si5351/MS5351M, BUF802, GVA-84+, GW1NZ DS841).
Prices: LCSC product pages read 24 Nov 2026 (unit price at the smallest break). Decision: 7 regulator types become 3; AMS1117, AP2112K, MT3608, LP2985, LM27761, LP5907 and LM337 go.

## 1. Rail loads (netlist `kicad/export/scope-fe.net` + datasheets)
| Rail | Loads (typ / max mA) | Typ | Max |
|---|---|---|---|
| +3V3 | TRF37D73 x5 265/325 (SLASE43 ICC 53/65); COS3502 x8 53/~69 (3.3 mA/ch typ, no max); STM32G474 ~40/~60 (est.); MS5351M 31/55 (IDD 24/38 + 3 outputs 2.2/5.6); GW1NZ VCCIO/VCCX ~20/~30 (est.); SN65LVDS2 4/7; TPH2501 U202 6.5/7.5; LED 2; +1V2 buck input 9/13; +/-2V5 converter input 82/98 | 513 | 667 |
| +1V2 | GW1NZ-1 core (est.) | 20 | 30 |
| +5V (4.80 V) | BUF802 35.5/40 (R_Bias 17.8k, CL mode); OPA197 1.0/1.3 | 37 | 41 |
| -5V (-4.81 V since 24 Nov, section 12) | BUF802 35.5/40; OPA197 1.0/1.3 (-2V5 no longer hangs here) | 37 | 41 |
| +2V5 | TLV3801 20/26.6; TPH2501 U201 6.5/7.5; VTAP_P 12.5 (16 x 2.2k pairs); CLH divider R108 1; TLV9001, TMUX136 0.1 | 40 | 48 |
| -2V5 | TLV3801 20/26.6; U201 6.5/7.5; VTAP_N 12.5; CLL R110 1; R303/R305/R384/R734 networks + VNEG_REF ~2 | 42 | 50 |
| +5V1 (new) | GVA-84+ x2 216/260 (108 typ, 130 max each); LM27762 A input 74/83 | 290 | 343 |

## 2. Chosen tree
(Set-points updated 24 Nov 2026, SPEC decisions 25 / 26: values in brackets; tolerances and headroom in section 12.)
```
USB-C VBUS 4.75-5.25 V -> F601 PTC -> D601 TVS -> FB601 -> VBUS (4.60-5.25 V at the converters, 0.16 ohm chain at 0.95 A)
 |- U601 TPS62A01A buck 2.4 MHz FPWM -> +3V3 3.315 V [3.327 V, 100k/22k] (TRF37D73 x5, COS3502, FPGA IO, MCU, LVDS rx)
 |     |- U602 TPS62A01A buck 2.4 MHz FPWM -> +1V2 (FPGA core)
 |     |- FB605 -> U605 LM27762 B (pump 2 MHz + LDOs) -> +2V5 / -2V5 [+2.520 / -2.440 V] -> FB606 / FB607 -> loads
 |     |- FB608 (new) -> MS5351M VDD/VDDO;  FB701 (exists) -> MCU VDDA
 |- U603 TPS63802 buck-boost FPWM 1.4-2.1 MHz -> +5V1 5.10 V [5.40 V, 19.6k/2.0k 0.1 %]
       |- GVA-84+ x2 bias tees [each via its own 2.49 R, R419 / R420] -> Vd 4.86-5.10 V [4.82-5.20 V]
       |- FB602 -> +5V1F -> U604 LM27762 A -> OUT+ 4.80 V -> FB604 -> +5V ; OUT- -4.64 V [-4.81 V] -> FB603 -> -5V (BUF802, OPA197)
```
Net names +5V / -5V are kept (values 4.80 / -4.64 V) so the analog sheets need no edits. The buck-boost replaces the boost because the
USB input spans the 5.1 V target (4.60-5.25 V): a boost cannot regulate when VIN > VOUT and pulse-skips near it (PDN-8). The
GVA-84+ move from VBUS to +5V1 fixes BIASTEE-1 and PDN-8 together.
+3V3 is the buck directly, no LDO after it: ripple about 0.4-0.9 mV pp at 2.4 MHz (section 4) against the FPGA VCCIO allowance of 5 %
(DS841 table 3-2 note 3), saturated TRF37D73 stages and COS3502 comparators with a 17 mV threshold; a 3.6 V buck + 0.7 A LDO would add
0.2 W and a part for no visible gain. The clock and ADC supplies get LC filters instead (MS5351M: new FB608 + moved 1 uF; VDDA: FB701 exists).

## 3. Per-regulator table
| | U601 TPS62A01A | U602 TPS62A01A | U603 TPS63802 | U604 LM27762 A | U605 LM27762 B |
|---|---|---|---|---|---|
| Vin in circuit | 4.60-5.25 | 3.22-3.43 | 4.60-5.25 | 5.319-5.466 (after FB602; was 5.03-5.15) | 3.24-3.37 (after FB605) |
| Vout | 3.327 (100k/22k 1 %; was 3.315 with 22.1k): 3.224-3.433 | 1.200 (100k/100k), 1.17-1.23 | 5.400 (19.6k/2.0k 0.1 %; was 5.103): 5.334-5.466 | +4.800 (300k/100k 1 %), -4.808 (150k/51k 1 %); 4.66-4.95 each | +2.520 (110k/100k 1 %), -2.440 (100k/100k 1 %); +/-2.5 % |
| Load typ/max | 0.51/0.67 A | 20/30 mA | 0.29/0.34 A | 37/41 mA each side | 40/48 (+), 42/50 (-) mA |
| Dropout (DS) | 100 % mode: VIN >= VO + I(RDSON_HS 0.18 + R_L 0.05) = 3.53 V (sec. 7.3.2 eq. 1, table 6.5) | VIN-VO 2.1 V, n/a | buck-boost: regulates for VIN above and below VO (sec. 9.4) | OUT+ 45 mV at 100 mA (5.5 table, Fig 5-3, ~20 mV at 41 mA); OUT-: VCP = VIN - RNEG x I, RNEG 2.5 ohm (Fig 5-4, 4 ohm used hot), LDO 30 mV at 100 mA | same; RNEG at 3.3 V not specified, 5 ohm assumed |
| Margin | >= 1.07 V | 2.0 V | n/a | OUT+ >= 0.355 V; OUT- worst case 5.319 - 41 mA x 4.5 R - 0.026 - 4.952 = 0.156 V, typ 0.38 V (section 12; was 0.06-0.11 V) | OUT+ 3.24 - 2.58 = 0.66 V; OUT- 3.24 - 0.25 - 0.03 - 2.50 = 0.45 V |
| Abs max / ROC | VIN 6.5 / 5.5 V: OK (hot-plug: sec. 7) | OK | VIN, VOUT 6.0 V; VO ROC <= 5.2 V exceeded (5.47 V max, user-approved), VOUT OVP 5.5 V min: 34 mV margin (open, section 12) | VIN 5.8 / 5.5 V: 5.466 OK | OK |
| Dissipation, Tj at 25 C | 0.19 W typ / 0.30 W max (eta 0.90 / 0.88 assumed), RthJA 157 K/W -> +27 / +45 K | < 5 mW | 0.13 / 0.20 W (eta 0.92 / 0.90 est.), 81 K/W -> +11 / +16 K | 0.032 / 0.040 W (eq. 5), 62.2 K/W -> +2 K | 0.067 / 0.088 W, +4 / +6 K |
| CIN (derated) | C603 10u 0805 25 V X5R (~5.5 uF at 5 V) + C602 100n; DS: 4.7 uF | C609 10u 0805 (~7 uF) + C607 1u | C601 22u 0805 (~6.5 uF at 5 V); DS: >= 4 uF effective | C612 22u 0805 (~6.5 uF) + C613 100n; DS 4.7 rec., >= 2 min | C625 10u 0805 (~7 uF) |
| COUT (derated) | C604 22u 0805 (~12 uF) + +3V3 plane 7 x 10u (~42 uF) = ~54 uF; DS table 8-3 proven 10-2x22 uF nominal | C605 22u (~18 uF at 1.2 V) + C608 1u + C503 10u; DS 22 uF | C610 + C611 22u 0805 (~13 uF); DS >= 7 uF eff., 2 x 22 rec. above 3.6 V | CCP C626 10u 0805 (~5 uF, DS >= 2 uF); C1 C618 1u 0603 25 V; OUT+ C617 10u, OUT- C621 10u (~5 uF each, DS 2.2 uF) | CCP C619 4.7u 0603 (~2.5 uF); C1 C624 1u 0402; OUT+ new 10u 0805, OUT- C628 10u (~8 uF each) |
| L / other | L602 1 uH 1008, 2.5 A (Isat 3.5 A); peak 0.87 A, ILIM 1.8 A max | L603 1 uH 1008 | L601 0.47 uH 4.4 x 4.2, +/-20 % (DS 0.37-0.57 uH eff.); Ipeak 0.65 A (eq. 2) | PGOOD to GND; EN+/EN- to VIN | EN+/EN- = U603 PG, 100k pull-up to U605 VIN |
All capacitors are MLCC; every part above is specified for ceramic output capacitors (no ESR window). Effective values: 22u 6.3 V 0805
~6.5 uF at 5 V / ~12 uF at 3.3 V; 10u 25 V 0805 ~5 uF at 5 V / ~7-8 uF at 2.5-3.3 V; 1u 0402 ~0.5 uF at 3-5 V (validation pdn.md factors).
+3V3 COUT above the proven 2 x 22 uF is the plane decoupling behind 15-70 mOhm of plane: keep only one 22 uF at U601 (C605 moves to
+1V2), fit a 0402 Cff footprint (120 pF, DS 8.2.2.3) on R1 and check the load step on the first build.

## 4. Noise and PSRR path (sampler floor 0.35 mV rms at the hold node)
| Path | Source | Attenuation | At the load |
|---|---|---|---|
| LM27762 pump -> +/-5V -> BUF802 | 1-2.5 mV pp at OUT (DS Fig 5-1, +/-3 V, 50-100 mA) | bead 600R (~19 ohm at 2 MHz, est.) into 1-5 uF at the load: -45 dB; BUF802 PSRR 49 dB (VS+) / 38 dB (VS-) at 100 kHz, >= 20 dB assumed at 2 MHz | < 1 uV at BUF802 out |
| LM27762 LDO noise | 22 uV rms 10 Hz-100 kHz (5.5 table) | BUF802 PSRR >= 38 dB | < 0.3 uV rms |
| LM27762 B -> -2V5 -> hold node | same 1-2.5 mV pp; 22 uV rms | FB607 + 2.2 uF: -45 dB; -2V5 to pedestal 0.09 V/V (theory sec. 7) | ripple < 1 uV, noise 2 uV rms (0.6 % of 0.35 mV) |
| -2V5 -> trigger level | 22 uV rms | 0.14 V/V | 3 uV rms |
| TPS62A01A -> +3V3 | dIL 0.39 A pp (1 uH, 2.4 MHz) -> 0.4-0.9 mV pp on ~25-55 uF | FPGA allows 165 mV; FB605 + C625 + LM27762 PSRR (43-50 dB at 10 kHz, Fig 7-3/7-4) for +/-2V5 | uV level at +/-2V5 |
| TPS63802 -> +5V1 -> GVA Vd | ~2.5 mV pp (0.5 A pp / 8 f C, 13 uF) | 2.2 uH tee + 10 uF cold end: -58 dB at 1.4 MHz | < 5 uV; LM27762 A input via FB602 + 22 uF |
Frequencies: buck 2.4 MHz (2nd harmonic 4.8 MHz; but 20 x 2.4 = 48.0 MHz and LM27762 24 x 2.0 = 48.0 MHz land on the
PH strobe at nominal frequency, recheck RP-7: free-running, slow beats possible; look for beat spurs in a flat-input capture on bring-up); LM27762 1.7-2.3 MHz; TPS63802 1.4 MHz (buck-boost) to 2.1 MHz
(boost) in FPWM, so its 2nd harmonic can sit near 3.125 MHz and harmonics near 48 MHz. Its residue at the sensitive nodes is below
5 uV by the chain above, so an aliased beat stays far under the floor. TLV62569 (1.5 MHz, 2nd harmonic 3.0 MHz) was avoided for that reason.
Ripple at the hold node from all paths: a few uV, << 0.35 mV. Accuracy of -2V5: FB- 1.5 % + 1 % divider = +/-2.5 % (+/-61 mV at -2.44 V, section 12) vs LM337 +/-3 %;
calibrated as before (trigger +/-8.5 mV, pedestal +/-5.5 mV). TLV3801 VCC-GND >= 2.52 x 0.975 - 7 mV bead - 9 mV track = 2.44 V >= 2.4 V min.
BUF802: VS >= 4.65 + 4.66 = 9.31 V >= 9 V (ROC 5.3), each side >= 4.5 V (section 12; was 9.30 V). GVA Vd = 5.334..5.466 - 2.49 R feed - tee = **4.82-5.20 V** (spec 4.8-5.2; section 12),
independent of USB voltage. LM27762 output is PFM at light load (DS 7.2.2.4.1): CCP kept >= 2 uF effective to avoid toggling.

## 5. USB budget (4.75 V at the connector)
+3V3: 3.3 V x 0.513 A / 0.90 = 1.88 W; +5V1: 5.10 V x 0.290 A / 0.92 = 1.61 W; total 3.49 W -> **0.75 A typ** at 4.63 V (was 0.86 A).
Sum of all maxima: 2.50 + 1.97 = 4.47 W -> 0.97 A. The 500 mA target is not reachable: the RF loads alone (5 x TRF37D73 0.87 W,
2 x GVA-84+ 1.08 W) need 0.42 A from 4.75 V before losses. A 5 V / 1.5 A USB-C source stays required (as now).

## 6. Parts (new and changed)
| Ref | Part | Package | LCSC | USD/board |
|---|---|---|---|---|
| U601, U602 | TPS62A01ADRLR (FPWM) | SOT-563 1.6 x 1.6, P0.5; 1 GND, 2 SW, 3 VIN, 4 EN, 5 FB, 6 PG | C5181455 (10k stock) | 2 x 0.197 |
| U603 | TPS63802DLAR | VSON-HR-10 2 x 3, P0.5, no EP; 1 EN, 2 MODE, 3 AGND, 4 FB, 5 PG, 6 VOUT, 7 L2, 8 GND, 9 L1, 10 VIN | C2845237 | 0.951 |
| U604, U605 | LM27762DSSR | WSON-12 2 x 3, P0.5, EP 1.0 x 2.65 (GND); 1 PGOOD, 2 FB+, 3 VIN, 4 GND, 5 CP, 6 OUT-, 7 FB-, 8 EN-, 9 C1-, 10 C1+, 11 OUT+, 12 EN+ | C473398 (36k) | 2 x 0.960 |
| L601 | 0.47 uH +/-20 %, XR0420-R47M (2nd source FEXU0420SR47MBHCB C49232844) | 4.4 x 4.2 | C5307593 (65 stock) | 0.106 |
| L602, L603 | 1 uH 2.5 A, FHD252010S-1R0MT | 1008 | C843292 | 2 x 0.076 |
| FB602-FB608 | 600R@100MHz 1.3 A, 0.15 ohm, BLM18KG601SN1D (FB602/603 retyped) | 0603 | C85833 | 7 x 0.017 |
| C (new) | 10u 25 V X5R (U605 OUT+) | 0805 | C15850 | 0.031 |
| R (new 9 + 6 changed) | U601 100k/22.1k; U602 100k/100k; U603 R603 459k, R604 49.9k; U604 300k/100k, 280k/100k; U605 130k/120k, 105k/100k; PG pull-up 100k; 0.1 % for U603-U605 dividers | 0402 | class | ~0.03 |
Removed: AMS1117 0.203, AP2112K 0.238, MT3608 0.064, LP2985 0.291, LM27761 1.231, LP5907 0.337, LM337 0.436, D602 0.025, L601 4.7 uH est 0.10
(2.93). Added 3.65. **BOM +0.73 USD -> about 63.58 USD** (limit 80). Regulator types 7 -> 3.
Moved capacitors (no new decoupling except one 10u): C603 -> U601 in; C609 -> U602 in; C605 -> U602 out; C601 -> U603 in; C610/C611 -> U603 out;
C612/C613 -> U604 in (top side at pin 3: fixes DECOUPLING-4); C618 -> U604 C1; C626 (old ADJ) -> U604 CCP; C617 -> U604 OUT+; C621 -> U604 OUT-;
C625 -> U605 in; C624 -> U605 C1; C619 -> U605 CCP; C628 -> U605 OUT-; freed C616 2.2u -> U101 +5V beside C108, C620 2.2u -> U302.3 (-2V5),
C615 1u -> U302.6 / U301.10 (+2V5) (PDN-6); C623 1u -> MS5351M VDD after FB608; C627 1u stays on -5V after FB603; C614 10n unused.
Voltage ratings: 5 V nodes (C601, C610-C612) need >= 10 V parts; C45783 is 6.3 V (keep only on +3V3 / +1V2) - LCSC # for a 10 V 22u 0805 to assign.

## 7. Layout notes (datasheet layout sections)
- TPS62A01A (8.4.1): CIN between VIN (3) and GND (1) on the IC layer, < 1 mm; hot loop CIN-VIN-HS/LS FET-GND; inductor at SW (2), small SW copper;
  COUT ground back to pin 1; FB divider at pin 5 away from SW.
- TPS63802 (12.1): both CIN (10/8) and COUT (6/8) are hot loops (buck and boost phases); place both tight on the top side; L between L1 (9)
  and L2 (7); AGND (3) by its own trace to GND near pin 8; FB (4) away from L1/L2. MODE (2) and EN (1) tied to VIN (never floating).
- LM27762 (7.4.1): CIN, CCP and C1 on the IC layer; CIN and CCP grounds join at GND (4); COUT+/COUT- grounds to the EP; R1-R4 at the FB pins,
  low ends to the EP ground. U605 placed in the power block like U604; the +/-2V5 beads at the regulator outputs.
- GVA feed: track from the U603 output capacitors to the L404/L406 cold ends (not through FB602). Hot-plug: USB cable L + all-MLCC
  input can ring above the 6.0 / 6.5 V abs max of U603 / U601 (SMAJ5.0A clamps at 9.2 V). Add a DNP footprint for a 1 ohm + 10 uF damper
  (or 47 uF tantalum, C22036, 10 V) on VBUS and measure the plug-in transient on the first board.

## 8. Sequencing
- U601 soft start 1 ms (6.5 table): +3V3 ramps 3.3 mV/us (GW1NZ VCCIO/VCCX 0.1-10 mV/us, DS841 table 3-3). U602 EN = +3V3, starts at its
  UVLO 2.3-2.5 V and ramps 1.2 mV/us (VCC 0.6-6 mV/us). AP2112K (20 us start-up) could exceed 6 mV/us: one reason for the buck.
- U603 starts from VBUS; U604 EN+/EN- = VIN, so the BUF802 rails come with +5V1. U605 is enabled by U603 PG: +/-2V5 (and the CLH/CLL clamp
  dividers, TMUX136, TLV3801) rise only after the BUF802 rails, so no clamp pin is driven above an unpowered BUF802 rail.
- TLV3801 VCC and VEE come from one IC with one enable: they rise together. LM27762 gives no start-up slope: the TMUX136 100-1000 us/V
  VCC ramp is unverified (open; bring-up step 1 already measures it).

## 9. Alternatives rejected
- TPS7A39 dual +/- LDO (+/-2V5 from +/-5 V): 5.67 USD at LCSC with 0 stock; 3 x 3 WSON. LM27762 does both rails for 0.96.
- TPS65131 / TPS65132 split-rail converters: 4 x 4 QFN-24 or DSBGA + I2C, about 2 USD, and the outputs still need LDOs for the BUF802.
- Keep MT3608 boost at 5.15 V: cannot regulate at USB 5.25 V and pulse-skips at D < 0.1 (PDN-8); non-synchronous diode loss.
- Negative LDOs (TPS7A30, LT1964, ADP7182) for -2V5: 1.5-3 USD each and still need a separate +2V5 regulator.
- TLV62569 1.5 MHz SOT-23-5: cheapest (0.067) but 2nd harmonic at 3.0 MHz near the 3.125 MHz strobe.
- Buck to 3.6 V + LDO to 3.3 V: +0.15-0.2 W and one more part for loads that tolerate 1 mV ripple.
- LM27762 B fed from +5V1: 0.25 W instead of 0.07 W and +0.05 A from USB.
- Chinese dual-output charge-pump / split-rail parts: none with a verified datasheet and LCSC stock found in this pass (not evaluated).

## 10. Open
Hot-plug transient vs 6 V abs max; TMUX136 ramp; LM27762 RNEG at 3.3 V (assumed 5 ohm, 0.42 V margin); COS3502 / MCU / FPGA maxima
are estimates; XR0420-R47M stock 65 (2nd source listed, its land not checked); board footprints for VSON-HR-10
(now `scope-fe:Texas_DLA0010A_VSON-HR-10_2x3mm_P0.5mm`) and WSON-12 (KiCad `WSON-12-1EP_3x2mm_P0.5mm_EP1x2.65`, matches DSS0012B).

## 11. Corrections and additions made in the schematic (24 Nov 2026, `kicad/gen/gen_power.py`)
- **Error fixed:** C45783 (CL21A226MAQNNNE) is a **25 V** 22u 0805 (LCSC page), not 6.3 V. C601, C604, C605, C610-C612
  keep it; no 10 V part is needed (section 6 last line and section 10 item withdrawn).
- **Error fixed:** C618 (1u 0603) carried C52923, an 0402 part number; the LCSC field is now empty (1u 0603 25 V to assign).
- C614 (10n) is not left unused: it moves to BUF802 U101 pin 10 (VSO-, top side), the DECOUPLING-1 fix without a new part.
- C606 and C622 (100n, not listed above) move to the TRF37D73 U401 / U402 VCC pins (PDN-7, +3V3); -5V keeps C627 1u at
  FB603 plus the BUF802 local capacitors.
- FB608 and C623 are drawn on the fpga_clock sheet (net +3V3_CLK). C508 / C509 (100n, one per MS5351M supply pin) and
  C510 (10u) also move behind FB608: with about 8 uF effective the bead (about 1.5 uH at low frequency, assumed)
  resonates near 45 kHz with Q about 3, instead of about 120 kHz with Q about 7 with 1.2 uF.
- U605 PGOOD to GND (as U604). Divider resistors of U603-U605 are 0.1 % (R603 459k is an E192 value).
- Added DNP footprints: C631 120 pF (U601 Cff) and C632 47 uF 10 V tantalum (C22036, VBUS damper, section 7).
  Recheck RP-3 (24 Nov): C632 is now fitted by default (0.25 USD).
- Generated BOM: **63.76 USD** (limit 80), against the 63.58 estimate in section 6.

## LCSC verification (24 Nov 2026)

- R603 / R604 are now **499k / 54.2k** 0.1 % (AR02BTC4993 C6466287, RT0402BRD0754K2L C852840): no 459k 0.1 % 0402 is
  stocked on LCSC. VOUT = 0.5 x (1 + 499/54.2) = 5.103 V; with FB +/-1 % 5.05-5.15 V (within 5.04-5.16).
- L601 is FXL0420-R47-M (C167200, 10.6k stock): 0.47 uH +/-20 %, 14 mR, Isat 7.6 typ / 9.5 A, same body and recommended
  land (a 2.2 / b 5.2 / c 2.5 mm) as XR0420-R47M, which stays the alternative (C5307593, 65 stock).
- C618 1u 0603 -> CL10B105KA8NNNC C29936 (25 V X7R), C619 4.7u 0603 -> 0603X475K160NT C99229 (16 V X5R): C15849 / C19666
  had 0 LCSC stock. C616 / C620 2.2u 0402 10 V -> CL05A225KP5NSNC C107369. FB601 -> BLM21PG221SH1D C88994.
- 0.1 % 25 ppm/K dividers: see `docs/bom.md` (LCSC column) and `kicad/gen/common.py` `LCSC_R01`.

## 12. 1 % dividers, +/-4.8 V and +5V1 5.40 V (24 Nov 2026, SPEC decisions 25 and 26)

User instructions: no 0.1 % resistors unless unavoidable, JLC basic parts for R / C, BOM consolidation; then (approved
change) +5V1 raised to about 5.35 V, both U604 outputs at +/-4.8 V nominal, OUT- worst-case headroom > 0.15 V with
41 mA x 4.5 ohm pump resistance, GVA-84+ drain kept in 4.8-5.2 V with a series drop. Datasheets re-read for this
(TI SLVSEU9D TPS63802, SNVSAF7C LM27762): TPS63802 VFB 500 mV +/-1 % (PWM), IFB <= 100 nA, R2 <= 100k, VO recommended
1.8-5.2 V, **VOUT OVP threshold 5.5 / 5.7 / 5.9 V**, abs max 6 V; LM27762 VFB+ 1.2 V +/-1.5 %, VFB- -1.22 V +/-1.48 %,
**R2 and R4 >= 50 kohm**, VIN 2.7-5.5 V (abs max 5.8 V), RNEG 2.5 ohm at 5.5 V / 100 mA, LDO- 30 mV at 100 mA.
Worst case below = reference tolerance + 2 x 1 % x R1 / (R1 + R2) for a 1 % divider (0.2 % for 0.1 %).

| Rail | Divider (was) | Nominal | Worst case | Requirement, margin |
|---|---|---|---|---|
| +5V1 (U603) | R603 / R604 19.6k / 2.0k **0.1 %** (499k / 54.2k 0.1 %) | 5.400 V (5.103) | 5.334-5.466 V (incl. IFB x R1 = 2 mV) | U604 headroom needs >= 5.326 V (below); <= 5.5 V (LM27762 ROC, TPS63802 OVP min): 34 mV. A 1 % divider gives +/-2.8 % = +/-0.15 V > the +/-0.087 V window: 0.1 % unavoidable |
| U604 VIN | after FB602 (82.5 mA x 0.15 ohm) and 3 mV track | 5.385 V | 5.319-5.466 V | <= 5.5 V ROC: OK |
| +5V (U604 OUT+) | R613 / R614 300k / 100k 1 % (0.1 %) | +4.800 V | 4.656-4.944 V | BUF802 >= 4.5 V after FB604 (6 mV): 4.650 V; LDO+ headroom 5.319 - 4.944 - 0.020 = 0.355 V |
| -5V (U604 OUT-) | R605 / R606 150k / 51k 1 % (280k / 100k 0.1 %) | -4.808 V (-4.636) | -4.664 ... -4.952 V | BUF802 >= 4.5 V: 4.658 V; headroom 5.319 - 0.041 x 4.5 - 0.026 - 4.952 = **0.156 V** (> 0.15 V; typ 5.385 - 0.185 - 0.013 - 4.808 = 0.38 V) |
| BUF802 total | | 9.61 V | 9.31-9.89 V | 9-10.5 V |
| +2V5 (U605 OUT+) | R615 / R616 110k / 100k 1 % (130k / 120k 0.1 %) | +2.520 V (2.500) | 2.456-2.584 V | TLV3801 VCC-GND >= 2.4 V after 16 mV: 2.44 V; headroom 0.66 V |
| -2V5 (U605 OUT-) | R607 / R608 100k / 100k 1 % (105k / 100k 0.1 %) | -2.440 V (-2.501) | -2.380 ... -2.500 V | headroom 3.24 - 0.01 - 0.25 - 0.03 - 2.50 = 0.45 V; +2V5 + abs(-2V5) <= 5.08 V (TPH2501 / TLV9001 / TLV3801 5.5 V) |
| +3V3 (U601) | R609 / R610 100k / 22k 1 % (100k / 22.1k 1 %) | 3.327 V (3.315) | 3.224-3.433 V | TRF37D73 <= 3.45 V, GW1NZ VCCIO 3.3 V +/-5 % |
| +1V2 (U602) | 100k / 100k 1 % (unchanged) | 1.200 V | 1.17-1.23 V | unchanged |

R2 / R4 >= 50k leaves 51k, 100k, 200k and 1M as JLC basic bottom resistors; 300k, 150k and 110k (tops) are extended
(300k is shared with the input divider string). -2V5 at -2.44 V (+/-2.5 %) moves TRIG_LEVEL by 0.139 V/V and VBIAS_A by
0.607 V/V: both calibrated / trimmed per board (kicad/README.md control-voltage table).

**GVA-84+ drain** (DS 4.8-5.2 V, 85-125 mA used): per chain +5V1 -> 10 uF -> R419 / R420 2.49 ohm 1 % 0402 (Vishay
CRCW04022R49FKED, C2085509) -> 100 nF / 1 nF -> 2.2 uH (LQM21PN2R2, DCR 0.125 ohm max, 0.07 assumed min) -> BLM15HD102
bead (1.25 ohm max, 0.6 ohm assumed min; Murata gives only the maximum) -> pin 3; trunk drop 0-30 mV. Vd max = 5.466 -
0.085 x (2.49 + 0.67) = **5.198 V**; Vd min = 5.334 - 0.03 - 0.125 x (2.51 + 1.375) = **4.82 V**; nominal (110 mA, 1.0 /
0.1 ohm) 4.99 V. If the bead's DCR were near 0, the maximum would be 5.25 V at 85 mA: measure Vd at TP404 / TP406 on the
first board. Dissipation 30 mW typ / 39 mW max in a 62.5 mW 0402. No existing footprint could be reused (the feed is
choke + RF bead only, both stay), so R419 / R420 were added: B side, below C419 / C429, fed from the C420 / C430 pad;
the old +5V1 via pair beside C419 / C429 was removed (layout/board/blocks/pstrobe/README.md).

**Other +5V1 loads at 5.466 V:** C610 / C611 / C612 22 uF 25 V 0805 (about 6 uF each at 5.4 V; TPS63802 CO >= 7 uF
effective: about 12 uF), C613 / C419 / C429 100 nF 16 V, C418 / C428 1 nF 50 V, C420 / C430 / C626 / C617 / C621 10 uF
25 V, C618 1 uF 50 V (now C15849); FB602 1.3 A. C632 (47 uF 10 V tantalum) and D601 (SMAJ5.0A) sit on VBUS, unchanged.
U604 dissipation (5.39 - 4.80) x 41 mA x 2 = 0.05 W. **USB budget** (section 5 updated): +5V1 5.40 V x 0.294 A / 0.92 =
1.73 W typ (2.02 W max), total 3.61 W -> **0.78 A typ** at 4.63 V, 0.98 A max (was 0.75 / 0.97 A).

**Open:** +5V1 is above the TPS63802 recommended VO maximum (5.2 V; the datasheet footnote puts the accuracy and load-step
margin into the 6 V abs max) and 34 mV under the minimum VOUT OVP threshold (5.5 V): a load step or start-up overshoot
could trip the OVP; check on the first board, fallback: a lower +5V1 set-point with correspondingly less U604 OUT- headroom.
