# gerbonara, with KiCad 9/10 schematic support

This directory is the Python package (`src/`, `pyproject.toml`, `README.md`, `LICENSE`) of a local fork of
[gerbonara](https://gitlab.com/gerbolyze/gerbonara). kicad-manga depends on it as a path dependency
(`../gerbonara`).

- **Base:** upstream `main` at `736107f` ("Reject oversized step-repeat expansions", v1.6.2 plus 6 commits).
- **Changes:** the 19 commits in `patches/`, made with `git format-patch`. Each one is a single fix or file
  format feature with its own tests, written to go upstream as is. Upstream's test suite and data are not
  copied here.

To apply them to an upstream checkout:

```sh
git checkout -b kicad-9-10 736107f
git am path/to/tools/gerbonara/patches/*.patch
```

## What the patches do

Upstream can load KiCad 9.0.6's demo and QA schematics. It fails on 87 of the 309 KiCad 10.0.8 schematics, and
on most schematics saved by KiCad 9 and 10 that use newer features.

**Fixes to existing behaviour:**

- `(paper ...)` was shadowed by a legacy field, so every schematic came out as A4 landscape, and portrait or
  custom paper failed to load.
- Symbol and sheet instance data was lost when loading, and with it every placed symbol's reference and unit.
  `Array()` mapped `sexp_type` elements as bare values, and sheet instances also parsed a second project as a
  child of the first.
- Title block comments were always dropped.
- Schematics without a `(lib_symbols ...)` section could not be serialized.
- Label properties used the PCB property type.
- Image parsing printed debug output.
- `(hide no)` and `(show_name no)` were read as true.

**Newly parsed:**

- Power symbols with `(power global)` or `(power local)`.
- Library symbols:
  - jumper pin settings;
  - `in_pos_files`;
  - `body_styles`;
  - Bézier curves, which are also exported to SVG.
- Placed symbols:
  - `body_style` and `convert`;
  - `in_pos_files`;
  - private properties;
  - the `show_name`, `do_not_autoplace` and `hide` flags on properties;
  - KiCad 10 assembly variants (also on sheets).
- Schematic graphics and objects:
  - arcs and Bézier curves;
  - tables;
  - groups;
  - rule area attributes.
- Text:
  - font colours;
  - hyperlinks.

## How it was tested

Every commit passes upstream's own tests for these modules: `tests/test_kicad_schematic.py`, and the symbol
library round-trip in `tests/test_kicad_symbols.py`. They ran against:

- KiCad's 9.0.6 and 10.0.8 demo and QA schematics;
- the 9.0.6 symbol libraries.

All 656 schematics load and survive a serialize/parse round trip. The one remaining test failure is a KiCad 10
QA project that references a sub-sheet file missing from KiCad's own repository.

The resvg and podman parts of upstream's test setup weren't available, so the tests ran with `RESVG=/bin/true`
and `--use-cached-data`. The PCB and footprint tests were not run.
