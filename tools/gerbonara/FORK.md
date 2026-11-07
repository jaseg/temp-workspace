# gerbonara, with KiCad 9/10 schematic support

This directory holds a local fork of [gerbonara](https://gitlab.com/gerbolyze/gerbonara): its Python package
(`src/`, `pyproject.toml`, `README.md`, `LICENSE`). kicad-manga uses it as a path dependency (`../gerbonara`).

- **Base:** upstream `main` at `736107f` ("Reject oversized step-repeat expansions", v1.6.2 plus 6 commits).
- **Changes:** the 41 commits in `patches/`, made with `git format-patch`. Each one is a single fix, file format
  feature or helper with its own tests, written to go upstream as is. Upstream's test suite and data are not
  copied here.

To apply them to an upstream checkout:

```sh
git checkout -b kicad-9-10 736107f
git am path/to/tools/gerbonara/patches/*.patch
```

## Loading KiCad 9/10 schematics (patches 1–19)

Upstream can load KiCad 9.0.6's demo and QA schematics. It fails on 87 of the 309 KiCad 10.0.8 ones, and on most
schematics saved by KiCad 9 and 10 that use newer features.

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

## SVG export and helpers (patches 20–41)

Even with patches 1–19, `Schematic.to_svg()` still failed on all 117 KiCad 10 demo schematics. With these patches
it exports all 656 schematics of the test corpus.

**Crashes fixed:**

- `Color` truthiness.
- Polyline point lists in symbols and schematics.
- Symbol arcs, including KiCad 6's radius form and arcs whose three points lie on a line.
- Missing pin colours in the default colorscheme.
- Global and hierarchical labels.
- Bus entries.
- Images had no export.

**Wrong output fixed:**

- Right-justified text was exported left-aligned.
- The far ends of label outlines were wrong.
- Dash-dot dash arrays were malformed.
- Pin names ignored the pin name offset.
- `Pin.bounding_box()` raised for every pin that wasn't at 270°.
- B size paper had the wrong height.
- Placed symbols defaulted to DNP.
- Every reference got a unit letter, even on single-unit symbols.

**Newly exported:** rectangles, circles, arcs, Bézier curves and rule areas.

**Helpers, as used by kicad-manga:**

- `PageSettings.size`
- `Image.size`, plus `png_size()` for reading a PNG's size
- `Symbol.resolve()`, made to work, with library lookups
- `SymbolInstance.transform_point()` and `transform_vector()`
- `SymbolInstance.unit_count`
- `TextMixin.is_hidden`
- `kicad_arc_svg_flags()`

## How it was tested

Every commit passes upstream's own tests for these modules: `tests/test_kicad_schematic.py`, and the symbol
library round-trip in `tests/test_kicad_symbols.py`. They ran against:

- KiCad's 9.0.6 and 10.0.8 demo and QA schematics;
- the 9.0.6 symbol libraries.

All 656 schematics load, survive a serialize/parse round trip, and export to well-formed SVG. The one remaining
test failure is a KiCad 10 QA project that references a sub-sheet file missing from KiCad's own repository.

The resvg and podman parts of upstream's test setup weren't available, so the tests ran with `RESVG=/bin/true`
and `--use-cached-data`. The PCB and footprint tests were not run.

## Known gaps

`Schematic.to_svg()` still renders:

- text boxes, tables and netclass flags as plain text or not at all;
- KiCad's text escapes such as `{slash}` literally.

Symbol field orientation goes through `TextMixin.to_svg()`'s rotation flipping, which is not checked against
KiCad.
