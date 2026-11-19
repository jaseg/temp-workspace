// Schematic sheets (.kicad_sch).

import { at, color, effects, paper, property, pts, rest, settings, stroke, titleBlock, uuid } from './common.js';
import { child, children, flag, hasAtom, num, numOf, readAll, str, strOf, text, xy } from './read.js';
import { readShape, readSymbolDef, readText, readTextBox, SHAPES } from './symbol.js';

/** 10.99 user-defined (custom_property "name" "value") on any schematic item. */
function customProperties(n) {
  return children(n, 'custom_property').map(property);
}

function readWire(n) {
  return { type: n[0], pts: pts(n), stroke: stroke(n), uuid: uuid(n), customProperties: customProperties(n), extra: rest(n) };
}

function readBusEntry(n) {
  const size = child(n, 'size');
  return { type: 'bus_entry', at: xy(child(n, 'at')), size: { w: num(size, 1, 0), h: num(size, 2, 0) }, stroke: stroke(n), uuid: uuid(n), extra: rest(n) };
}

function readJunction(n) {
  return { type: 'junction', at: xy(child(n, 'at')), diameter: numOf(n, 'diameter', 0), color: color(n), uuid: uuid(n), customProperties: customProperties(n), extra: rest(n) };
}

function readNoConnect(n) {
  return { type: 'no_connect', at: xy(child(n, 'at')), uuid: uuid(n), customProperties: customProperties(n), extra: rest(n) };
}

/** label, global_label, hierarchical_label, directive_label, netclass_flag */
function readLabel(n, ctx) {
  return {
    type: n[0],
    text: str(n),
    at: at(child(n, 'at')),
    shape: strOf(n, 'shape'),
    length: numOf(n, 'length'),
    effects: effects(n),
    fieldsAutoplaced: flag(n, 'fields_autoplaced'),
    properties: readAll(n, 'property', property, ctx),
    customProperties: customProperties(n),
    uuid: uuid(n),
    extra: rest(n),
  };
}

function readSymbolInstance(n, ctx) {
  const instances = [];
  for (const project of children(child(n, 'instances'), 'project')) {
    for (const path of children(project, 'path')) {
      instances.push({
        project: str(project), path: str(path), reference: strOf(path, 'reference'), unit: numOf(path, 'unit'),
        variants: settings(path, 'variant'),
      });
    }
  }
  return {
    type: 'symbol',
    libId: strOf(n, 'lib_id'),
    libName: strOf(n, 'lib_name'),
    at: at(child(n, 'at')),
    mirror: strOf(n, 'mirror'),
    unit: numOf(n, 'unit', 1),
    bodyStyle: numOf(n, 'body_style') ?? numOf(n, 'convert', 1),
    inBom: flag(n, 'in_bom', true),
    onBoard: flag(n, 'on_board', true),
    inPosFiles: flag(n, 'in_pos_files', true),
    excludeFromSim: flag(n, 'exclude_from_sim'),
    dnp: flag(n, 'dnp'),
    fieldsAutoplaced: flag(n, 'fields_autoplaced'),
    properties: readAll(n, 'property', property, ctx),
    customProperties: customProperties(n),
    pins: children(n, 'pin').map(p => ({ number: str(p), uuid: uuid(p), alternate: strOf(p, 'alternate'), extra: settings(p, 'custom_property') })),
    instances,
    uuid: uuid(n),
    settings: settings(n, 'passthrough'),
    extra: rest(n),
  };
}

function readSheet(n, ctx) {
  const size = child(n, 'size');
  const instances = [];
  for (const project of children(child(n, 'instances'), 'project')) {
    for (const path of children(project, 'path')) {
      instances.push({ project: str(project), path: str(path), page: strOf(path, 'page'), variants: settings(path, 'variant') });
    }
  }
  return {
    type: 'sheet',
    at: xy(child(n, 'at')),
    size: { w: num(size, 1, 0), h: num(size, 2, 0) },
    stroke: stroke(n),
    fill: { color: color(child(n, 'fill')) },
    inBom: flag(n, 'in_bom', true),
    onBoard: flag(n, 'on_board', true),
    excludeFromSim: flag(n, 'exclude_from_sim'),
    dnp: flag(n, 'dnp'),
    fieldsAutoplaced: flag(n, 'fields_autoplaced'),
    properties: readAll(n, 'property', property, ctx),
    customProperties: customProperties(n),
    pins: readAll(n, 'pin', p => ({
      name: str(p), shape: str(p, 2), at: at(child(p, 'at')), effects: effects(p), uuid: uuid(p), extra: settings(p, 'custom_property'),
    }), ctx),
    instances,
    uuid: uuid(n),
    extra: rest(n),
  };
}

function readImage(n) {
  const data = child(n, 'data');
  return {
    type: 'image', at: xy(child(n, 'at')), scale: numOf(n, 'scale', 1), layer: strOf(n, 'layer'),
    data: data ? data.slice(1).map(text).join('') : '', uuid: uuid(n), extra: rest(n),
  };
}

function readTable(n, ctx) {
  return {
    type: 'table',
    columnCount: numOf(n, 'column_count', 1),
    columnWidths: child(n, 'column_widths')?.slice(1).map(Number) ?? [],
    rowHeights: child(n, 'row_heights')?.slice(1).map(Number) ?? [],
    cells: readAll(child(n, 'cells'), 'table_cell', c => ({ ...readTextBox(c), span: child(c, 'span')?.slice(1).map(Number) }), ctx),
    uuid: uuid(n),
    settings: settings(n, 'border', 'separators', 'layer', 'locked'),
    extra: rest(n),
  };
}

function readRuleArea(n, ctx) {
  return {
    type: 'rule_area',
    shapes: readAll(n, SHAPES, readShape, ctx),
    inBom: flag(n, 'in_bom', true), onBoard: flag(n, 'on_board', true), dnp: flag(n, 'dnp'), excludeFromSim: flag(n, 'exclude_from_sim'),
    extra: rest(n),
  };
}

function readGroup(n) {
  return { type: 'group', name: str(n), libId: strOf(n, 'lib_id'), uuid: uuid(n), locked: flag(n, 'locked') || hasAtom(n, 'locked'), members: (child(n, 'members') ?? []).slice(1).map(text), extra: rest(n) };
}

/** Item readers by head token. */
const ITEMS = {
  wire: readWire, bus: readWire,
  bus_entry: readBusEntry, junction: readJunction, no_connect: readNoConnect,
  label: readLabel, global_label: readLabel, hierarchical_label: readLabel, directive_label: readLabel, netclass_flag: readLabel,
  text: readText, text_box: readTextBox,
  symbol: readSymbolInstance, sheet: readSheet, image: readImage, table: readTable, rule_area: readRuleArea, group: readGroup,
  ...Object.fromEntries(SHAPES.map(s => [s, readShape])),
};

export function readSchematic(root, ctx) {
  return {
    type: 'schematic',
    uuid: uuid(root),
    paper: paper(root),
    titleBlock: titleBlock(root),
    libSymbols: readAll(child(root, 'lib_symbols'), 'symbol', readSymbolDef, ctx),
    items: readAll(root, Object.keys(ITEMS), (n, c) => ITEMS[n[0]](n, c), ctx),
    settings: settings(root, 'sheet_instances', 'symbol_instances', 'bus_alias', 'net_chain', 'netclass', 'embedded_fonts', 'embedded_files', 'invalid_content'),
    extra: rest(root),
  };
}

