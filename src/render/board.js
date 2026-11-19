// Board (.kicad_pcb) and footprint (.kicad_mod) rendering into a scene.
// Layers are KiCad layer names ("F.Cu", "B.SilkS", ...) plus the pseudo-layer "holes".

import { angleOf, bezierPoints, flattenPts, rotate, scale, translate } from '../geom.js';
import { strokeText } from './text.js';
import { fieldKey, itemKey, padKey } from '../kicad/keys.js';

export const HOLES = 'holes';

/** Copper layer names, front to back. */
export function copperLayers(model) {
  const names = (model.layers ?? []).filter(l => /\.Cu$/.test(l.name)).map(l => l.name);
  return names.length ? sortCopper(names) : ['F.Cu', 'B.Cu'];
}

function sortCopper(names) {
  const rank = n => (n === 'F.Cu' ? -1 : n === 'B.Cu' ? 1e6 : Number(/In(\d+)/.exec(n)?.[1] ?? 1e5));
  return [...names].sort((a, b) => rank(a) - rank(b));
}

/** Expand layer wildcards of pads: "*.Cu", "F&B.Cu", "*.Mask". */
function expandLayers(layers, copper) {
  const out = new Set();
  for (const l of layers) {
    if (l === '*.Cu') copper.forEach(c => out.add(c));
    else if (l.startsWith('*.')) ['F', 'B'].forEach(s => out.add(`${s}.${l.slice(2)}`));
    else if (l.startsWith('F&B.')) ['F', 'B'].forEach(s => out.add(`${s}.${l.slice(4)}`));
    else out.add(l);
  }
  return [...out];
}

const isSilk = layer => /\.SilkS$/.test(layer);

// Pad outlines in pad-local coordinates --------------------------------------------------------

function roundRect(w, h, r) {
  r = Math.min(r, w / 2, h / 2);
  if (r <= 0) return [{ x: -w / 2, y: -h / 2 }, { x: w / 2, y: -h / 2 }, { x: w / 2, y: h / 2 }, { x: -w / 2, y: h / 2 }];
  const out = [];
  const corners = [[w / 2 - r, h / 2 - r, 0], [-w / 2 + r, h / 2 - r, 90], [-w / 2 + r, -h / 2 + r, 180], [w / 2 - r, -h / 2 + r, 270]];
  for (const [cx, cy, a0] of corners) {
    for (let i = 0; i <= 6; i++) {
      const a = ((a0 + (90 * i) / 6) * Math.PI) / 180;
      out.push({ x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) });
    }
  }
  return out;
}

function chamferRect(w, h, size, corners) {
  const c = name => (corners.includes(name) ? size : 0);
  const tl = c('top_left'), tr = c('top_right'), br = c('bottom_right'), bl = c('bottom_left');
  return [
    { x: -w / 2 + tl, y: -h / 2 }, { x: w / 2 - tr, y: -h / 2 }, { x: w / 2, y: -h / 2 + tr }, { x: w / 2, y: h / 2 - br },
    { x: w / 2 - br, y: h / 2 }, { x: -w / 2 + bl, y: h / 2 }, { x: -w / 2, y: h / 2 - bl }, { x: -w / 2, y: -h / 2 + tl },
  ];
}

function trapezoid(w, h, d) {
  const dx = (d?.x ?? 0) / 2, dy = (d?.y ?? 0) / 2;
  return [
    { x: -w / 2 - dy, y: h / 2 + dx }, { x: w / 2 + dy, y: h / 2 - dx },
    { x: w / 2 - dy, y: -h / 2 + dx }, { x: -w / 2 + dy, y: -h / 2 - dx },
  ];
}

/** Draw a pad's copper shape on one layer, in pad-local coordinates. */
function padShape(scene, layer, pad, shape = pad.shape) {
  const { w, h } = pad.size;
  switch (shape) {
    case 'circle':
      return scene.disc(layer, { x: 0, y: 0 }, w / 2);
    case 'oval':
      return w > h
        ? scene.segment(layer, { x: -(w - h) / 2, y: 0 }, { x: (w - h) / 2, y: 0 }, h)
        : scene.segment(layer, { x: 0, y: -(h - w) / 2 }, { x: 0, y: (h - w) / 2 }, w);
    case 'roundrect':
      return pad.chamfer.length && pad.chamferRatio
        ? scene.polygon(layer, chamferRect(w, h, pad.chamferRatio * Math.min(w, h), pad.chamfer))
        : scene.polygon(layer, roundRect(w, h, pad.roundrectRatio * Math.min(w, h)));
    case 'chamfered_rect':
      return scene.polygon(layer, chamferRect(w, h, pad.chamferRatio * Math.min(w, h), pad.chamfer));
    case 'trapezoid':
      return scene.polygon(layer, trapezoid(w, h, pad.rectDelta));
    case 'custom':
      padShape(scene, layer, pad, pad.anchor ?? 'rect');
      for (const g of pad.primitives) graphic(scene, { ...g, fill: g.fill === 'none' && g.type === 'poly' ? 'solid' : g.fill }, layer);
      return;
    default:
      return scene.polygon(layer, roundRect(w, h, 0));
  }
}

function drill(scene, d) {
  if (!d || !d.w) return;
  const o = d.offset ?? { x: 0, y: 0 };
  if (d.oval && d.w !== d.h) {
    const long = Math.max(d.w, d.h), short = Math.min(d.w, d.h);
    const a = d.w > d.h ? { x: (long - short) / 2, y: 0 } : { x: 0, y: (long - short) / 2 };
    scene.segment(HOLES, { x: o.x - a.x, y: o.y - a.y }, { x: o.x + a.x, y: o.y + a.y }, short);
  } else {
    scene.disc(HOLES, o, d.w / 2);
  }
}

function renderPad(scene, pad, copper) {
  scene.withTransform(translate(pad.at.x, pad.at.y), () => {
    scene.withTransform(rotate(pad.at.rot), () => {
      for (const layer of expandLayers(pad.layers, copper)) padShape(scene, layer, pad);
      drill(scene, pad.drill);
    });
  });
}

// Graphics and text -----------------------------------------------------------------------------

/** gr_*, fp_* and pad primitives. `layer` overrides the item's own layer (pad primitives). */
export function graphic(scene, g, layer = g.layer) {
  const w = g.width ?? 0;
  const filled = g.fill === 'solid' || g.fill === 'yes';
  switch (g.type) {
    case 'line':
      return scene.segment(layer, g.start, g.end, w);
    case 'rect': {
      const pts = [g.start, { x: g.end.x, y: g.start.y }, g.end, { x: g.start.x, y: g.end.y }];
      if (filled) scene.polygon(layer, pts);
      if (w > 0 || !filled) scene.polyline(layer, pts, w, true);
      return;
    }
    case 'circle': {
      const r = Math.hypot(g.end.x - g.center.x, g.end.y - g.center.y);
      return scene.circle(layer, g.center, r, w, filled);
    }
    case 'arc':
      return scene.arc(layer, g.start, g.mid, g.end, w);
    case 'poly': {
      const pts = flattenPts(g.pts);
      if (filled) scene.polygon(layer, pts);
      if (w > 0 || !filled) scene.polyline(layer, pts, w, true);
      return;
    }
    case 'curve':
      return g.pts.length === 4 && scene.polyline(layer, bezierPoints(...g.pts), w);
  }
}

/** Board text: stroked Newstroke on silkscreen, native font elsewhere. */
export function boardText(scene, t, upright = false) {
  if (t.hide || !t.text) return;
  const e = t.effects;
  let rot = t.at.rot;
  let { h: hj, v: vj } = e.justify;
  // Footprint text is kept readable: flip text that would read upside down.
  const total = (((rot + angleOf(scene.transform)) % 360) + 360) % 360;
  if (upright && total > 90 && total <= 270) {
    rot += 180;
    hj = hj === 'left' ? 'right' : hj === 'right' ? 'left' : hj;
    vj = vj === 'top' ? 'bottom' : vj === 'bottom' ? 'top' : vj;
  }
  const rec = {
    str: t.text, at: { ...t.at, rot }, h: e.size.h, w: e.size.w,
    thickness: e.thickness ?? e.size.h / (e.bold ? 5 : 8), bold: e.bold, italic: e.italic, hj, vj, mirror: e.justify.mirror,
  };
  if (!isSilk(t.layer)) return scene.text(t.layer, rec);
  // Stroke text: lay out in model space through the scene transform by drawing polylines.
  for (const line of strokeText({ ...rec, x: t.at.x, y: t.at.y, rot })) scene.polyline(t.layer, line, rec.thickness);
}

// Items ----------------------------------------------------------------------------------------

/** Expand text variables like ${REFERENCE} from the footprint's own properties. */
function expandVars(text, fp) {
  return text.replace(/\$\{(\w+)\}/g, (all, name) => fp.properties.find(p => p.name.toUpperCase() === name)?.value ?? all);
}

export function renderFootprint(scene, fp, key, copper) {
  const fpTransform = [translate(fp.at.x, fp.at.y), rotate(fp.at.rot), scale(fp.at.scale?.x ?? 1, fp.at.scale?.y ?? 1)];
  const ref = fp.properties.find(p => p.name === 'Reference')?.value;
  const withFp = fn => scene.withTransform(fpTransform[0], () => scene.withTransform(fpTransform[1], () => scene.withTransform(fpTransform[2], fn)));
  withFp(() => {
    scene.beginItem(key, { kind: 'footprint', ref });
    fp.graphics.forEach(g => graphic(scene, g));
    fp.textBoxes.forEach(t => boardText(scene, { ...t, at: { ...t.start, rot: t.angle } }));
    fp.texts.forEach(t => boardText(scene, { ...t, text: expandVars(t.text, fp) }, true));
    fp.zones.forEach(z => zone(scene, z));
    fp.dimensions.forEach(d => dimension(scene, d));
    scene.endItem();
    fp.properties.forEach(p => {
      if (p.hide || !p.layer) return;
      scene.beginItem(fieldKey(key, p.name), { kind: 'field', ref, field: p.name, parent: key });
      boardText(scene, { ...p, text: expandVars(p.value, fp) }, true);
      scene.endItem();
    });
    fp.pads.forEach((pad, i) => {
      scene.beginItem(padKey(key, pad, i), { kind: 'pad', ref, pad: pad.number, net: pad.net, parent: key });
      renderPad(scene, pad, copper);
      scene.endItem();
    });
  });
}

function track(scene, t) {
  if (t.mid) scene.arc(t.layer, t.start, t.mid, t.end, t.width);
  else scene.segment(t.layer, t.start, t.end, t.width);
}

function via(scene, v, copper) {
  const [top, bottom] = v.layers.length === 2 ? v.layers : ['F.Cu', 'B.Cu'];
  const i0 = copper.indexOf(top), i1 = copper.indexOf(bottom);
  const span = i0 >= 0 && i1 >= 0 ? copper.slice(Math.min(i0, i1), Math.max(i0, i1) + 1) : copper;
  for (const l of span) scene.disc(l, v.at, v.size / 2);
  scene.disc(HOLES, v.at, v.drill / 2);
}

function zone(scene, z) {
  for (const f of z.filled) scene.polygon(f.layer, flattenPts(f.pts));
  for (const outline of z.outline) {
    const pts = flattenPts(outline);
    for (const l of z.layers) if (!l.includes('*')) scene.polyline(l, pts, 0.05, true);
  }
}

function dimension(scene, d) {
  if (d.pts.length >= 2) scene.polyline(d.layer, flattenPts(d.pts), d.text?.effects.thickness ?? 0.1);
  if (d.text) boardText(scene, d.text);
}

/** Render a board model. */
export function renderBoard(scene, model) {
  const copper = copperLayers(model);
  model.items.forEach((it, i) => scene.safely(() => boardItem(scene, it, i, copper), it.type));
  return scene;
}

function boardItem(scene, it, i, copper) {
  const key = itemKey(it, i);
  switch (it.type) {
    case 'footprint':
      return renderFootprint(scene, it, key, copper);
    case 'track':
      scene.beginItem(key, { kind: 'track', net: it.net, layer: it.layer });
      track(scene, it);
      return scene.endItem();
    case 'via':
      scene.beginItem(key, { kind: 'via', net: it.net });
      via(scene, it, copper);
      return scene.endItem();
    case 'zone':
      scene.beginItem(key, { kind: 'zone', net: it.net, name: it.name });
      zone(scene, it);
      return scene.endItem();
    case 'text':
      scene.beginItem(key, { kind: 'text' });
      boardText(scene, it);
      return scene.endItem();
    case 'text_box':
      scene.beginItem(key, { kind: 'text' });
      boardText(scene, { ...it, at: { ...it.start, rot: it.angle } });
      if (it.border && it.start && it.end) graphic(scene, { type: 'rect', start: it.start, end: it.end, width: it.width, layer: it.layer });
      return scene.endItem();
    case 'dimension':
      scene.beginItem(key, { kind: 'dimension' });
      dimension(scene, it);
      return scene.endItem();
    case 'line': case 'rect': case 'circle': case 'arc': case 'poly': case 'curve':
      scene.beginItem(key, { kind: 'graphic', layer: it.layer });
      graphic(scene, it);
      return scene.endItem();
  }
}

/** Render a footprint file (.kicad_mod) at the origin. */
export function renderFootprintFile(scene, model) {
  renderFootprint(scene, { ...model, at: { x: 0, y: 0, rot: 0, scale: { x: 1, y: 1 } } }, model.uuid ?? 'footprint', ['F.Cu', 'B.Cu']);
  return scene;
}

