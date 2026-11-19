// Routed copper connectivity of a board: which pads are joined by tracks, vias and zone fills.
// Pads are identified as "REF.NUMBER" (with "#2", "#3"... for repeated pad numbers).

import { apply, flattenPts, multiply, rotate, scale, segmentDistance, translate } from '../geom.js';
import { copperLayers } from '../render/board.js';
import { itemKey, padKey } from '../kicad/keys.js';

function unionFind() {
  const parent = new Map();
  const find = a => {
    if (!parent.has(a)) parent.set(a, a);
    let r = a;
    while (parent.get(r) !== r) r = parent.get(r);
    while (parent.get(a) !== r) {
      const n = parent.get(a);
      parent.set(a, r);
      a = n;
    }
    return r;
  };
  return { find, union: (a, b) => parent.set(find(a), find(b)) };
}

/** Point-in-polygon with edges bucketed into horizontal bands (zone fills have 100k+ vertices). */
function polygonTester(pts) {
  let y0 = Infinity, y1 = -Infinity, x0 = Infinity, x1 = -Infinity;
  for (const p of pts) (y0 = Math.min(y0, p.y)), (y1 = Math.max(y1, p.y)), (x0 = Math.min(x0, p.x)), (x1 = Math.max(x1, p.x));
  const bands = Math.max(1, Math.min(1024, Math.ceil(pts.length / 64)));
  const h = (y1 - y0) / bands || 1;
  const buckets = Array.from({ length: bands }, () => []);
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[(i + 1) % pts.length];
    const lo = Math.max(0, Math.floor((Math.min(a.y, b.y) - y0) / h)), hi = Math.min(bands - 1, Math.floor((Math.max(a.y, b.y) - y0) / h));
    for (let k = lo; k <= hi; k++) buckets[k].push(a, b);
  }
  return (x, y) => {
    if (x < x0 || x > x1 || y < y0 || y > y1) return false;
    const edges = buckets[Math.min(bands - 1, Math.floor((y - y0) / h))];
    let inside = false;
    for (let i = 0; i < edges.length; i += 2) {
      const a = edges[i], b = edges[i + 1];
      if (a.y > y !== b.y > y && x < ((b.x - a.x) * (y - a.y)) / (b.y - a.y) + a.x) inside = !inside;
    }
    return inside;
  };
}

/** Spatial hash of anchors (points with a reach) per layer. */
function anchorIndex(cell = 2) {
  const grid = new Map();
  const list = [];
  const add = (layer, a) => {
    a.layer = layer;
    list.push(a);
    const r = a.r ?? 0;
    for (let i = Math.floor((a.x - r) / cell); i <= Math.floor((a.x + r) / cell); i++) {
      for (let j = Math.floor((a.y - r) / cell); j <= Math.floor((a.y + r) / cell); j++) {
        const k = `${layer}|${i}|${j}`;
        if (!grid.has(k)) grid.set(k, []);
        grid.get(k).push(a);
      }
    }
  };
  const near = (layer, x, y) => grid.get(`${layer}|${Math.floor(x / cell)}|${Math.floor(y / cell)}`) ?? [];
  return { add, near, list };
}

const footprintTransform = fp => multiply(translate(fp.at.x, fp.at.y), multiply(rotate(fp.at.rot), scale(fp.at.scale?.x ?? 1, fp.at.scale?.y ?? 1)));

export function boardRouting(board) {
  const copper = copperLayers(board);
  const isCopper = l => copper.includes(l);
  const expand = layers => [...new Set(layers.flatMap(l => (l === '*.Cu' ? copper : l === 'F&B.Cu' ? ['F.Cu', 'B.Cu'] : [l])))].filter(isCopper);
  const uf = unionFind();
  const anchors = anchorIndex();
  const pins = new Map();
  const padNet = new Map();

  // Pads are named REF.NUMBER; footprints sharing a reference are told apart by position.
  const refOf = fp => fp.properties.find(p => p.name === 'Reference')?.value ?? '?';
  const refCount = new Map();
  for (const it of board.items) if (it.type === 'footprint') refCount.set(refOf(it), (refCount.get(refOf(it)) ?? 0) + 1);

  board.items.forEach((it, i) => {
    const key = itemKey(it, i);
    if (it.type === 'footprint') {
      const ref = refCount.get(refOf(it)) > 1 ? `${refOf(it)}@(${it.at.x}, ${it.at.y})` : refOf(it);
      const m = footprintTransform(it);
      const seen = new Map();
      it.pads.forEach((pad, k) => {
        if (pad.kind === 'np_thru_hole' || !pad.number) return;
        const n = (seen.get(pad.number) ?? 0) + 1;
        seen.set(pad.number, n);
        const id = n > 1 ? `${ref}.${pad.number}#${n}` : `${ref}.${pad.number}`;
        const [x, y] = apply(m, pad.at.x, pad.at.y);
        const rot = pad.at.rot + it.at.rot;
        const node = 'pad:' + id;
        pins.set(id, { id, ref, number: pad.number, itemKey: padKey(key, pad, k), node, pos: { x, y } });
        padNet.set(id, pad.net);
        uf.find(node);
        // Pad area: point is inside if within the rotated rectangle (good enough for connectivity).
        const contains = (px, py) => {
          const [lx, ly] = apply(rotate(-rot), px - x, py - y);
          return Math.abs(lx) <= pad.size.w / 2 + 1e-3 && Math.abs(ly) <= pad.size.h / 2 + 1e-3;
        };
        const r = Math.hypot(pad.size.w, pad.size.h) / 2;
        for (const l of expand(pad.layers)) anchors.add(l, { x, y, r, node, contains });
      });
    } else if (it.type === 'track') {
      const node = 'track:' + key;
      const w = it.width / 2;
      const seg = { a: it.start, b: it.end };
      for (const p of [it.start, it.end]) anchors.add(it.layer, { x: p.x, y: p.y, r: w, node, end: true, contains: (px, py) => segmentDistance(px, py, seg.a.x, seg.a.y, seg.b.x, seg.b.y) <= w + 1e-3 });
    } else if (it.type === 'via') {
      const node = 'via:' + key;
      const [top, bottom] = it.layers.length === 2 ? it.layers : ['F.Cu', 'B.Cu'];
      const i0 = copper.indexOf(top), i1 = copper.indexOf(bottom);
      const span = i0 >= 0 && i1 >= 0 ? copper.slice(Math.min(i0, i1), Math.max(i0, i1) + 1) : copper;
      const r = it.size / 2;
      for (const l of span) anchors.add(l, { x: it.at.x, y: it.at.y, r, node, contains: (px, py) => Math.hypot(px - it.at.x, py - it.at.y) <= r + 1e-3 });
    }
  });

  // Track ends, vias and pads join whatever copper they touch on the same layer.
  for (const a of anchors.list) {
    for (const b of anchors.near(a.layer, a.x, a.y)) {
      if (b.node === a.node) continue;
      if (b.contains(a.x, a.y) || (a.contains && a.contains(b.x, b.y))) uf.union(a.node, b.node);
    }
  }

  // Filled zone islands join the pads, vias and track ends inside them.
  board.items.forEach((it, i) => {
    if (it.type !== 'zone' || it.keepout) return;
    it.filled.forEach((f, k) => {
      const inside = polygonTester(flattenPts(f.pts));
      const node = `zone:${itemKey(it, i)}:${k}`;
      for (const a of anchors.list) if (a.layer === f.layer && inside(a.x, a.y)) uf.union(node, a.node);
    });
  });

  // Routed groups: pads sharing a root.
  const groups = new Map();
  for (const p of pins.values()) {
    const root = uf.find(p.node);
    if (!groups.has(root)) groups.set(root, { pins: [], wires: [] });
    groups.get(root).pins.push(p.id);
  }
  board.items.forEach((it, i) => {
    if (it.type !== 'track' && it.type !== 'via') return;
    const key = itemKey(it, i);
    const g = groups.get(uf.find((it.type === 'track' ? 'track:' : 'via:') + key));
    if (g) g.wires.push(key);
  });
  const pinNet = new Map();
  for (const g of groups.values()) {
    g.pins.sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
    g.name = padNet.get(g.pins[0]) || `(unrouted ${g.pins[0]})`;
    g.named = !!padNet.get(g.pins[0]);
    for (const p of g.pins) pinNet.set(p, g);
  }
  return { pins, pinNet, padNet };
}
