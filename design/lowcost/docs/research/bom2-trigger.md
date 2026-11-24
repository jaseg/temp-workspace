# BOM review 2: trigger front end (TMUX136, SN65LVDS2, C303)

Date 24 Nov 2026. Scope: `kicad/gen/gen_trigger_phase.py` U301-U304; simulation `sim/trig_switch/`
(RESULT.md, RESULT.json). Part classes and stock verified today with the LCSC product-detail JSON and the
jlcpcb.com parts search (same method as `docs/bom.md`, "LCSC verification"). Nothing in the schematic
generator, BOM or layout is changed by this note; it is the decision record for the change.

## Summary of decisions
| # | Decision | Reason |
|---|---|---|
| A | **Replace TMUX136 (U301) by two diode bridges (4 x BAT15-04W) + SS8550 + MMBT3904 + 9 R** | removes an extended part with 32 pcs world stock at LCSC/JLC, its two open points (Ron unspecified 0.4-1.4 V above its GND, 100-1000 us/V ramp) and 3 extended BOM lines; bandwidth and isolation of the same order as the TMUX136 |
| B | **Replace SN65LVDS2 (U304) by a 9th COS3502 (U313, unit A; unit B tied off)** | coarse path needs < 100 MHz; COS3502 already on the board, CM range covers the 1.2 V LVDS level; one extended line less |
| C | **C303 (1 nF C0G) is deleted** with the TMUX136 local ground | no question of C0G vs X7R left |

## Option survey for (A)
Facts that decide it: BUF_OUT_T is DC-coupled and can reach the BUF802 clamps (+/-1.5 V); TRIG_LEVEL
spans only -0.30..+0.31 V (DAC network); TLV3801 IN+ needs VEE + 1.5 V = -0.94 V..VCC; BAT15 VR max 4 V.
1. **Series diode per input, steered bias**: offset one diode drop (0.29 V at 2 mA) puts the signal path
   outside the TRIG_LEVEL range, drift 2 mV/K (20 K = 40 mV = about 130 ps on a 1 Vpp 100 MHz clock), and
   deselecting the DC-coupled BUF_OUT_T needs the common node above +1.5 V, again outside TRIG_LEVEL.
   Rejected.
2. **Four-diode bridge per input**: offset cancels (simulated +6 mV fixed, 7 uV/K), off state is reverse
   biased on both sides whatever the source does, no DC path through an off bridge even at +/-1.5 V.
   **Chosen.**
3. **Shunt muting**: a forward-biased diode (about 15 R) against the 25-50 R source gives only 8-13 dB.
   Rejected.
4. **EXT summed AC-coupled onto IN- with the signal muted**: needs muting of BUF_OUT_T (option 3, too weak)
   and loses isolation of EXT in signal mode completely. Rejected.
5. **Selection after the comparator**: a second TLV3801 (5.13 USD). Rejected.

## Isolation requirement
- Signal mode, EXT left connected: the smallest trigger is +/-20 mV at the comparator; a disturbance of
  10 % of that (2 mV) from a +/-0.5 V EXT signal needs 48 dB. Met by the bridge at 100 MHz (48.8 dB; TMUX136
  reference 40.7 dB), not above (36 dB at 240 MHz, 22 dB at 1 GHz). Neither switch meets it at GHz:
  operating rule "remove / stop EXT_CLK when triggering on small signals" (theory doc section 5).
- EXT mode: the signal residual shifts EXT crossings by v_res / slope. For <= 5 ps at an EXT slope of
  1 V/ns and a +/-0.3 V signal, v_res <= 5 mV, i.e. 36 dB. Met up to about 250 MHz signal content (45.8 /
  37.7 dB at 100 / 240 MHz); at 1 GHz 22.8 dB (TMUX136 reference 28.6 dB) gives about 22 mV, i.e. 20 ps at
  1 V/ns. For signals synchronous to the clock the error is the same every cycle (fixed shift, removed by
  calibration); for data it is data-dependent jitter. Accepted: same order as the TMUX136 (-34 dB at
  240 MHz is its only datasheet point).

## Chosen circuit (all values basic or already on the board)
```
BUF_OUT_T (line end) = X1 ----+---- D_a1 pin 3                 EXT_CLK SMA -> X2 --+-- 49.9 R (R301) -> GND
                                                                                   +-- D_a2 pin 3
Bridge k (k = 1 SIG, 2 EXT): package P_ak (BAT15-04W): pin 1 = Tk, pin 3 = Xk, pin 2 = Bk
                             package P_bk (BAT15-04W): pin 1 = Tk, pin 3 = Y,  pin 2 = Bk
Y = TLV3801 IN+ (U302.5)
T1 -1k- S    B1 -1k- SB    T2 -1k- SB    B2 -1k- S        (4 x 1k 0402, C11702)
Q1 SS8550 (C8542): E +2V5, B -10k- TRIG_SEL, C = S;  R2 1k S -> -2V5
Q2 MMBT3904 (C20526): E -2V5, B -10k- S, B -3.3k- -2V5, C = SB;  R5 1k SB -> +2V5
```
- TRIG_SEL low (MCU reset: PA1 high-Z, R737 2.0k pull-down): S +2.43 V, SB -2.32 V, **signal selected**,
  bridge 1 at 2.1 mA, bridge 2 off with T2 / B2 on the saturated transistors. TRIG_SEL high: both
  transistors off, bridge 2 on at 1.1 mA through R5 / R2, bridge 1 off at -1.38 / +1.38 V. Q2 off margin:
  Vbe 0.26 V with S at -1.38 V. Rail current 12.5 mA (SIG) / 1.1 mA (EXT) from the LM27762 rails.
- Polarity is unchanged for firmware: TRIG_SEL low = signal (as the TMUX136 SEL low = A).
- Switch time about 0.5 us (0.37 V spike on Y when going back to SIG): firmware waits 10 us.
- Power-up: no ramp-rate condition (the TMUX136 needed 100-1000 us/V). With +/-2V5 off and TRIG_SEL high,
  0.3 mA flows from the GPIO through Q1's base-collector junction into S: harmless; at reset TRIG_SEL is
  low anyway.
- Removed: U301, R302 10k, R303 17.8k, R304 1.5k, R305 2.7k, C301 + C302 100 nF, C303 1 nF C0G, TP301
  VSW_GND, the VSW_GND PWR_FLAG. Kept: R301 49.9 R EXT termination (now at bridge 2 X2).
- New refs (proposal): D317-D320 BAT15-04W, Q301 SS8550, Q302 MMBT3904, R3xx 1k x 6, 10k x 2, 3.3k x 1.

### Simulated performance (variant A, `sim/trig_switch/RESULT.md`)
| | Bridge | TMUX136 (model) |
|---|---|---|
| SIG -3 dB / loss at 100 MHz | 1.26 GHz / -1.1 dB (0.8 dB is the 500 R load on the line end) | 0.93 GHz / -0.05 dB |
| EXT -3 dB | 1.13 GHz | 1.79 GHz |
| EXT leak, SIG mode, 100M / 1G / 2G | -48.8 / -22.4 / -19.4 dB | -40.7 / -24.5 / -23.7 dB |
| SIG leak, EXT mode, 100M / 1G / 2G | -45.8 / -22.8 / -19.8 dB | -45.9 / -28.6 / -27.7 dB |
| DC offset, drift (SIG) | +6.4 mV, 7 uV/K (calibrated, item 9) | Ron x 1 uA |
| Kick-back per 50 fC (assumed) | 12.9 mV, settles 0.32 ns | 7.2 mV |
| EXT return loss 100M / 1G / 2G | -26 / -13 / -10 dB | not modelled |
- BUF_OUT_T stays a 49.9 R-fed high-impedance end (bridge input 500 R, gain 0.88 at DC): the 22 mV
  sampler kick-out arrives as before (-0.8 dB). The smallest trigger at the tip grows from about 200 to
  about 230 mVpp (gain 0.88).
- EXT_CLK levels (DC-coupled, 50 R): passes -0.9..+1.0 V at the SMA (linear to +/-0.9 V, gain 0.97); the
  lower limit is the TLV3801 common mode (-0.94 V), the upper the BAT15 reverse voltage in signal mode
  (3.4 V at +1.0 V; 4 V absolute at +1.5 V). The crossing must lie inside TRIG_LEVEL -0.30..+0.31 V: sine
  or square clocks centred on 0 V, 0.1-1.8 Vpp. LVCMOS (0..3.3 V) needs an external SMA DC block and a 6 dB
  attenuator. The old range was +/-0.5 V.

### Cost
| | Parts per board | Extended BOM lines |
|---|---|---|
| TMUX136 path | 1.18 (U301 @10) + 0.02 passives = 1.20 USD | 3 (TMUX136, 2.7k, 1n C0G) |
| Bridge path | 4 x 0.3655 + 0.015 + 0.010 + 9 x 0.0012 = 1.50 USD | 0 new (BAT15-04W already used) |
Net +0.30 USD per board in parts, -3 extended-part fees (about 3 USD each per order): cheaper for any
order under about 30 boards; +7 placements. BAT15-04W C5380972: stock 1465 (24 Nov 2026), 22-23 per board
= about 63 boards. TMUX136 C2673277: stock 32 (LCSC and JLC).

### Layout notes
- Four SOT-323 in a 2 x 2 block at U302 pin 5: P_b1 and P_b2 with pin 3 (Y) within 1 mm of IN+, Y a
  single short L1 stub (< 0.5 mm per pin), no via on Y. P_a1 at the BUF_OUT_T line end (pin 3 = the line
  end, no stub), P_a2 at the EXT trace with R301 at its pin 3.
- Each bridge: P_a and P_b side by side, pins 1 (T) facing and joined by one short trace, pins 2 (B) the
  same; the 1k feeds sit at the T / B traces, their far ends on L3 bias traces to S / SB. Mirror the two
  packages of a bridge so the polarity pairs see the same copper (offset matching).
- No capacitor on S, SB, T or B (S / SB move with the signal in one state). Q1 / Q2 and their resistors
  away from the RF block, on L6 if convenient; +2V5 / -2V5 at the emitters with the existing 100 nF.
- L2 ground under the bridge block continuous; GND vias at the R301 pad and around the block.

## (B) SN65LVDS2 -> COS3502
- Requirement (theory doc section 5): COARSE identifies the edge (cycle count) for sparse stamps, captured by
  IDES10 at 768 Mbit/s (1.302 ns bins); latency calibrated (item 7), it must be stable to well inside one bin.
  Already limited to about 100 MHz edges by the 2 x 470 R bridge (1.4 ns RC). Above that the type-2 loop
  works from dense fine stamps (at 100 MHz, 2.3 M stamps/s) and does not need COARSE.
- COS3502 (datasheet rev 1.0, Cosine): tpd 3 ns typ / 5.5 ns max at 50 mV overdrive (4.5 / 7 at 20 mV),
  skew 0.5 ns, tr / tf 1.5 ns, toggle 90 MHz (5 V, 50 mV overdrive; 3.3 V not specified), VCM -0.2..Vs+0.2
  = -0.2..3.5 V, IB 2 pA (no DC load on the 470 R legs), hysteresis 1.6 mV, input capacitance not specified.
- TLV3801 output stage runs between VCC (+2V5) and GND: VCC - GND = 2.52 V < 2.6 V gives VOCM 0.92-1.29 V
  (typ 1.2), VOD 250-450 mV: inside the COS3502 range; the comparator sees +/-175 mV (HF) to +/-350 mV
  (LF) differential, overdrive far above 50 mV, so delay dispersion stays small.
- SN65LVDS2: 400 Mbit/s, 2.5 ns typ; capability unused beyond the 100 MHz bridge limit.
- Lost: possibly the band between the COS3502 toggle limit at 3.3 V (estimate 60-90 MHz) and about 100 MHz;
  firmware treats COARSE as invalid above 60 MHz (known from the fine-stamp frequency).
- FPGA direct read: no. GW1NZ-1 has no differential input (DS841 note, theory doc); LVCMOS33 thresholds
  0.8 / 2.0 V do not bracket 1.03-1.38 V, and the bank stays at 3.3 V for the taps; a two-pin
  pseudo-differential read has the same problem. No free COS3502 half: U305-U312 serve the 16 taps.
- Change: U313 COS3502SR (C49304672, extended but already used, stock 3705 / 3709, 0.3588 USD @5): pin 1
  +INA via 470 R from CMP_P, pin 2 -INA via 470 R from CMP_N, pin 7 OUTA -> COARSE, pin 8 +3V3 with 100 nF,
  pin 5 GND; unit B: pin 3 to GND, pin 4 to +3V3 (output low, quiet), pin 6 open. Polarity as before.
  Saves 0.27 USD (0.6247 @10 vs 0.3588) and one extended fee. Layout: SOIC-8 in the U304 place, 470 R at
  the U302 pins as before.

## (C) C303
C303 (1 nF C0G, extended) decoupled the TMUX136 local -0.9 V ground; it goes with U301, R304, R305 and C302.
No change needed elsewhere.
