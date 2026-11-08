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

## Minecraft style

`--style minecraft` draws the schematic, seen from straight above, as a redstone build out of the blocks of a
Minecraft resource pack:

```sh
uv run kicad-manga board.kicad_sch -s minecraft --pack default-pack.zip           # ./board-minecraft.svg/.png/.pdf
uv run kicad-manga board.kicad_sch -s minecraft --pack mine.zip --pack default.zip  # stacked, the first one wins
```

- **Packs:** any pack, as a .zip (also with a folder inside) or a folder. Packs stack like in the game. Textures,
  block models, blockstates, the biome colormaps and the bitmap font all come from the packs.
  Texture-only packs work on top of a complete pack, and on their own with simple built-in models.
- **Grid:** one block per schematic grid step (`block_mm`, 1.27 mm). Pins, wires and labels snap to it.
- **Parts:**
  - Wires are redstone dust. Grounds are dim and supplies at full power. Dust is drawn `dust_width` times wider
    than in the game, so that it reads on paper. Buses are rails.
  - Diodes are repeaters pointing from anode to cathode, and LEDs are lit repeaters. Dual diodes become two
    repeaters.
  - Transistors are comparators: collector or drain at the back, emitter or source in front, base or gate at a
    side. P-type parts use subtract mode.
  - Passives are short rows between their pins. Resistors are bricks, capacitors are two rows of pressure plates
    (the + plate gold), inductors are copper and ferrite beads oxidized copper.
  - Other parts get a low body with their pin names painted on top. Supplies are torches, grounds hoppers,
    no-connects cobwebs and mounting holes cauldrons.
- **Fitting things in:** a passive that collides with a neighbour, a wire or another part is tried one and two
  blocks to the side, and with slimmer plates or bodies. Its pins are rerouted with dust until everything fits.
  Repeaters and comparators move up to two blocks the same way. Text sits on plaques of block textures
  (labels, references, values, notes), and plaques move out of the way of dust, parts and each other. The run
  prints how many parts and plaques moved.
- **Around it:** the circuit stands on smooth stone in a meadow. Around it are a stone border with a wall,
  lanterns and zone signs, a title block platform, a legend, and trees, ponds, props and flowers. Tall things
  stay where they don't hide the circuit. Parts placed beside the sheet get ground of their own.
- **Drawing:** each block is drawn from its model's upward faces, lower faces a little darker. Blocks that show
  little from above (flowers, torches, lanterns) are drawn as their item icon, like on a map, and standing blocks
  cast a short shadow.
- **Output:** the blocks become one raster image at `px_per_block` pixels per block (16, the pack's texture size),
  cut into tiles and drawn pixelated. Text goes on top as vector paths traced from the pack's font, so it stays
  sharp at any zoom. An A1 sheet gives a PDF of about 10 MB that opens in a few seconds.

```toml
style = "minecraft"
[minecraft]
packs = ["default-pack.zip"]     # relative to the settings file
block_mm = 1.27
dust_width = 3.0
px_per_block = 16
```

The code is in `minecraft/`:

- `pack.py`: resource packs.
- `topdown.py`: block models into small images seen from above.
- `font.py`: the bitmap font.
- `world.py`: the block grid, routing and plaque placement.
- `circuit.py`: the schematic into blocks.
- `page.py`: the border, title block and decorations.
- `draw.py`: the world into SVG.
- `render.py`: the whole pipeline, and the PDF.

## Development

```sh
uv sync
uv run pytest      # a few high-level sanity checks
```
