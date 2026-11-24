# BOM review 2: +5V1 divider, inductors / beads, USB input, resistor defragmentation (24 Nov 2026)

Scope: the user's review items on the 0.1 % divider, "four inductor types and three bead types", PTC -> 0 R, TVS DNP,
tantalum -> MLCCs, TLV9001, BAT15-03W, and the extended resistor values. This file only proposes: schematic, layout and
BOM are unchanged. Not repeated here (other BOM-2 notes): R119 / R118 / R123 / RV101 / C106 (bom2-input-taps.md),
U301 / R303 / R305 / C303 deleted with the TMUX136 (bom2-trigger.md).
JLC class / stock: jlcpcb.com search API (library filter "base": 30 values 0402WGF, 80 values 0603WAF, 4 beads, 2 inductors
(10 uH multilayer, 3-15 mA): no basic power inductor); LCSC detail JSON for parameters; read 24 Nov 2026. Checks run in scratch
(repo scripts imported unchanged): hot-plug ngspice deck, sim/bias_tee + 1 uH model, sim/strobe chain / extras, sim/strobe_arms
(rail R, D401 swapped), sim/bom2_taps deck_ab (r_term_s), sim/bom2_input deck (bias resistors swapped).

## A. +5V1 without 0.1 % resistors
**GVA-84+ supply (Mini-Circuits datasheet + typical data GVA-84+_VIEW.pdf, fetched).** "Device operating voltage 4.8 / 5.0
/ 5.2 V" is the characterised range, not an absolute limit (abs max 5.8 V on pin 3, 160 mA). Typical data, 25 C, Vd 4.75 /
5.00 / 5.25 V: Icc 92 / 106 / 121 mA, gain at 2 GHz 18.44 / 18.57 / 18.66 dB, P1dB at 2 GHz 19.89 / 20.88 / 21.61 dBm. So P1dB moves about 4 dB/V, gain 0.5 dB/V; current 0.058 mA/mV. (-45 C at 4.75 V: P1dB 18.0 dBm, 2.8 dB down.)
At 4.71 V (worst case below): P1dB about -1.2 dB = -12 % saturated swing. Strobe chain model (GVA Vsat 3.6 -> 3.15 V):
step into 50 R 7.14 -> 6.27 V; phase gates need >= 2.0 V and get >= 2.75 V with the 80 ps stub at nominal
(phase_array RESULT), so >= 2.4 V worst (20 % margin). The sampler strobe (2 x TRF37D73 on +3V3) is not affected.

**Options.**
1. **TPS63802 with a 1 % basic divider (recommended).** Best basic ratio below the 5.20 V limit: R603 **20k** /
   R604 **2.2k** (9.091). VFB 0.5 V +/-1 %, 1 % parts, IFB 100 nA x 20k: **+5V1 4.904 / 5.045 / 5.191 V** (max <= 5.20 V
   recommended maximum, 0.31 V below the 5.5 V OVP minimum). 47k/5.1k (9.216) would reach 5.25 V.
   GVA feed drop: trunk 30 mV + 125 mA x (1 uH DCR 0.048 + bead 1.25) -> **Vd 4.71 / 4.92 / 5.19 V** (0.1 % version
   4.85-5.17 V). Consequence: up to -1.2 dB GVA P1dB at the worst corner, -0.3 dB nominal; phase margin above.
2. **Fixed / other converters (rejected).** TPS63002 fixed 5 V (C116655, 1.99 USD, 2021 stock, VSON-10 3x3,
   extended): output accuracy not specified beyond VFB +/-1 % of the adjustable part plus 0.5 % line / 0.5 % load
   typical, so no better than option 1, and 1.25-1.5 MHz puts its 2nd harmonic at 2.5-3.0 MHz beside the 3.125 MHz
   strobe (the reason TLV62569 was rejected). TPS630701 (2.0-2.6 USD, VQFN-15), TPS63020 (0.98, 2.4 MHz, adjustable,
   same VFB +/-1 %), TPS63805/06/10 (DSBGA): no tighter reference. Boosts (TPS61022/23 class) cannot regulate at
   VBUS 5.25 V > 5.1 V. JLC basic DC-DC: only TPS5430 and XL1509 (buck, VIN >= 4.5-5.5 V): no fit.
3. **Feeding differently (rejected).** GVA or LM27762 from VBUS: 4.60-5.25 V at the converters, worse than option 1.
   The series drops are reduced instead: L404/L406 2.2 uH (DCR 0.125-0.16) -> 1 uH 1008 (0.040, section B),
   FB602 0.15 -> 0.05 ohm, FB603/FB604 0.15 -> 0.05 ohm (BLM18PG121SN1D).

**BUF802 rails from U604 (LM27762) for option 1.** U604 VIN = +5V1 - FB602 (83 mA x 0.05) - 3 mV = 4.897 / 5.039 / 5.191 V.
LM27762: VFB+ 1.2 V +/-1.5 %, VFB- -1.22 V +/-1.48 %, R2 / R4 >= 50k, OUT+ dropout ~20 mV at 41 mA, OUT- headroom
= VIN - 41 mA x 4.5 ohm (RNEG hot) - 26 mV - |OUT-|. Exhaustive search over basic values (0402 and 0603, bottoms
>= 51k): **no all-0402 basic combination reaches 9.0 V** (best 7.05 V; the 0402 basic set has no top for ratio ~3).
With 0603 basic tops / bottoms:
| Rail | Divider (was) | Min / nom / max | Check |
|---|---|---|---|
| +5V (OUT+) | R613 **470k 0603** / R614 **150k 0603** (309k / 100k) | +4.812 / +4.960 / +5.111 V | regulates at every corner (4.812 < VINmin - 0.02 = 4.877); nominal 59 mV headroom |
| -5V (OUT-) | R605 **510k 0603** / R606 **200k 0402** (270k / 100k) | -4.206 / -4.331 / -4.459 V | OUT- headroom 4.897 - 0.185 - 0.026 - 4.459 = **0.227 V** (>= 0.15) |
| BUF802 total | at the pins, FB603/FB604 0.05 ohm, 3 mV tracks | **9.008 / 9.29 / 9.57 V** | >= 9.0 V worst case (8 mV margin, all extremes stacked); mid-supply +0.31 V |
| +2V5 (U605) | R615 **220k 0603** / R616 **200k 0402** (110k / 100k) | 2.456 / 2.520 / 2.585 V | unchanged nominal; R616 bottom 200k |
| -2V5 | R607 / R608 100k / 100k (unchanged) | -2.380 / -2.440 / -2.500 V | sum max 5.085 V <= 5.5 V |
BUF802 output swing VS- + 3.4 V = **-0.81 V** worst (needs -0.5 V: 0.31 V margin, was 0.475 V); VS+ - 2.0 V = +2.81 V.
CLH +1.5 V >= mid-supply +0.31 V; CLL -1.5 V <= mid-supply: inside the clamp ranges. 1 % 0402 alternative that keeps all
footprints (R613 / R605 200k / 100k: 3.60 / -3.66 V) gives 7.05 V: rejected. **Decision: option 1** (no 0.1 %, no new IC).

## B. Inductors and ferrite beads
| Present type | Where, current | Needed property | Decision |
|---|---|---|---|
| 47 uH LQH32CN470K23L 1210 x5 | L401 sampler TRF #1 (3.125 MHz square into the 12 dB pad), L302 line driver (1 kHz-3 Gbps), L402 sampler TRF #2, L403/L405 phase TRF #1; 53-65 mA | L >= 22-47 uH only where a stage drives 50 R at <= 3 MHz content | **keep for L401, L302 only** |
| 2.2 uH LQM21PN2R2 0805 x2 | L404/L406 GVA tees, 108-130 mA | final stage drives a shorted stub: below 300 MHz the line is shorted, choke value irrelevant (bias_tee RESULT) | **-> 1 uH 1008** |
| 1 uH FHD252010S-1R0MT 1008 x2 | L602/L603 TPS62A01A, peak 0.87 A, ILIM <= 1.8 A | TPS62A01 table 8-3: 1 uH only (0.47 uH listed for TPS62A02 only) | **-> DFE252012F-1R0M** (TI's listed part; FHD has 262 in stock) |
| 0.47 uH FXL0420-R47-M x1 | L601 TPS63802, Ipk 0.65 A | TPS63802: 0.37-0.57 uH effective only (table 10-1) | **keep** (cannot share 1 uH) |
**1 uH DFE252012F-1R0M (C435392, Murata, 1008, Isat 3.3 / 4.7 A, 40 mR, 68k stock, 0.101 USD) for L402-L406, L602, L603.**
Bias-tee AC re-run (sim/bias_tee models, BLM15HD102 S2P fit, 1008 pads; 1 uH SRF unpublished: 60 / 120 MHz, Rp 300 R):
| Tee | Present | With 1 uH (SRF 60 / 120 MHz) |
|---|---|---|
| GVA, stub-loaded stage 0.1-6 GHz (bead x1.0 / x0.65) | -0.20 / -0.23 dB | -0.20 / -0.23 dB (identical) |
| GVA through line 30-70 MHz | -0.47 dB | -0.17 / -0.14 dB |
| phase TRF #1 tee at 30-70 MHz (with / without 1 k) | -0.28 dB (47 uH + 1 k) | -0.18 / -0.17 dB; 3-6 GHz -0.16 dB |
| TRF #2 sampler (stub-loaded) | -0.20 dB | -0.20 dB |
PH_STROBE 48-50 MHz train, TRF + 10 dB pad + GVA, real 100 nF couplings (extras.train): step into 50 R 6.73 V (2.2 uH),
**6.82 V (1 uH)**, settled in 160 ns. The 1 k across L402/L403/L405 (R416-R418) damped the 47 uH self-resonance; with 1 uH
the response is the same without it: **R416-R418 removed**. DC: TRF pins +0.06-0.1 V; converters: Isat 3.3 > ILIM 1.8 A.
Result: **3 inductor types** (47 uH x2, 1 uH x7, 0.47 uH x1), 1.70 -> 1.03 USD.

**Beads.** JLC basic: GZ1608D601TF (0603, 600 R, 200 mA, 0.45 R), BLM18PG121SN1D (0603, 120 R, 2 A, 0.05 R), GZ2012D101 / D601 (0805).
- **BLM18PG121SN1D C14709 (basic) for FB601-FB607.** FB601 USB input at 0.97 A max (49 % of 2 A; 48 mV): one part, no
  paralleling, footprint 0805 -> 0603; kept (not deleted) to keep converter switching current off the cable. FB602-FB605
  (U604 / U605 inputs, BUF802 rails): the low DCR is what makes the 9.0 V above (GZ1608D601TF on FB603/FB604 would cost
  33 mV: 8.975 V). FB606/FB607 (+/-2V5, 57 mA): TLV3801 VCC-GND >= 2.456 - 0.003 - 0.009 = 2.44 V (GZ1608: 2.42 V).
  Ripple at 2 MHz: about 3 ohm against 2.2-10 uF (16-36 mohm): -38 to -45 dB, so 1-2.5 mV pp pump ripple gives
  < 3 uV at the hold node (0.09 V/V) and < 2 uV at the BUF802 output: << 0.35 mV floor.
- **FB608 (MS5351M clock supply) -> BLM15HD102SN1D** (the existing 0402 RF-bead line): keeps >= 600 R at 100 MHz
  against FPGA noise for clock jitter; 55 mA x 1.25 R = 69 mV -> VDD >= 3.155 V (spec 2.97 V). Footprint 0603 -> 0402.
- BLM15HD102SN1D stays for the 7 RF tees and FB701: pad on the 50 R line, 1 k at 100 MHz to 3 GHz, no basic part.
Result: **2 bead types** (BLM15HD102 x9 extended, BLM18PG121 x7 basic); BLM18KG601SN1D and BLM21PG221SH1D go.

## C. USB input: PTC -> 0 R, TVS DNP, tantalum -> MLCC damper
F601 -> **0 R 1206 UNI-ROYAL 1206W4F0000T5E C17888 (basic, 1.49 M stock)**, same footprint. D601 SMAJ5.0A **DNP** (land kept).
Plug-in deck: 5.25 V step (live legacy A-to-C source; a C-to-C source turns VBUS on only after seeing Rd), cable 1.0-1.5 uH
+ 0.05-0.10 ohm loop, FB601 0.1 uH / 0.05 ohm, input ceramics C601 22u + C603 10u + C602 100n = 12 uF effective at 5 V
(20 uF bracket), 5 mohm ESR. Lowest absolute maximum on VBUS: **TPS63802 VIN / EN / MODE 6.0 V** (TPS62A01A 6.5 V;
USBLC6-2 VBUS is itself a >= 6 V clamp; no MCU VBUS sense; J501 pin 1 only passes VBUS on).
| Case (L / R / Cin) | no damper | old: 47 uF tantalum (ESR 0.5-0.9) + PTC | **4 x (1 R + 47 uF 10 V 1206)** |
|---|---|---|---|
| 1.5 uH / 0.05 / 12 uF | 8.58 V | 5.25-5.64 V | **5.27 V** (5.57 V if each 47 uF derates to 12 uF) |
| 1.0 uH / 0.05 or 1.5 uH / 0.10 ohm | 8.27 / 7.90 V | - | 5.25 / 5.25 V |
**Damper: 4 parallel branches of 1 ohm 1206 (1206W4F100KT5E C17928, basic, 250 mW) in series with 47 uF 10 V X5R 1206
(CL31A476MPHNNNE C96123, basic, ~16 uF each at 5 V assumed).** Rd 0.25 ohm (0.7 x sqrt(L/Cin)), Cd ~64 uF >= 4 Cin. Worst peak 5.57 V: >= 0.43 V below 6.0 V (0.73 V with the assumed derating). Fewer branches
(3) give 5.52 / 5.82 V, 2 x 22 uF 25 V 5.9-6.3 V: rejected. Resistor stress (3-branch run, per branch): 3.4 A / 11.7 W
peak, 0.18 mJ, 17 us decay; a 1206 thick film takes about 8x that pulse power (0805 would be about 4x). Steady
dissipation: converter ripple current into 0.25 ohm is negligible next to the 12 uF ceramics (10 mohm at 1.4 MHz).
Cost 4 x 0.175 = 0.70 USD (tantalum 0.25); the damper also damps the cable / input-filter resonance seen by the converters.

## D. Resistor defragmentation and small parts
JLC basic 0402 (all 30): 0, 10, 22, 33, 49.9, 100, 120, 200, 220, 330, 470, 510 R; 1, 1.5, 2, 2.2, 3.3, 4.7, 5.1, 10, 12, 15,
20, 22, 33, 47, 51, 100, 200 k; 1 M. 0603 basic (80) adds e.g. 47, 75 R, 18k, 150k, 220k, 300k, 470k, 510k, 2 M, 10 M.
**Pi pads (50 R, exact 0603 / 0402 positions kept):**
| Pad | Was (dB, RL) | New | Attenuation, RL in / out | Effect (strobe chain model) |
|---|---|---|---|---|
| Sampler 12 dB R402 (0603) / R404 / R403 | 82 / 91 / 82: 11.97 dB, 40 dB | **100 / 120 / 100** | 12.46 dB, 20.4 / 20.4 dB | TRF #2 input -0.5 dB (more margin to +10 dBm); edge 141.6 -> 144.7 ps; step 4.59 V same |
| Line driver 12 dB R307 / R308 / R309 | 82 / 91 / 82 | **100 / 100 / 100** | 11.48 dB, 23.5 / 23.5 dB | line amplitude +6 % (0.21 -> 0.22 V) |
| Phase 10 dB R408/R412 (0603) / R410/R414 / R409/R413 | 100 / 68 / 100: 9.63 dB, 49.6 dB | **120 / 100 / 120** | 10.69 dB, 18.4 / 18.4 dB | GVA input -1.1 dB vs now; edge 137 -> 147 ps nominal (pess 318 -> 320 ps); step 7.18 -> 7.16 V |
(100/100/100 for the phase pads gives 158 ps; the 0603 first shunts carry 44-53 mW of 100 mW.)
**Bridge rails R202/R203 24.9 R** (strobe_arms deck, as built, +/-1.3 V): 24.9 R 100 ps / eff 105 % / kick 187 / 102 / 22 mV;
**22 R: 103 ps / 107.6 % / 190 / 103 / 22.4 mV**; 33 R: 94 ps / 98.4 % / 178 / 97 / 21 mV. Both inside the bias trim;
**22 R (C25092)** chosen: lower rail R keeps more drive for a weak strobe (the risk side). Two 49.9 R: not needed.
**Strobe-line terminations R378/R379 43 R** (bom2_taps as-built deck, cc 0.5 pF): 43 R tap-15 peak 3.36 V, swing min /
mean 47.2 / 55.7 mV, spacing sd 2.22 ps; **49.9 R: 3.59 V, 47.2 / 56.1 mV, 1.92 ps**; 33 R: 2.92 V, 32.9 mV (worse).
49.9 R (|Gamma| 0.09) is as good or better at the 3 ns latch: **49.9 R (C25120)**.
**FPGA series R401/R405/R407/R411 47 R -> 49.9 R** (C25120): TRF input 1.20 -> 1.18 V (-2 %), stage 1 saturates anyway.
**TRIG_LEVEL network** (R383 5.1k DAC / R384 8.87k from -2V5 / R385 2.0k shunt, 10 nF): -0.29 / +0.31 V nominal, but only
-0.283 / +0.306 V guaranteed over -2V5 +/-2.5 %. New **R384 10k, R385 3.3k** (R383 5.1k kept): -0.342 / +0.476 V nominal,
**-0.332 / +0.466 V guaranteed** (spec +/-0.30 V), 0.23 mV/LSB (was 0.17), Rth 1.67k (TLV3801 Ib 10 uA max -> 17 mV,
calibrated), 10 nF -> 9.5 kHz, -2V5 coefficient 0.167 V/V, DAC load 7.6k (>= 5k). Only-R384 = 10k fails (-0.257 V).
**BUF802 R_Bias R107 17.8k -> 18k 0603 (C25810, basic)**: datasheet point 17.8k (35.5 mA) within 1.1 %; 20k 0402 would cut
Iq about 8 % (two-point fit 35.5 / 22 mA at 17.8k / 35.7k), outside the characterised wide-band point: rejected.
**R105/R106 2 x 4.99M (IN -> In_Bias) -> 2 x 1 M 0402 (C26083)**, footprints kept. Input deck (proposed servo network):
LF/HF deviation 1 Hz-100 MHz max 0.58 % -> 1.05 % (at 10 kHz, inside the servo doublet the firmware two-term fit
already removes); 1 Hz gain +0.01 %; overload re-bias 5x faster; 2 M thermal current noise adds about 22 uV rms at the
BUF802 input above the 8.8 kHz servo corner (10 M: 10 uV) against the 0.35 mV floor. 10 M 0603 + 0 R: 0.77 %, layout change.
**U701 TLV9001 -> TPH2501** (C126713, the U201/U202 line, same SOT-23-5 pinout 1 OUT, 2 V-, 3 +IN, 4 -IN, 5 V+):
supply +/-2V5 4.84-5.09 V (spec 2.5-5.5 V); +IN at GND = mid-supply, RRIO; output -1.933 V is 0.45 V above V- at 0.32 mA;
VOS 0.5 mV max x noise gain 1.667 x 0.4 V/V to OUT = 0.33 mV (TLV9001 1.6 mV max: 1.07 mV), drift 1.3 uV/K at OUT,
noise 6.5 nV/rtHz in 160 Hz: < 0.2 uV. Stability: unity-gain stable (GBW 120 MHz); C722 100 nF from OUT to -IN makes it a
follower above 160 Hz driving 15k || 10k, not a capacitive load. Iq 6.5 mA on +/-2V5 (U605 55 / 57 mA, -2V5 headroom
0.45 -> 0.42 V). +0.35 USD, one extended line less. Eliminating the amplifier (Rmid from -2V5): +/-18 mV at OUT from the
rail tolerance (calibrated) but ~50x the drift (LM27762 reference vs VREF+, not ratiometric): rejected.
**D401 BAT15-03W (0 stock) -> BAT15-04W** (C5380972, the D201-D316 line): use **D2: pin 2 (cathode) to the tap / stub
node, pin 3 (common = D2 anode) to GND, pin 1 (D1 anode) to GND**, so D1 is shorted and adds nothing at the strobe node
(one pad there, as with SOD-323; LS 1.4 vs 1.8 nH). Never pin 2 to GND with pin 3 on the tap (D2 would clamp the wanted
positive pulse). Arms re-run: sampling 100 ps / 104.9 % (as built 100 / 105.1 %); falling edge, overload +/-1.5 V: tap
-1.28 V (was -1.37), per-diode reverse 3.80-3.86 V (was 3.87-3.93), clamp 101 mA. Using D1 with pin 2 floating instead
(+0.08 pF at the tap): 101 ps, -1.29 V: also fine, not chosen. D402/D403 (DNP): same part and pinning if ever fitted.
**Capacitors extended only for dielectric:** C303 1n C0G goes with the TMUX136; C106 becomes 1n C0G (C53547) as servo
Cint and must stay C0G (X7R makes tau voltage / temperature dependent); basic C0G stops at 100 pF in 0402 (2.2 nF C0G
C28260 is 0805: would need Rf1 2.2k, owned by the input study). C207 / C631 -> 100p basic (input study). No other change.

## Change table (for the schematic agent)
| Ref | Old -> new | JLC | LCSC (verified) | Layout |
|---|---|---|---|---|
| R603 / R604 | 12k / 1.3k 0.1 % -> 20k / 2.2k 1 % 0402 | basic | C25765 / C25879 | value only |
| R613 / R614 / R605 / R615 | 309k / 100k / 270k / 110k 0402 -> 470k / 150k / 510k / 220k 0603 | basic | C23178 / C22807 / C23192 / C22961 | footprint 0402 -> 0603 |
| R606 R616 | 100k -> 200k 0402 | basic | C25764 | value only |
| L402 L403 L405 / L404 L406 / L602 L603 | 47 uH 1210 / 2.2 uH 0805 / FHD252010S 1008 -> 1 uH DFE252012F-1R0M 1008 | extended | C435392 | footprint 1210 / 0805 -> 1008; L602/L603 none |
| R416 R417 R418 | 1k across L402/L403/L405 -> removed | - | - | removed |
| FB601 / FB602-FB607 | BLM21PG221SH1D 0805 / BLM18KG601SN1D -> BLM18PG121SN1D 0603 | basic | C14709 | FB601 footprint 0805 -> 0603; others none |
| FB608 | BLM18KG601SN1D 0603 -> BLM15HD102SN1D 0402 | extended (existing line) | C21516 | footprint 0603 -> 0402 |
| F601 | PTC 1206 -> 0 R 1206 | basic | C17888 | none |
| D601 | SMAJ5.0A -> DNP | - | (C353442) | none |
| C632 + new C633-C635, new R618-R621 | 47u tantalum 3528 -> 4 x (1 R 1206 in series with 47 uF 10 V X5R 1206), VBUS to GND | basic | C17928 / C96123 | footprint change, +7 parts |
| R402 (0603) / R403 / R404 | 82 / 82 / 91 R -> 100 / 100 / 120 R | basic | C22775 / C25076 / C25079 | value only |
| R307 R308 R309 | 82 / 91 / 82 R -> 100 R | basic | C25076 | value only |
| R408 R412 (0603) / R409 R413 / R410 R414 | 100 / 100 / 68 R -> 120 / 120 / 100 R | basic | C22787 / C25079 / C25076 | value only |
| R202 R203 | 24.9 R -> 22 R | basic | C25092 | value only |
| R378 R379, R401 R405 R407 R411 | 43 R, 47 R -> 49.9 R | basic | C25120 | value only |
| R384 / R385 | 8.87k / 2.0k -> 10k / 3.3k | basic | C25744 / C25890 | value only |
| R107 | 17.8k 0402 -> 18k 0603 | basic | C25810 | footprint 0402 -> 0603 |
| R105 R106 | 4.99M -> 1 M | basic | C26083 | value only |
| U701 | TLV9001IDBVR -> TPH2501-TR | extended (existing line) | C126713 | none (SOT-23-5, same pinout) |
| D401 (D402 D403 DNP alike) | BAT15-03W SOD-323 -> BAT15-04W SOT-323: pin 2 to the tap, pins 1 and 3 to GND | extended (existing line) | C5380972 | footprint SOD-323 -> SOT-323 |
Stock (JLC, 24 Nov): C435392 68k, C14709 2.34 M, C17888 1.49 M, C96123 572k, C17928 155k, C22787 2.19 M, C25810 692k,
C23178 912k, C22807 801k, C23192 637k, C22961 856k, C25764 3.18 M, C5380972 1465 (19 per board: 77 boards), C126713 6067.
Cost per board: about -0.21 USD (inductors -0.67, D401 -0.17, PTC / TVS / 0.1 % -0.14, beads -0.03, damper +0.45, TPH2501 +0.35).
**Extended BOM lines removed: 23** (R603, R604, 47 R, 82 R x2 lines, 91 R, 68 R, 43 R, 24.9 R, 8.87k, 17.8k, 270k, 309k, 110k,
4.99M, LQM21PN2R2, BLM18KG601, BLM21PG221, PTC, SMAJ5.0A (DNP), tantalum, TLV9001,
BAT15-03W); FHD252010S is replaced one-for-one by DFE252012F (stock).

## Extended passives that remain, and why
BLM15HD102SN1D x9 (GHz bead in 0402 on the 50 R lines; no basic equivalent); LQH32CN470K23L x2 (47 uH, SRF >= 15 MHz,
170 mA, for the 3.125 MHz and 1 kHz-3 Gbps 50 R stages); DFE252012F-1R0M x7 and FXL0420-R47-M (no basic power inductor;
TPS63802 needs 0.47 uH); R114-R116 300k 0402 (Rin 1.000 M / alpha 0.100 in three 50 V parts; 300k 0603 C23024 is basic and
75 V, but a footprint change in the input network: left to the input study); C101 / C102 / C205 / C314-C345 and C106 1n C0G
(tolerance or dielectric graded, bom2-input-taps.md).
