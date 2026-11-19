// Highlighting changes: toned-down base colours, extraction of the primitives of changed items into
// highlight scenes, and change areas.

import { createScene } from '../render/scene.js';
import { emptyBox, isEmptyBox, padBox, unionBox } from '../geom.js';

/** Highlight colours per change kind, for light and dark canvas backgrounds. */
export const PALETTE = {
  light: { electrical: [0.86, 0.04, 0.45, 1], metadata: [0.85, 0.45, 0, 1], layout: [0.05, 0.55, 0.7, 1] },
  dark: { electrical: [1, 0.3, 0.65, 1], metadata: [1, 0.72, 0.15, 1], layout: [0.3, 0.8, 0.95, 1] },
};

export const isDark = bg => 0.2126 * bg[0] + 0.7152 * bg[1] + 0.0722 * bg[2] < 0.5;

/** Tone a colour down: desaturate and mix it towards the background by k (0..1). */
export function tone(c, bg, k) {
  const gray = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  return [0, 1, 2].map(i => {
    const desat = c[i] + (gray - c[i]) * Math.min(1, k * 0.8);
    return desat + (bg[i] - desat) * k;
  }).concat(c[3]);
}

/** Copy the primitives of the given items (scene item indices) into a new scene, all on one layer. */
export function extract(scene, indices, layerName = 'hl') {
  const out = createScene();
  const l = { name: layerName, segments: [], triangles: [], fans: [], texts: [] };
  out.layers.set(layerName, l);
  if (!indices.size) return out;
  for (const src of scene.layers.values()) {
    for (let i = 0; i < src.segments.length; i += 6) if (indices.has(src.segments[i + 5])) l.segments.push(...src.segments.slice(i, i + 6));
    for (let i = 0; i < src.triangles.length; i += 9) if (indices.has(src.triangles[i + 2])) l.triangles.push(...src.triangles.slice(i, i + 9));
    for (const f of src.fans) if (indices.has(f.item)) l.fans.push(f);
    for (const t of src.texts) if (indices.has(t.item)) l.texts.push(t);
  }
  return out;
}

/** key → item indices, where a parent key (symbol, footprint) also covers its pins and pads. */
function keyIndex(scene) {
  if (scene.keyIndex) return scene.keyIndex;
  const index = new Map();
  const add = (k, i) => (index.get(k) ?? index.set(k, []).get(k)).push(i);
  scene.items.forEach((it, i) => {
    if (it.key !== undefined) add(it.key, i);
    if (it.parent !== undefined && it.kind !== 'field') add(it.parent, i);
  });
  return (scene.keyIndex = index);
}

/** Scene item indices for a change's keys. */
export function itemIndices(scene, keys) {
  const set = new Set();
  if (!scene) return set;
  const index = keyIndex(scene);
  for (const k of keys) for (const i of index.get(k) ?? []) set.add(i);
  return set;
}

/** Bounding box of a change's items in both versions (null if it has no geometry, e.g. settings). */
export function changeArea(change, scenes) {
  let box = emptyBox();
  for (const [side, keys] of [['old', change.old], ['new', change.new]]) {
    const scene = scenes[side];
    if (!scene) continue;
    for (const i of itemIndices(scene, keys)) box = unionBox(box, scene.items[i].bbox);
  }
  if (isEmptyBox(box)) return null;
  const size = Math.max(box.x1 - box.x0, box.y1 - box.y0);
  return padBox(box, Math.max(1, size * 0.15));
}
