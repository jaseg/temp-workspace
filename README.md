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
yanartas-pillowbox generate --set width=80 --set length=150 --set height=30 \
    --set thickness=0.5 -o box.svg
```

### Persistence

The UI saves the last valid configuration to **`./yanartas-pillowbox.json`** in the current
working directory. Saves happen through the server, debounced, and the file is reloaded on
startup. Files from schema version 1 are migrated (see below). If the file is missing,
corrupt, invalid or from an unknown schema version, the tool logs a warning and starts with
the defaults. It never crashes because of the file.

## Web UI

* **Left column:** the parameter form. Invalid values are flagged inline next to the field.
  While any value is invalid, the previews keep showing the last valid design and
  *Download* is disabled. Below the form, *Derived geometry* lists the computed fold and cut
  radii, arc length, the straight-edge length, the circumference and the flat panel width.
* **Pattern (2D):** the exact SVG you will download. Zoom with the wheel or the +/− buttons,
  drag to pan, and double-click or press *Fit* to reset. The header shows the pattern and
  sheet sizes. All lines are black, as in the export, and differ only in dashing (see
  *Output SVG*). A legend shows the line types; dashes keep their on-screen size at any
  zoom. The backdrop stays light in the dark theme so the black lines remain visible.
* **Folded box (3D):** an orbitable, shaded view of the closed box, folded exactly from the
  pattern faces (drag to orbit, scroll to zoom). Fold lines are drawn black, dashed by fold
  direction. The camera has almost no inertia, and the
  dimension labels keep the same on-screen size at any zoom.
* **Body cross-section:** a 2D section through the closed body, perpendicular to its length.
  The body has this same section everywhere between the curved folds. It shows the closed
  width and height, and marks the two straight folds where they are seen end-on.
* **Payload:** below the body controls, set the width, depth and height of a rectangular
  payload, and a **margin**: the minimum true distance from any point of the payload to the
  nearest point of the box surface. The payload is drawn centred inside the box in the
  cross-section and 3D views, with the margin envelope dashed in the cross-section. It turns
  red if the margin is not met. *Derived geometry* shows the actual clearance. It is never drawn in the SVG,
  but it is saved with the settings and in the SVG's embedded config. Set any payload
  dimension to 0 to hide it.
  * **Max** next to each payload field sets it to the largest value that keeps the margin in
    the current box.
  * **Fit box to payload** (in the body controls) sets width, length and height to the
    smallest box that holds the payload with its margin, minimizing the area of the
    pattern's bounding box.
    Glue tab and thickness are left alone. Results are rounded to 0.01 mm, always
    towards a box that still fits.
* **Parameter dimensions:** all three views annotate the inputs they show:
  * **Pattern:** circumference (both panels, flat), length (along the front panel's
    midline), height (across a flap), and the glue-tab width and taper (both at the tab's
    bottom end);
  * **Folded box:** width, length (along the top ridge) and height;
  * **Cross-section:** width, height, and half the circumference (the front panel's arc).

  Focusing or hovering a field highlights its dimensions in every view, and clicking a
  dimension jumps to its field. Each view has a *Dimensions* toggle. The dimensions are
  computed in Python from the same geometry (`dimensions.py`) and are preview-only: they
  never appear in the downloaded SVG.
* **Import:** *Import SVG…* or drag and drop a previously downloaded SVG anywhere onto the
  page to restore all of its parameters. A file without an embedded config, or with an
  incompatible one, produces a clear error message.
* **Download SVG** and **Reset to defaults** are in the top bar.
* Light and dark themes follow `prefers-color-scheme`.

## Parameter reference

All lengths are in millimetres.

| Key | Default | Meaning / constraints |
|---|---|---|
| `width` | 55 | Width of the closed box's cross-section, measured from fold to fold. 10–1000. This drives the panel size: see *circumference* below. |
| `length` | 120 | Length along the middle of a panel, between the apexes of the two curved folds: the shortest distance between the curves. 10–2000. The straight edges (corner to corner) are `length + height` long. |
| `height` | 20 | Total height (thickness) of the closed box at maximum bulge. The curved folds bow into the panels by height/2. At most ≈ 0.463·width (the UI states the exact limit). |
| `payload_width` | 30 | Payload size across the box. 0–2000. Preview only (see *Payload*). |
| `payload_depth` | 100 | Payload size along the box length. 0–2000. |
| `payload_height` | 13 | Payload size along the box height. 0–2000. |
| `payload_margin` | 1 | Minimum clearance between payload and box surface (true 3D distance). 0–100. |
| `glue_tab_width` | 12 | Width of the glue tab. 3–100, and narrower than one panel (half the circumference). |
| `glue_tab_taper` | 9 | How far each end of the glue tab is cut back along the length. 0 to (length + height)/2 − 1. Below the *Min. glue-tab taper* shown in the UI, the glued tab reaches past the curved folds near the corners. |
| `thickness` | 0.4 | Material thickness, 0–5. The flap cut edge is offset from the curved folds by t/2 (see below). |

The stroke width is fixed at 0.1 mm.

**Computed, not set:** the **circumference** is the perimeter of the closed body's
cross-section, i.e. the flat width of both panels together. It follows from `width` and the
height: the more the panels bulge, the more material it takes to span the same width. Each
panel is half the circumference wide in the flat pattern. The UI shows both values under
*Derived geometry*, and the pattern view dimensions the circumference.

### Payload fit and clearance

Distances are measured to the zero-thickness box surface. Inside the closed box, the body's
cross-section has a height profile `Zp(X)`, and each end wall (a flap mirrored across its
crease) stands `Zp(X)` in from the end of the straight edges. So the interior is
`|Z| ≤ Zp(X), |Y| ≤ (length + height)/2 − Zp(X)`.

The surface consists of the panels, which are cylinders with rulings along the length, and
the end walls, which are cylinders with vertical rulings. For a payload inside the box, the
true distance to the surface is the smaller of two 2D distances:

* **Panels:** the distance in the cross-section between the payload rectangle and the
  profile.
* **End walls:** exactly `(length − payload_depth)/2`. In plan view every wall point is at
  least `length/2` from the centre (the midline length), with equality at the centre.

This works because the nearest point on an unbounded cylinder that isn't on the real surface
lies outside the box, so the real surface is crossed first.

*Fit box to payload* sets `length = payload_depth + 2·margin`. It then searches over the
cross-section's sagitta/panel ratio: for each ratio, it finds the smallest panel width whose
profile keeps at least `margin` from the payload rectangle (`payload.py`). The tests check
the clearance against a brute-force distance to every vertex of a fine 3D mesh.

### Geometry model

The flat pattern is laid out as front panel, back panel and then the glue tab, side by side.
The straight body edges are `length` long. Each flap is a lens between two circular arcs
through the panel corners:

`W` below is the flat panel width (half the circumference).

* the **curved fold** bows *into* the panel by the fold sagitta `s_f` (`height/2`). Its distance from the chord at position `u` is `f(u)`;
* the **cut edge** bows *out* of the panel by `s_c = s_f − thickness/2`.

The closed box (shown in the 3D preview) is folded exactly from these faces, without
stretching:

* **Panels:** each panel bends into a cylinder whose rulings run along the length. Measured
  along the panel width `u`, the cross-section rises by exactly `f(u)`. That makes the box
  `2·s_f` deep and puts each curved fold in a plane at 45°.
* **Flaps:** folding along such a planar crease mirrors the flap across that plane. Each flap
  becomes a curved end wall standing straight across the box's height. The front and back
  flaps of one end lie on the same wall and overlap; nothing creases them along a midline.
* **Thickness:** with zero thickness, each flap's cut edge lands exactly on the opposite
  panel's curved fold. The `thickness/2` offset leaves room for the material.
* **Glue tab:** it lies against the inside of the front panel's free edge.

The cross-section's shape depends only on the ratio `s_f / W`, so for a given `width` and
height the tool solves for the `W` whose folded cross-section is exactly `width` wide
(`crosssection.py`).

This only works if the fold arc turns at most 45° at the corners (`s_f < 0.207·W`). The tool
allows `s_f ≤ 0.2·W`, which for a given box width means a fold sagitta of at most ≈ 0.232·width
(height ≤ ≈ 0.463·width). The tests check that every 3D face is an isometric image of its
pattern face and that the faces stay joined along every fold.

## Output SVG & line convention

All lines are black (`#000000`) and differ only in dashing. Folds are grouped by their
direction as seen from the **print side**, which is the side facing you when you view the
SVG. That side becomes the outside of the box.

| Layer (`<g id>`) | Inkscape label | Line | `stroke-dasharray` (mm) |
|---|---|---|---|
| `cut` | Cut | solid | — |
| `fold-mountain` | Fold - mountain | dash-dot | `3 1.5 0.5 1.5` |
| `fold-valley` | Fold - valley | dashed | `3 2` |

The dashes follow the origami convention. Each fold's direction is computed from the folded
3D model, not set by hand. For a pillow box printed on the outside, every fold is a mountain
fold: the panels fold around the interior, and the flaps and glue tab fold inwards. So the
valley layer is only written when there are valley folds, which currently there aren't.
Fold lines use butt caps so dashes and dots keep their nominal lengths. Some laser software
turns dashed strokes into separate short segments or ignores the dashing. Either way the
layers keep the line types apart.

* **Units and canvas:** `width`/`height` are given in mm with a matching `viewBox`, so one
  user unit is 1 mm. The canvas is the pattern's bounding box plus exactly **10 mm** on every
  side. There are no page-size settings.
* **Cut outline:** exactly one closed `<path>` (one `M`, ending in `Z`) that traces the whole
  contour in one direction. Arcs are exact SVG `A` commands.
  The path has no duplicate segments and no stray subpaths.
* **Fold lines:** separate open paths, dashed by fold direction. They end exactly on the
  outline and never run along it.
* **Styling:** `fill="none"`, `stroke` and `stroke-width` are plain attributes on every
  element, with a fixed 0.1 mm stroke width. There are no CSS classes and no `<style>`.
* **Metadata:** the complete config is stored as JSON in
  `<metadata><pillowbox:config version="3">…</pillowbox:config></metadata>`, with the
  namespace `https://github.com/jaseg/yanartas-pillowbox/ns/config`. That is what *Import*
  and `--from-svg` read back. The `version` field is the config schema version. Files from
  an unknown version are rejected with a clear message.
* **Schema versions:** version 1 stored the flat panel width as `width`; version 2 the
  closed box width. Version 3 renamed `depth` to `height`, measures `length` along the panel
  midline (it was corner to corner) and dropped the direct-sagitta mode, the stroke width,
  the thumb notch and the label. Version-1 and -2 files (saved settings and SVGs) are
  converted on load so they describe the same box; removed options are ignored. Line colors used to be settings; they are now fixed to black, and old color settings are
  ignored on load.

## HTTP API

| Method & path | Body | Response |
|---|---|---|
| `GET /api/defaults` | — | `{config, fields}` with the default config and field specs (labels, units, ranges) |
| `GET /api/config` | — | `{config}` with the current (persisted) config |
| `PUT /api/config` | `{config}` | Validates and saves it, returns `{config, saved}`; `422 {errors}` if invalid |
| `POST /api/render` | `{config}` | `{config, svg, model, section, info, dimensions, payload}`; `422 {errors: {field: message}}` if invalid |
| `POST /api/payload` | `{config, action: "fit"}` or `{config, action: "maximize", field}` | `{config}` with the fitted box or maximized payload (not saved); `422 {errors}` if impossible |
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
* `payload.py`: payload fit test, per-dimension maximize and the box fit.
* `dimensions.py`: preview dimension annotations, tagged with the parameter they show.
* `persistence.py`, `server.py`, `cli.py`.
* `static/`: the no-build ES-module frontend, with web components for the parameter input
  and both previews. three.js r160 is vendored under `static/vendor/three` (MIT).
