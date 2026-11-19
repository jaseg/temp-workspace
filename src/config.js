// Viewer configuration. Precedence: DEFAULTS < config file < URL parameters / CLI flags.
//
// {
//   "mode": "diff",                     // left | right | split | diff
//   "uiTheme": "auto",                  // light | dark | auto (interface only)
//   "colorThemes": [{"name": "...", "url": "themes/x.json"} | {"name": "...", "theme": {...}}],
//   "colorTheme": "KiCad Default",      // name of the theme to start with
//   "hiddenLayers": ["F.Fab", "B.Fab"], // layer names (boards) or object classes (schematics)
//   "kinds": {"electrical": true, "metadata": true, "layout": true, "minor": true},
//   "tone": {"old": 0.72, "new": 0.45}   // how much the versions are toned down in the diff view
// }
// Colour themes are KiCad colour-theme JSON files. Only themes listed here can be selected.

export const DEFAULTS = {
  mode: undefined,
  uiTheme: 'auto',
  colorThemes: [],
  colorTheme: 'KiCad Default',
  hiddenLayers: [],
  kinds: { electrical: true, metadata: true, layout: true, minor: true },
  tone: { old: 0.72, new: 0.45 },
};

const isObject = v => v && typeof v === 'object' && !Array.isArray(v);

/** Merge configuration layers (later ones win; objects merge, arrays and values replace). */
export function mergeConfig(...layers) {
  const out = {};
  for (const layer of layers) {
    for (const [k, v] of Object.entries(layer ?? {})) {
      if (v === undefined) continue;
      out[k] = isObject(v) && isObject(out[k]) ? mergeConfig(out[k], v) : v;
    }
  }
  return out;
}

/** Configuration from URL parameters: mode, ui, theme, hide (comma-separated layers). */
export function configFromParams(params) {
  return {
    mode: params.get('mode') ?? undefined,
    uiTheme: params.get('ui') ?? undefined,
    colorTheme: params.get('theme') ?? undefined,
    hiddenLayers: params.has('hide') ? params.get('hide').split(',').filter(Boolean) : undefined,
  };
}
