# Manga-style schematic render

`yanartas-pillowbox-sensors-manga.svg`, `.png` and `.pdf` are the sensor board's KiCad
schematic redrawn by [`tools/kicad-manga`](../../tools/kicad-manga). `kicad-manga.toml` here
holds the title panel text, because the schematic has no title block.

To re-render, from `tools/kicad-manga`:

```sh
uv run kicad-manga path/to/yanartas-pillowbox-sensors.kicad_sch \
    -c ../../docs/schematic-manga/kicad-manga.toml \
    -o ../../docs/schematic-manga/yanartas-pillowbox-sensors-manga
```
