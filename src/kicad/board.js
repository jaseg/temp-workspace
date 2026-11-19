// Boards (.kicad_pcb).

import { at, paper, property, rest, settings, titleBlock, uuid } from './common.js';
import { child, children, flag, hasAtom, num, numOf, readAll, str, strOf, text, xy } from './read.js';
import {
  GRAPHICS, layersOf, netOf, readBoardText, readBoardTextBox, readDimension, readFootprint, readGraphic, readZone,
} from './footprint.js';

/** (layers (0 "F.Cu" signal ["User name"]) ...) */
function readLayers(root) {
  const l = child(root, 'layers');
  if (!l) return [];
  return l.slice(1).filter(Array.isArray).map(e => {
    e.used = true;
    return { id: Number(e[0]), name: text(e[1]), kind: text(e[2]), userName: text(e[3]) };
  });
}

function readTrack(n, ctx) {
  return {
    type: n[0] === 'arc' ? 'arc' : 'segment',
    start: xy(child(n, 'start')),
    mid: n[0] === 'arc' ? xy(child(n, 'mid')) : undefined,
    end: xy(child(n, 'end')),
    width: numOf(n, 'width', 0),
    layer: strOf(n, 'layer'),
    net: netOf(n, ctx),
    locked: flag(n, 'locked') || hasAtom(n, 'locked'),
    uuid: uuid(n),
    settings: settings(n, 'solder_mask_margin', 'layers', 'status'),
    extra: rest(n),
  };
}

function readVia(n, ctx) {
  const drill = child(n, 'drill');
  return {
    type: 'via',
    kind: ['blind', 'micro', 'buried', 'through'].find(k => n.includes(k)) ?? 'through',
    at: xy(child(n, 'at')),
    size: numOf(n, 'size', 0),
    drill: num(drill, 1, 0),
    layers: layersOf(n),
    net: netOf(n, ctx),
    locked: flag(n, 'locked') || hasAtom(n, 'locked'),
    uuid: uuid(n),
    settings: settings(n, 'free', 'remove_unused_layers', 'keep_end_layers', 'zone_layer_connections', 'padstack', 'teardrops',
      'tenting', 'covering', 'plugging', 'filling', 'capping', 'backdrill', 'tertiary_drill', 'status'),
    extra: rest(n),
  };
}

function readGroup(n) {
  return { type: 'group', name: str(n), libId: strOf(n, 'lib_id'), uuid: uuid(n), locked: flag(n, 'locked') || hasAtom(n, 'locked'), members: (child(n, 'members') ?? []).slice(1).map(text), extra: rest(n) };
}

function readImage(n) {
  const data = child(n, 'data');
  return { type: 'image', at: xy(child(n, 'at')), scale: numOf(n, 'scale', 1), layer: strOf(n, 'layer'), locked: flag(n, 'locked'), data: data ? data.slice(1).map(text).join('') : '', uuid: uuid(n), extra: rest(n) };
}

function readTarget(n) {
  return { type: 'target', shape: str(n), at: xy(child(n, 'at')), size: numOf(n, 'size', 0), width: numOf(n, 'width', 0), layer: strOf(n, 'layer'), uuid: uuid(n), extra: rest(n) };
}

/** Tables, barcodes, points and the like: kept as positioned settings so changes still show up. */
function readOpaqueItem(n) {
  return { type: n[0], at: at(child(n, 'at')), layer: strOf(n, 'layer'), uuid: uuid(n), settings: settings(n, ...new Set(n.slice(1).filter(Array.isArray).map(c => c[0]))), extra: rest(n) };
}

const ITEMS = {
  footprint: readFootprint, module: readFootprint,
  segment: readTrack, arc: readTrack, via: readVia,
  zone: readZone,
  gr_text: readBoardText, gr_text_box: readBoardTextBox,
  dimension: readDimension, group: readGroup, image: readImage, target: readTarget,
  table: readOpaqueItem, barcode: readOpaqueItem, point: readOpaqueItem, drill_chart: readOpaqueItem, drill_map: readOpaqueItem,
  grid_item: readOpaqueItem, generated: readOpaqueItem,
  ...Object.fromEntries(GRAPHICS.map(g => ['gr_' + g, readGraphic])),
};

export function readBoard(root, ctx) {
  // Legacy net table: (net 3 "GND"), used to resolve numeric net references.
  const netTable = children(root, 'net');
  ctx.nets = new Map(netTable.map(n => [str(n, 1), str(n, 2)]));
  const general = child(root, 'general');
  return {
    type: 'board',
    paper: paper(root),
    titleBlock: titleBlock(root),
    thickness: numOf(general, 'thickness', 1.6),
    layers: readLayers(root),
    nets: [...ctx.nets.values()].filter(Boolean),
    properties: readAll(root, 'property', property, ctx),
    items: readAll(root, Object.keys(ITEMS), (n, c) => ITEMS[n[0]](n, c), ctx),
    settings: settings(root, 'general', 'setup', 'constraint', 'net_class', 'net_chains', 'variants', 'embedded_fonts', 'embedded_files'),
    extra: rest(root),
  };
}
