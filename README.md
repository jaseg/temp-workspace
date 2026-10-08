# yanartas-pillowbox

Generate **laser-ready SVG folding patterns for pillow boxes**, configured through a local web
UI with live 2D and 3D previews. The tool runs entirely offline: the UI is served from
`127.0.0.1`, and all frontend assets, including three.js, ship inside the package.

A pillow box is cut from one flat sheet. It has two body panels and a glue tab. Each short
end of each panel has a curved (circular-arc) fold. The lens-shaped flap outside that fold
closes the end, and pressing the flaps in makes the body bulge into a "pillow".

## Installation & running

Requires Python ≥ 3.11. With [uv](https://docs.astral.sh/uv/):

```sh
uvx yanartas-pillowbox                 # from PyPI, once published
uvx --from . yanartas-pillowbox        # from a checkout
uv run yanartas-pillowbox              # inside a checkout (dev environment)
```

Or use `pip install .`, then run `yanartas-pillowbox`.

### Commands

```text
yanartas-pillowbox [serve] [--port N] [--no-browser]
```
Starts the web UI on a free port, or on `--port`. It prints the URL and opens it in your
browser unless you pass `--no-browser`. The server only listens on `127.0.0.1`.

```text
yanartas-pillowbox generate [--config FILE | --from-svg FILE] [--set key=value ...] -o out.svg
```
Generates an SVG headlessly, using the same engine as the UI.

* `--config FILE` takes a JSON config, either the persisted `yanartas-pillowbox.json` or any
  subset of the parameters below.
* `--from-svg FILE` reuses the config embedded in a previously generated SVG.
* `--set key=value` overrides a single parameter and can be repeated. Booleans accept
  `true/false/yes/no/1/0`.
* `-o -` writes the SVG to stdout.

Validation errors are printed per field, and the command exits with status 2.

```sh
yanartas-pillowbox generate --set width=80 --set length=150 --set depth=40 \
    --set thumb_notch=true -o box.svg
```

### Persistence

The UI saves the last valid configuration to **`./yanartas-pillowbox.json`** in the current
working directory. Saves happen through the server, debounced, and the file is reloaded on
startup. If the file is missing, corrupt, invalid or from another schema version, the tool
logs a warning and starts with the defaults. It never crashes because of the file.

## Web UI

* **Left column:** the parameter form. Invalid values are flagged inline next to the field.
  While any value is invalid, the previews keep showing the last valid design and
  *Download* is disabled. Below the form, *Derived geometry* lists the computed fold and cut
  radii, arc length, closed width and depth.
* **Pattern (2D):** the exact SVG you will download. Zoom with the wheel or the +/− buttons,
  drag to pan, and double-click or press *Fit* to reset. The header shows the pattern and
  sheet sizes. Dimension lines are drawn in the margin (preview only, never exported). A
  legend maps each color to its line category. Lines are shown in their real colors, and the
  backdrop is picked for the best contrast against all of them in the current theme.
* **Folded box (3D):** an orbitable, shaded approximation of the closed box (drag to orbit,
  scroll to zoom).
* **Import:** *Import SVG…* or drag and drop a previously downloaded SVG anywhere onto the
  page to restore all of its parameters. A file without an embedded config, or with an
  incompatible one, produces a clear error message.
* **Download SVG** and **Reset to defaults** are in the top bar.
* Light and dark themes follow `prefers-color-scheme`.

## Parameter reference

All lengths are in millimetres.

| Key | Default | Meaning / constraints |
|---|---|---|
| `width` | 60 | Width of one body panel (the chord of the curved fold). 10–1000. |
| `length` | 120 | Length of the straight body edge, corner to corner. 10–2000. |
| `arc_mode` | `depth` | `depth`: derive the arc from `depth`. `sagitta`: use `sagitta` directly. |
| `depth` | 30 | Target box depth at maximum bulge. Fold sagitta = depth / 2. Must be < 2·width/π. |
| `sagitta` | 15 | Curved-fold sagitta (used when `arc_mode = sagitta`). Must be < width/π. |
| `glue_tab_width` | 12 | Width of the glue tab. 3–100. |
| `glue_tab_taper` | 6 | How far each end of the glue tab is cut back along the length. 0 to length/2 − 1. |
| `thickness` | 0.4 | Material thickness, 0–5. The flap cut edge is offset from the curved folds by t/2 (see below). |
| `stroke_width` | 0.1 | Stroke width written to every line (hairline). 0.001–2. |
| `color_cut` | `#FF0000` | Cut outline. |
| `color_fold_straight` | `#0000FF` | Straight fold between the panels. |
| `color_fold_curved` | `#00A000` | Curved flap folds. |
| `color_fold_glue` | `#FF00FF` | Glue-tab fold. |
| `thumb_notch` | `false` | Cut a semicircular thumb notch into each flap's apex. |
| `thumb_notch_radius` | 8 | Notch radius. At most the flap height (cut sagitta + fold sagitta) minus 1 mm, and at most width/3. |
| `label` | `false` | Add a text label on the front panel, in its own layer. |
| `label_text` | `yanartas` | Label text, max. 64 characters (required when `label` is on). |
| `label_size` | 6 | Font size of the label. 1–100. |
| `color_label` | `#000000` | Label color (engrave layer). |

### Geometry model

The flat pattern is laid out as front panel, back panel and then the glue tab, side by side.
The straight body edges are `length` long. Each flap is a lens between two circular arcs
through the panel corners:

* the **curved fold** bows *into* the panel by the fold sagitta `s_f` (`depth/2`, or
  `sagitta`);
* the **cut edge** bows *out* of the panel by `s_c = s_f − thickness/2`.

When the box is closed, the two creases at one end face each other and form a lens
`2·s_f` deep, which is the box depth. Folding a flap in mirrors its cut edge across its
crease onto the opposite panel's crease, which has the same arc length. The flap therefore
exactly fills the end opening. The `thickness/2` offset makes it a touch smaller, so both
flaps can overlap.

A panel of width `W` cannot bulge past a half cylinder, which is why `s_f < W/π`. The 3D
preview bends each panel into a circular arc of arc length `W` (no stretching) with height
`s_f`. That gives the approximate closed width shown under *Derived geometry*.

## Output SVG & color convention

The file is meant to go straight into LightBurn, Inkscape, RDWorks and similar software.
Each color normally maps to one operation.

| Layer (`<g id>`) | Inkscape label | Default color | Typical operation |
|---|---|---|---|
| `cut` | Cut | `#FF0000` red | Cut through |
| `fold-straight` | Fold - straight | `#0000FF` blue | Score / perforate |
| `fold-curved` | Fold - curved flaps | `#00A000` green | Score / perforate |
| `fold-glue` | Fold - glue tab | `#FF00FF` magenta | Score / perforate |
| `label` | Label (engrave) | `#000000` black | Engrave (only present when enabled) |

Two categories only share a color if you set them that way.

* **Units and canvas:** `width`/`height` are given in mm with a matching `viewBox`, so one
  user unit is 1 mm. The canvas is the pattern's bounding box plus exactly **10 mm** on every
  side. There are no page-size settings.
* **Cut outline:** exactly one closed `<path>` (one `M`, ending in `Z`) that traces the whole
  contour in one direction, including any thumb notches. Arcs are exact SVG `A` commands.
  The path has no duplicate segments and no stray subpaths.
* **Fold lines:** separate open paths, always solid (never dashed, because cutter software
  treats dashes as geometry). They end exactly on the outline and never run along it.
* **Styling:** `fill="none"`, `stroke` and `stroke-width` are plain attributes on every
  element. There are no CSS classes and no `<style>`. The label is a `<text>` element filled
  with the label color, for engraving. If your laser software ignores SVG text, convert it
  with *Path → Object to Path* in Inkscape, or just disable the label.
* **Metadata:** the complete config is stored as JSON in
  `<metadata><pillowbox:config version="1">…</pillowbox:config></metadata>`, with the
  namespace `https://github.com/jaseg/yanartas-pillowbox/ns/config`. That is what *Import*
  and `--from-svg` read back. The `version` field is the config schema version. Files from
  an incompatible version are rejected with a clear message.

## HTTP API

| Method & path | Body | Response |
|---|---|---|
| `GET /api/defaults` | — | `{config, fields}` with the default config and field specs (labels, units, ranges) |
| `GET /api/config` | — | `{config}` with the current (persisted) config |
| `PUT /api/config` | `{config}` | Validates and saves it, returns `{config, saved}`; `422 {errors}` if invalid |
| `POST /api/render` | `{config}` | `{config, svg, model, info}`; `422 {errors: {field: message}}` if invalid |
| `POST /api/import` | SVG as the raw body or a multipart `file` | `{config}`; `400 {error}` if unusable |

## Development

```sh
uv run --group dev pytest        # tests
uv run --group dev ruff check .  # lint
uv run --group dev ruff format . # format
```

Layout:

* `src/yanartas_pillowbox/config.py`: the config dataclass, field specs, validation and
  schema versioning.
* `geometry.py`: pure geometry (typed outline, folds, 3D mesh). It has no Flask or SVG code.
* `svg.py`: SVG serialization and config extraction.
* `persistence.py`, `server.py`, `cli.py`.
* `static/`: the no-build ES-module frontend, with web components for the parameter input
  and both previews. three.js r160 is vendored under `static/vendor/three` (MIT).
