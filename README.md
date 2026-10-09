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
startup. If the file is missing, corrupt, invalid or from another schema version, the tool logs a warning and starts with
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
  * **Board preset** fills in the payload size of a common development board: Raspberry Pi
    Model A, Model B and Zero (each also with a HAT or pHAT), Arduino UNO Q (with and
    without a shield), STM32 Nucleo-64, BeagleBone Black, Odroid C4 and N2+, and Jetson
    Orin Nano (Super) and Orin Nano 2. The board's long side runs along the box. The sizes
    are approximate (`presets.py`): heights include connectors and stacked add-on boards, and
    some are estimated, so check your own board. The preset is not a setting; the dropdown
    just shows which preset, if any, matches the current payload size.
  * **Max** next to each payload field sets it to the largest value that keeps the margin in
    the current box.
  * **Fit box to payload** (in the body controls) sets width, length and height to the
    smallest box that holds the payload with its margin, minimizing the area of the
    pattern's bounding box.
    Glue tab and thickness are left alone. Results are rounded to 0.01 mm, always
    towards a box that still fits.
* **Parameter dimensions:** all three views annotate the inputs they show:
  * **Pattern:** circumference (both panels, flat), length (along the front panel's
    midline), height (across an inner flap), and the glue-tab width and taper (both at the
    tab's bottom end);
  * **Folded box:** width, length (along the top ridge) and height;
  * **Cross-section:** width, height, and the front panel's arc (part of the
    circumference). This view shades the material at its thickness, the box interior and the
    payload space, and draws the glue tab and, dashed, the payload margin.

  Width, length and height are interior dimensions, so where they are measured inside the
  material their end points sit off the drawn lines by the material allowance.

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
| `width` | 55 | Interior width of the closed box's cross-section, from fold to fold (between the material's inner corners). 10–1000. This drives the panel size: see *circumference* below. |
| `length` | 120 | Interior length along the middle of the box, between the end walls: the shortest distance between the curves. 10–2000. The straight edges (corner to corner) are `length + height + 3·thickness` long. |
| `height` | 20 | Interior height of the closed box at maximum bulge. At most ≈ 0.46·width (the UI states the exact limit). |
| `payload_width` | 30 | Payload size across the box. 0–2000. Preview only (see *Payload*). |
| `payload_depth` | 95 | Payload size along the box length. 0–2000. With interior walls, it has to fit between them. |
| `payload_height` | 13 | Payload size along the box height. 0–2000. |
| `payload_margin` | 1 | Minimum clearance between payload and box surface (true 3D distance). 0–100. |
| `glue_tab_width` | 12 | Width of the glue tab. 3–100, and narrower than the front panel it is glued onto. |
| `glue_tab_taper` | 9 | How far each end of the glue tab is cut back along the length. 0 to half the straight edge − 1. Below the *Min. glue-tab taper* shown in the UI, the glued tab reaches past the curved folds near the corners. |
| `interior_walls` | on | Extends each inner flap into a bridge along the front panel and a second, interior end wall (see *Interior walls* below). |
| `interior_wall_offset` | 10 | Clear gap between the inside of the doubled end wall and the outside of the interior wall. 0–500. The payload space between the interior walls is `length − 2·(offset + thickness)`. |
| `fpc_cutout` | `none` | `none`, `front`, `back` or `both`: cuts the top of the inner flaps' curved edge off level at that end of the box, leaving a slot for a flat cable (FPC). With interior walls, it instead notches both bridge folds (see below). `front` is the end at the top of the pattern, `back` the one at the bottom. The outer flaps are never cut. |
| `fpc_cutout_width` | 15 | Width of that flat section. 0 to the inner flaps' width − 1. The cut is level and exactly this wide. The flap's edge is not quite symmetric, so the section sits around its highest point, within about a millimetre of the flap's centre. |
| `print_side` | `outside` | `outside` or `inside`: the side of the material the fold indicators are drawn for (e.g. the side the laser scores). It only switches the fold lines between mountain and valley; the pattern is identical either way. |
| `thickness` | 0.2 | Material thickness, 0–5. Width, length and height are interior dimensions; the pattern adds the material around them (see *Material thickness* below). Height − thickness must be at least 0.5. |

The stroke width is fixed at 0.1 mm.

**Computed, not set:** the **circumference** is the perimeter of the closed body's
cross-section (along the middle of the material), i.e. the flat width of both panels
together. It follows from `width`, the height and the thickness: the more the panels bulge,
the more material it takes to span the same width. The two panels differ slightly in width
(see below). The UI shows these values, and the outside dimensions, under *Derived
geometry*, and the pattern view dimensions the circumference.

### Payload fit and clearance

Distances are measured to the material's inner surface, half a thickness inside the
mid-surface that the geometry model folds. That surface consists of the panels, which are
cylinders with rulings along the length, and the inner flaps' end walls, which are
cylinders with vertical rulings. For a payload inside the box, the true distance to the
surface is the smaller of two 2D distances, each minus half the thickness:

* **Panels:** the distance in the cross-section between the payload rectangle and each
  panel's mid-surface.
* **End walls:** the distance in plan view between the payload and the back panel's crease
  curve. It is `(length − payload_depth)/2` whenever the payload spans the box's centre.

This works because the nearest point on an unbounded cylinder that isn't on the real surface
lies outside the box, so the real surface is crossed first.

*Fit box to payload* sets `length = payload_depth + 2·margin`. It picks the height with a
fast search on an approximation: the interior as a zero-thickness box, whose cross-section
shape depends only on its sagitta/panel ratio. The pattern area is flat around its minimum,
so the approximation costs next to nothing. It then solves the exact smallest width for that
height (`payload.py`). The tests check the clearance against a brute-force distance to every
vertex of a fine 3D mesh.

### Geometry model

The flat pattern is laid out as front panel, back panel and then the glue tab, side by side.
Each flap sits between its panel's **curved fold**, a circular arc through the panel corners
that bows *into* the panel by the fold sagitta `s_f` (distance `f(u)` from the chord at
position `u`), and its **cut edge**, which bows *out* of the panel.

The model folds the material's mid-surface. The closed box (shown in the 3D preview) is
folded exactly from the pattern faces, without stretching:

* **Panels:** each panel bends into a cylinder whose rulings run along the length. Measured
  along the panel width `u`, the cross-section rises by exactly `f(u)`. That puts each
  curved fold in a plane at 45°.
* **Flaps:** folding along such a planar crease mirrors the flap across that plane. Each flap
  becomes a curved end wall standing straight across the box's height, at its own panel's
  crease. Nothing creases the flaps along a midline.

This only works if a fold arc turns at most 45° at the corners (`s_f < 0.207·W`, `W` being
the panel's flat width). The tool allows `s_f ≤ 0.2·W`, which limits the height to roughly
0.46·width. The tests check that every 3D face is an isometric image of its pattern face
and that the faces stay joined along every fold.

#### Interior walls

Seen in a lengthwise cut, each end of the box goes from a doubled wall (`||`) to a doubled
wall plus an interior wall (`||  |`). On the pattern, each inner (back-panel) flap
continues past its former cut edge into a **bridge** and then a second oval flap, the
**interior wall**:

* The inner flap's top edge becomes a fold where it meets the inside of the front panel.
  That fold sits at the bridge's mid-surface, one thickness inside the front panel's
  mid-surface.
* The bridge runs `offset + thickness` along the inside of the front panel, then folds
  down into the interior wall. The interior wall reaches down to the back panel's inner
  surface.
* Both folds follow the exact curve as fine polylines, emitted as one dashed SVG path each.
  Bridge and interior wall are slightly narrower than the inner flap: they stop where the
  interior wall would be lower than 1 mm, two thicknesses, or a tenth of the height. That
  leaves some room at the body folds, where the inner flap's edge is cut at the bridge's
  level instead.
* Folding them is only approximately isometric, since a bridge can't lie perfectly flat
  against both curved surfaces at once; the material's flexibility absorbs the difference.
  The 3D view therefore draws bridges and interior walls as translucent surfaces, like the
  payload, rather than as folded paper.
* The payload clearance and *Fit box to payload* count the interior walls: *Fit* adds
  `2·(offset + thickness)` to the length.
* **FPC cutout with interior walls:** the cutout notches both bridge folds over its width.
  The inner flap and the interior wall are cut back by the same depth below the bridge,
  which keeps its full edge. The fold lines stop at the notches, and each notch is its own
  closed cut path. A flat cable runs under the bridge and out between the inner and outer
  flaps.

#### Material thickness

`width`, `length` and `height` are the interior. With thickness `t`, the material's
mid-surface lies `t/2` outside it, and the two flaps of each end lie on top of each other:

* The **front** panel's flaps close on the **outside**. Its fold bows in by `height/2`. The
  **back** panel's flaps close on the **inside**, and its fold bows in by `height/2 + t`, so
  the outer wall stands one thickness outside the inner wall. As a result the front panel
  is about `t` flatter than the back.
* **Inner flaps** are cut short to the front panel's inner surface. Near the corners, where
  that surface dips below the fold chord, their edge runs along the chord.
* **Outer flaps'** cut edges are flush with the back panel's outer surface all along. At the
  corners they reach slightly past the panel corners, which shows as short cut steps.
* With `t > 0` the cut edges are fine polylines (about 0.5 mm segments) that follow these
  surfaces exactly. At zero thickness they are the plain circular arcs.
* **Glue tab:** it lies on the **outside** of the front panel, unlike in usual packaging. The
  back panel's glue fold sits `t / sin α` beyond the front panel's free edge (α being the
  panel's angle at that edge), so the tab wraps around that edge.
* **Width solve:** the interior width runs between the inner corners at the two side folds,
  where the panels' inner surfaces meet. The tool solves for the two panels' flat widths so
  that this is exactly `width` (`crosssection.solve_body`).
* **Lengths:** the straight edges are `length + height + 3·t` long.

## Output SVG & line convention

All lines are black (`#000000`) and differ only in dashing. Folds are grouped by their
direction as seen from the **print side**: by default the outside of the box, which is the
side facing you when you view the SVG. Set `print_side` to `inside` if you score or mark the
other side of the material. The pattern is not mirrored for that, since a pillow box is its
own mirror image. Only the fold indicators flip.

| Layer (`<g id>`) | Inkscape label | Line | `stroke-dasharray` (mm) |
|---|---|---|---|
| `cut` | Cut | solid | — |
| `fold-mountain` | Fold - mountain | dash-dot | `3 1.5 0.5 1.5` |
| `fold-valley` | Fold - valley | dashed | `3 2` |

The dashes follow the origami convention. Each fold's direction is computed from the folded
3D model, not set by hand. Seen from the outside, every fold of a pillow box is a mountain
fold: the panels fold around the interior, and the flaps and glue tab fold inwards. Seen
from the inside, every fold is a valley fold. A fold layer is only written when it has
folds.
Fold lines use butt caps so dashes and dots keep their nominal lengths. Some laser software
turns dashed strokes into separate short segments or ignores the dashing. Either way the
layers keep the line types apart.

* **Units and canvas:** `width`/`height` are given in mm with a matching `viewBox`, so one
  user unit is 1 mm. The canvas is the pattern's bounding box plus exactly **10 mm** on every
  side. There are no page-size settings.
* **Cut outline:** exactly one closed `<path>` (one `M`, ending in `Z`) that traces the whole
  contour in one direction. Arcs are exact SVG `A` commands; with material thickness,
  flap edges that follow the body are fine polylines. The path has no duplicate segments
  and no stray subpaths. FPC notches through the interior walls' folds are extra closed
  paths (`cut-notch-N`) in the same layer.
* **Fold lines:** separate open paths, dashed by fold direction. They end exactly on the
  outline (or a notch) and never run along it.
* **Styling:** `fill="none"`, `stroke` and `stroke-width` are plain attributes on every
  element, with a fixed 0.1 mm stroke width. There are no CSS classes and no `<style>`.
* **Metadata:** the complete config is stored as JSON in
  `<metadata><pillowbox:config version="5">…</pillowbox:config></metadata>`, with the
  namespace `https://github.com/jaseg/yanartas-pillowbox/ns/config`. That is what *Import*
  and `--from-svg` read back. The `version` field is the config schema version. Files from
  another version are rejected with a clear message.
* **Schema versions:** the version is bumped whenever the meaning of saved settings
  changes. Settings files and SVGs from any other version are rejected; there are no
  migrations.

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
