# Handoff: picking up work on yanartas-pillowbox

This note is for a new Claude Code session that starts from the latest state of the
`yanartas-pillowbox` branch. It covers how the user wants the work done, the current state
of things, and what is still open. The code itself is described in `README.md` (features,
every setting, export formats), `ARCHITECTURE.md` (algorithms), `rust/README.md` (the mesh
core) and `artifact/README.md` (the in-browser build). Read those for anything not here.

## The project in one paragraph

A generator for pillow boxes that are folded from a flexible PCB with a security mesh on it.
It takes a box size and produces:

- the flat pattern as an SVG (cut and fold lines),
- a 3D preview,
- an OpenSCAD model of the interior,
- a KiCad board with Gerbers. The board has a security mesh on both copper layers, either a
  KiMesh grid or a space-filling curve, with the curve's core written in Rust. A flat cable
  (FPC) with a plug leaves one edge of the board.

Boxes are one piece, or two identical pieces (`pieces = "two"`, see `_build_piece` in
`geometry.py`). Everything runs from a Flask web UI (`yanartas-pillowbox serve`), a CLI, and
an in-browser Pyodide build that is published as a claude.ai Artifact (`artifact/`).

## How the user wants the work done

- **Commits:**
  - Commit and push to `origin yanartas-pillowbox` after each finished batch of work.
  - Don't open PRs unless asked.
  - End every commit message with these two lines (update the session URL to the new
    session's):

    ```
    Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
    Claude-Session: https://claude.ai/code/<session>
    ```

  - Commit messages so far: a short summary line, then a short plain-prose body.
- **Git identity:** don't set `user.name`/`user.email` in the repository's own config; the
  checkout has been shared with the user's own machine. Use the global config (Claude,
  noreply@anthropic.com).
- **Leave these alone; they are the user's:**
  - local edits to `docs/partition/partition.ipynb`,
  - an untracked `pillowbox-protos/` folder,
  - `.ipynb_checkpoints/` folders.
- **Before committing:**
  - `uv run --group dev ruff check .`
  - `uv run --group dev ruff format --check .`
  - the full test suite. It runs the fast tests by default (`-m 'not slow'`, about 2.5
    minutes, 899 passed / 14 skipped at the last run). The slow full-size layouts run with
    `-m slow`.
- **Docs:** update `README.md` (the settings table, the export sections) and `ARCHITECTURE.md`
  along with code changes.
- **Artifact:** rebuild the in-browser build with `uv run python artifact/build.py` when
  Python modules change. If you add a module, add it to `PY_MODULES` in `artifact/build.py`.
- **Testing and checking:**
  - Prefer small, tailored test cases.
  - Keep checks fast: the partition neck check must stay under 100 ms.
  - Check visual changes for real, by rendering the SVG or taking a screenshot of the UI with
    Playwright, and look at the result before calling it done.
- **Code style:** match the surrounding code. Docstrings and comments are terse and
  parenthetical, and module constants carry short trailing comments.
- **Notebooks** (`docs/partition/`, `docs/mesh/`):
  - Port the algorithm faithfully, without changing the original code.
  - An export script writes JSON (its schema documented at its top), and the notebook checks
    itself against that JSON within a tolerance.
  - Save notebooks with their outputs.
  - Each notebook must run on "Restart & run all" with only its `requirements.txt`.
  - In the mesh notebook, basic geometry operations live in `support/` modules.
  - The mesh notebook's sources (`mesh.src`, the port files, the build script) were kept
    outside the repository and are not available to a new session. If it needs changes, edit
    `docs/mesh/mesh.ipynb` and `docs/mesh/support/` directly.
- **Mockups:** the user prints SVG mockups on transparent film. Marks printed on one side
  only therefore show from both sides.

## Environment notes

The previous session ran in a local microVM, not the standard cloud container. That VM's
setup and scratch tools are not in the repository. A fresh environment needs:

- **Python:** Python ≥ 3.12 through uv (gerbonara 1.6 needs it), then `uv sync`. This also
  builds the Rust PyO3 extension (`rust/python`) with maturin, so a Rust toolchain is
  required.
- **Browser build:** the `wasm32-unknown-unknown` Rust target, plus `wasm-bindgen-cli` at
  exactly the version of `wasm-bindgen` in `rust/Cargo.lock` (0.2.129 at the time of
  writing).
- **Browser checks:** Playwright with Chromium (`uv tool install playwright`,
  `playwright install chromium`, plus Chromium's system libraries).
- **UI screenshots:** start the server with
  `uv run yanartas-pillowbox serve --no-browser --port N`. To stop it, kill the server's
  process ID. A `pkill -f` on the command line also matches, and kills, the shell running
  it.
- **Layout timing:** a full-size space-filling-curve layout takes about 3–5 minutes per
  board. The KiMesh default (`mesh_algorithm = "kimesh"`) lays out in seconds.

## State at handoff (latest commit cc8500f)

All work is committed and pushed. These are the recent changes, newest first:

- **Glue guides** (two pieces): six short dotted marks for gluing the other piece's tab on at
  the right height.
  - **Where they are drawn:** on both silkscreens, in the SVG's "Glue guides" layer, and in
    the 2D view, which has a legend entry for them.
  - **On the tab:** three marks run across the tab and 5 mm on into the panel.
  - **On the free edge:** three marks run from the edge past the tab's width plus 5 mm.
  - **How the marks pair up:** a mark at `y` on one piece's tab lands at `d + Lp − y` on the
    other piece's free edge, where `d = cfg.inner_offset` and `Lp = cfg.front_length`. This
    was checked against `FoldedBox`. The middle marks share one `y`, which is correct; the
    user questioned it and then agreed.
  - **Clearance:** the end marks stay past the tab's mitres and 1 mm clear of the curved
    folds.
  - **Code:** `geometry.glue_guides` and `Pattern.guides`; `pcb.GUIDE_LAYERS` and
    `pcb.GUIDE_WIDTH`.
- **`stiffener_glue_tab`** (`off` by default): whether the glue tab gets a stiffener
  (`geometry.stiffener_outlines(..., tab=)`).
- **KiCad page:** the board goes on the smallest A-series sheet (A4 to A0, landscape or
  portrait) that holds the outline inside the default drawing sheet's frame and clear of its
  title block, with 2 mm clearance from both.
  - **Placement:** the design can go anywhere on the sheet and is placed as near the middle
    as fits. Positions are searched on a 41 × 41 grid (`pcb.sheet`, `Sheet`).
  - **Larger than A0:** a custom ("User") page.
  - **Example:** the user's 107 × 101 × 48.5 mm two-piece box goes on A4 portrait.
- **Fold settings** (space-filling curve only):
  - `mesh_partition_folds` (`follow` / `ignore`): whether the partitions' Voronoi cells
    follow the folds.
  - `mesh_curve_folds` (`avoid` / `free`): whether the curve keeps to each panel and crosses
    the folds as seldom as it can.
  - **How it's done:** a setting that ignores the folds treats the whole area as one zone.
    `partition.partition(..., ends=)` keeps each partition's strip end inside the curve's
    zones.
- **Connector presets:** `fpc_connector` has a "Custom" choice first and is the default. A
  preset fixes the pin count, pitch, edge margin and plug length, and the UI locks those
  fields.
  - **Series:** Hirose FH12 and FH34SRJ, Molex 503480, Omron XF2M, TE 1734839, XUNPU FPC-05F
    (0.5 mm pitch) and TE 84953 (1 mm pitch). They are listed in `presets.CONNECTOR_SERIES`.
  - **Pin counts:** only those in stock at LCSC (checked 2026-10-23). Stock at Mouser and
    Digi-Key was not verified.
  - **Left out:** Hirose FH35C (staggered contacts, which the plug footprint can't draw) and
    Molex 52745 (no drawing could be found).
- **Mesh notebook** (`docs/mesh/`): the space-filling-curve mesh step by step, from the
  partitions to the traces.
  - **Fidelity:** graph, relaxation, lanes and arcs are ported exactly; settling is
    simplified.
  - **Recording:** `export_mesh_cases.py` and a small Rust recorder (`recorder/`) record the
    real algorithm's steps for the notebook to check against.
- **Partition notebook** (`docs/partition/`): the partition algorithm.

## Open or possible next items

Nothing is in progress. Things that came up and were left open:

- **Two-piece glue tab:** the user first reported a miter or overlap problem at the glue
  tab's ends, then found they had glued it up wrong. No fix was made. If it comes up again,
  check it in the 3D model first (`FoldedBox.map`; `glue_tab_taper(cfg, gap)` sets each
  end's miter).
- **Connector presets:**
  - TE 1734839 has only four pin counts in stock.
  - The single-row plug model can't draw staggered contacts (FH35C).
  - A preset with fewer pins than the mesh needs makes the PCB export fail with a clear
    error. This is intended.
- **KiCad page:** the grid search can miss a sheet the design only just fits, by up to half
  a grid step. The page was checked only against KiCad's default drawing sheet layout
  (frame 10 + 2 mm, title block 110 × 34 mm); it was not opened in KiCad itself.
