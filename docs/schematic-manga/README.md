# Manga-style schematic render

`yanartas-pillowbox-sensors-manga.svg` / `.png` are the sensor board's KiCad schematic redrawn
in a pastel manga style: wires coloured per net, junctions drawn as hearts, label pills, ribbon
banners for the section titles, screentone shadows and little faces on the larger ICs. The
empty parts of the sheet get plants standing along the bottom edge, garlands along the top,
climbing vines, loose cables with plugs coming in from the edges, wall shelves, stray parts,
clouds and a few faint sound effects. These are drawn procedurally in `drawings.py` and placed
only where the circuit leaves room.

KiCad isn't needed. `render.py` parses the `.kicad_sch` and draws it from scratch. Then
`finish.js` lays out the text-dependent shapes in Chromium and writes the outputs.

```sh
# fonts (SIL OFL), from fontsource
mkdir -p fonts && for f in m-plus-rounded-1c/files/m-plus-rounded-1c-latin-{500,800}-normal \
    zen-maru-gothic/files/zen-maru-gothic-latin-700-normal \
    mochiy-pop-one/files/mochiy-pop-one-{latin,japanese}-400-normal; do
  curl -sSo "fonts/$(basename $f).woff2" "https://cdn.jsdelivr.net/npm/@fontsource/$f.woff2"; done

python3 render.py path/to/yanartas-pillowbox-sensors.kicad_sch fonts raw.svg
node finish.js raw.svg yanartas-pillowbox-sensors-manga.svg yanartas-pillowbox-sensors-manga.png 10
python3 stitch.py yanartas-pillowbox-sensors-manga.png   # PNG is rendered in tiles
```

The last argument to `finish.js` sets the PNG resolution in px/mm. At 10 px/mm an A1 sheet
comes out at 8410×5940. The SVG has its fonts embedded, so it looks the same anywhere.
