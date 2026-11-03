# Hatched Extruded Type

A single-file web app (`index.html`) that renders text as oblique-extruded 3D SVG:

- Any Google Font (list from the Fontsource API, outlines from the Fontsource CDN,
  previews in the chooser via the Google Fonts CSS API), or a local `.ttf`/`.otf`/`.woff`.
- Extrusion angle and length (default 45° to the top right, 0.5 × font size), with the
  extruded sides shaded by a line hatch running along the extrusion direction.
- Letter faces textured with an adjustable crosshatch; its line width is locked to the
  extrusion hatch width by default.
- Live preview, Copy SVG and Download SVG. The output is plain paths, clip paths and
  hatch lines; no fonts are embedded.

Open `index.html` in a browser (it needs network access for opentype.js and the fonts).

If a `fonts/index.json` sits next to the page, fonts are read from bundled packs
(concatenated WOFF files, indexed as `[pack, offset, length]`) instead of Fontsource. The
claude.ai artifact build uses this, because its sandbox blocks requests to other hosts.
Inside an artifact, Download SVG goes through the viewer's `downloads` capability.
