// Connectivity of one schematic sheet, following KiCad's rules:
// - a wire connects its end points; a wire end touching another wire's interior joins it (T)
// - junctions join everything at their point, including wire interiors
// - pins connect at wire ends, other pins, junctions; labels connect anywhere on a wire
// - labels with the same name are one net (local within the sheet; global/power everywhere)
// Hierarchical connections to other sheets are represented by their names only.

import { findDef, placedPins, referenceOf } from '../kicad/place.js';
import { itemKey, pinKey } from '../kicad/keys.js';
import { segmentDistance } from '../geom.js';

const EPS = 1e-4;
const ptKey = p => `${Math.round(p.x * 1e4)},${Math.round(p.y * 1e4)}`;

function unionFind() {
  const parent = new Map();
  const find = a => {
    let r = a;
    while (parent.has(r) && parent.get(r) !== r) r = parent.get(r);
    let x = a;
    while (parent.has(x) && parent.get(x) !== r) {
      const next = parent.get(x);
      parent.set(x, r);
      x = next;
    }
    if (!parent.has(r)) parent.set(r, r);
    return r;
  };
  const union = (a, b) => {
    const ra = find(a), rb = find(b);
    if (ra !== rb) parent.set(ra, rb);
  };
  return { find, union, nodes: () => parent.keys() };
}

/** Grid of segments for "which segments pass through this point" queries. */
function segmentGrid(segs, cell = 5) {
  const grid = new Map();
  const cellKey = (i, j) => `${i},${j}`;
  for (const s of segs) {
    const [i0, i1] = [Math.floor(Math.min(s.a.x, s.b.x) / cell), Math.floor(Math.max(s.a.x, s.b.x) / cell)];
    const [j0, j1] = [Math.floor(Math.min(s.a.y, s.b.y) / cell), Math.floor(Math.max(s.a.y, s.b.y) / cell)];
    for (let i = i0; i <= i1; i++) for (let j = j0; j <= j1; j++) {
      const k = cellKey(i, j);
      if (!grid.has(k)) grid.set(k, []);
      grid.get(k).push(s);
    }
  }
  return p => (grid.get(cellKey(Math.floor(p.x / cell), Math.floor(p.y / cell))) ?? []).filter(s => segmentDistance(p.x, p.y, s.a.x, s.a.y, s.b.x, s.b.y) < EPS);
}

const naturalCompare = (a, b) => a.localeCompare(b, undefined, { numeric: true });

/**
 * @returns {{nets: object[], pinNet: Map<string, object>, pins: Map<string, object>, wireNet: Map<string, object>}}
 *   pins are identified as "REF.NUMBER"; nets have {name, pins: string[], wires: string[] (item keys), named}
 */
export function schematicNetlist(sch) {
  const uf = unionFind();
  const segs = [];
  sch.items.forEach((it, i) => {
    if (it.type !== 'wire') return;
    const key = itemKey(it, i);
    for (let k = 1; k < it.pts.length; k++) segs.push({ a: it.pts[k - 1], b: it.pts[k], key });
    for (const p of it.pts) uf.union('w:' + key, 'p:' + ptKey(p));
  });
  const onWire = segmentGrid(segs);
  const joinWiresAt = p => onWire(p).forEach(s => uf.union('p:' + ptKey(p), 'w:' + s.key));

  // Wire ends touching other wires' interiors, and junctions.
  for (const s of segs) joinWiresAt(s.a), joinWiresAt(s.b);
  for (const it of sch.items) if (it.type === 'junction') joinWiresAt(it.at);

  const labels = [];
  const ncPoints = new Set();
  const pins = new Map();
  // Symbols sharing a reference (e.g. unannotated "R?") are told apart by position.
  const refCount = new Map();
  for (const it of sch.items) if (it.type === 'symbol') refCount.set(`${referenceOf(it)}|${it.unit}`, (refCount.get(`${referenceOf(it)}|${it.unit}`) ?? 0) + 1);
  sch.items.forEach((it, i) => {
    const key = itemKey(it, i);
    switch (it.type) {
      case 'label': case 'hierarchical_label': case 'global_label': {
        joinWiresAt(it.at);
        const scope = it.type === 'global_label' ? 'g:' : 'l:';
        uf.union('p:' + ptKey(it.at), scope + it.text);
        labels.push({ name: it.text, type: it.type, node: 'p:' + ptKey(it.at), key });
        break;
      }
      case 'no_connect':
        ncPoints.add(ptKey(it.at));
        break;
      case 'sheet':
        for (const p of it.pins) {
          uf.union('p:' + ptKey(p.at), `sheet:${key}:${p.name}`);
          labels.push({ name: `${it.properties.find(f => /^Sheet ?name$/i.test(f.name))?.value ?? 'sheet'}/${p.name}`, type: 'sheet_pin', node: 'p:' + ptKey(p.at), key });
        }
        break;
      case 'symbol': {
        const def = findDef(sch, it);
        if (!def) break;
        const ref = refCount.get(`${referenceOf(it)}|${it.unit}`) > 1 ? `${referenceOf(it)}@(${it.at.x}, ${it.at.y})` : referenceOf(it);
        const value = it.properties.find(p => p.name === 'Value')?.value;
        for (const p of placedPins(def, it)) {
          const at = 'p:' + ptKey(p.tip);
          if (def.power) {
            // Power symbols name a global net (local power symbols only within the sheet).
            uf.union(at, (def.power === 'local' ? 'l:' : 'g:') + value);
            labels.push({ name: value, type: 'power', node: at, key });
            continue;
          }
          if (ref.startsWith('#')) continue; // virtual symbols (power flags) are not part of the netlist
          const id = `${ref}.${p.number}`;
          pins.set(id, { id, ref, number: p.number, name: p.name, symbolKey: key, itemKey: pinKey(key, p.number), node: at, nc: ncPoints.has(ptKey(p.tip)), pos: p.tip });
          uf.union('pin:' + id, at);
          // Hidden power input pins connect to the global net named after the pin (legacy libraries).
          if (p.pin.hide && p.etype === 'power_in') uf.union(at, 'g:' + p.name);
        }
        break;
      }
    }
  });
  for (const p of pins.values()) p.nc ||= ncPoints.has(p.node.slice(2));

  // Collect nets.
  const byRoot = new Map();
  const net = root => {
    if (!byRoot.has(root)) byRoot.set(root, { pins: [], wires: [], labels: [] });
    return byRoot.get(root);
  };
  for (const p of pins.values()) net(uf.find('pin:' + p.id)).pins.push(p.id);
  for (const s of segs) {
    const n = net(uf.find('w:' + s.key));
    if (!n.wires.includes(s.key)) n.wires.push(s.key);
  }
  for (const l of labels) net(uf.find(l.node)).labels.push(l);

  const RANK = { power: 0, global_label: 1, label: 2, hierarchical_label: 3, sheet_pin: 4 };
  const nets = [];
  const pinNet = new Map();
  const wireNet = new Map();
  for (const n of byRoot.values()) {
    if (!n.pins.length && !n.labels.length) continue;
    n.pins.sort(naturalCompare);
    const best = [...n.labels].sort((a, b) => RANK[a.type] - RANK[b.type] || naturalCompare(a.name, b.name))[0];
    const first = n.pins[0] && pins.get(n.pins[0]);
    n.named = !!best;
    n.name = best ? best.name : n.pins.length === 1 ? `unconnected-(${first.ref}-Pad${first.number})` : `Net-(${first.ref}-Pad${first.number})`;
    nets.push(n);
    for (const p of n.pins) pinNet.set(p, n);
    for (const w of n.wires) wireNet.set(w, n);
  }
  return { nets, pins, pinNet, wireNet };
}
