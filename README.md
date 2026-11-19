# kicad-diff

Semantic visual diff for KiCad schematics (`.kicad_sch`), symbol libraries (`.kicad_sym`),
footprints (`.kicad_mod`) and boards (`.kicad_pcb`).

Instead of blending two renders, kicad-diff parses both versions and classifies every change as
**electrical** (connections), **layout** (moves, reroutes, zone geometry) or **metadata** (values,
properties), and highlights each kind differently.

Targets KiCad 10.0 and 10.99 (development). Older files are read on a best-effort basis.

## Development

No runtime dependencies and no build step: the browser loads `src/` directly.

```bash
npm test                 # unit tests
npm run corpus:fetch     # fetch KiCad's test files and libraries into .cache/
npm run test:corpus      # parse the KiCad corpus (10.0 and 10.99)
```

## License

GPL-3.0-or-later
