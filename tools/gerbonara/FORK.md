# gerbonara, with KiCad 9, 10 and 10.99 schematic support

This directory holds a local fork of [gerbonara](https://github.com/jaseg/gerbonara): its Python package
(`src/`, `pyproject.toml`, `README.md`, `LICENSE`). kicad-manga uses it as a path dependency (`../gerbonara`).

- **Base:** upstream `main` at `8a3056c` ("Attach object attributes to regions").
- **Changes:** the 52 commits in `patches/`, made with `git format-patch`. Upstream's test suite and data are not
  copied here.

The changes are proposed upstream as a stack of six pull requests. Each one builds on the one before:

| # | Pull request | Patches |
|---|---|---|
| 1 | [Fix KiCad schematic parsing bugs that lose data](https://github.com/jaseg/gerbonara/pull/10) | 1–8 |
| 2 | [Support KiCad 9 and 10 schematics](https://github.com/jaseg/gerbonara/pull/11) | 9–24 |
| 3 | [Fix KiCad schematic SVG export](https://github.com/jaseg/gerbonara/pull/12) | 25–43 |
| 4 | [Add helpers for KiCad symbol libraries and placed symbols](https://github.com/jaseg/gerbonara/pull/13) | 44–46 |
| 5 | [Support schematics of KiCad's 10.99 development version](https://github.com/jaseg/gerbonara/pull/14) | 47–48 |
| 6 | [Draw KiCad schematic text like KiCad; export netclass flags, text boxes and tables](https://github.com/jaseg/gerbonara/pull/15) | 49–52 |

Each pull request's description lists its changes and what its tests do and don't cover.

To apply the patches to an upstream checkout:

```sh
git checkout -b kicad-schematics 8a3056c
git am path/to/tools/gerbonara/patches/*.patch
```

## What it adds

- **Loading:** KiCad 9, 10 and 10.99 schematics load and round-trip without losing data. Upstream already fails
  on 87 of KiCad 10.0.8's 424 demo and QA schematics. Older formats are best effort: KiCad 7 and 8 schematics load
  and export, but their output isn't checked.
- **SVG export:** `Schematic.to_svg()` exports every schematic in the test corpora. Newly exported:
  - rectangles, circles, arcs, ellipses, Bézier curves and rule areas;
  - images, netclass flags, text boxes and tables.
- **Text:** placed like KiCad places it, including the rotation and mirroring of symbol fields, with text escapes
  such as `{slash}` decoded.
- **Helpers used by kicad-manga:**
  - `PageSettings.size`, `Image.size` and `png_size()`;
  - `Symbol.resolve()`, with library lookups;
  - `SymbolInstance.transform_point()`, `transform_vector()` and `unit_count`;
  - `TextMixin.is_hidden`;
  - `kicad_arc_svg_flags()`.

## How it is tested

The tests follow upstream's approach: they run against corpora of real KiCad files, fetched at test time. No test
files are written by hand or added to the repository.

- **Corpora:** the demo and QA schematics of KiCad 9.0.6, 10.0.8 and master at `9903ced` (2026-11-07), from
  KiCad's GitLab (GPL-3.0-or-later). A new `kicad_extra_source_revisions` setting fetches the extra versions.
- **Checks:** every schematic must load and export to well-formed SVG. Those in KiCad 9 format or newer must
  also survive a serialize/parse round trip. Text placement is compared with KiCad's own SVG export of its
  `qa/data/cli/basic_test` schematic.
- **Status:** every commit passes `tests/test_kicad_schematic.py` and `tests/test_kicad_symbols.py`, run with
  `RESVG=/bin/true` and `--use-cached-data`. The PCB and footprint tests were not run.

## Known gaps

- **Not checked against KiCad's output:**
  - global and hierarchical labels;
  - netclass flag shapes and tables;
  - fields of symbols at 180° or 270°, or mirrored about the x axis.
- **Not in any corpus file:** ellipses, elliptical arcs and pin map overrides.
