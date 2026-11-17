# KiCad IC symbol editor

A single-page tool for drawing KiCad schematic symbols of ICs from a pin table.
Plain HTML, CSS and JavaScript (ES modules and web components). No framework,
no build step, no server code, no dependencies.

## Running it

ES modules don't load from `file://`, so serve the folder with any static web server:

```bash
python3 -m http.server 8000
```

Then open http://localhost:8000.

## Using it

- **Table (left):** one row per pin. Click a column header to sort.
  - Typing a pin name fills in Group, Side, Type and Unit from similar names already in the table
    (only if Group is still empty).
  - **Repeat selected** inserts continued copies of the selected rows: `PA0, PA1 → PA2, PA3`,
    `TX0_P, TX0_N → TX1_P, TX1_N`, BGA balls `A1, B1 → C1, D1` (skipping I, O, Q, S, X, Z).
  - **Enter** moves down; on the last row it adds a continued row.
  - Duplicate pin numbers show in red.
- **Preview (right):** mouse wheel zooms, dragging pans, clicking a pin jumps to its row.
- **Layout rules:** each pin goes on its Side of its Unit. Pins of the same Group stay together,
  with one empty grid step between groups, in table order. Power pins with the same name are
  stacked (one visible pin, the rest hidden) unless turned off in Symbol settings.
- Work is saved in the browser (localStorage) after every change. Use **Download .xlsx** for
  real backups, and to edit pins in a spreadsheet.

## Code map

| File | What it does |
| --- | --- |
| `index.html`, `style.css` | Page skeleton and looks |
| `js/main.js` | Wires everything together; header buttons; saving in the browser |
| `js/pins.js` | The data model: pin fields, table columns, conversion to/from spreadsheet rows |
| `js/pin-table.js` | `<pin-table>` component: the editable table |
| `js/symbol-preview.js` | `<symbol-preview>` component: SVG drawing, zoom and pan |
| `js/settings-dialog.js` | `<symbol-settings>` component: the symbol settings dialog |
| `js/layout.js` | Where the body and pins go (shared by preview and export) |
| `js/kicad-export.js` | Writes the `.kicad_sym` file |
| `js/autocomplete.js` | Guesses a pin's group from its name |
| `js/increment.js` | Continues pin names and numbers for "Repeat selected" |
| `js/footprint-import.js` | Reads pad numbers from a `.kicad_mod` file |
| `js/xlsx.js`, `js/zip.js` | Minimal .xlsx reading/writing |

To add a pin column: add it to `COLUMNS` and `newPin()` in `js/pins.js`. The table and the
xlsx import/export pick it up from there.
