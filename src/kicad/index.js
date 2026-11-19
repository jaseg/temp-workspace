// Entry point: detect a KiCad file's type and version, and read it into a plain-object model.

import { parse } from '../sexpr.js';
import { child, ignore, num, str, unhandled } from './read.js';
import { readSchematic } from './schematic.js';
import { readSymbolLib } from './symbol.js';
import { readFootprint } from './footprint.js';
import { readBoard } from './board.js';

/**
 * Supported format versions: [last version written by KiCad 9.0 (exclusive), newest known 10.99].
 * Everything in between was written by KiCad 10.0 (including its development versions) or 10.99.
 */
export const VERSIONS = {
  schematic: [20250114, 20261106],
  symbol_lib: [20241209, 20261106],
  footprint: [20241229, 20261031],
  board: [20241229, 20261031],
};

const READERS = {
  kicad_sch: ['schematic', readSchematic],
  kicad_symbol_lib: ['symbol_lib', readSymbolLib],
  footprint: ['footprint', readFootprint],
  module: ['footprint', readFootprint],
  kicad_pcb: ['board', readBoard],
};

/** 'ok', 'older' (pre-10.0, read best-effort), 'newer' (beyond the newest known 10.99) or 'unknown'. */
export function versionStatus(type, version) {
  const range = VERSIONS[type];
  if (!range || !version) return 'unknown';
  if (version <= range[0]) return 'older';
  if (version > range[1]) return 'newer';
  return 'ok';
}

/**
 * Read a KiCad file. Never throws for malformed content: problems are reported in `errors`
 * (elements that could not be read are dropped) and `unhandled` (tokens no reader understood).
 * @returns {{type: string, version: number|undefined, versionStatus: string, generator: string|undefined,
 *            model: object|null, errors: object[], unhandled: Map<string, number>}}
 */
export function readKicad(text) {
  const errors = [];
  let root;
  try {
    root = parse(text, err => errors.push({ pos: err.pos, message: err.message }));
  } catch (e) {
    return { type: 'unknown', version: undefined, versionStatus: 'unknown', model: null, errors: [{ pos: e.pos ?? 0, message: e.message }], unhandled: new Map() };
  }
  const entry = READERS[root[0]];
  const version = num(child(root, 'version'));
  const generator = str(child(root, 'generator'));
  ignore(root, 'generator_version');
  if (!entry) {
    errors.push({ pos: 0, message: `Not a supported KiCad file (${root[0]})` });
    return { type: 'unknown', version, versionStatus: 'unknown', generator, model: null, errors, unhandled: new Map() };
  }
  const [type, read] = entry;
  const ctx = { version, errors };
  root.used = true;
  const model = read(root, ctx);
  model.version = version;
  return { type, version, versionStatus: versionStatus(type, version), generator, model, errors, unhandled: unhandled(root) };
}

/** File type from a file name, for inputs whose content is not yet known. */
export function typeFromName(name) {
  const m = /\.(kicad_sch|kicad_pcb|kicad_sym|kicad_mod|kicad_pro)$/.exec(name);
  return m && { kicad_sch: 'schematic', kicad_pcb: 'board', kicad_sym: 'symbol_lib', kicad_mod: 'footprint', kicad_pro: 'project' }[m[1]];
}
