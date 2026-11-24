# Recheck of the validation findings after the fix round (24 Nov 2026)

Method: independent check from the primary files only. Board: pcbnew on a zone-refilled copy of
`layout/board/scope-fe.kicad_pcb` (coordinates below are board mm minus 100). Netlist: fresh `kicad-cli sch export
netlist` of `kicad/scope-fe.kicad_sch`. DRC/ERC: `tools/run_drc.sh --rules jlc4 --parity`, `tools/run_erc.sh` on
scratch copies. Scripts and reports are in scratch only. No design file was changed.

## Status per finding
| Id | Status | Evidence (measured) |
|---|---|---|
| RF-1 | mitigated | T401 still at (32.94, 11.30), arms uncoupled 0.16 mm, 17.827 / 17.827 mm (105.6 ps); covered by sim/strobe_arms (no 2nd sampling instant). gen_strobe.py:259 note still says 16.75 mm / 99 ps |
| RF-2 | fixed | GND via in NT401/402/403 pad 2 (0.00 mm); TL402/403 now end at x 11.283 |
| RF-3 | partly | R378/R379 = 43 R (netlist); phase_array sim not re-run (RESULT 21 Nov), 30 vs 35 ps open |
| RF-4 | fixed | R204 pads y 10.79 / 11.81, symmetric about 11.30; arm lengths equal |
| RF-5 | open | not changed (BUF_OUT_T y 22.35 route unchanged) |
| RF-6 | not re-measured | block README updated; cut geometry not re-sampled here |
| RF-7 | **worse** | +2V5 vias (9.20, 24.70) and (9.20, 26.65): via edge 0.105 mm from BUF_OUT_T (x 8.79); their antipads remove L2 under the trace centre at both points; +2V5 0.3 mm L1 track at x 9.20 runs 0.18 mm from BUF_OUT_T for 2.4 mm |
| PDN-1..5, 8 | fixed | power tree replaced (U601/U602 TPS62A01A, U603 TPS63802 +5V1, U604/U605 LM27762; U606/U607 gone); GVA chokes on /+5V1 |
| PDN-6 | fixed | C616 2.2u F 2.13 mm from U101.1; C620 2.2u B 0.68 mm from U302.9; C615 1u B 1.3-1.6 mm |
| PDN-7 | fixed | C606 / C622 100n F 2.23 mm from U401.1 / U402.1, beside C404 / C409 |
| DECOUPLING-1 | fixed | C614 10n F, pad 1.34 mm from U101.10 over 1.73 mm of 0.25 mm L1; its GND via 0.92 mm (not "below") |
| DECOUPLING-2 | open (low) | U302 still only bottom caps: C305 0.9-1.2 mm, C307 / C620 0.5-0.8 mm, no top HF cap |
| DECOUPLING-3 | fixed | C303 1n F 0.98 mm from U301.5, C302 B 0.16, C301 B 0.09 mm from pin 10; VSW_GND 0.5 mm L1 bar |
| DECOUPLING-4 | fixed | U604.3: C613 100n F 1.17 mm, C612 22u F 2.69 mm |
| DECOUPLING-5 | partly | C508 F 1.45 mm from U502.7, but the +3V3_CLK via sits at the pin, 2.65 mm from C508 (C509: 3.06 mm) |
| DECOUPLING-6 | not re-measured | C502 / C506 GND vias overlap their pads by 0.035 mm |
| DECOUPLING-7 | mitigated | C309 100n now F 0.95 mm from U303.1; no 1 nF |
| DECOUPLING-8 | fixed | C602 100n B 0.80 mm from U608.5 (GND via 1.10 mm) |
| BIASTEE-1 | fixed | /+5V1 5.10 V; extracted 92-118 mOhm U603 -> L404/L406, about 20-40 mV |
| BIASTEE-2 | mitigated | VCC 100n added; C403/C408 vs C432/C433 reference swap still unresolved in the schematic |
| BIASTEE-3, -5 | open / not re-measured | no re-simulation of the as-built tee parasitics |
| BIASTEE-4 | fixed | C419 / C429 100n at 1.70 mm from L404 / L406 cold pads, GND vias 0.62 mm, both alike |
| BIASTEE-6 | fixed for chokes | no via in any choke pad; but open vias remain in soldered pads of R107.2, C413.2 (3 vias), C423.2, C430.2, C420.2, C310, R377.1, R334.2 (plus overlaps R503-R505, U301.5, U304.5); no POFV note anywhere |
| ZONES-1 | fixed | L3 GND: max 5.9 mm to a GND via (47.8, 31.5), was 23.2 mm |
| ZONES-2 | fixed | L6 GND: max 5.7 mm in the tap row, 6.3 mm at the board edge (43.9, 55.6) |
| ZONES-3 | mitigated | L2/L5 antipad slots in the FPGA fan-out now <= 3.25 x 1.95 mm (59.35, 10.65) and 2.85 mm (63.6, 5.35); mcuif row 4.35 x 1.45 mm unchanged |
| ZONES-4 | mitigated | 33 of 65 fast vias with GND via <= 1 mm; all strobe vias OK; 20 TAP vias, COARSE (3.90, 31.55) 1.73 mm, MCU_CLK 1.01 mm |
| THEORY-1 / IO-1 | fixed in SPEC 18, schematic, kicad/README; **ToO not updated** | 24 MHz / IDIV 1 x FBDIV 16 = CLKOUT 384 MHz (<= 400), ODIV 2 -> VCO 768 MHz (400-800), PFD 24 MHz, PCLK = FCLK/5 = 76.8 MHz, OSER10 DDR 768 Mbit/s (<= 1100); 48 MHz = 16 bits, 3.0 MHz = 256 bits. Margins 4 %. ToO lines 116, 183, 220, 246 still 960 Mbit/s / 96 MHz |
| THEORY-2, 4-7 | open | ToO dated 22 Nov, phase/input/sampler sims not re-run |
| THEORY-8 | **worse** | ToO section 9 (l. 290-309) still describes AMS1117, MT3608, LM27761, LM337 and GVA on VBUS; root README also 22 Nov |
| IO-2, IO-3, IO-5 | open | pins unchanged (CLK2 on 34, TAP0-3/8-11/ADC_TRIG on IOR6), no place-and-route run |
| IO-4 | mitigated | UCPD_DBDIS documented (kicad/README l. 275) |
| IO-6 | partly | ADC_TRIG text updated; DBG2 not re-checked |
| PARTS-1 | mitigated | R402 / R408 / R412 0603; R404 / R410 / R414 still 0402 (lower dissipation) |
| PARTS-2, PARTS-3 | open | R401/R407/R411 47 R; T401 still on 0805USB land (pads 0.51 x 0.76) |
| PARTS-4 | partly | R735 4.7k / R736 5.1k limits VBIAS_K to about 1.40 V, but sim/strobe_arms shows 3.93-4.18 V reverse on the falling edge at the +/-1.5 V clamp (> 4 V VR) |
| PARTS-6 | fixed | LM337 removed |
| PARTS-7 | mitigated | XTAL_CL 10 pF + about 2 pF stray for the 12 pF crystal |
| PARTS-9 | open | R122, D402, D403, C631, C632 have no DNP / exclude flags on the board (32 parity warnings) |

## Regressions
- DRC jlc4 + parity: 0 errors, 0 unconnected, 451 warnings (199 Note field, 199 lib mismatch, 32 DNP/BOM attribute,
  11 lib footprint, 10 net_conflict: TL401-403 GND pins 2/4, J601 shield pads). Courtyard overlaps: 0.
- ERC: 0 errors, 16 warnings (SMA library links / symbol mismatch).
- RF widths: all RF tracks 0.16 mm (0.10 mm strobe/PH_LINE sections) as designed. L2 under RF: every centre-line miss is
  a pad cut or own-via antipad except BUF_OUT_T at (8.79, 24.67) and (8.79, 26.63) (+2V5 vias) and PH_STROBE_N at
  (59.43, 10.79) (TAP5 via / FPGA slot).
- L4 +3V3: one polygon, 4536 mm2 (was 4710); all 63 +3V3 vias land on it; nearest plane via 2.82 mm at U401/U402 pin 1
  (via pair behind the caps). Two +1V2 islands (59 mm2) now share L4 under the FPGA.
- Minor rails: narrowest +2V5 0.3 mm (32.6 mm total). Extracted track R from the output bead to the load: +2V5 to
  U301.10 241 mOhm, to U302.6 184 mOhm; -2V5 <= 173; +5V <= 156; -5V <= 120 mOhm; +1V2 8 mOhm. At full rail current the
  drop is <= 12 mV everywhere.
- Supply copper beside fast / analog nets (same layer, edge gap): +2V5 / BUF_OUT_T 0.18 mm (2.4 mm), +3V3 / TAP8
  0.15 mm (1.2 mm), +1V2 / S_STROBE_P 0.22, +3V3 / S_STROBE_N 0.22 mm (2.5 mm), VTAP_N / MCU_CLK 0.22 (L6),
  +2V5 / PH_STROBE_N 0.27 (L6), VTAP_N / U310A+ tap node 0.28 mm over about 10 mm (L6).
- Vias at IC pins rather than at the capacitor (user's layout request): plane via nearer the pin than the cap at
  U704 pins 24/36/48, U502 pins 1/7, U501.1, U101.8 and U310.8. The analog and power ICs otherwise follow the rule.
- Moved capacitors C602, C606, C614, C615, C616, C620, C622, C623, C306 (and C630, C612, C613): board value and pad
  nets equal the netlist.
- BOM: 473 references = netlist, values match; line sum 63.76 USD = docs/bom.md total. 42 fitted lines (mostly 0402
  passives, C616/C620, R603-R616 0.1 % dividers) have no LCSC number; GVA-84+ and SMA are off LCSC.
