# yanartas-pillowbox

Local, web-based utility to generate flexible printed circuit board Tamper-Sensing Meshes that fold up like Pillow
Boxes. See [the project documentation](https://ashen.yasec.de/yanartas-pillowbox).

> [!NOTE]
> This project is fully slop-coded. It does the job, but it's not pretty, elegant or human-maintainable code. Do not
> rely on this code being good, and verify anything generated with it before production. Probably avoid interacting with
> the code without the help of an LLM as it's quite likely to give you eye cancer.

## Installation & running

Requires Python ≥ 3.12. With [uv](https://docs.astral.sh/uv/):

```sh
uvx --from . yanartas-pillowbox        # from a checkout
```

Or use `pip install .`, then run `yanartas-pillowbox`.

### Commands

```text
yanartas-pillowbox [serve] [--port N] [--no-browser]
```
Starts the web UI on a free port, or on `--port`. It prints the URL and opens it in your browser unless you pass
`--no-browser`. The server only listens on `127.0.0.1`.

```text
yanartas-pillowbox generate [--config FILE | --from-svg FILE] [--set key=value ...] -o out.svg
```

Generates an SVG from the command line, using the same engine as the UI.

* `--config FILE` takes a JSON config that the web UI persists into the current working directory when you run it.
* `--from-svg FILE` reuses the config embedded in a previously generated SVG.
* `--set key=value` overrides a single parameter and can be repeated.
* `-o -` writes the SVG to stdout.

For example: ``sh yanartas-pillowbox generate --set width=80 --set length=150 --set height=30 \
    --set thickness=0.5 -o box.svg
``

```text
yanartas-pillowbox pcb [--config FILE | --from-svg FILE] [--set key=value ...] -o DIR [--name NAME]
```
Lays the box out as a flex PCB with a security mesh on both sides (see *PCB layout* below) and writes `NAME.kicad_pcb`
and `NAME.kicad_pro`, the Gerber and drill files in `NAME-gerbers/`, and `NAME-top.svg` / `NAME-bottom.svg` into `DIR`
(`NAME` defaults to `pillowbox`). Needs the FPC cable option to be enabled in the config.

### Configuration Persistence

The UI automatically saves the last valid configuration to **`./yanartas-pillowbox.json`** in the current working
directory. 

## Parameter reference

> [!HINT]
> The following section is LLM-generated.

All lengths are in millimetres.

| Key | Default | Meaning / constraints |
|---|---|---|
| `pieces` | `one` | `one`: the usual one-piece pattern. `two`: two identical pieces, each one panel with an outer flap at its top end, an inner flap at its bottom end, the FPC cable on its free edge and a glue tab on the other (see *Two pieces*). |
| `width` | 107 | Interior width of the closed box's cross-section, from fold to fold (between the material's inner corners). 10–1000. This drives the panel size: see *circumference* below. |
| `length` | 101 | Interior length along the middle of the box, between the inner end walls: the shortest distance between the curves. 10–2000. The back panel's straight edges (corner to corner) are `length + height + 3·thickness` long, the front panel's `2·end_wall_gap` longer. |
| `end_wall_gap` | 10 | Clear gap, in the middle of the box, between each outer end wall and the inner end wall inside it, covered by a lid (see *End wall gap* below). 0–500. 0 stacks the two walls of each end on each other, with no lid. |
| `lid_overlap` | 5 | How far each lid runs on over the outside of the back panel, past the inner end wall's outer surface (measured along the box). 0–200. Only with an end wall gap. |
| `lid_offset` | 2 | How far the lids float above the back panel where they come closest; the box's end sections grow by as much in height, and wider to match (see *End wall gap*). 0–100, limited per box: the widened sections may turn at most 45° at the sides, so steep boxes and thick material allow less (the UI states the limit). Only with an end wall gap. |
| `height` | 48.5 | Interior height of the closed box at maximum bulge. At most ≈ 0.46·width (the UI states the exact limit). |
| `payload_width` | 56 | Payload size across the box. 0–2000. Preview only (see *Payload*). |
| `payload_depth` | 85 | Payload size along the box length. 0–2000. It has to fit between the inner end walls. |
| `payload_height` | 22 | Payload size along the box height. 0–2000. |
| `payload_clearance` | 8 | Minimum clearance between payload and box surface (true 3D distance). 0–100. |
| `glue_tab_width` | 12 | Width of the glue tab, and of the lids' glue tabs. 3–100, and narrower than the front panel it is glued onto. The tab's ends are cut back only as far as needed to stay off the front panel's curved folds, from square up to 45° (*Glue-tab taper* in the UI); the default end wall gap needs none. |
| `fpc_cutout` | `none` | `none`, `front`, `back` or `both`: cuts the top of the inner flaps' curved edge off level at that end of the box, leaving a slot for a flat cable (FPC). `front` is the end at the top of the pattern, `back` the one at the bottom. The outer flaps are never cut. |
| `fpc_cutout_width` | 15 | Width of that flat section. 0 to the inner flaps' width − 1. The cut is level and exactly this wide. The flap's edge is not quite symmetric, so the section sits around its highest point, within about a millimetre of the flap's centre. |
| `fpc_cable` | `up` | `none`, `up` or `down`: a flat cable of the flex PCB leaving the front panel's free straight edge (the glued edge), turning up (towards the top of the pattern, the box's front end) or down along it (see *FPC cable* below). |
| `fpc_entry_offset` | 0 | Where the cable leaves the edge: how far (mm) from the lowest it can go (turning up; the highest, turning down). Folded into the box, its first corner lies on the back panel beside the edge and must stay clear of the inner flap at that end: 0 puts it as near as that allows. |
| `fpc_cable_length` | 55 | From the front panel's edge to the plug's tip, with every corner folded flat. 10–2000. The cable sticks out beside the edge; every further row makes the pattern wider (the default takes one). |
| `fpc_connector` | `custom` | A connector preset, `<series>-<pins>` (e.g. `hirose-fh12-30`): fixes `fpc_pins`, `fpc_pitch`, `fpc_edge_margin` and `fpc_plug_length` to the series' recommended FPC end, whatever is given for them (the UI locks those fields). Series: Hirose FH12, Hirose FH34SRJ, Molex 503480, Omron XF2M, TE 1734839, XUNPU FPC-05F (0.5 mm), TE 84953 (1 mm); only the pin counts in stock at LCSC (October 2026). `custom`: set them yourself. |
| `fpc_pins` | 61 | Contacts of the FPC connector, 2–200. The default holds the default space-filling-curve mesh: 3 partitions × 4 traces × 2 ends × 2 sides, and a GND pin after every four ends (plus pin 1). The PCB layout refuses a plug with too few pins. |
| `fpc_pitch` | 0.5 | Contact pitch, 0.1–2.54. |
| `fpc_edge_margin` | 0.5 | From the outermost contacts' centres to the plug's edges: the plug is `(pins − 1)·pitch + 2·margin` wide (31 mm by default, the usual `(pins + 1)·pitch`). At most the front panel's straight edge beside the back panel, less 1 mm. |
| `fpc_plug_length` | 4.5 | Length of the plug at the cable's end, 1–50: the part that goes into the connector, stiffened (4.5 mm or more for Hirose FH12 and the like). |
| `fpc_cable_inset` | 0 | How much narrower than the plug the rest of the cable is on each side; the plug's ears then stick out, on past the vias and the traces' fan-out behind the contacts, narrowing at 45°. 0–10. |
| `fpc_corner_radius` | 1 | Rounds the cable's corners and where it meets the front panel's edge (not the plug's). 0–10; smaller where there is no room, e.g. at most half the clearance at the slots between rows. |
| `fpc_cable_gap` | 1 | Cut-to-cut clearance between the cable's rows, and between the cable and the rest of the pattern. 0.1–20. |
| `mesh_trace_width` | 0.15 | PCB layout: width of the security mesh's traces, on both copper layers and along the cable. 0.05–2. |
| `mesh_trace_space` | 0.15 | The least copper-to-copper space between them (and the clearance of the rest of the layout): never undercut, checked by the design rules. Settled, the traces spread into the room left over, so the average space is larger: about 20 % with the space-filling curve, 5 % with the KiMesh grid (reported as *Average space*). 0.05–2. |
| `mesh_traces` | 4 | Mesh traces (loops, two ends each) per side of the foil: for the space-filling curve, per partition (so `mesh_partitions × mesh_traces` per side); for KiMesh, in all. The exit cell is twice as many trace pitches wide as a side has traces (KiMesh: every cell, 2.4 mm by default). Whole numbers 1–16; the plug needs a pin per end plus the GND pins. |
| `mesh_partitions` | 3 | Space-filling curve only: each side's mesh area is split into this many partitions of equal area, each with `mesh_traces` traces of its own from the connector. Whole numbers 1–16. KiMesh ignores it. |
| `mesh_edge_clearance` | 0.5 | How far the mesh keeps off the foil's cut edges and slits. 0–10. |
| `mesh_seed` | 0 | Seed of the mesh's layout: the same seed gives the same mesh. Any text, distilled into a 256-bit key; the layout's randomness is drawn from it by cryptographically secure generators (SHAKE-256, ChaCha20 in the Rust core), each part of the layout a stream of its own. The die button puts in a fresh 128-bit seed. |
| `stiffener_flap_offset` | 0.5 | How far the flaps' stiffener outlines (KiCad's User.1, the SVG's stiffener layer) stay inside the flaps (mm): each edge moved in, the corners mitred. 0–10. |
| `stiffener_glue_tab` | `off` | `on` gives the glue tab a stiffener too (User.1 and the SVG's stiffener layer), as the flaps have; `off` leaves it bare. |
| `stiffener_tab_offset` | 0.5 | The same for the glue tab's stiffener, if on (mm). 0–10. |
| `mesh_algorithm` | `kimesh` | How the mesh is laid out: `kimesh` (tiles on a square grid, fast) or `sfc` (a closed space-filling curve after Bedel et al. 2022: follows edges and folds, crosses each fold as seldom as can be, takes a minute or more per layer). See *PCB layout*. |
| `mesh_shape` | `lines` | Space-filling curve only: how its traces are drawn: `lines` each trace redrawn as the smooth curve through its vertices, in straight segments no two of which turn more than 10° (but where that would bring copper closer); `arcs` that curve redrawn in straight lines and circular arcs (KiCad track arcs) within the polyline's own error of it, further (up to 3 % of the pitch) where it has room to the copper beside it, so mostly arcs. |
| `mesh_partition_folds` | `follow` | Space-filling curve only: the Voronoi map the partitions are cut from. `follow`: each panel's cells on their own, crossing a fold costs more and the partitions' borders keep to the folds where they can; `ignore`: the whole area one zone, cells and borders across the folds as anywhere else. |
| `mesh_curve_folds` | `avoid` | Space-filling curve only: `avoid` lays each panel's curve out on its own, half a spacing off the folds, joined across them only as often as needed (two crossings a join); `free` lays it out over the whole area as if there were no folds (no bare strips along them, but many crossings). The strips' ends (where each partition's curve opens) are kept within one zone either way. |
| `mesh_back_offset` | `cell` | KiMesh only: how far the back (B.Cu) mesh's grid is offset from the front one's, in x and y: `cell` half a cell; `cell_trace` half a cell plus a trace width, so that the back traces also lie over the front traces' gaps. |
| `print_side` | `outside` | `outside` or `inside`: the side of the material the fold indicators are drawn for (e.g. the side the laser scores). It only switches the fold lines between mountain and valley; the pattern is identical either way. |
| `thickness` | 0.2 | Material thickness, 0–5. Width, length and height are interior dimensions; the pattern adds the material around them (see *Material thickness* below). Height − thickness must be at least 0.5. |

## Development

```sh
uv run --group dev pytest        # tests
uv run --group dev ruff check .  # lint
uv run --group dev ruff format . # format
```

### Source Layout:

* `src/yanartas_pillowbox/config.py`: the config dataclass, field specs, validation and schema versioning.
* `geometry.py`: pure geometry (typed outline, folds, 3D mesh). It has no Flask or SVG code.
* `svg.py`: SVG serialization and config extraction.
* `payload.py`: payload fit test, per-dimension maximize and the box fit.
* `dimensions.py`: preview dimension annotations, tagged with the parameter they show.
* `scad.py`: the OpenSCAD interior model.
* `api.py`: the JSON API, shared by the Flask server and the in-browser build.
* `persistence.py`, `server.py`, `cli.py`.
* `static/`: the no-build ES-module frontend, with web components for the parameter input and both previews. three.js
  r160 is vendored under `static/vendor/three` (MIT).

## License

GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later): see LICENSE. The Rust core in `rust/` is under the
same license.
