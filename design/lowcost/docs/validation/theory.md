# Validation: theory of operation (key `theory`)

Scope: `docs/theory-of-operation.md` (ToO) against physics, `sim/*/RESULT.md` (+ json), `kicad/export/scope-fe.net`,
`kicad/README.md`, `SPEC.md`, `layout/board/README.md` and `layout/board/blocks/*/README.md`, datasheet extracts
(Gowin DS841-2.8E, COS3502, GVA-84+, TRF37D73, BUF802). Validation only; no design file changed.
Own arithmetic: `/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/val/theory/calc.py` (output `calc.out`).

## Method
1. Recomputed every network transfer, range and LSB from netlist values (VREF+ 2.9 V, 12 bit).
2. Recomputed the time base (bits, strobe periods, reverse-pulse instants, ADC cycles) and checked it against the
   STM32G474 ADC cycle counts and the GW1NZ-1 PLL / gearbox limits (DS841 tables 3-16 and 3-20).
3. Recomputed phase-detector window, stamp rates and gap statistics for the simulated (34.7 ps) and as-built (30 ps) spacing.
4. Checked the efficiency-correction formula and the noise budget against `sim/sampler/RESULT.md`.
5. Compared every part/value/pin statement in the ToO with the netlist (457 parts) and the pin tables (all FPGA and
   MCU pins of the ToO tables queried from the netlist).
6. Compared each "simulated/verified" claim with the configuration in the deck scripts vs. the as-built layout READMEs.

## Checked and found correct (recomputed)
- TRIG_LEVEL = 0.2424 Vdac - 0.1394 x 2.5 V, -0.300..+0.306 V, 0.172 mV/LSB (R383 5.1k, R384 8.87k, R385 2.0k).
- VBIAS_A = 0.385 Vdac - 1.537 V: -1.460..-0.497 V, 0.273 mV/LSB (R733 7.5k / R734 4.7k); reset about -1.69 V with PA6 at -0.4 V.
- VBIAS_K = Vdac (R735 5.1k, R736 100k), VTAP_TH = Vdac/31 (R723 30k / R724 1k): 6.5..87 mV, 0.023 mV/LSB.
- VNEG_REF = -2.9 x 10.0k/14.7k = -1.973 V; ADC_REF_MID = 2.9 x 10k/40k = 0.725 V (R703/R704); VOFS 0.580 - 0.402 Vdac.
- TMUX136 local ground R304 1.5k / R305 2.7k: -0.893 V; SEL from R302/R303: +1.23 V high, -0.89 V low (= its GND).
- Hold chain: U201 G = 1 + 1.00k/499 = 3.0, Vadc = 2 x 0.725 - U201out: 0.415..2.485 V for +/-0.5 V at the bridge (g 0.69).
- Correction x_k = (v_k - 0.31 v_(k-1))/0.476 follows from v_k = (1-e)v_(k-1) + e(g x_k + ped) with e = g = 0.69.
- Time base: 1.0417 ns/bit; PH 20 bits = 20.83 ns; S 320 bits = 333.3 ns; reverse pulses at +10.42 ns (PH) and +166.7 ns (S).
  ADC 6.5 + 12.5 = 19 cycles = 316.7 ns < 20 cycles = 333.3 ns; window 40..148.3 ns, 18.3 ns before the S reverse pulse
  (ToO says 18.6 ns); variant 40..175.4 ns against 208.3 ns. A periodic hardware trigger needs only conversion time < period,
  so a 1-cycle spare is fine if the trigger latency is constant (synchronous clock mode).
- PH reverse pulse at +10.42 ns reaches COS3502 outputs >= 10.42 + 4.5 ns (tPD typ, COS3502 DS p.5) = 14.9 ns, after the
  +12 ns latch; COS3502 VCM -0.2 V..Vs+0.2 V covers the -21..+55 mV sum node; Vos 5 mV max < 24 mV half swing.
- Trigger minimum: 200 mVpp tip x 0.200 = 40 mVpp at BUF802 OUT, full amplitude at the open TMUX end = +/-20 mV. Correct.
- Stamp rate 48e6 x 560 ps = 0.027 f; 10 k/s at 370 kHz; P(no hit in 100 us) < 1e-3 from 2.6 MHz; 3 Gbps PRBS: 0.75e9
  rising edges/s, P(hit) 0.34 -> 16.5 M/s ("half of 34 M/s"). Arithmetic consistent for a 560 ps window.
- All FPGA pins of the ToO table (strobes 39/40, 38/35; TAP0..7 28-32/41/47/6; TAP15..8 9-11/13-17; COARSE 27; ADC_TRIG 18;
  SPI 20/21/22/24; JTAG 3/4/5/7; DBG2 8; DONE 46; RECONFIG 48; CLK 33) and the MCU pins (PA0, PA2, PA4, PA5, PA6, PB1, PB11,
  PF0, SPI PB3/4/5/9, I2C PA15/PB7, PB6, PB13, PA1, PA11/12, PA9/10, PF1) match the netlist. J501 pinout matches.
- Strobe/line pads 82/91/82, 100/68/100, 47 R series, 49.9 R S_STROBE_N termination, 2.2 uH GVA chokes, 47 uH TRF chokes,
  2 x 470 R LVDS2 bridge, 100 R LVDS load, 2.2k/2x1k readout (VTAP current 16 x 5 V/6.4k = 12.5 mA), 0.5 pF tap caps,
  D402/D403 DNP, D401 fitted (cathode on the stub node: correct polarity), R122 DNP (EXT_CLK single 49.9 R R301): as stated.
- Power: +3V3 TRF37D73 5 x 53 mA typ (65 max) + COS3502 8 x 6.6 mA + FPGA/MCU/clock ~0.1 A = 0.42-0.49 A; GVA-84+ 2 x 108 mA
  (130 max); boost input about 0.19 A (BUF802 35.5 mA at R_Bias 17.8k = R107). Total 0.83-0.95 A: "0.85-0.9 A" is right.

## Findings
**THEORY-1 (medium, verified) Time base exceeds the GW1NZ-1 PLL limit.** 960 Mbit/s from OSER10 needs FCLK = 480 MHz
(DDR, PCLK 96 MHz x 5), i.e. rPLL CLKOUT 480 MHz and VCO >= 960 MHz. DS841-2.8E table 3-20, GW1NZ-1 LV C6/I5 (U501 is
GW1NZ-LV1QN48C6/I5): VCO 400-800 MHz, CLKOUT 3.125-400 MHz. The gearbox (FMAXOSERx 1100 Mbps, table 3-16) is not the
limit; the clock is. In spec the maximum is 800 Mbit/s (FCLK 400 MHz). The same applies to the 960 Mbit/s COARSE IDES.
ToO section 6 table, SPEC decision 17. Fix (firmware/clock only, MS5351M is programmable): e.g. FPGA_CLK = MCU_CLK = 20 MHz,
x40 = 800 Mbit/s (VCO 800), PH 20 bits = 40 MHz, S 320 bits = 2.5 MHz = 400 ns = 24 ADC clocks at 60 MHz (MCU 20 MHz HSE
x6 = 120 MHz; MS5351M 25 MHz x 24 = 600 MHz / 30). Costs 17 % stamp rate, eases COS3502/latch timing. Re-state all derived numbers.

**THEORY-2 (medium, verified) Phase-detector key figures are for the simulated 35/70 ps line, not the as-built one.**
Built (blocks/phase/README.md lines 46-55): PSTRB 0.10 mm 62 R, 4.514 mm, 26.25 ps unloaded -> 39.40 ps loaded, 41.3 R;
PH_LINE 0.10 mm 62 R, 9.707 mm, 69.40 ps; difference 30.0 ps. ToO still gives 34.7 +/- 3.1 ps, window 58-579 ps (table,
section 1), "560 ps window" (lines 38, 200), diagram "16 x 70 ps / 16 x 35 ps" (lines 28, 30), and computes stamp rates from
560 ps. With 30 ps: window 15-16 x 30 = 450-480 ps -> 0.022-0.023 f stamps/s (not 0.027 f), 10 k/s from 430-460 kHz (not 360),
< 1e-3 gap probability from 3.0-3.2 MHz (not 2.5), 3 Gbps 13.7 M/s (not ~17). Single-shot rms (19 ps) not re-derived.
Also the "difference" rule itself is not what the sim shows: phase_array RESULT measured strobe 34.2 ps/tap and signal
75.7 ps/tap (74.1 in results.json), whose difference is 41.5 ps, yet the reported spacing is 34.7 ps. The as-built spacing is
therefore uncertain by about +/-7 ps, and "aim the meander 5 ps shorter" (ToO line 159) has no consistent basis.
Fix: re-run `sim/phase_array/deck.py` with z_s 62 R / td_s 26.25 ps, 0.5 pF, 0.53 pF/0.465 pF pad loads, 49.9 R
terminations, signal sections for 69.4 ps; update the table, window, rates and section 1 diagram from that run.

**THEORY-3 (medium, verified) GVA-84+ supply is below its minimum at nominal USB, not only at 4.75 V.** GVA-84+ Vd
4.8-5.2 V (datasheet table, gva84.txt line 139). bias_tee RESULT: choke/bead drop 0.15-0.18 V; plus PTC F601 and FB601 at
0.85-0.9 A (about 0.1-0.2 V together) and cable drop. A 5.00 V source gives Vd about 4.6-4.75 V; 4.75 V USB gives about 4.4-4.5 V.
GVA current -0.058 mA/mV (datasheet) -> -15..-25 mA, lower Psat: this feeds directly into open risk 1 (tap 15 already
below 2.0 V in the pessimistic case). The AMS1117 (dropout ~1.1-1.3 V) is also at the edge at VBUS 4.4-4.5 V.
ToO risk 8 says "below 4.8 V when USB delivers 4.75 V". Fix: state it as the typical case; consider powering the GVAs from the
+5V4 boost (5.32 V, needs ~0.22 A more from the MT3608) or re-rank risk 1/8 together.

**THEORY-4 (medium, likely) Sample rate is a burst rate; throughput and firmware budget not addressed.** 3.0 MS/s x
(12-bit ADC word + SPI record "(strobe index, k, valid)" with sequence number, >= 16 bit) = >= 12 MB/s into 128 KB SRAM
(G474CB): full in about 8-10 ms. SPI1 master max 60 Mbit/s at 120 MHz (/2) vs >= 48 Mbit/s needed (80 % duty, DMA, no gaps).
USB FS bulk about 1 MB/s -> sustained <= ~0.25 MS/s. 40 CPU cycles per sample at 120 MHz for pairing, correction and
calibration: only off-line. ToO sections 1/6 present 3.0 MS/s without this. Fix: state burst length, duty and sustained rate;
pack records in the FPGA (e.g. 8 bit), or decimate valid stamps only.

**THEORY-5 (medium, suspected) Strobe kick-out into the trigger is phase-locked to the strobe grid.** 19 mVpp at the TMUX
end (sampler deck with an ideal 3 V / 130 ps strobe, not the final 4.6 V 2xTRF chain + 80 ps stub; strobe/bridge_results.json
shows the kick rising from 18 to 29 mV between those drive cases at its own node) against +/-20 mV minimum signal. Because the
S_STROBE sits at a fixed bit offset from a phase strobe, any comparator toggle it causes lands at a fixed tap position and
biases the tracking-loop fit (a systematic, not random, error). ToO risk 4 treats it only as an amplitude issue.
Fix: re-simulate the kick with the final chain; reject stamps from the phase strobe(s) coincident with S_STROBE in the FPGA,
or fit the 100 R / ferrite option at R113.

**THEORY-6 (low, verified) Sampler and input decks simulated other parasitics than built.** Hold node: layout copper 268 fF
(windowed, blocks/analog/README.md line 44) is not in `sim/sampler` (2.2 pF + 1 pF + 2.7 pF amp model): +7.9 % hold C, e
0.69 -> 0.66 in the 3 V case. Input: deck uses Csma 0.25 pF, Cvin 0.15 pF, pads 0.07 pF (`sim/input/input_stage.py` lines
47, 84, 95); built SMA centre pad + taper 824 fF, divider node 196 fF, BUF802 input 211 fF (windowed). The ToO "2.0 pF",
S11 -3.4 dB at 2 GHz and 1.7 GHz unterminated BW are therefore optimistic; HF divider ratio drops about 1.5 % (inside the trim).

**THEORY-7 (low, verified) Noise and correction text.** For independent readings the deconvolution noise factor is
sqrt(1 + 0.31^2)/0.476 = 2.20, not 2.08 (=1/0.48): 165 uV -> 363 uV, not 344 uV. "Doubles the noise" compares with the
hold node; vs. the non-deconvolved input-referred 239 uV it is x1.52. With the final strobe (e ~1, g 0.74, ToO section 3)
the figure is about 223 uV at the bridge (1.1 mV at the tip), so the key-figure "0.35 mV / 1.75 mV" belongs to the 3 V-strobe
case. State which strobe case the table uses.

**THEORY-8 (low, verified) Stale or inconsistent text.**
- Section 4 line 135: stub "13.2 mm at 6.057 ps/mm on the old 4-layer"; built TL401-403 13.503 mm at 5.925 ps/mm.
- Section 5 lines 160-164: 4-layer geometry (0.26 mm 59 R / 0.16 mm 72.8 R, 40/75 ps "effective stays 35 ps") still leads.
- TRIG_LEVEL reset state "-0.34 V" (ToO line 280, kicad/README table): with PA4 high-Z it is -2.5 x 1.632k/8.87k = -0.46 V
  (-0.34 V is PA4 at 0 V); PA4 then sits about -0.4..-0.46 V via 5.1k (substrate injection as for PA6).
- Latch "window 10-20.8 ns" vs "valid from strobe + 9 ns ... to + 24 ns" (line 180-181).
- Section 10 omits `sim/bias_tee` (lists "47 uH choke SRF" as unverified; bias_tee covers it, but on the 4-layer parasitics).
- kicad/README: "TRF37D73 x6" (line 128; netlist has 5: U303, U401, U402, U403, U405); J501 "DBG2 (FPGA pin 6)" (line 106; is 8);
  "IDES on pin 47" (line 261; is 27); "+160 ns" (line 250); "strobe lines 40 ps per tap" (line 252).
- SPEC decision 4 (40/75 ps, 0.16/0.26 mm, JLC04161H-7628) and decision 9 not marked superseded by decision 15 / the 6L build.
No AD9508, relay, op-amp difference amplifier, J701 or old FPGA pin numbers remain as live statements in the ToO.

## Not covered by any simulation (as built)
- Phase array with 62 R / 41.3 R loaded strobe lines into 49.9 R (|G| 0.09), 0.5 pF hold caps, 30 ps difference, 48 MHz.
- Phase array with 3 Gbps data (line edge 321 ps 10-90 at tap 15 vs 333 ps UI; feed-through plateaus with a falling edge after
  the strobe; bubble codes from 1-UI pulses inside a 450 ps window).
- Strobe kick into the trigger with the final strobe chain; reverse-pulse shift at 3.0 MHz with the 268 fF node.
- Six-layer bias-tee parasitics (bias_tee used JLC04161H-7628 via/pad values); balun DLW21SN pad map.
- Input stage with the built SMA / node capacitances; real BUF802.
- Anything FPGA/firmware: PLL plan, OSER10/IDES placement, IODELAY on serialiser pins, tracking loop, LUT fit, SPI/DMA throughput.

## Feasibility risks, ranked (validator's view)
1. Phase-strobe amplitude at tap 15 (behavioural GVA, pessimistic 2.0-2.3 V) made worse by GVA Vd 4.4-4.75 V (THEORY-3) and
   the 41 R line (launch into 41.3 R gives about 0.90 of the 50 R amplitude).
2. Time base out of FPGA spec (THEORY-1): fixable in firmware, but every derived number moves.
3. As-built tap spacing / window unknown to +/-7 ps (THEORY-2), not re-simulated.
4. Strobe kick-out as a systematic stamp error (THEORY-5).
5. Real BUF802 bandwidth (~2 GHz expected vs 3.3 GHz modelled) and the built input parasitics (THEORY-6).
6. Data path / firmware throughput (THEORY-4) and 1152-LUT budget.
