# scope-fe KiCad 7 project (generated)

Hierarchical schematic for `design/lowcost/SPEC.md`. **Every `.kicad_sch` here is generated; do not edit
in KiCad and expect it to survive** — change the generator in `gen/` and rerun.

## Regenerate

```
cd design/lowcost/kicad/gen
python3 test_schlib.py        # library self-test (96 pin placements, rotation/mirror, via kicad-cli netlist)
python3 gen_all.py            # all sheets + project files + netlist checks + export/ (PDF, SVG, PNG)
python3 gen_all.py --no-export
```

`gen_all.py` runs `gen_<sheet>.py` for each critical sheet if it exists, otherwise the placeholder from
`gen_placeholders.py` (which never overwrites a non-placeholder file), then `gen_fpga_clock.py`,
`gen_power.py`, `gen_mcu_if.py`, `gen_root.py`, and collects every embedded `scope-fe:` symbol into
`scope-fe.kicad_sym`. It then exports the netlist (`export/scope-fe.net`), asserts key inter-sheet connections
(FPGA/MCU pins, VBIAS_A/K, STRB_A/K, BUF_OUT_S/T, EXT_CLK, TRIG_LEVEL, TERM_50, VOFS, ADC_IN, ADC_REF_MID),
fails on any two-pin part with both pins on one net, lists single-node and NC-flagged nets, writes
`export/scope-fe.pdf` plus one SVG/PNG per sheet (PNG via `gen/svg2png.js`, node + playwright/chromium), and
finally runs `gen_bom.py` (`docs/bom.csv`, `docs/bom.md`). Each critical sheet also has its own check:
`python3 gen_<sheet>.py --check <dir>` (input: always run).

`Sheet.render()` splits every wire at each pin, wire end and label lying on its interior (`split_wires`):
KiCad 7 connects only at wire ends. Before this was in the library, mcu_if had 9 false opens (VOFS, VBIAS_A/K,
TRIG_LEVEL feedback/divider resistors, relay gate pull-down) and the split exposed three real shorts that are now
fixed (strobe bias tees drawn with the wire through the bead and choke; crystal XB on the GND symbol).
Requires KiCad 7.0.x `kicad-cli` and `/usr/share/kicad/symbols`.

## Files and ownership

| File | Generator | Owner |
|---|---|---|
| `gen/schlib.py` | library (API in its docstring) | infrastructure |
| `gen/common.py` | sheet table (`SHEETS`: names, ref bases, sheet pins), passive helpers | infrastructure; change sheet pins here only |
| `scope-fe.kicad_sch`, `.kicad_pro`, `scope-fe.kicad_sym`, `sym-lib-table` | `gen_root.py`, `gen_all.py` | infrastructure |
| `input.kicad_sch` | `gen_input.py` | input stage (SMA, HFD3/3 relay, 5:1, BUF802, OPA197 servo, splitter, EXT_CLK SMA), refs 1xx |
| `sampler.kicad_sch` | `gen_sampler.py` | bridge 2x BAT15-04W, 2.2 pF hold, TPH2501 x2, refs 2xx |
| `trigger_phase.kicad_sch` | `gen_trigger_phase.py` | TMUX136, TLV3801, TRF37D73 line driver, 16 taps, COS3502 x8, SN65LVDS2, refs 3xx |
| `strobe.kicad_sch` | `gen_strobe.py` | sampler strobe (2x TRF37D73, balun, fitted BAT15-03W clamp), phase strobes (TRF + GVA-84+ x2, 80 ps stubs), refs 4xx |
| `fpga_clock.kicad_sch` | `gen_fpga_clock.py` | infrastructure, refs 5xx |
| `power.kicad_sch` | `gen_power.py` | infrastructure, refs 6xx |
| `mcu_if.kicad_sch` | `gen_mcu_if.py` | infrastructure, refs 7xx |
| `gen/gen_placeholders.py` | placeholder sheets (unused now: all four critical generators exist) | infrastructure |
| `gen/gen_bom.py` | `../docs/bom.csv`, `../docs/bom.md` from `export/scope-fe.net`; price table inside | integration |
| `export/` | `scope-fe.net`, `.pdf`, per-sheet `.svg`/`.png` (generated) | - |

A critical-sheet generator must: `sh = common.new_sheet("<name>")`, put one hierarchical label for every
net in `common.hier_pins("<name>")` (same name and shape), draw the signal path with `wire/path`, and
`sh.save()`. The root picks the sheet up unchanged. Need a new inter-sheet net? Add it to `SHEETS` in
`common.py` (both sheets) and rerun `gen_all.py`.

## Conventions

- Units mm, Y down, 1.27 mm grid (`g(n)`). Rotation counter-clockwise, `mirror="x"|"y"` as in KiCad.
- Power: global power symbols only: `+5V -5V +3V3 +2V5 -2V5 +1V2 VBUS GND`. Local intermediate rails on the
  power sheet are labels (`+5V4`, `+5V4F`, `-5V_LDO`). `VBUS` is the filtered USB 5 V (relay coil, GVA-84+).
- Inter-sheet nets: SPEC names as hierarchical labels; the root connects equal names via local labels at
  the sheet pins. `CMP_P/CMP_N` stay inside `trigger_phase` (TLV3801 -> line driver and LVDS receiver).
- Fields: `Footprint` (KiCad standard library, checked to exist at generation), `LCSC`, optional `MPN`,
  `Price`, `Note`. Passive LCSC numbers are the usual JLC basic parts (verify value/stock before ordering).
- Instance paths `/<root uuid>/<sheet uuid>` are derived from the sheet name, so references are stable
  across regeneration and KiCad opens the project annotated.

## FPGA (GW1NZ-LV1QN48C6/I5, LCSC C5799569, 6.68 USD)

Verified from Gowin UG842-1.6.8E (GW1NZ-1 pinout, xlsx pin list, QN48 column) and UG843-1.8.7E (QN48 view,
recommended land pattern EP 4.3 x 4.3 mm -> footprint `QFN-48-1EP_6x6mm_P0.4mm_EP4.3x4.3mm`), DS841-2.8E.

- Power: VCC (core 1.07-1.26 V) pins 12, 37 = +1V2; VCCX 36, VCCIO0 1, VCCIO1 25 = +3V3 (VCCX >= VCCIO);
  VSS 2, 26, EPAD = GND. 100 nF per pin + 10 uF per rail. Ripple limits VCC 3 %, VCCIO/VCCX 5 %.
- Banks: Bank0 = 3-8, 35, 38-48 (top, IOT), Bank1 = 9-11, 13-24, 27-34 (right, IOR). Both at 3.3 V.
- **No true LVDS on GW1NZ-1** (LVDS column NONE for every pin; DS841: "GW1NZ-1 only supports ELVDS
  output", which needs VCCIO 2.5 V and resistor networks). Strobes are therefore complementary LVCMOS33
  on True/Comp pairs: PH_STROBE_P/N = 40/39 (IOT16A/B), S_STROBE_P/N = 38/35 (IOT17A/B). No LVDS input
  either: COARSE comes from the SN65LVDS2 on trigger_phase, into pin 47 (IOT10A/GCLKT_0).
- FPGA_CLK (MS5351M CLK0) -> 33 (IOR5A/GCLKT_2/RPLL_T_in). CLK2 -> 34 (spare clock).
- TAP0..15 -> 9, 10, 11, 13-24, 27 (Bank1; may be permuted for routing). SPI slave SCK/MOSI/MISO/CS ->
  28/29/30/31 (dual-purpose MSPI/SSPI config pins, free after internal-flash boot). ADC_TRIG -> 41.
- Config: RECONFIG_N 48, DONE 46, READY 45 (4.7k pull-ups; MCU reads FPGA_DONE, drives FPGA_RECONFIG
  open-drain), JTAGSEL_N 44 (4.7k pull-up + solder jumper to GND), MODE0 43 / MODE1 42 (4.7k to GND;
  MODE2 is internally grounded on QN48), JTAG TCK 3 (4.7k pull-down), TMS 4, TDI 5, TDO 7 on a 1x6 header.
  Unused: 6, 8, 32 (NC flags).

## Clock

MS5351M (LCSC C1509083, 0.91 USD), Si5351A-B-GT pin-compatible MSOP-10 (library symbol reused), 25 MHz
3225 crystal (C9006, ~0.07, CL 8 pF via internal load caps). CLK0 -> FPGA_CLK, CLK1 -> MCU_CLK (STM32 HSE
bypass, PF0), CLK2 -> FPGA pin 34, 33 R series each. I2C from the MCU (pull-ups on mcu_if).

## Power tree (LCSC 1 pc; "~" = estimate from memory, not re-checked in this session)

| Rail | Part | From | Load | Price |
|---|---|---|---|---|
| VBUS | USB-C 6P (C2927039 ~0.10), PTC 1.5 A (C118413, 0.08), SMAJ5.0A (C353442, 0.03), 2 A ferrite | USB | ~0.85 A total | ~0.2 |
| +3V3 | AMS1117-3.3 (C6186) | VBUS | 0.45 A (TRF37D73 x6, FPGA, MS5351M, COS3502, LVDS rx) | ~0.06 |
| +1V2 | AP2112K-1.2 (C460310) | +3V3 | 0.03 A | 0.24 |
| +5V4 | MT3608 boost 5.32 V (C84817) + 4.7 uH + SS14, ferrite/22 uF pi -> +5V4F | VBUS | 0.2 A | ~0.15 |
| +5V | LP2985-50DBVR (C74511), 10 nF bypass | +5V4F | 0.04 A (BUF802, OPA197) | 0.29 |
| -5V | LM27761 (C129351), -4.99 V, + ferrite/10 uF | +5V4F | 0.09 A incl. -2V5 | 1.23 (verified, prices.md) |
| +2V5 | LP5907MFX-2.5 (C165132) | +5V4F | 0.05 A | 0.34 |
| -2V5 | LM337 SOT-223 (C19267471, XBLW), 120/120 R, 10 uF ADJ bypass | -5V | 0.04 A | 0.44 |

Total about 2.5 USD plus passives. Why the boost: LM27761 needs VIN >= |VOUT| + 2 ohm x I + 30 mV;
from 4.75 V USB it cannot hold the BUF802's -4.5 V minimum. The boost also gives the +5V LDO headroom.

## MCU interface (J701, 2x13 2.54 mm)

Pin map on the sheet. DAC outputs are scaled by difference amplifiers (TP2272 dual on +/-2.5 V, 3 packages,
VMID = VREF+/2 buffered): TRIG_LEVEL = 0.25 (Vdac - VMID) (+/-0.30 V), VOFS = 0.40 (Vdac - VMID)
(+/-0.48 V), VBIAS_A = -1.0 V + 0.5 (Vdac - VMID) (anode rail, -0.4..-1.6 V), VBIAS_K = +1.0 V + 0.5 (Vdac -
VMID) (cathode rail, +0.4..+1.6 V); offset from a Thevenin divider (24.9k/16.5k to -2V5 resp. +2V5) on the
+ input, R1 20k / R2 10k. (Signs corrected at integration: the earlier +1 V on the anode rail forward-biased the
bridge.) VTAP_TH = DAC/31 (8-85 mV). VTAP_P/N = +2V5/-2V5 through 0 R links.
ADC_REF_MID = VREF+ x 1/4 = 0.725 V. Relay: 2N7002 low-side, flyback 1N4148W to VBUS; TERM_50 = coil low end.

## BOM

`docs/bom.md` (generated): **61.6 USD for one board** (MCU, PCB excluded) against the 80 USD budget, 5.8 USD of it
estimates. Largest lines: TRF37D73 x5 7.50, GW1NZ-1 6.68, BAT15-04W x18 6.58, GVA-84+ x2 5.98, BUF802 5.89,
TLV3801 5.13. First order with LCSC minimum quantities ~89 USD. LCSC numbers that pointed at other parts were
corrected (power LDOs, TVS, PTC, 2x13 header) or removed (several resistor values) on 21 Nov 2026.

## Open points

Integration (21 Nov 2026):
- Root netlist: 242 nets, no single-node nets; 11 NC-flagged pins, all intended (K101 3/10 unused NC contacts,
  BUF802 NC 9/13/16, FPGA 6/8/32 unused, NC pins of AP2112K/MT3608/LP5907). Not a KiCad ERC: run ERC in eeschema.
- Stock: HFD3/3 (C340658) and BAT15-03W (C5310874) 0 at LCSC; TRF37D73 25 at LCSC (Mouser has stock); SMA
  edge connectors not sourced (2 x ~2 USD estimate); TP2272 changed to TP2272-SO1R (TP2272-SR out of stock).
- LCSC numbers missing (BOM `est`): 1.5p, 2.2p, 3.3p, 100p, 470p, 220p, 2.2u 0402, 4.7u 0603, 1% values (4.99M,
  300k, 17.8k, 14.3k, 22.1k, 24.9, 499, 82, 91, 68, 47, 470, 49.9, 24.9k, 40.2k, 30k, 16.5k, 78.7k, 499k, 1.54M,
  18k, 2.7k), 600R beads, 47 uH 1008, 120 nH 0402, 4.7 uH SRN4018, 50k trimmer.
- Tap hold caps are 0.5 pF (nearest stocked C0G value, LCSC C1544) instead of 0.47 pF.
- HFD3 relay footprint/pinout (Kemet EC2 used) to check against the Hongfa drawing; LM337S (XBLW) SOT-223
  pinout to check against the TI pinout used in the symbol.
- Sampler ADC must sample before the S_STROBE falling edge (+160 ns) - FPGA/MCU firmware timing.
- Phase strobe stubs now 80 ps (13.2 mm) per sim/phase_array (strobe sheet; not part of the phase_trigger fragment,
  which takes PSTRB_A/K from its X2/X3 interfaces); signal-line meander drawn 70 ps per tap for 75 ps, strobe lines 40 ps per tap (layout pitch 4.514 mm).
- Remaining cosmetic text overlaps: power sheet value/power-symbol labels, COS3502 power units, MS5351M
  +3V3 pair.

Earlier:
1. Prices marked "~" and the passive/crystal/USB LCSC numbers were not re-checked in this session.
2. TP2272 supply range and RRIO behaviour on +/-2.5 V not verified (any 5 V RRIO dual fits the footprint).
3. MODE[1:0] = 00 for autoboot from internal flash is from memory of Gowin UG290; verify. Verify in Gowin
   EDA that OSER10 can be placed on IOT16/IOT17 and IDES on pin 47 (GW1NZ-1 IO logic placement rules).
4. USB power ~0.85 A exceeds a default USB port (0.5/0.9 A): needs a 1.5 A-capable USB-C supply (no PD
   negotiation on board). AMS1117 dissipates ~0.8 W.
5. LM337 output-capacitor stability with ceramics, minimum-load 10 mA: check; a low-noise negative LDO
   (e.g. TPS7A30) would be better but costs ~2 USD more.
6. MS5351M exact equivalence to Si5351A (register map, crystal load) assumed from its datasheet claim.
7. GVA-84+ chains (strobe sheet) are expected on VBUS via their own chokes; HFD3 relay coil on VBUS.
