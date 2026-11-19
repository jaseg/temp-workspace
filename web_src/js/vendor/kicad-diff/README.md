# kicad-diff

Semantic visual diff for KiCad schematics (`.kicad_sch`), symbol libraries (`.kicad_sym`),
footprints (`.kicad_mod`), boards (`.kicad_pcb`) and whole projects.

Instead of blending two renders, kicad-diff parses both versions and classifies every change:

- **electrical**: pins that connect, disconnect or move between nets (schematic connectivity and
  routed copper on boards), added or removed parts, pads and labels
- **values & properties**: values, fields, footprint assignments, attributes, settings
- **layout**: moved or rotated parts, rerouted wires and tracks with unchanged connections, zone
  outlines and fills, graphics (most of these are *minor* and highlighted faintly)

The diff view tones down KiCad's colours (the old version more than the new one) and shows each
change with a bright highlight of the changed elements and a soft shade over its area. The old and
new views use the KiCad colour theme unchanged; the split view can show the highlights on both
sides. Changes are listed with previous/next navigation (`n`/`p`), visited markers and a short
description of the selected change; clicking an element selects its change.

Annotations (freehand, rectangles, ellipses, text) can be exported as JSON or embedded in a PDF
export of the diff, as real PDF annotations.

Targets KiCad 10.0 and 10.99 (development). Older files are shown on a best-effort basis with a
warning; elements that cannot be read are left out instead of failing the whole file.

## Usage

### Command line

```bash
kicad-diff html old.kicad_pcb new.kicad_pcb -o diff.html     # self-contained, works offline
kicad-diff serve old.kicad_sch new.kicad_sch                 # serve on localhost and open a browser
kicad-diff serve HEAD~1:board.kicad_pcb HEAD:board.kicad_pcb # versions from git
kicad-diff html old-project/ new-project/                    # whole projects (.kicad_pro or folder)
kicad-diff serve                                             # viewer with file upload
```

Options: `--mode left|right|split|diff`, `--ui light|dark`, `--hide F.Fab,B.Fab`,
`--color-theme theme.json` or `--color-theme pcm:<identifier>` (from the KiCad add-on repository;
repeatable), `--theme NAME`, `--config config.json`, `--project`, `--port`, `--no-open`.
See `kicad-diff --help`.

### On a web server

Serve the repository's `web/`, `src/` and `vendor/` folders as static files and open
`web/index.html?old=URL&new=URL`. Further parameters: `config=URL`, `mode`, `ui`, `theme`, `hide`,
and `project=1` (a `.kicad_pro` URL opens the project overview automatically).

### As web components

```html
<script type="module" src="src/ui/kicad-diff.js"></script>
<kicad-diff old-src="a.kicad_sch" new-src="b.kicad_sch" mode="diff"></kicad-diff>
```

`<kicad-diff-project>` (in `src/ui/project.js`) compares projects. Colours of the interface are
CSS custom properties (`--kd-*`) a host page can override.

### Configuration

A JSON file (see `src/config.js`): default mode, interface theme, hidden layers, change kinds,
toning, and the colour themes users can choose from. Only themes listed in the configuration or on
the command line are offered; `tools/fetch-pcm-theme.js` downloads themes from the KiCad add-on
repository for static deployments.

## Development

No runtime dependencies and no build step: the browser loads `src/` directly. Vendored: `earcut`
(polygon triangulation) and `pdf-lib` (PDF export, loaded on demand); see `vendor/LICENSES.md`.

```bash
npm test                 # unit tests
npm run test:e2e         # browser tests (Playwright, headless Chromium)
npm run corpus:fetch     # fetch KiCad's test files (10.0.8, pinned 10.99) and libraries into .cache/
npm run test:corpus      # corpus tests (sampled libraries; test:corpus:full for all files)
```

Corpus tests read every file of KiCad's own test data in both target versions: tokenizer round
trips, no read errors or unknown tokens (`test/corpus/known-unhandled.json`), recovery from damaged
files, rendering without errors, and diff invariants (a file has no changes against itself, against
a reordered copy, or against a copy with regenerated UUIDs) plus seeded edits that must be
classified correctly. Golden change lists for real file pairs live in `test/golden/`.

`tools/gen-font.js` and `tools/gen-themes.js` regenerate the Newstroke font subset and KiCad's
default colour theme from a KiCad source checkout.

## License

GPL-3.0-or-later. The Newstroke font data is GPL-2.0-or-later (KiCad); vendored libraries keep
their licenses.
