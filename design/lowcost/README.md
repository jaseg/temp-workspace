# Low-cost sampling oscilloscope front end

2 GHz / 3 Gbps equivalent-time sampling front end (diode-bridge sampler, 16-tap delay-line phase
recovery, GW1NZ-1 FPGA, user-supplied STM32G474). Start with `docs/theory-of-operation.md`.

## Directory map

| Path | Content |
|---|---|
| `SPEC.md` | design specification; its Decisions section overrides the text above it |
| `sim/input/`, `sim/sampler/`, `sim/strobe/`, `sim/phase/`, `sim/phase_array/` | ngspice + Python simulations; `RESULT.md`, plots and JSON in each |
| `kicad/` | generated KiCad 7 hierarchical schematic (7 sheets), `export/` netlist, PDF, SVG/PNG; see `kicad/README.md` |
| `kicad/gen/` | schematic generators, netlist checks, BOM generator |
| `layout/input_stage/`, `layout/sampler/`, `layout/phase_trigger/` | pcbnew-scripted layout fragments with render PNG and README |
| `docs/` | `theory-of-operation.md`, `bom.md` / `bom.csv` (generated) |

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

# schematic, netlist checks, exports and BOM (docs/bom.md, docs/bom.csv)
cd kicad/gen && python3 test_schlib.py && python3 gen_all.py      # --no-export skips PDF/SVG/PNG

# layout fragments
cd layout/input_stage   && python3 gen_input_stage.py
cd layout/sampler       && python3 gen_sampler.py
cd layout/phase_trigger && python3 gen_phase_trigger.py
```

The `.kicad_sch`, `.kicad_pcb`, `export/` and BOM files are generated; edit the generators, not the outputs.
KiCad ERC and pcbnew DRC are not part of these scripts and have not been run.
