// Annotations: freehand lines, rectangles, ellipses and text notes drawn on top of the diff.
// They are stored in model coordinates (mm), so they stay in place when zooming and can be
// exported as JSON or embedded into a PDF.
//
//   {type: 'pen', points: [{x, y}], color, width}
//   {type: 'rect' | 'ellipse', x0, y0, x1, y1, color, width}
//   {type: 'text', x, y, text, size, color}

export const FORMAT = 'kicad-diff-annotations';

export const TOOLS = [
  ['pen', '✎', 'Freehand'],
  ['rect', '▭', 'Rectangle'],
  ['ellipse', '◯', 'Ellipse'],
  ['text', 'T', 'Text note'],
  ['erase', '⌫', 'Erase'],
];

/** Bounding box of an annotation in model coordinates. */
export function annotationBox(a) {
  if (a.type === 'pen') {
    const xs = a.points.map(p => p.x), ys = a.points.map(p => p.y);
    return { x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) };
  }
  if (a.type === 'text') return { x0: a.x, y0: a.y - a.size, x1: a.x + a.size * 0.6 * a.text.length, y1: a.y };
  return { x0: Math.min(a.x0, a.x1), y0: Math.min(a.y0, a.y1), x1: Math.max(a.x0, a.x1), y1: Math.max(a.y0, a.y1) };
}

/** Topmost annotation within `tol` model units of a point. */
export function hitAnnotation(list, p, tol) {
  for (let i = list.length - 1; i >= 0; i--) {
    const b = annotationBox(list[i]);
    if (p.x >= b.x0 - tol && p.x <= b.x1 + tol && p.y >= b.y0 - tol && p.y <= b.y1 + tol) return i;
  }
  return -1;
}

const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

/** SVG markup of annotations in screen coordinates. `toScreen(x, y)` maps model → px; `scale` is px per mm. */
export function annotationsSvg(list, toScreen, scale) {
  return list.map(a => {
    const w = Math.max(1, a.width * scale);
    const stroke = `fill="none" stroke="${esc(a.color)}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"`;
    if (a.type === 'pen') return `<polyline points="${a.points.map(p => Object.values(toScreen(p.x, p.y)).join(',')).join(' ')}" ${stroke}/>`;
    if (a.type === 'text') {
      const p = toScreen(a.x, a.y);
      return `<text x="${p.x}" y="${p.y}" fill="${esc(a.color)}" font-size="${a.size * scale}" font-family="system-ui, sans-serif" font-weight="600">${esc(a.text)}</text>`;
    }
    const p = toScreen(Math.min(a.x0, a.x1), Math.min(a.y0, a.y1));
    const q = toScreen(Math.max(a.x0, a.x1), Math.max(a.y0, a.y1));
    if (a.type === 'rect') return `<rect x="${p.x}" y="${p.y}" width="${q.x - p.x}" height="${q.y - p.y}" ${stroke}/>`;
    return `<ellipse cx="${(p.x + q.x) / 2}" cy="${(p.y + q.y) / 2}" rx="${(q.x - p.x) / 2}" ry="${(q.y - p.y) / 2}" ${stroke}/>`;
  }).join('');
}

async function sha256(text) {
  try {
    const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
    return [...new Uint8Array(hash)].map(b => b.toString(16).padStart(2, '0')).join('');
  } catch {
    return undefined; // not available outside secure contexts
  }
}

/** Export document: annotations plus which files (by name and content hash) they belong to. */
export async function exportAnnotations(list, sources, extra = {}) {
  const file = async s => s && { name: s.name, sha256: await sha256(s.text) };
  return {
    format: FORMAT,
    version: 1,
    created: new Date().toISOString(),
    files: { old: await file(sources?.old), new: await file(sources?.new) },
    ...extra,
    annotations: list,
  };
}

/**
 * Read an exported document. Returns {annotations, warning} where warning notes a mismatch
 * between the files the annotations were made for and the files shown now.
 */
export async function importAnnotations(json, sources) {
  const doc = typeof json === 'string' ? JSON.parse(json) : json;
  if (doc?.format !== FORMAT || !Array.isArray(doc.annotations)) throw new Error('Not a kicad-diff annotations file');
  let warning = '';
  for (const side of ['old', 'new']) {
    const want = doc.files?.[side]?.sha256;
    const have = sources?.[side] && (await sha256(sources[side].text));
    if (want && have && want !== have) warning = 'These annotations were made for different versions of the files.';
  }
  return { annotations: doc.annotations, warning };
}
