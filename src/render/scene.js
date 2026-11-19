// Display list ("scene") built from a model: per-layer buffers of simple primitives that both the
// WebGL renderer and the PDF exporter consume.
//
//   segments  [x1, y1, x2, y2, width, item]   round-capped lines; a zero-length segment is a disc
//   triangles [x, y, item] per vertex          small filled polygons, triangulated with earcut
//   fans      {verts: [x, y, ...], item}       large filled polygons (zone fills), filled even-odd
//                                              with the stencil buffer instead of triangulated
//   texts     {str, x, y, rot, h, w, ...}      text drawn with a native font (or stroked, see text.js)
//
// Every primitive belongs to an item (an element of the model). Items carry a stable `key` that the
// diff engine uses to refer to them, plus a bounding box for picking and highlighting.

import earcut from '../../vendor/earcut.js';
import {
  angleOf, apply, arcPoints, circlePoints, emptyBox, extendBox, IDENTITY, isMirrored, multiply, scaleOf,
} from '../geom.js';
import { textCorners } from './text.js';

// Polygons with more vertices than this skip triangulation (earcut gets slow on zone fills).
const LARGE_POLYGON = 256;

export function createScene() {
  const layers = new Map();
  const items = [];
  const byKey = new Map();
  const bbox = emptyBox();
  let m = IDENTITY;
  let k = 1;
  let item = -1;

  function layer(name) {
    let l = layers.get(name);
    if (!l) layers.set(name, (l = { name, segments: [], triangles: [], fans: [], texts: [] }));
    return l;
  }

  function touch(x, y, pad) {
    extendBox(bbox, x, y, pad);
    if (item >= 0) extendBox(items[item].bbox, x, y, pad);
  }

  const scene = {
    layers, items, byKey, bbox,
    errors: [],

    /** Run fn; on failure record the error and keep going (the item drawn so far stays as is). */
    safely(fn, what) {
      try {
        fn();
      } catch (e) {
        scene.errors.push({ what, message: e.message });
      } finally {
        item = -1;
        m = IDENTITY;
        k = 1;
      }
    },

    /** Start a new item; primitives added until endItem() belong to it. */
    beginItem(key, info = {}) {
      item = items.length;
      items.push({ key, ...info, bbox: emptyBox(), layers: new Set() });
      if (key !== undefined) byKey.set(key, item);
      return item;
    },
    endItem() {
      item = -1;
    },

    /** Draw with an extra transform (applied before the current one). */
    withTransform(t, fn) {
      const prev = m;
      const prevK = k;
      m = multiply(m, t);
      k = scaleOf(m);
      try {
        fn();
      } finally {
        m = prev;
        k = prevK;
      }
    },

    get transform() {
      return m;
    },

    segment(name, a, b, width) {
      const [x1, y1] = apply(m, a.x, a.y);
      const [x2, y2] = apply(m, b.x, b.y);
      const w = width * k;
      layer(name).segments.push(x1, y1, x2, y2, w, item);
      touch(x1, y1, w / 2);
      touch(x2, y2, w / 2);
      if (item >= 0) items[item].layers.add(name);
    },

    polyline(name, pts, width, closed = false) {
      for (let i = 1; i < pts.length; i++) scene.segment(name, pts[i - 1], pts[i], width);
      if (closed && pts.length > 2) scene.segment(name, pts[pts.length - 1], pts[0], width);
    },

    /** Filled disc. */
    disc(name, c, r) {
      scene.segment(name, c, c, 2 * r);
    },

    circle(name, c, r, width, filled = false) {
      if (filled) scene.polygon(name, circlePoints(c.x, c.y, r).slice(0, -1));
      if (width > 0 || !filled) scene.polyline(name, circlePoints(c.x, c.y, r), width);
    },

    arc(name, start, mid, end, width) {
      scene.polyline(name, arcPoints(start, mid, end), width);
    },

    /** Filled polygon (possibly concave; first point need not be repeated). Filled even-odd. */
    polygon(name, pts) {
      if (pts.length < 3) return;
      const flat = new Float32Array(2 * pts.length);
      pts.forEach((p, i) => {
        const [x, y] = apply(m, p.x, p.y);
        flat[2 * i] = x;
        flat[2 * i + 1] = y;
        touch(x, y, 0);
      });
      const l = layer(name);
      if (pts.length > LARGE_POLYGON) {
        l.fans.push({ verts: flat, item });
      } else {
        for (const i of earcut(flat)) l.triangles.push(flat[2 * i], flat[2 * i + 1], item);
      }
      if (item >= 0) items[item].layers.add(name);
    },

    /**
     * Text at a model position. `t` = {str, at: {x, y, rot}, h, w, thickness, bold, italic, hj, vj, mirror}.
     * The transform's rotation and mirroring are folded into the record.
     */
    text(name, t) {
      if (!t.str) return;
      const [x, y] = apply(m, t.at.x, t.at.y);
      const rec = { ...t, x, y, rot: (t.at.rot ?? 0) + angleOf(m), h: t.h * k, w: t.w * k, thickness: (t.thickness ?? 0) * k, mirror: !!t.mirror !== isMirrored(m), item };
      delete rec.at;
      layer(name).texts.push(rec);
      for (const p of textCorners(rec)) touch(p.x, p.y, rec.thickness / 2);
      if (item >= 0) items[item].layers.add(name);
    },
  };
  return scene;
}
