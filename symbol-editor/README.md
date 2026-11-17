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
  - All pins of a group are on the same side: changing one pin's side moves the whole group.
  - **Repeat selected** inserts continued copies of the selected rows: `PA0, PA1 → PA2, PA3`,
    `TX0_P, TX0_N → TX1_P, TX1_N`, BGA balls `A1, B1 → C1, D1` (skipping I, O, Q, S, X, Z).
    A continued pin number that is already in use is left empty.
  - **Tab** in an empty Name or Number cell fills in the continuation of the nearest one above
    (shown as grey text before you press it).
  - **Enter** moves down; on the last row it adds a continued row.
  - **Paste** several cells (from a spreadsheet, or text from a PDF) into a cell, and they fill the
    table from there to the right and down. Datasheet types like `I/O`, `I`, `O`, `P` are understood.
  - Duplicate pin numbers show in red.
- **Preview (right):** mouse wheel zooms, dragging pans, clicking a pin jumps to its row.
  Drag the bar between table and preview to resize them.
- **Balance sides** moves whole groups between left and right until both are about equally long.
- **Undo / Redo:** buttons, or Ctrl+Z and Ctrl+Y / Ctrl+Shift+Z.
- **Import .kicad_sym** loads the first symbol of a KiCad library. Groups are rebuilt from the
  gaps between pins.
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
| `js/history.js` | Undo and redo |
| `js/pins.js` | The data model: pin fields, table columns, conversion to/from spreadsheet rows |
| `js/pin-table.js` | `<pin-table>` component: the editable table |
| `js/symbol-preview.js` | `<symbol-preview>` component: SVG drawing, zoom and pan |
| `js/settings-dialog.js` | `<symbol-settings>` component: the symbol settings dialog |
| `js/layout.js` | Where the body and pins go (shared by preview and export) |
| `js/balance.js` | "Balance sides" |
| `js/kicad-export.js` | Writes the `.kicad_sym` file |
| `js/kicad-import.js` | Reads a `.kicad_sym` file |
| `js/autocomplete.js` | Guesses a pin's group from its name |
| `js/increment.js` | Continues pin names and numbers for "Repeat selected" |
| `js/footprint-import.js` | Reads pad numbers from a `.kicad_mod` file |
| `js/xlsx.js`, `js/zip.js` | Minimal .xlsx reading/writing |

To add a pin column: add it to `COLUMNS` and `newPin()` in `js/pins.js`. The table and the
xlsx import/export pick it up from there.
