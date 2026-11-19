// KiCad colour themes (KiCad's own colour-theme JSON format) and layer → colour lookup.

import DEFAULT_THEME from './default-theme.js';

export { DEFAULT_THEME };

/** "rgb(1, 2, 3)" / "rgba(1, 2, 3, 0.5)" → [r, g, b, a] in 0..1. */
export function parseColor(css) {
  const m = /rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+))?\s*\)/.exec(css ?? '');
  return m ? [m[1] / 255, m[2] / 255, m[3] / 255, m[4] === undefined ? 1 : Number(m[4])] : null;
}

function merge(base, over) {
  const out = { ...base };
  for (const [k, v] of Object.entries(over ?? {})) {
    out[k] = v && typeof v === 'object' && !Array.isArray(v) ? merge(base?.[k], v) : v;
  }
  return out;
}

/** A theme JSON (possibly partial, e.g. an old or schematic-only theme) completed with the defaults. */
export function loadTheme(json) {
  return merge(DEFAULT_THEME, typeof json === 'string' ? JSON.parse(json) : json);
}

/** Theme key for a board layer name, e.g. "F.SilkS" → "f_silks", "In3.Cu" → copper.in3, "User.2" → "user_2". */
export function boardKey(layer) {
  if (layer === 'F.Cu') return ['copper', 'f'];
  if (layer === 'B.Cu') return ['copper', 'b'];
  const inner = /^In(\d+)\.Cu$/.exec(layer);
  if (inner) return ['copper', `in${inner[1]}`];
  const user = /^User\.(\d+)$/.exec(layer);
  if (user) return [`user_${user[1]}`];
  if (layer === 'holes') return ['background'];
  return [layer.toLowerCase().replace('.', '_')];
}

export function boardColor(theme, layer) {
  let v = theme.board;
  for (const k of boardKey(layer)) v = v?.[k];
  return parseColor(v) ?? [0.6, 0.6, 0.6, 1];
}

export function schematicColor(theme, key) {
  return parseColor(theme.schematic?.[key]) ?? [0.5, 0.5, 0.5, 1];
}

/** Board layers back to front (as seen from the top). */
export function boardLayerOrder(names) {
  const rank = name => {
    const inner = /^In(\d+)\.Cu$/.exec(name);
    if (inner) return 300 - Number(inner[1]);
    const user = /^User\.(\d+)$/.exec(name);
    if (user) return 700 + Number(user[1]);
    return BOARD_RANK[name] ?? 650;
  };
  return [...names].sort((a, b) => rank(a) - rank(b));
}

const BOARD_RANK = {
  'B.Fab': 100, 'B.CrtYd': 110, 'B.Adhes': 120, 'B.Paste': 130, 'B.SilkS': 140, 'B.Mask': 150, 'B.Cu': 200,
  'F.Cu': 400, 'F.Mask': 450, 'F.Paste': 460, 'F.Adhes': 470, 'F.SilkS': 480, 'F.CrtYd': 490, 'F.Fab': 500,
  'Edge.Cuts': 600, Margin: 610, 'Dwgs.User': 620, 'Cmts.User': 630, 'Eco1.User': 640, 'Eco2.User': 645,
  holes: 1000,
};

/** Schematic layers (named after their theme keys) back to front. */
export const SCHEMATIC_LAYERS = [
  'sheet_background', 'component_body', 'note_background', 'rule_area', 'sheet', 'component_outline', 'notes', 'pin',
  'wire', 'bus', 'bus_entry', 'junction', 'bus_junction', 'no_connect', 'pin_number', 'pin_name',
  'label_local', 'label_global', 'label_hier', 'netclass_flag', 'sheet_label', 'sheet_name', 'sheet_filename',
  'sheet_fields', 'reference', 'value', 'fields', 'dnp_marker',
];

/** Colour key for a schematic layer name (most are theme keys themselves). */
export function schematicKey(layer) {
  return { notes: 'note', bus_entry: 'bus' }[layer] ?? layer;
}
