# Low-cost sampling front end: design specification (working document)

Target: 2 GHz / 3 Gbps equivalent-time sampling front end, parts budget 80 USD (lowest of LCSC,
DigiKey, Mouser; the microcontroller is added by the user and not counted), switchable external
clock or phase recovery from the probed signal. Background and earlier simulations:
`docs/frontend-summary.md`, `docs/scope-frontend.md`, `docs/research/*.md`, `sim/*.py`.

Values marked (sim) are starting points; the simulation tasks may change them and record the final
values in `design/lowcost/sim/<area>/RESULT.md`. Those RESULT files take precedence over this file.

## Signal chain

```
SIG_IN (SMA) -- K1 50R termination relay -- 5:1 compensated divider (1 Mohm) -- BUF802 (+OPA197 servo)
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
`VOFS` (input offset), `ADC_IN`, `ADC_TRIG`, `ADC_REF_MID`, `TERM_50` (relay drive),
`SPI_SCK/MOSI/MISO/CS`, `I2C_SCL/SDA`, `FPGA_CLK`, `MCU_CLK`, `FPGA_DONE`, `FPGA_RECONFIG`, JTAG.

## Parts already chosen (lowest verified price, USD)
BUF802IRGTR 5.89; OPA197 0.75; TPH2501 0.43 (TPH2502 dual 0.58); TP2272 dual 0.50; TP1541A 0.38;
BAT15-04W 0.37 @10; TLV3801DSGR 5.13; TMUX136MRSER 1.22; TRF37D73IDSGR 1.50; GVA-84+ 2.99;
COS3502SR 0.36; GW1NZ-LV1QN48 6.68; MS5351M 0.91; LM27761 1.23; HFD3 relay 1.74.

## Files
- `design/lowcost/sim/<area>/` simulations (ngspice + Python, reuse `sim/` helpers), `RESULT.md` each.
- `design/lowcost/kicad/` KiCad 7 project (hierarchical), generators in `design/lowcost/kicad/gen/`.
- `design/lowcost/layout/<fragment>/` layout fragments (pcbnew-scripted `.kicad_pcb`).
- `design/lowcost/docs/` theory of operation, BOM.
