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
run it again on each sub-sheet file if you want those too. Schematics are read with
[gerbonara](https://gitlab.com/gerbolyze/gerbonara), from a local fork in `../gerbonara` that adds KiCad 9
and 10 support (see `../gerbonara/FORK.md`). It is tested with KiCad 9 and 10 files; KiCad 7 and 8 files
should mostly work.

PDF output needs `rsvg-convert` (librsvg; on Debian/Ubuntu the `librsvg2-bin` package) or Inkscape on the
`PATH`. SVG and PNG output need nothing beyond the Python dependencies.

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

1. `kicad.py` loads the schematic with gerbonara. `circuit.py` draws the sheet, and `page.py` lays out the page
   and the decorations.
2. Text is measured with HarfBuzz in the fonts the page uses (`text.py`), so label pills, banners and speech
   bubbles fit exactly. Text sits on explicit baselines, so every renderer draws it at the same place.
3. SVG output (`svg.py`):
   - Elements built in code use gerbonara's `Tag`.
   - Artwork lives outside the Python code. Drawings with computed geometry are jinja2 templates in
     `templates/`. Fixed artwork (faces, the mascot, screentones, symbols) is standalone SVG files in `static/`,
     whose `<defs>` go into the page and can be edited in Inkscape on their own.
4. resvg rasterises the PNG. `rsvg-convert` (or Inkscape) converts the SVG to PDF, with a fontconfig
   configuration that points it at the page's fonts. The screentones end up as PDF tiling patterns.
5. Fonts: the SVG embeds them as WOFF2 for browsers. resvg, `rsvg-convert` and HarfBuzz use TTF copies with
   clean family names, all cached in `~/.cache/kicad-manga/fonts`.

## Development

```sh
uv sync
uv run pytest      # a few high-level sanity checks
```

## Paper craft style

`--style papercraft` (or `style = "papercraft"` in the settings) draws the schematic as a scrapbook page:

```sh
uv run kicad-manga board.kicad_sch -s papercraft                # ./board-papercraft.svg/.png/.pdf
```

- **Parts** are pastel cardstock with a soft cast shadow; symbol lines and pins are thin strips of paper. Resistors
  are paper bars showing their colour code, capacitors two plates of card (the + plate coral), inductors quilled
  paper coils and ferrite beads grey bands. Big IC bodies get a little paper face.
- **Wires** are washi tape in the net's colour: dotted for signals, stitched for supplies, pinstriped for grounds.
  Buses are wide striped lavender tape. Junctions are brass paper fasteners, no-connects small crosses of tape,
  DNP parts are crossed out with tape.
- **Labels** are paper luggage tags with a punched hole; global and hierarchical labels are paper pennants. Big
  text sits on a strip of printed washi tape with torn ends, outlined in white; long notes are torn notepaper.
- **Around it:** a scalloped, polka-dotted mat with a stitched edge, paper flowers on its corners, bunting along
  the top, a title card with the title in cut-paper letters, a chip sticker with a speech bubble, die-cut stickers,
  loose washi tape and paper confetti in the free space.
- **Realism:** colours are muted to what paper and ink look like, edges are cut by an unsteady hand, strips vary in
  width, tape is laid in overlapping pieces, and shadows are soft (two stacked translucent copies, no blur filter).
  The page is a tiled cardstock bitmap and large pieces show a paper grain bitmap.
  The textures are generated by `scripts/make_paper_textures.py` and tile seamlessly.
- No filters or group opacity, so PDFs stay fast to open (an A1 sheet is about 4 MB).

Text is set in Mali, headings and the title in Sniglet (both SIL OFL, fetched like the other fonts). The code is in `papercraft/`.
