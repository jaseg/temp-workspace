# kicad-manga

Renders a KiCad schematic sheet as a pastel, manga-styled poster in SVG, PNG and PDF.

- **Nets** are coloured in families: names sharing a prefix share a hue, supply rails get
  warm shades and grounds lilac-grey.
- **Characters:** capacitors become cats (chonkier with more capacitance), resistors are
  grumpy and throw bricks, ferrite beads and inductors are caterpillars, and crystals dance.
- **Around the circuit:** plants, garlands, cables, shelves and a title panel with a mascot
  fill the empty space.

```sh
uv run kicad-manga board.kicad_sch                  # ./board-manga.svg/.png/.pdf
uv run kicad-manga board.kicad_sch -f pdf -o out/board --title "My Board" --kicker "回路図"
```

The tool handles one `.kicad_sch` file per run. Sub-sheets show up as boxes with their pins;
run it again on each sub-sheet file if you want those too. It is tested with KiCad 9 and 10
files. KiCad 7 and 8 files should mostly work; older formats aren't supported.

## Settings

Settings are applied in this order, later ones winning:

1. Built-in defaults.
2. `kicad-manga.toml`, read from next to the schematic, else from the current directory, or
   from the file given with `-c FILE`.
3. Command-line flags.

```toml
formats = ["svg", "png", "pdf"]
png_px_per_mm = 10
seed = 42                # decoration layout
characters = true        # --no-characters
decorations = true       # --no-decorations
sound_effects = true
font_dir = ""            # default: downloaded once into ~/.cache/kicad-manga/fonts

[title]                  # empty: taken from the schematic's title block
title = ""               # title block title, else the file name
subtitle = ""            # title block comment 1
kicker = "回路図"         # small line above the title
bubble = ""              # the mascot's line; title block comment 2
```

The title panel footer shows the page number, company, revision, date and paper size from
the schematic.

## What gets drawn

- **Symbols:** all fields, multiple units and body styles, and pin shapes (inverted, clock,
  active-low, non-logic). IC bodies get a pastel per library, and a face when the body is
  otherwise empty.
- **Characters:** passives are matched by reference prefix, so they work with any library:
  `C` is a cat, `R`/`TH` a resistor, `L`/`FB` a caterpillar, and `Y`/`X` a crystal. Buses become one long
  cat each, with windows, headlight eyes and lots of little legs.
  Polarised capacitors wear a "+" badge.
- **Labels:** local, global (with their input/output/bidirectional/tri-state/passive
  shapes), hierarchical, and netclass/directive flags.
- **Wiring:** wires and buses (with their dash styles), bus entries, junctions and
  no-connects.
- **Text and graphics:** text (big text becomes ribbon banners, long notes speech bubbles),
  text boxes, tables, images, lines, rectangles, circles, arcs, Béziers and rule areas.
- **Sub-sheets:** drawn as boxes with their pins.
- **Paper:** any paper size, ISO or US, in either orientation, or custom. The decorations
  scale with the page. When the circuit would collide with the frame, the title panel or the
  plants along the bottom, it is shrunk and moved to make room.

The SVG is meant to stay editable. Its top-level groups are Inkscape layers:

- Background
- Decorations (back)
- Schematic, with sub-layers per kind of item
- Frame
- Decorations (front)
- Title & legend

Every schematic item is its own group with a `data-kind`, every symbol is a group with its
reference as id, and wires are grouped by net.

## How it works

1. `circuit.py` draws the sheet; `page.py` lays out the page and decorations.
2. Headless Chromium (Playwright) measures text in the embedded fonts, so label pills,
   banners and bubbles fit exactly.
3. The same browser rasterises the PNG in tiles and prints the PDF. Before printing, the
   halftone patterns become flat tints, since Chromium would otherwise embed a bitmap per
   pattern use.

It uses whichever Chromium Playwright finds. If the installed Playwright doesn't match the
browser on the system, set `KICAD_MANGA_CHROMIUM` to a Chrome or Chromium binary.

## Development

```sh
uv sync
uv run pytest      # a few high-level sanity checks; the end-to-end test is skipped without Chromium
```
