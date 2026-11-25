# Low-cost sampling oscilloscope front end

2 GHz / 3 Gbps equivalent-time sampling front end (diode-bridge sampler, 16-tap delay-line phase
recovery, GW1NZ-1 FPGA, on-board STM32G474CBT6, USB-C), one six-layer 100 x 57 mm board. Start with
`docs/theory-of-operation.md`.

## Directory map

| Path | Content |
|---|---|
| `SPEC.md` | design specification; its Decisions section overrides the text above it |
| `sim/input/`, `sim/sampler/`, `sim/strobe/`, `sim/strobe_arms/`, `sim/phase/`, `sim/phase_array/`, `sim/bias_tee/` | ngspice + Python simulations; `RESULT.md`, plots and JSON in each |
| `sim/trig_switch/`, `sim/bom2_input/`, `sim/bom2_taps/` | BOM-reduction studies: diode-bridge trigger selector, input servo without trimmer (as-built LF/HF correction), as-built phase array with the tap capacitors |
| `kicad/` | generated KiCad 7 hierarchical schematic (7 sheets), `export/` netlist, PDF, SVG/PNG; see `kicad/README.md` |
| `kicad/gen/` | schematic generators, netlist checks, BOM generator |
| `layout/board/` | the integrated six-layer board (JLC06161H-3313, 100 x 57 mm): `scope-fe.kicad_pcb` / `.kicad_pro`, generator `gen_board.py` with `board_slow.py`, `board_power.py`, `board_stitch.py`, `board_finish.py`, six blocks under `blocks/<name>/gen_<name>.py` on `boardlib.py`; `RULES.md` (layout rules), `TOPOLOGY.md` (routing plan), README (as built, check results, review), renders `scope-fe-L1..L6.png`, `scope-fe-all.png`, `scope-fe-detail-*.png` |
| `layout/input_stage/`, `layout/sampler/`, `layout/phase_trigger/` | the three old four-layer fragments, superseded by `layout/board/`; left at their git-tag state for reference (refs and nets do not match the schematic) |
| `tools/` | KiCad nightly DRC / ERC wrappers (`run_drc.sh --rules jlc4 --parity`, `run_erc.sh`) |
| `docs/` | `theory-of-operation.md`, `bom.md` / `bom.csv` (generated, 70.39 USD per board, 81 lines, 27 extended part numbers, JLC class and stock per line), `research/power-tree.md` (TPS62A01A x2, TPS63802, LM27762 x2), `VALIDATION.md` + `validation/*.md` (review findings, re-checks) |

## Regenerate

Requirements: Python 3 with numpy and matplotlib, ngspice, KiCad 7.0.x (`kicad-cli`, `pcbnew` Python module,
`/usr/share/kicad/symbols`), node + playwright/chromium for the PNG export.

```
# each line from design/lowcost in a fresh shell; simulations in this order
cd sim/input       && python3 input_stage.py
cd sim/sampler     && python3 bridge.py && python3 multistrobe.py && python3 chain.py && python3 plots.py
cd sim/strobe      && python3 chain.py && python3 bridge.py && python3 extras.py
cd sim/phase       && python3 line_drive.py && python3 gate50.py && python3 feedthrough.py && python3 neutralise.py && python3 tdc_mc.py
cd sim/phase_array && python3 run.py && python3 extra.py && python3 bridge_rev.py
cd sim/strobe_arms  && python3 arms.py && python3 plots.py       # as-built strobe arms, falling edge
cd sim/trig_switch  && python3 switch.py                          # trigger selector (about 10 min)
cd sim/bom2_input   && python3 bom2_input.py                      # input servo, LF/HF correction (as built)
cd sim/bom2_taps    && python3 taps.py all                        # as-built phase array, tap capacitors (about 6 min)

# schematic, netlist checks, exports and BOM (docs/bom.md, docs/bom.csv)
cd kicad/gen && python3 test_schlib.py && python3 gen_all.py      # --no-export skips PDF/SVG/PNG

# board: blocks (each writes blocks/<name>/<name>.kicad_pcb), then the integrated board (about 110 s)
cd layout/board/blocks/<name> && python3 gen_<name>.py     # analog, phase, pstrobe, fpga, power, mcuif
cd layout/board && python3 gen_board.py                     # writes scope-fe.kicad_pcb, runs check_board

# checks with the KiCad nightly CLI (on scratch copies; see tools/README.md)
tools/run_drc.sh --rules jlc4 --parity layout/board/scope-fe.kicad_pcb
tools/run_erc.sh
```

The `.kicad_sch`, `.kicad_pcb`, `export/` and BOM files are generated; edit the generators, not the outputs.
Last results (25 Nov 2026, after the BOM reduction round and its re-check): DRC jlc4 + parity 0 errors / 0 unconnected
(450 warnings, all library / symbol-field / parity artefacts, listed in `layout/board/README.md`), ERC 0 errors
(18 library warnings), netlist checks 0 failed, check_board 0, via-in-pad FAIL 0.
The power tree, clock plan (768 Mbit/s serialiser, SPEC decision 18) and decoupling as built are in `kicad/README.md`.
Board review tools: `layout/board/render_board.py` (renders), `layout/board/decap_audit.py` (decoupling capacitor at the
pin, vias at the capacitor; SPEC decision 23), `layout/board/net_view.py` (net-coloured crops). Validation findings and
their status: `docs/VALIDATION.md` (last section: status after the BOM reduction round).
