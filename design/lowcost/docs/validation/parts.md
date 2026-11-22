# Validation: parts (pinouts, footprints, ratings versus datasheets)

Key `parts`. Validation only; no design file changed. Scripts and downloads in `scratchpad/val/parts/` (`nl.py`,
`fp.py`, `pads.py`, `dl_*`). Coordinates in mm relative to the aux origin (100, 100), the same frame as rf.md.

## Method
1. Parsed `kicad/export/scope-fe.net` and listed, for each of the 66 non-passive parts, every pin with its
   pinfunction and net (`pins.txt`). Compared these with the pin tables in the datasheets.
2. Loaded `layout/board/scope-fe.kicad_pcb` with pcbnew 7.0.11 and dumped pad numbers, nets, local and absolute
   positions and sizes for the packages that matter (QFN/WSON/UQFN, SOT-89, CMC, crystal, J501, J601). Compared them
   with the TI land patterns (RGT0016C, DSG0008A, RSE0010A), Gowin UG843 Fig. 4-17/4-18 (QN48) and the Murata
   JEFL243C-0010P-01 drawing (DLW21SN).
3. Checked ratings: supplies, input ranges, diode VR, pi-pad and termination dissipation (`pads.py`).
4. Compared DNP and footprint-only status across the netlist (`dnp` property), docs/bom.md and the board attributes.

## Checked and found correct
- Pinouts match the netlist for these parts:
  - BUF802 RGT (SBOS998E Table 4-1): 1 VS+, 2 IN, 3 In_Bias, 4 In_Aux, 5/8 VS-, 6 Aux_Bias=VS- (CL mode), 7 R_Bias
    17.8k, 10 VSO-, 11 OUT, 12 VSO+, 9/13/16 NC open. The EP is isolated, so tying it to GND is fine.
    CLH/CLL = +/-1.5 V (1k/1.5k from +/-2V5), inside the mid-supply..rail limit.
  - OPA197, TLV9001 (DBV), TPH2501 (3PEAK SOT23-5: Out, V-, +In, -In, V+); TRF37D73 (SLASE43: 1 VCC, 2 RFIN,
    3/4/6/8 NC->GND, 5 PWDN->GND, 7 RFOUT+bias, EP GND); GVA-84+ (1 IN, 3 OUT/DC, 2/tab GND); BAT15-04W (1 A, 2 K,
    3 common); BAT15-03W (SOD-323, pad 1 = K).
  - TMUX136 (SCDS367E Table 5-1): 1 A1, 2 A2, 3 B1, 4 B2, 5 GND, 6 EN active low, 7 COM2, 8 COM1, 9 SEL, 10 VCC.
  - TLV3801 (SNOSDD7C Table 5-1): 1 OUT-, 2 GND, 3 VEE, 4 IN-, 5 IN+, 6/7 VCC, 8 OUT+, EP to VEE.
  - SN65LVDS2 DBV (SLLS373: 1 VCC, 2 GND, 3 A, 4 B, 5 R).
  - COS3502 SOP-8 (Cosine DS p.2: 1 +INA, 2 -INA, 3 +INB, 4 -INB, 5 Vs-, 6 OUTB, 7 OUTA, 8 Vs+). OUTA = even TAP and
    OUTB = odd TAP on all 8 parts. The design does not use the TLV3502 pinout.
  - GW1NZ-LV1 QN48: all 48 pins match UG842 (`qn48_pins.txt`), EPAD = GND as UG842 recommends.
  - MS5351M (Si5351A MSOP-10 order), 3225 crystal (1/3 XA/XB, 2/4 GND).
  - STM32G474CBT6 power pins: 1 VBAT, 19 VSSA, 20 VREF+, 21 VDDA, 23/35/47 VSS, 24/36/48 VDD, 7 NRST, 45 BOOT0.
  - AMS1117, AP2112K, MT3608, LP2985, LP5907, LM27761 (SNVSA85D Table 4-1), USBLC6-2SC6, USB-C CC 5.1k.
  - LM337: the XBLW datasheet (fetched, p.4) gives SOT-223 as 1 ADJ, 2 VIN (tab), 3 VOUT. It matches U607 and closes
    the "check SOT-223 pinout" BOM note.
- Land patterns:
  - DSG0008A EP 0.9x1.6 at 0.5 mm pitch (TRF37D73, TLV3801, LM27761).
  - RSE0010A: columns +/-0.675, pins 5/10 at +/-0.9, 0.55x0.25 / 0.55x0.2 / 0.3x0.6. U301 pads match exactly.
  - RGT0016C EP 1.68.
  - QN48: pads at +/-2.95 (Gowin P = 5.90), 0.8x0.2 (Gowin L 0.85, b 0.2), EP 4.3x4.3 (Gowin D2/E2 4.3).
- T401 DLW21SN pin map. Murata places (1)(4) at one end and (2)(3) at the other; the windings are (1)-(2) and
  (4)-(3), dotted at (1) and (4). On the 0805USB footprint, pads 1 and 4 share one end (y = -0.835) and pads 1-2 run
  along one side. Winding 1 = pad 1 (C410 drive) -> pad 2 STRB_A, and winding 2 = pad 3 GND -> pad 4 STRB_K. The
  dotted ends are on the same end, so the balun polarity is correct. A mirrored part only swaps two identical
  windings. The earlier "unverified" item is closed.
- Supplies: BUF802 10 V (max 14); TLV3801 VCC-VEE 5.0 V (max 5.5), VCC-GND 2.5 V (rec. min 2.4); TMUX136
  VCC-local GND 3.39 V (rec. 2.3-4.8), SEL 2.12 / 0 V local (VIH 1.3, VIL 0.6); TRF37D73 3.3 V (3.0-3.45); TLV9001
  5.0 V (1.8-5.5); TPH2501 5.0 / 3.3 V (2.5-5.5); OPA197 10 V; COS3502 3.3 V.
- Regulator settings: MT3608 0.6x(1+78.7/10) = 5.32 V; LM27761 -1.22x(1+1.54M/499k) = -4.985 V; LM337
  -1.25x(1+120/120) = -2.5 V, min load 10.4 mA through 120 R (TI: 6 mA).
- Drive levels: TRF #2 input 8.4 dBm (TRF #1 at +/-2.3 V through 11.9 dB; limit 10 dBm); GVA input 10.6 dBm (9.7 dB
  pad; limit 13 dBm); GVA pin 3 DC stays under 5.8 V.
- Current ratings (LCSC listings): BLM15HD102 250 mA (1.25 R), LQH32CN470 170 mA, LQM21PN2R2 Isat 450 mA; B5819W
  (C8598) 40 V / 1 A.
- Other pad dissipation: R401/R405/R407/R411 (47 R) 6.8 mW; R406 dummy 7 mW; PSTRB 49.9 R terminations (R379 type)
  < 8 mW; R307 (trigger pad, U303 not saturated, line +/-0.21 V) < 20 mW.
- Not re-reported, covered by other keys with numbers that agree with mine: GVA drain below 4.8 V (biastee BT-1),
  LM27761 headroom / 5.5 V window (pdn PDN-5), AMS1117 and LM337 output-capacitor ESR (pdn).

## Findings

**PARTS-1 (medium, verified arithmetic / likely in hardware): input shunt resistors of the saturated pi pads run at
or above the 0402 rating.**
The TRF37D73 stages that feed the pads are driven into saturation with a 50 % square wave (sim/strobe/RESULT.md: +/-2.3
V into 50 R). With a square wave, Vrms equals Vpeak.
- R402 82 R at (46.18, 9.47): 2.3^2/82 = **64.5 mW**, or 56 mW with the 47 uH droop (4.30 V step). The rating is
  62.5 mW at 70 C.
- R404 91 R: 32 mW.
- R408 / R412 100 R at (15.27, 30.53) / (15.27, 44.47): **52.9 mW** (85 %). R410 / R414 68 R: 35 mW.
- For comparison, the OP1dB sine (16.5 dBm) gives only 27 / 22 mW, so the square-wave drive is what costs the margin.

Impact: the resistors drift and age, and pad attenuation and match shift, which changes the strobe amplitude that the
bias calibration depends on. Above 70 C board temperature they exceed the rating.
Fix: use 0603 (100 mW) or 0402 anti-surge / 0.1 W parts (for example Panasonic ERJ-PA2 / ERJ-2RKF high-power) for
R402, R404, R408, R410, R412, R414. Measuring TP401 / TP403 / TP405 on the first board settles the real swing.

**PARTS-2 (low, verified): stage-1 TRF37D73 input is within 0.4-1.4 dB of its 10 dBm absolute maximum, depending on
FPGA drive strength.**
S_STROBE_P / PH_STROBE_P/N -> 47 R (R401, R407, R411) -> 50 R. A 3.3 V square gives +/-0.60 V = 8.6 dBm with a 40 R
pin (the sim value), 9.6 dBm at 25 R and 10.4 dBm at 15 R (12-24 mA LVCMOS33 settings). The limit is 10 dBm
(SLASE43 6.1). The stage needs only about +/-0.18 V to saturate (2.3 V / 22.3 dB).
Fix: fix DRIVE = 8 mA in the Gowin constraints, or raise R401 / R407 / R411 to 100 R (6.5 dBm at 25 R; still
2.6x the saturation drive).

**PARTS-3 (low, verified): T401 land pattern is the Coilcraft 0805USB pattern, not Murata's DLW21SN land.**
Board pads at (32.105 / 33.775, 10.865 / 11.735) against Murata section 16.7: pad 0.76 x 0.51 (Murata 0.8 x 0.4);
gap across the part 0.36 (Murata >= 0.4, *2: risk of a short between lines); total width 1.38 (Murata <= 1.2, *1: the
part can rotate); outer length 2.43 (Murata 2.6). Topology and polarity are correct (see above).
Fix: make a DLW21SN footprint (pads 0.8 x 0.4 on a 1.8 x 0.8 centre grid) or trim the 0805USB pads to 0.4 mm width.

**PARTS-4 (low, verified): BAT15-04W bridge diodes can exceed VR = 4 V at the top of the VBIAS_K DAC range.**
VBIAS_K reaches +2.7 V (kicad/README control-voltage table). D201 pin 3 sits on the input through R201 10 R. The
static reverse voltage of the common->K diode is VBIAS_K - Vin:
- 3.2 V at Vin = -0.5 V;
- **4.2 V** at the BUF802 CLL clamp (-1.5 V);
- plus the S_STROBE reverse pulse (1.9 V with D401, theory sec. 4).

At the intended bias (+/-0.6 to +/-1.2 V) the maximum is 1.7 + 1.9 = 3.6 V (90 %).
Fix: limit VBIAS_K to about 1.5 V in firmware, or change R735/R736 so that the DAC full scale maps to about 1.5 V.

**PARTS-5 (low, verified): TMUX136 A1 goes 0.3 V below its abs-max during input overload.**
U301 at (8.04, 27.80), with A1 = BUF_OUT_T through R112 49.9 R + R113 0 R. At the BUF802 clamp -1.5 V, A1 is
-1.5 + 0.893 = **-0.61 V** relative to the local GND (VSW_GND). The limits are -0.3 V abs max and 0 V recommended
(SCDS367E 6.1/6.3). The clamp diode current is limited by 49.9 R to a few mA (IK limit -50 mA), so damage is
unlikely, but the diode current also pulls VSW_GND (Thevenin 964 R) down. The normal +/-0.5 V range is 0.39-1.39 V
local, which is fine.
Fix: accept and document, or move CLL to about -1.1 V (R110/R111) if the +/-1.5 V overload range is not needed.

**PARTS-6 (low, verified arithmetic): the -2V5 LM337 runs at its minimum recommended differential, and the PDN-5 fix
makes it worse.**
|VI-VO| = 4.985 - 2.50 = 2.49 V nominal. TI LM337 recommended operating minimum is 2.5 V (SLVS047 7.3; the XBLW
datasheet gives no dropout). With VFB/VREF tolerances (LM27761 1.202-1.238, LM337 1.213-1.287) it is 2.34-2.64 V. With
the -4.8 V setting proposed in pdn.md it would be 2.3 V. The LM337 usually regulates down to about 1.5 V at 40 mA,
but ripple rejection of the LM27761's 2 MHz ripple falls near dropout. -2V5 feeds TLV3801 VEE, VNEG_REF (U701) and
the U201 hold buffer.
Fix: choose the -5 V setting and the -2V5 regulator together. Options: -2.4 V (R607 120 / R608 110 R), or a
low-dropout negative LDO such as TPS7A30, which would also fix the ESR issue in pdn.md.

**PARTS-7 (low, verified): Y501 load capacitance does not match the MS5351M setting.**
C9006 is YXC X322525MOB4SI, 25 MHz, **CL 12 pF**, ESR 50 R (LCSC listing). kicad/README says "CL 8 pF via internal load
caps", and the Si5351 offers 6 / 8 / 10 pF. At 8 pF plus about 2 pF stray, the oscillator runs about +20 to +30 ppm
high (estimate, C1 about 4 fF). That is a time-base scale error, harmless for equivalent-time display but visible
against an external reference.
Fix: set XTAL_CL = 10 pF in firmware and correct the README, or buy an 8 pF 25 MHz 3225 crystal.

**PARTS-8 (low, likely): tap comparator inputs go slightly below the COS3502 common-mode range.**
The tap node is the average of the hold nodes, which sit at 0 V (2.2k to +/-2V5 plus 2x1k). It follows the line,
+/-0.21 V for data (theory sec. 5). The COS3502 VCM is -0.2 V min (DS 3.4), and the recommended range is -Vs..+Vs,
i.e. >= 0 V. VTH is +3..+90 mV, so below-range inputs only ever mean "low". The part claims no phase inversion.
Risk: slower recovery or delay skew on the first edge after a low.
Fix: none needed, or bias VTAP_P/N slightly asymmetric (+50 mV) together with VTAP_TH.

**PARTS-9 (low, verified): DNP and footprint-only status exists only in the schematic and BOM.**
The netlist and docs/bom.md mark D402 (25.52, 32.90), D403 (25.52, 42.10) and R122 (6.11, 25.99) as DNP. The KiCad 7
board has no DNP attribute, and these footprints are not excluded from position files. J501 (42.0, 53.2,
"footprint only, no part") is a THT footprint that is not excluded from the BOM either. A CPL/BOM exported from the
board would place all four.
Fix: set exclude-from-pos/BOM on D402, D403, R122 and J501 in the board, or filter them in the assembly export.
Separately, the D602 value "SS14 / B5819W" names an SMA part on a SOD-123 footprint. Change the value to B5819W, which
matches LCSC C8598.

## Datasheets not obtained / not verified
- Würth 490107671612 (J501): the we-online PDF returned "Access Denied". The footprint (staggered 1.27 mm, 1.5 mm
  drills, NPTH 2.2 / 2.6) was compared only with its own generator description.
- Bourns 3314J (RV101): pad 1/3 side and pad 2 side used as a rheostat (pins 2 and 3 to GND). Not compared with the
  Bourns drawing.
- The following were checked against well-known standard pinouts and the KiCad library footprints, not against their
  own datasheets in this run: HRO TYPE-C-31-M-12, AMS1117, AP2112K, MT3608 (C84817), LP2985, LP5907, USBLC6, MS5351M,
  STM32G474 (beyond the power pins), SOT-89 / DF782 land, SMA edge connector.
- Capacitor voltage ratings checked only where an LCSC number is given (C45783 / C15850 / C52923 25 V, C1525 16 V);
  C616 / C620 (2.2 uF 0402) and C619 (4.7 uF 0603) are unassigned.
