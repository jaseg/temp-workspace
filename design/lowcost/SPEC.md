# Low-cost sampling front end: design specification (working document)

Target: 2 GHz / 3 Gbps equivalent-time sampling front end, parts budget 80 USD (lowest of LCSC,
DigiKey, Mouser; the microcontroller is added by the user and not counted), switchable external
clock or phase recovery from the probed signal. Background and earlier simulations:
`docs/frontend-summary.md`, `docs/scope-frontend.md`, `docs/research/*.md`, `sim/*.py`.

Values marked (sim) are starting points; the simulation tasks may change them and record the final
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
COS3502SR 0.36; GW1NZ-LV1QN48 6.68; MS5351M 0.91; LM27761 1.23.

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
6. **TMUX136** on a local -0.9 V ground; **SN65LVDS2** coarse receiver bridged with 2 x 470 R; 100 R across
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
    U701 TLV9001 making VNEG_REF = -0.68 x VREF+ for the VOFS mid-scale (offset drift). Details: `kicad/README.md`.
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
24. **Plugged vias** (validation BIASTEE-6 / recheck RF2-4, 24 Nov 2026): the board is ordered with resin-plugged, capped
    vias for the open vias that touch soldered pads (list in `layout/board/README.md`); the vias are not moved.
