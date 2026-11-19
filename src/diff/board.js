// Changes between two versions of a board, and between two footprints.

import { fieldKey, itemKey, padKey } from '../kicad/keys.js';
import { boardRouting } from './netlist-pcb.js';
import { connectivityChanges, reroutes } from './connectivity.js';
import { changedWiring } from './wires.js';
import { canon, change, changedKeys, describeMove, fmtPoint, match, propertyChanges, q, same, sameItems } from './util.js';

const refOf = fp => fp.properties.find(p => p.name === 'Reference')?.value ?? fp.name;

function indexed(model, types) {
  return model.items.map((it, i) => ({ it, key: itemKey(it, i) })).filter(e => types.includes(e.it.type));
}

const PAD_GEOMETRY = ['kind', 'shape', 'size', 'drill', 'layers', 'roundrectRatio', 'chamferRatio', 'chamfer', 'rectDelta', 'primitives', 'anchor'];

/** Compare two footprints (placed or library). `ka`/`kb` are their scene item keys. */
export function footprintChanges(fa, fb, ka, kb, out, { placed = true } = {}) {
  const r = refOf(fb);
  if (placed) {
    const move = describeMove(fa.at, fb.at);
    const flip = fa.layer !== fb.layer ? `flipped to ${fb.layer === 'B.Cu' ? 'back' : 'front'}` : '';
    if (move || flip) out.push(change('layout', 'modified', r, `${r} ${[move, flip].filter(Boolean).join(', ')}`, { minor: !flip, old: [ka], new: [kb] }));
  }
  const meta = [];
  const fo = [], fn = [];
  if (fa.name !== fb.name) meta.push(`Footprint ${fa.name} → ${fb.name}`);
  if (!sameItems(fa.attributes, fb.attributes)) meta.push(`Attributes ${fa.attributes.join(' ') || '(none)'} → ${fb.attributes.join(' ') || '(none)'}`);
  for (const p of propertyChanges(fa.properties, fb.properties)) {
    if (p.op === 'style') continue;
    meta.push(p.text);
    fo.push(fieldKey(ka, p.name));
    fn.push(fieldKey(kb, p.name));
  }
  for (const k of ['descr', 'tags']) if (fa[k] !== fb[k]) meta.push(`${k === 'descr' ? 'Description' : 'Keywords'}: ${q(fa[k])} → ${q(fb[k])}`);
  if (!same(fa.settings, fb.settings) || !same(fa.extra, fb.extra)) meta.push('Other footprint settings changed');
  if (meta.length) out.push(change('metadata', 'modified', r, meta.length === 1 ? `${r} ${meta[0]}` : `${r}: ${meta.length} attributes changed`, { details: meta.length > 1 ? meta : [], old: fo.length ? fo : [ka], new: fn.length ? fn : [kb] }));

  // Pads: numbering and nets are electrical, geometry is layout.
  const pa = fa.pads.map((p, i) => ({ p, key: padKey(ka, p, i) }));
  const pb = fb.pads.map((p, i) => ({ p, key: padKey(kb, p, i) }));
  const pads = match(pa, pb, [e => e.p.uuid, e => `${e.p.number}|${fmtPoint(e.p.at)}`, e => e.p.number || undefined]);
  for (const e of pads.removed) out.push(change('electrical', 'removed', r, `${r} pad ${e.p.number || '(unnumbered)'} removed`, { old: [e.key] }));
  for (const e of pads.added) out.push(change('electrical', 'added', r, `${r} pad ${e.p.number || '(unnumbered)'} added`, { new: [e.key] }));
  for (const [ea, eb] of pads.pairs) {
    const a = ea.p, b = eb.p;
    const sub = `${r} pad ${b.number}`;
    if (a.number !== b.number) out.push(change('electrical', 'modified', sub, `${r} pad ${a.number} renumbered to ${b.number}`, { old: [ea.key], new: [eb.key] }));
    if (placed && a.net !== b.net) out.push(change('electrical', 'modified', sub, `${sub} net ${a.net || '(none)'} → ${b.net || '(none)'}`, { old: [ea.key], new: [eb.key], net: b.net }));
    const geo = PAD_GEOMETRY.filter(k => !same(a[k], b[k]));
    const moved = describeMove(a.at, b.at);
    if (geo.length || moved) out.push(change('layout', 'modified', sub, `${sub} ${[moved, geo.length ? `${geo.join(', ')} changed` : ''].filter(Boolean).join(', ')}`, { old: [ea.key], new: [eb.key] }));
    if (a.pinFunction !== b.pinFunction || a.pinType !== b.pinType) out.push(change('metadata', 'modified', sub, `${sub} pin function ${q(a.pinFunction)} → ${q(b.pinFunction)}`, { minor: true, old: [ea.key], new: [eb.key] }));
    if (!same(a.settings, b.settings)) out.push(change('metadata', 'modified', sub, `${sub} clearances or other settings changed`, { minor: true, old: [ea.key], new: [eb.key] }));
  }

  // Graphics and texts of the footprint: one minor layout change.
  const look = f => [...f.graphics, ...f.texts.map(t => ({ ...t, text: '' })), ...f.textBoxes, ...f.zones, ...f.dimensions];
  if (!sameItems(look(fa), look(fb))) out.push(change('layout', 'modified', r, `${r} footprint graphics changed`, { minor: true, old: [ka], new: [kb] }));
  const texts = f => f.texts.map(t => t.text).sort().join('\n');
  if (texts(fa) !== texts(fb)) out.push(change('metadata', 'modified', r, `${r} footprint text changed`, { minor: true, old: [ka], new: [kb] }));
}

function footprints(a, b, out) {
  const { pairs, removed, added } = match(indexed(a, ['footprint']), indexed(b, ['footprint']), [
    e => e.it.uuid, e => (/\?$/.test(refOf(e.it)) ? undefined : refOf(e.it)), e => `${e.it.name}|${fmtPoint(e.it.at)}`,
  ]);
  for (const e of removed) out.push(change('electrical', 'removed', refOf(e.it), `${refOf(e.it)} removed (${e.it.name})`, { old: [e.key] }));
  for (const e of added) out.push(change('electrical', 'added', refOf(e.it), `${refOf(e.it)} added (${e.it.name})`, { new: [e.key] }));
  for (const [ea, eb] of pairs) footprintChanges(ea.it, eb.it, ea.key, eb.key, out);
}

function zones(a, b, out) {
  const name = e => `Zone${e.it.name ? ' ' + e.it.name : ''}${e.it.net ? ` (${e.it.net})` : e.it.keepout ? ' (rule area)' : ''}`;
  const { pairs, removed, added } = match(indexed(a, ['zone']), indexed(b, ['zone']), [e => e.it.uuid, e => `${e.it.net}|${e.it.layers}|${e.it.name}|${e.it.priority}`]);
  for (const e of removed) out.push(change('layout', 'removed', name(e), `${name(e)} removed`, { old: [e.key] }));
  for (const e of added) out.push(change('layout', 'added', name(e), `${name(e)} added`, { new: [e.key] }));
  for (const [ea, eb] of pairs) {
    const za = ea.it, zb = eb.it;
    const f = { old: [ea.key], new: [eb.key] };
    if (za.net !== zb.net) out.push(change('electrical', 'modified', name(eb), `${name(eb)} net ${za.net || '(none)'} → ${zb.net || '(none)'}`, f));
    if (!same(za.outline, zb.outline) || !same(za.layers, zb.layers)) out.push(change('layout', 'modified', name(eb), `${name(eb)} outline changed`, { minor: true, ...f }));
    else if (!same(za.filled, zb.filled)) out.push(change('layout', 'modified', name(eb), `${name(eb)} fill changed`, { minor: true, ...f }));
    if (!same(za.keepout, zb.keepout) || !same(za.settings, zb.settings) || za.priority !== zb.priority) out.push(change('metadata', 'modified', name(eb), `${name(eb)} settings changed`, { minor: true, ...f }));
  }
}

const OTHER = ['line', 'rect', 'circle', 'arc', 'poly', 'curve', 'text', 'text_box', 'dimension', 'image', 'target', 'table', 'barcode', 'point', 'group', 'drill_chart', 'drill_map', 'grid_item', 'generated'];

function graphics(a, b, out) {
  const { pairs, removed, added } = match(indexed(a, OTHER), indexed(b, OTHER), [e => e.it.uuid, e => canon(e.it)]);
  const isOutline = e => e.it.layer === 'Edge.Cuts';
  const name = e => (isOutline(e) ? 'Board outline' : e.it.text !== undefined ? `Text ${q(e.it.text)}` : `${e.it.type} on ${e.it.layer ?? 'board'}`);
  for (const e of removed) out.push(change('layout', 'removed', name(e), `${name(e)} removed`, { minor: !isOutline(e), old: [e.key] }));
  for (const e of added) out.push(change('layout', 'added', name(e), `${name(e)} added`, { minor: !isOutline(e), new: [e.key] }));
  for (const [ea, eb] of pairs) {
    if (same(ea.it, eb.it)) continue;
    if (ea.it.text !== eb.it.text) out.push(change('metadata', 'modified', name(eb), `Text changed: ${q(ea.it.text)} → ${q(eb.it.text)}`, { old: [ea.key], new: [eb.key] }));
    else out.push(change('layout', 'modified', name(eb), `${name(eb)} changed`, { minor: !isOutline(eb), old: [ea.key], new: [eb.key] }));
  }
}

function boardSettings(a, b, out) {
  const meta = [];
  if (!same(a.layers, b.layers)) meta.push('Layer stack changed');
  if (a.thickness !== b.thickness) meta.push(`Board thickness ${a.thickness} → ${b.thickness} mm`);
  for (const k of changedKeys(a.titleBlock ?? {}, b.titleBlock ?? {})) meta.push(`Title block ${k} changed`);
  for (const p of propertyChanges(a.properties, b.properties)) meta.push(`Board variable ${p.text}`);
  for (const k of changedKeys(a.settings, b.settings)) meta.push(`${k.replace(/_/g, ' ')} settings changed`);
  for (const k of changedKeys(a.extra, b.extra)) meta.push(`Unsupported element ${k} changed`);
  if (meta.length) out.push(change('metadata', 'modified', 'board', meta.length === 1 ? meta[0] : `${meta.length} board settings changed`, { minor: true, details: meta.length > 1 ? meta : [] }));
}

export function diffBoard(a, b) {
  const out = [];
  const segs = model => indexed(model, ['track']).filter(e => !e.it.mid).map(({ it, key }) => ({ a: it.start, b: it.end, key, group: `${it.layer}|${it.width}` }));
  const wiring = changedWiring(segs(a), segs(b));
  // Arc tracks and vias: compared whole.
  const others = model => indexed(model, ['track', 'via']).filter(e => e.it.type === 'via' || e.it.mid);
  const ov = match(others(a), others(b), [e => canon({ ...e.it, net: 0 })]);
  for (const e of ov.removed) wiring.old.add(e.key);
  for (const e of ov.added) wiring.new.add(e.key);

  const ra = boardRouting(a), rb = boardRouting(b);
  const pinLabel = id => id.replace(/^(.*)\.([^.]+)$/, '$1 pad $2');
  const electrical = connectivityChanges(ra, rb, { changedWires: wiring, pinLabel, noun: 'routed net' });
  out.push(...electrical);

  const explained = new Set(electrical.flatMap(c => [...c.old, ...c.new]));
  const left = { old: new Set([...wiring.old].filter(k => !explained.has(k))), new: new Set([...wiring.new].filter(k => !explained.has(k))) };
  const netOf = model => {
    const nets = new Map(indexed(model, ['track', 'via']).map(e => [e.key, { name: e.it.net || '' }]));
    return k => nets.get(k);
  };
  for (const [net, keys] of reroutes(left, netOf(a), netOf(b))) {
    const summary = net ? `Routing of net ${net} changed` : 'Unconnected routing changed';
    out.push(change('layout', 'modified', net ? `net ${net}` : 'routing', summary, { minor: true, old: keys.old, new: keys.new, net }));
  }

  footprints(a, b, out);
  zones(a, b, out);
  graphics(a, b, out);
  boardSettings(a, b, out);
  return out;
}

/** Two .kicad_mod files. */
export function diffFootprint(a, b) {
  const out = [];
  footprintChanges(a, b, a.uuid ?? 'footprint', b.uuid ?? 'footprint', out, { placed: false });
  return out;
}
