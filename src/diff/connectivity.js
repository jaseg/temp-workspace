// Electrical changes between two connectivity graphs (schematic netlists or board routing).
// A graph is {pins: Map<id, {itemKey}>, pinNet: Map<id, net>} with net = {name, pins: id[], wires: key[]}.

import { change } from './util.js';

/** Pair new nets with old nets by largest shared-pin overlap. Returns Map newNet → oldNet. */
function matchNets(oldG, newG) {
  const out = new Map();
  const taken = new Set();
  const candidates = [];
  for (const n of new Set(newG.pinNet.values())) {
    const counts = new Map();
    for (const p of n.pins) {
      const o = oldG.pinNet.get(p);
      if (o) counts.set(o, (counts.get(o) ?? 0) + 1);
    }
    for (const [o, c] of counts) candidates.push([c + (o.name === n.name ? 0.5 : 0), n, o]);
  }
  candidates.sort((a, b) => b[0] - a[0]);
  for (const [, n, o] of candidates) {
    if (out.has(n) || taken.has(o)) continue;
    out.set(n, o);
    taken.add(o);
  }
  return out;
}

const peers = (net, id, common) => (net ? net.pins.filter(p => p !== id && common.has(p)) : []);
const sameSet = (a, b) => a.length === b.length && a.every(x => b.includes(x));

/**
 * Electrical changes: pins that connected, disconnected or moved between nets.
 * `changedWires` = {old: Set, new: Set} of wire/track item keys whose geometry changed, used to
 * highlight the wiring involved. `noun` names what pins belong to ("net", or "routed net" for boards).
 */
export function connectivityChanges(oldG, newG, { changedWires = { old: new Set(), new: new Set() }, pinLabel = id => id, noun = 'net' } = {}) {
  const common = new Set([...oldG.pins.keys()].filter(id => newG.pins.has(id)));
  const matched = matchNets(oldG, newG);
  const groups = new Map();
  for (const id of common) {
    const o = oldG.pinNet.get(id), n = newG.pinNet.get(id);
    const po = peers(o, id, common), pn = peers(n, id, common);
    if (sameSet(po, pn)) continue;
    let op;
    if (!po.length) op = 'connected';
    else if (!pn.length) op = 'disconnected';
    else if (matched.get(n) === o) continue; // the pin stayed; other pins joined or left this net
    else op = 'moved';
    // Group pins that changed the same way: by the net left, the net joined, or both.
    const key = `${op}\u0000${op === 'connected' ? '' : o?.name}\u0000${op === 'disconnected' ? '' : n?.name}`;
    if (!groups.has(key)) groups.set(key, { op, from: o, to: n, pins: [] });
    groups.get(key).pins.push(id);
  }

  const out = [];
  for (const g of groups.values()) {
    const names = g.pins.map(pinLabel);
    const list = names.length > 6 ? `${names.slice(0, 6).join(', ')} and ${names.length - 6} more` : names.join(', ');
    const subject = g.pins.length === 1 ? names[0] : `${g.pins.length} pins`;
    const summary =
      g.op === 'connected' ? `${subject} connected to ${noun} ${g.to.name}` :
      g.op === 'disconnected' ? `${subject} disconnected from ${noun} ${g.from.name}` :
      g.from.name === g.to.name ? `${subject} split off from ${noun} ${g.from.name}` :
      `${subject} moved from ${noun} ${g.from.name} to ${noun} ${g.to.name}`;
    const wires = (net, side) => (net?.wires ?? []).filter(w => changedWires[side].has(w));
    out.push(change('electrical', g.op === 'connected' ? 'added' : g.op === 'disconnected' ? 'removed' : 'modified', subject, summary, {
      details: g.pins.length > 1 ? [list] : [],
      old: [...g.pins.map(p => oldG.pins.get(p).itemKey), ...wires(g.from, 'old')],
      new: [...g.pins.map(p => newG.pins.get(p).itemKey), ...wires(g.to, 'new')],
      net: g.op === 'disconnected' ? g.from.name : g.to.name,
    }));
  }

  // Renamed nets with unchanged members.
  for (const [n, o] of matched) {
    if (n.name !== o.name && n.named && o.named && sameSet(o.pins.filter(p => common.has(p)), n.pins.filter(p => common.has(p)))) {
      out.push(change('electrical', 'modified', `net ${n.name}`, `Net ${o.name} renamed to ${n.name}`, { minor: true, old: o.wires, new: n.wires, net: n.name }));
    }
  }
  return out;
}

/** Group item keys of changed wiring by net, for "rerouted" layout changes. */
export function reroutes(changedWires, oldNetOf, newNetOf) {
  const byNet = new Map();
  for (const [side, netOf] of [['old', oldNetOf], ['new', newNetOf]]) {
    for (const key of changedWires[side]) {
      const name = netOf(key)?.name ?? '';
      if (!byNet.has(name)) byNet.set(name, { old: [], new: [] });
      byNet.get(name)[side].push(key);
    }
  }
  return byNet;
}
