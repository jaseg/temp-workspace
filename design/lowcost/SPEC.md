# Low-cost sampling front end: design specification (working document)

Target: 2 GHz / 3 Gbps equivalent-time sampling front end, parts budget 80 USD (lowest of LCSC,
DigiKey, Mouser; the microcontroller is added by the user and not counted), switchable external
clock or phase recovery from the probed signal. Background and earlier simulations:
`docs/frontend-summary.md`, `docs/scope-frontend.md`, `docs/research/*.md`, `sim/*.py`.

**Superseded text:** the signal chain, rails and parts list below are the first plan. The numbered decisions
override them; in particular TMUX136, SN65LVDS2 and the LVDS receiver are replaced by decision 27, TLV9001 by 33,
the 0.1 % divider by 30, RV101 by 28 / 35. Values marked (sim) are starting points; the simulation tasks may change them and record the final
values in `design/lowcost/sim/<area>/RESULT.md`. Those RESULT files take precedence over this file.

## Signal chain

```
SIG_IN (SMA, no termination) -- 5:1 compensated divider (1 Mohm) -- BUF802 (+OPA197 servo)
   -- BUF_OUT 50R --+-- resistive splitter --> SAMPLER: 4-diode bridge (2x BAT15-04W), 2.2 pF hold,
                    |                           TPH2501 hold amp (G=+5), TPH2501 inverting level shift -> ADC_IN (MCU PA0)
                    +--> TRIG: TMUX136 (A = signal, B = EXT_CLK SMA) -> TLV3801 (VCC +2.5, VEE -2.5, LVDS out ref. GND)
                              LVDS+ -> AC -> TRF37D73 line driver -> pad -> 16-tap delay line (35 ps/tap) -> 50R term
                              LVDS pair also bridged (high impedance) -> LVDS receiver -> FPGA (coarse time stamp)
16 taps: two-diode gate (1x BAT15-04W each), hold caps 0.47 pF, readout 2.2k bias / 2x1k summing (sim),
         8x COS3502 dual comparator -> FPGA TAP[15:0]
FPGA GW1NZ-LV1QN48: 1 Gbps serialisers make PH_STROBE (50 MHz, phase recovery) and S_STROBE
         (3.125 MHz = PH_STROBE/16, sampler), ADC_TRIG to the MCU, SPI to the MCU.
Clock: MS5351M + 25 MHz crystal -> FPGA_CLK and MCU_CLK (programmable strobe rate avoids fixed ratios).
```

No AD9508, no divider. Every delay-line snapshot that contains an edge is a time stamp relative to
the strobe clock; the coarse LVDS path tells which edge it was. Software fits the signal phase.

## Rails
`+5V` and `-5V` (BUF802, OPA197), `+3V3` (FPGA IO, TRF37D73, MS5351M, logic), `+2V5` and `-2V5`
(TLV3801, TMUX136 supply shifted: VDD = +0.8..+2.5/GND pin on -2V5 to be checked, hold amps),
`+1V2` (FPGA core), `GND`. Power input: 5 V (USB). How -5 V is made is the power sheet's choice
(must respect BUF802 minimum +/-4.5 V) and is priced in the BOM.

## Net names between sheets (hierarchical labels)
`BUF_OUT_S` (splitter leg to sampler, 50R), `BUF_OUT_T` (splitter leg to trigger switch, 50R),
`EXT_CLK`, `TRIG_SEL`, `TRIG_LEVEL`, `CMP_P`/`CMP_N` (TLV3801 LVDS), `COARSE` (LVDS receiver out to FPGA),
`TAP0..TAP15`, `PH_STROBE_P`/`PH_STROBE_N` (FPGA pins to phase strobe driver),
`S_STROBE_P`/`S_STROBE_N` (FPGA pins to sampler strobe driver),
`STRB_A`/`STRB_K` (sampler strobe pulses at the bridge), `PSTRB_A`/`PSTRB_K` (strobe lines along the taps),
`VBIAS_A`/`VBIAS_K` (bridge bias), `VTAP_P`/`VTAP_N` (tap readout rails), `VTAP_TH` (tap threshold),
`VOFS` (input offset), `ADC_IN`, `ADC_TRIG`, `ADC_REF_MID`,
`SPI_SCK/MOSI/MISO/CS`, `I2C_SCL/SDA`, `FPGA_CLK`, `MCU_CLK`, `FPGA_DONE`, `FPGA_RECONFIG`, JTAG.

## Parts already chosen (lowest verified price, USD)
BUF802IRGTR 5.89; OPA197 0.75; TPH2501 0.43 (TPH2502 dual 0.58); TP2272 dual 0.50; TP1541A 0.38;
BAT15-04W 0.37 @10; TLV3801DSGR 5.13; TMUX136MRSER 1.22; TRF37D73IDSGR 1.50; GVA-84+ 2.99;
COS3502SR 0.36; GW1NZ-LV1QN48 6.68; MS5351M 0.91; LM27761 1.23. (TMUX136 superseded by decision 27.)

## Files
- `design/lowcost/sim/<area>/` simulations (ngspice + Python, reuse `sim/` helpers), `RESULT.md` each.
- `design/lowcost/kicad/` KiCad 7 project (hierarchical), generators in `design/lowcost/kicad/gen/`.
- `design/lowcost/layout/<fragment>/` layout fragments (pcbnew-scripted `.kicad_pcb`).
- `design/lowcost/docs/` theory of operation, BOM.

## Decisions after the first simulation round (these override the text above)
1. **Splitter**: BUF802 OUT pin -> 10 R -> sampler bridge input (bridge within 3 mm of the BUF802);
   BUF802 OUT pin -> 49.9 R -> 50 R line `BUF_OUT_T` -> TMUX136 (high-impedance end). A series position
   (0 R, optionally ferrite or 100 R) sits in the trigger leg against strobe kick-out. `BUF_OUT_S` is the
   BUF802 output node itself; the 10 R belongs to the sampler sheet/fragment, the 49.9 R to the input one.
2. **Hold amplifier gain +3** (1.00 k / 499 R), level shifter and ADC network as in `sim/sampler/RESULT.md`.
3. **Strobes are 50 % duty square waves** from complementary LVCMOS33 FPGA pin pairs (GW1NZ-1 has no
   true LVDS). Sampler strobe: 2x TRF37D73 + 12 dB pad + shorted stub (80 ps) + balun, bias adjustable
   (`sim/strobe/RESULT.md`). Phase strobe: per polarity TRF37D73 + 10 dB pad + GVA-84+ + stub.
   A Schottky clamp (BAT15) at each strobe launch point removes the wrong-polarity pulse of the second
   edge if the verification run shows the diodes need it.
4. **Tap geometry: co-propagating lines.** Strobe lines PSTRB_A/PSTRB_K run along the 16 gates at
   40 ps per tap (loaded; 0.16 mm / 72.8 R trace, 4.514 mm pitch on JLC04161H-7628) and end in 50 R terminations;
   the signal line takes 75 ps per tap (meander between taps; 0.26 mm / 59 R trace, 9.929 mm, drawn 70 ps per tap
   loaded to 50 R; delays raised from 35 / 70 ps so the meander keeps 0.5 mm same-net gaps), launched from the same end, so the effective tap spacing is
   75 - 40 = 35 ps. Verified in `sim/phase_array/` for 35 / 70 ps; the 40 / 75 ps layout is not re-simulated.
   (Superseded for the geometry by the six-layer board of decision 15: 0.10 mm lines, 39.4 ps strobe and 69.4 ps signal
   per tap, about 30 ps effective, PSTRB terminations 43 R (decision 22); not re-simulated.)
5. **Tap readout**: 2.2 k to VTAP_P/VTAP_N (+/-2.5 V), 2 x 1 k summing to the comparator, threshold
   VTAP_TH 0..+80 mV; rising edges only (line feed-through, see `sim/phase/RESULT.md`).
6. (Superseded by decision 27: diode-bridge selector and a COS3502 COARSE receiver.) **TMUX136** on a local -0.9 V ground; **SN65LVDS2** coarse receiver bridged with 2 x 470 R; 100 R across
   the TLV3801 outputs (`sim/phase/RESULT.md`).
7. **Input stage** as in `sim/input/RESULT.md` (fixed 5:1, OPA197 integrator servo; termination: decision 10).
8. Power tree, FPGA pins, MCU interface: `kicad/README.md`.
9. PCB for the layout fragments (revised on user request): **JLCPCB standard 4-layer stack-up JLC04161H-7628**
   (L1 0.035 mm, prepreg 7628 0.2104 mm er about 4.4, core 1.065 mm, prepreg 0.2104 mm, L4 0.035 mm; 1.6 mm board).
   50 R outer-layer microstrip with solder mask is about 0.36 mm wide over the L2 ground (compute and state it);
   every RF trace must have its calculated width for its target impedance over its whole length, with ground
   pour clearance large enough (>= 2 x trace width, or the coplanar effect included in the calculation).
   Layer 2 solid ground, 0402 passives (0201 where a simulation asks for it), SMA edge-launch connectors.
   (The stack-up is superseded by decision 15; the width and pour-gap rules still apply.)
10. No switchable termination (user decision): external feed-through terminator.
11. Programming header: Würth WR-WST 490107671612 with the yanartas sensing board J3 pinout (J501, footprint only).
12. STM32G474 on board (user decision, 21 Nov 2026): STM32G474CBT6 LQFP-48 (U704) replaces the MCU header J701; USB FS
    on the USB-C receptacle, SWD/UART on J501. The 80 USD budget now includes the MCU. Pin plan: `kicad/README.md`.
13. **Control voltages without difference amplifiers** (user instruction, 21 Nov 2026: "generate what can be generated in
    software directly and only use op-amps where necessary"): DAC pins drive passive networks (TRIG_LEVEL = DAC + -2V5 sum
    at the TLV3801, VBIAS_A = DAC/-2V5 divider, VBIAS_K = DAC via 5.1k, VOFS = DAC into the servo node); the only op-amp is
    U701 TLV9001 (TPH2501 since decision 33) making VNEG_REF = -0.68 x VREF+ for the VOFS mid-scale (offset drift). Details: `kicad/README.md`.
14. **Layout = one integrated board** (review, 21 Nov 2026): `layout/board/scope-fe.kicad_pcb`, 100 x 57 mm, generated by
    `layout/board/gen_board.py` from six blocks; the three layout fragments are superseded. Fully routed, DRC 0 errors
    (`layout/board/README.md`).
15. **Six layers, JLCPCB JLC06161H-3313** (user decision, 22 Nov 2026; replaces the 4-layer stack-up of decision 9 for the
    board): L1 components, RF and analog routing (50 R microstrip 0.16 mm over the 0.0994 mm prepreg); L2 solid GND
    (cut only under the hold / divider nodes and SMA pads); L3 slow bias / control lines and the minor rails (+5V, -5V, +2V5,
    -2V5, +1V2, VBUS, VTAP_P/N) as routed tracks, rest GND pour; L4 one solid +3V3 plane; L5 solid GND; L6 inter-block
    digital buses (TAP0..15, COARSE, clocks, SPI, I2C, JTAG, ADC_TRIG) over L5, plus bottom-side decoupling and slow parts.
    No fast net on L3 or over a plane gap. Rules: `layout/board/RULES.md`.
16. **MCU, programming header, control voltages** are on the board as in decisions 11-13 (STM32G474CBT6 U704; Würth
    WR-WST 490107671612 J501 with the yanartas sensing board pinout; passive DAC networks against -2V5 plus one TLV9001).
17. **Synchronous clock plan** (lead with the user, 22 Nov 2026; replaces 50 MHz / 3.125 MHz): one MS5351M PLL with integer
    dividers gives 24 MHz to the FPGA and to the MCU. FPGA serialiser 960 Mbit/s (24 MHz x 40, 1.04 ns per bit); phase
    strobe 48 MHz = 20 bits; sampling strobe 3.0 MHz = 320 bits = 16 phase strobes. MCU system clock 120 MHz, ADC in
    synchronous clock mode at 60 MHz: one strobe period = 20 ADC clocks, a 12-bit conversion with 6.5-cycle sampling takes
    19. Variant if two ADCs run together and the ADC clock limit is lower (about 52 MHz, unverified): ADC 48 MHz, sampling
    strobe 2.4 MHz = 20 ADC clocks = 400 bits. An MCU timer triggers the ADC internally and marks the frame start on
    ADC_TRIG (PB11 -> FPGA); the FPGA aligns its strobe counter to it once (bit slips plus the output delay block).
    (Serialiser rate and bit counts superseded by decision 18.)
18. **Clock plan at 768 Mbit/s** (24 Nov 2026, validation THEORY-1 / IO-1; replaces the 960 Mbit/s of decision 17): 960 Mbit/s
    needs FCLK 480 MHz, above the GW1NZ-1 rPLL limit (DS841-2.8E table 3-20, LV C6/I5: VCO 400-800 MHz, CLKOUT <= 400 MHz).
    FPGA_CLK 24 MHz -> rPLL IDIV 1, FBDIV 16, ODIV 2: VCO 768 MHz, FCLK 384 MHz, PCLK 76.8 MHz (FCLK/5); OSER10 / IDES10 at
    768 Mbit/s (limit 1100, table 3-16), 1.302 ns per bit. Phase strobe 48 MHz = 16 bits, sampling strobe 3.0 MHz = 256 bits
    (= 16 phase strobes, = 20 ADC clocks at 60 MHz as before); variant 2.4 MHz = 320 bits. MCU and ADC unchanged.
19. **Power tree with three regulator types** (24 Nov 2026, user instruction, `docs/research/power-tree.md`): TPS62A01A buck
    VBUS -> +3V3 and +3V3 -> +1V2; TPS63802 buck-boost VBUS -> +5V1 (5.10 V, also the GVA-84+ drain supply); LM27762
    +5V1 -> +4.80 / -4.64 V (nets +5V / -5V) and +3V3 -> +/-2.50 V (nets +2V5 / -2V5, enabled by the TPS63802 power good).
    AMS1117, AP2112K, MT3608, LP2985, LM27761, LP5907 and LM337 are removed. Every regulator's input range, dropout and
    margin are in that note.
20. **Decoupling by moving existing capacitors first** (user instruction, 24 Nov 2026): the freed regulator capacitors go to
    the new converters and to the load pins named in the validation (list in `kicad/README.md`); the only new capacitor is
    C630 (U605 OUT+); C631 is a DNP footprint, C632 (VBUS damper) is fitted since the recheck (RP-3).
21. **Strobe arms and bias** (`sim/strobe_arms/RESULT.md`, rev. 2): the as-built uncoupled 50 R balun arms stay (17.827 mm =
    105.6 ps each); R204 sits symmetrically in both arms; nominal bridge bias +/-1.3 V, trimmed per board for an efficiency
    of about 100 %. VBIAS_K is 0.520 x DAC (R735 4.7k / R736 5.1k, +0.10..+1.40 V; validation PARTS-4). Firmware keeps
    |VBIAS_A| and |VBIAS_K| at or below 1.30 V: the S_STROBE falling edge adds about 1.1 V to the BAT15-04W reverse voltage,
    3.93 V at a +/-1.5 V input overload (4 V rating). D401 stays fitted.
22. **Small part changes** (validation, 24 Nov 2026): PSTRB_A/K terminations R379 / R378 43 R (loaded line 41.3 R, RF-3);
    pad input shunts R402 / R408 / R412 in 0603 (PARTS-1); MS5351M XTAL_CL = 10 pF for the 12 pF crystal (PARTS-7).
23. **Decoupling layout rule** (user review, 24 Nov 2026): every decoupling capacitor sits at its supply pin on the IC's
    side with the shortest loop, and the plane or rail vias sit at the capacitor (behind it), not at the IC pin. Converter
    hot loops are closed on L1 (TPS63802 input / output 1.9 x 2.8 mm). `layout/board/decap_audit.py` checks the rule;
    the exceptions without room are listed in `docs/VALIDATION.md` (RF2-3).
24. ~~**Plugged vias**~~ **WITHDRAWN (24 Nov 2026, user decision):** plugged / capped / resin-filled vias are not ordered
    for this board (cost). Instead no via lies in or touches a soldered pad (layout rule 12, `layout/board/RULES.md`,
    enforced by `layout/board/via_in_pad.py` on every `gen_board.py` run); the board is a standard JLCPCB six-layer
    order with ordinary tented vias. Only the exposed pads listed in `layout/board/README.md` ('Vias out of pads')
    keep small 0.2 mm vias in the pad, by datasheet, tented on the far side.
25. **BOM optimisation: 1 % JLC basic passives** (user instruction, 24 Nov 2026: "Don't use 0.1% resistors unless you
    *really* can't avoid it. Try to map as many of the parts as possible to JLCPCB's basic parts catalog, especially the
    caps and resistors. For the rest, apply some BOM optimization, trying to combine parts where possible."). All
    resistors are 1 % thick film except the U603 divider R603 / R604 (12k / 1.3k, 0.1 %; superseded by decision 30): +5V1 must stay <= 5.20 V (TPS63802
    VO maximum) and keep the GVA-84+ drain >= 4.8 V; a 1 % divider spreads +5V1 by +/-2.8 % (4.90-5.20 V at best), which
    puts the drain at 4.70 V in the worst corner. Tolerance errors of the former 0.1 % parts go to the RV101 LF/HF trim
    (input servo), the firmware offset / gain calibration (VOFS mid-scale, VNEG_REF -1.933 V) or to the regulator
    margins (decision 26). Values moved to JLC basic parts where the circuit allows (Rf2 22k, Rmid 33k, VNEG_REF
    10k / 15k, VBIAS_A 5.1k / 3.3k, VTAP_TH 33k / 1k, ADC_REF_MID 10k / 3.3k = 0.720 V, hold gain 1.00k / 510 = 2.96,
    +3V3 100k / 22k = 3.327 V, 2.2 uF 0402 -> 4.7 uF 10 V, 1 uF X7R -> X5R 25 V, green LED -> red); RF impedances, pads,
    the bridge, tap readout, terminations, divider-compensation and C0G capacitors are unchanged. BOM: 103 -> 94 fitted
    lines, 26 -> 35 basic and 74 -> 58 extended part numbers, 0.1 % resistors 20 -> 2, 73.13 -> 70.45 USD. Footprints
    and layout unchanged (values only). Details: `docs/research/power-tree.md` section 12, `docs/bom.md`.
26. **Asymmetric BUF802 rails, +5V1 5.115 V** (24 Nov 2026; net names +5V / -5V / +5V1 / +2V5 / -2V5 kept). A first
    version of this decision raised +5V1 to 5.40 V for symmetric +/-4.8 V rails; it is **withdrawn**: the TPS63802 output
    is specified 1.8-5.2 V and its VOUT overvoltage threshold is 5.5 V minimum, so 5.40 V (5.47 V worst case) was out of
    specification; the 2.49 R GVA-84+ feed resistors it needed (R419 / R420) are removed again and the pstrobe layout is
    back as before. Now (divider superseded by decision 30): U603 +5V1 = 5.115 V (5.054-5.177 V, 0.1 % divider); GVA-84+ drain 4.85-5.17 V. U604 runs
    asymmetric rails, which the BUF802 datasheet allows (SBOS998E 8.3: split supplies "symmetrically balanced around GND
    or asymmetric"; ROC total 9-13 V): OUT+ +4.908 V (4.760-5.056 V; in LDO dropout by up to 37 mV at the worst corner),
    OUT- -4.514 V (4.381-4.647 V), both 1 % dividers (309k / 100k, 270k / 100k); total 9.14-9.70 V (>= 9.13 V at the pins),
    OUT- headroom 0.181 V worst case (41 mA x 4.5 ohm, 26 mV dropout). Mid-supply sits +0.20 V above GND. U605
    +2.520 / -2.440 V (1 %, +/-2.5 %). Consequences and numbers: `docs/research/power-tree.md` section 12.
27. **Trigger front end without TMUX136 and SN65LVDS2** (BOM review 2, 24 Nov 2026; `docs/research/bom2-trigger.md`,
    `sim/trig_switch/RESULT.md`): the input selector is two four-diode bridges (D317 / D318 signal, D319 / D320 EXT_CLK,
    2 x BAT15-04W each; feeds R391-R394 1k) steered by Q301 SS8550 / Q302 MMBT3904 (R386 / R388 10k, R389 3.3k, R387 /
    R390 1k) from TRIG_SEL; TRIG_SEL low (reset) = signal, as before. Simulated -3 dB 1.26 GHz (signal) / 1.13 GHz (EXT),
    isolation 48.8 / 45.8 dB at 100 MHz, about 22 dB at 1 GHz (TMUX136 model 24-29 dB): operating rule "remove EXT_CLK when
    triggering on small signals"; offset +6.4 mV (calibrated); EXT_CLK range -0.9..+1.0 V (was +/-0.5 V). The COARSE
    receiver is a 9th COS3502 (U313 unit A, unit B tied off; COARSE valid to about 60 MHz, firmware ignores it above).
    Removed: U301, U304, R302-R305, C301-C303, TP301, net VSW_GND. Reason: TMUX136 32 pcs world stock, two open datasheet
    points, 3 extended lines; SN65LVDS2 extended. +0.30 USD parts, 7 more placements, cheaper below about 30 boards.
28. **Input servo without trimmer, C101 50 V, capacitors below 1 nF** (`docs/research/bom2-input-taps.md` A / B,
    `sim/bom2_input/RESULT.md`): RV101 removed; R118 Rf1 4.7k, R119 Rofs 10k, R123 Rmid 15k, R120 22k to GND, C106 Cint
    1 nF C0G (LF gain 0.1997 = HF gain; VOFS 0.2 / 1.289 / 2.7 V -> OUT +0.512 / 0 / -0.663 V). The LF/HF mismatch (BUF802
    Cin spread, up to +/-15 %, no part tolerance can remove it) is measured once with any 0.2-2 kHz square wave and
    corrected in firmware (IIR, unity at DC): residual flatness 0.34-0.78 % (trimmed analog 0.67 %; as built 0.29-0.55 % with the fixed-basis fit, decision 35). C101 = 1.5 pF
    +/-0.05 pF 50 V Murata (C76901; sees <= 47.7 V at the +/-50 V input rating, below 50 V/ns); C207 220p -> 100p, C631
    (DNP) 120p -> 100p (basic). C106 must stay C0G (X7R would make the servo time constant voltage dependent).
29. **Tap coupling capacitors C314-C345** (coordinator decision, overrides the printed-capacitor recommendation of
    bom2-input-taps.md C): the parts cannot be DNP (they are the only strobe path into each gate: no capture without them).
    The printed L1/L2 capacitor is **not** used: an L2 strobe island under every tap would cut the ground plane under the
    tap row and is not field-verified. The 0402 parts stay fitted, changed from the FH +/-0.25 pF part (its low corner
    0.25 pF fails, 60 ps rms) to Murata GJM1555C1HR50WB01D 0.5 pF +/-0.05 pF C0G (C76912, extended, JLC stock 121k,
    32 per board; 0.45 pF corner 17.1 ps rms). No layout change.
30. **+5V1 and the LM27762 dividers with 1 % JLC basic resistors** (replaces the 0.1 % U603 pair of decisions 25 / 26;
    `docs/research/bom2-power-passives.md` A, `docs/research/power-tree.md` section 13): R603 / R604 20k / 2.2k -> +5V1
    4.904 / 5.045 / 5.191 V (<= 5.20 V); GVA-84+ drain 4.71-5.19 V (P1dB about -1.2 dB at the low corner, phase gates
    still >= 2.4 V for 2.0 V needed). U604: R613 / R614 470k / 150k (0603), R605 510k (0603) / R606 200k -> +4.960 / -4.331 V,
    BUF802 total at the pins 9.008 / 9.29 / 9.57 V (9.0 V minimum met with all tolerances stacked, 8 mV;
    0.29 V typical), OUT- headroom 0.227 V. U605: R615 220k (0603) / R616 200k, +2.520 V unchanged. TPS63002 (fixed 5 V) rejected:
    no better accuracy, 1.99 USD, harmonic next to the strobe. No 0.1 % part remains on the board. Re-check (B2-4): the
    OUT+ setpoint (max 5.111 V, above the 5.0 V adjustable range) can exceed what +5V1F allows (min 4.877 V), so the
    positive LDO sits in dropout on about 1 board in 6 (PSRR lost, FB604 + capacitors still about -50 dB at 2 MHz); the
    9.0 V total holds either way because OUT+ >= 4.812 V. Keep FB603 / FB604 (0.05 R) and the as-built rail tracks: the
    8 mV margin leaves no room for added series drop (B2-5).
31. **Inductors 4 -> 3 types, beads 3 -> 2 types** (bom2-power-passives.md B): 47 uH 1210 kept only where a stage drives a
    50 R pad with <= 3 MHz content (L401, L302); L402, L403, L405 (47 uH 1210) and L404, L406 (2.2 uH 0805) -> 1 uH
    DFE252012F-1R0M 1008 (bias-tee rerun identical in the stub-loaded band, 48 MHz train 6.82 V vs 6.73 V); the 1k dampers
    R416-R418 are removed (R415 across L401 stays); L602 / L603 FHD252010S (262 in stock) -> the same DFE252012F-1R0M;
    L601 0.47 uH unchanged (TPS63802 needs 0.37-0.57 uH). Beads: FB601-FB607 -> BLM18PG121SN1D (basic, 2 A, 0.05 R;
    FB601 0805 -> 0603); FB608 -> BLM15HD102SN1D 0402 (the RF-bead line).
32. **USB input** (user review): F601 PTC -> 0 R 1206 (C17888, basic, same land); D601 SMAJ5.0A DNP (land kept);
    the 47 uF tantalum C632 -> RC damper 4 x (1 R 1206 R618-R621 + 47 uF 10 V X5R 1206 C632-C635), all basic: plug-in
    peak 5.27 V (5.57 V with strong MLCC derating) against the TPS63802 6.0 V abs max (8.6 V undamped). Re-check (B2-3,
    1.5 uH cable, 20 uF converter input): 5.33 V at a realistic 18 uF per damper capacitor, 5.78 V if each keeps only
    12 uF; a 5.5 V (vSafe5V maximum) hot-plug gives 5.58 V / 6.05 V. Accepted: the 6.05 V case needs the worst cable,
    the worst MLCC derating and a 5.5 V source together; a fifth 1 R + 47 uF branch (5.89 V) is the fallback if the
    first-board measurement shows less than 0.3 V margin.
33. **Resistor defragmentation and small parts** (bom2-power-passives.md D, all values JLC basic): pads sampler
    R402 / R404 / R403 100 / 120 / 100 (12.46 dB), line R307-R309 100 / 100 / 100 (11.48 dB), phase R408 / R410 / R409 and
    R412 / R414 / R413 120 / 100 / 120 (10.69 dB, edge about 10 ps slower); R202 / R203 24.9 -> 22 R (103 ps, 107.6 %
    efficiency, inside the bias trim); R378 / R379 43 -> 49.9 R (last tap 3.59 V vs 3.36 V, supersedes decision 22 for
    these two); R401 / R405 / R407 / R411 47 -> 49.9 R; TRIG_LEVEL R384 / R385 10k / 3.3k (-0.332..+0.466 V guaranteed;
    the old network did not guarantee +/-0.30 V); R107 17.8k -> 18k 0603; R105 / R106 4.99M -> 1M (R106 10 M since decision 35; overload re-bias 5x
    faster, 22 uV rms extra noise vs 0.35 mV floor); U701 TLV9001 -> TPH2501 (same pinout, U201 / U202 line, Vos 0.33 mV
    at OUT, +6.5 mA on +/-2V5); D401 BAT15-03W (0 stock) -> half a BAT15-04W (pin 2 on the stub node, pins 1 and 3 to GND;
    never pin 2 to GND with pin 3 on the node), D402 / D403 (DNP) alike with the polarity of their line (D403: pin 1 on
    PSTRB_K, pins 2 / 3 to GND).
34. **Final consolidation pass** (this review, after applying 27-33): R114-R116 300k 0402 (extended) -> 300k 0603 (C23024,
    basic, 75 V: more margin at the +/-50 V input; the string sits on VIN before Ctop, so the larger pads do not change
    the HF divider); R737 TRIG_SEL pull-down 2.0k -> 3.3k (the 2.0k line was single-use after R385; reset still selects
    the signal: pin +0.45 V, Q301 base 0.14 mA). Considered and not done: Cint 1 nF C0G -> 100 pF basic with a 10x servo
    network (no re-simulation), C618 / C619 0603 -> 0402 and the 0 R / 100 R / 120 R 0603 vs 0402 pairs (ratings / layout;
    basic lines cost no fee), DNP of the USBLC6-2SC6 (not asked). Study overlap resolved here: C303 (the 1 nF C0G line
    the input study meant to share) goes with the TMUX136, so the C0G line stays for C106 alone. Result of decisions 27-34: extended part numbers
    58 -> 27, fitted part lines 94 -> 80, no 0.1 % resistor, BOM 70.45 -> 70.39 USD (`docs/bom.md`).
35. **BOM-2 repair** (25 Nov 2026, independent re-check `docs/validation/recheck-bom2.md`, findings B2-1 ... B2-12):
    - **R106 1 M -> 10 M 0603 (C7250, basic), on B.Cu** (B2-9). With R105 = R106 = 1 M the bias network adds a third
      time constant (about 12 us) next to the servo doublet; the firmware fit then left 1.4-2.8 % flatness. Re-run of
      `sim/bom2_input` (as built R105 1 M 0402 / R106 10 M 0603): raw LF/HF mismatch -7.1 ... +6.0 % (60 boards),
      after correction 0.29-0.55 % flat (1 Hz-100 MHz), step deviation 0.13-0.26 %; overload recovery 49.9 us (was
      48.3); HF response unchanged. No 0402 basic part exists above 1 M (2 M / 4.7 M / 10 M 0402 are extended), and an
      0603 does not fit the R105 / C107 column, so R106 moved to the bottom side (static bias resistor, RULES rule 8,
      like R107); R105 on the gate node stays 0402.
    - **Firmware correction:** six first-order terms at fixed time constants (2-300 us, log spaced), amplitudes by
      linear least squares with a small ridge (the free two-term fit is ill-conditioned); applied only when the fitted
      |LF/HF - 1| exceeds 1 % (below that the raw response, 0.46 %, is flatter than the corrected one).
    - **Stock** (B2-2): LCSC / JLC stock of all 80 numbers re-read on 25 Nov 2026; BAT15-04W 865 (37 boards at 23 per
      board), TRF37D73 25 (5 boards): buy both ahead of the order (TRF37D73 at Mouser) or consign them.
    - **D319 silkscreen** moved to Fab where it ran into the board edge (B2-11). Other low findings are documented
      (decisions 30 / 32, `docs/theory-of-operation.md` section 10, `docs/VALIDATION.md`).
    BOM: 81 fitted lines (53 basic, 28 extended = 27 extended part numbers), 450 parts, 0 resistors at 0.1 %, 70.39 USD.
