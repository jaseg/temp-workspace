// Entry point of the diff engine: semantic changes between two read KiCad files.

import { diffSchematic } from './schematic.js';
import { diffBoard, diffFootprint } from './board.js';
import { diffSymbolLib } from './library.js';
import { change } from './util.js';

const ENGINES = { schematic: diffSchematic, board: diffBoard, footprint: diffFootprint, symbol_lib: diffSymbolLib };
const EMPTY = { schematic: { items: [], libSymbols: [] }, board: { items: [], layers: [] }, symbol_lib: { symbols: [] } };
const ORDER = { electrical: 0, metadata: 1, layout: 2 };

/**
 * @param {object|null} oldFile  result of readKicad() (null if the file was added)
 * @param {object|null} newFile  result of readKicad() (null if the file was removed)
 * @returns {object[]} changes, most important first
 */
export function diffFiles(oldFile, newFile) {
  const type = newFile?.model ? newFile.type : oldFile?.type;
  const engine = ENGINES[type];
  if (!engine) return [];
  if (oldFile?.model && newFile?.model && oldFile.type !== newFile.type) {
    return [change('metadata', 'modified', 'file', `File type changed from ${oldFile.type} to ${newFile.type}`)];
  }
  const empty = type === 'footprint' ? null : EMPTY[type];
  if (!oldFile?.model && type === 'footprint') return [change('electrical', 'added', 'footprint', 'Footprint added')];
  if (!newFile?.model && type === 'footprint') return [change('electrical', 'removed', 'footprint', 'Footprint removed')];
  let changes;
  try {
    changes = engine(oldFile?.model ?? empty, newFile?.model ?? empty);
  } catch (e) {
    return [change('metadata', 'modified', 'file', `The comparison failed: ${e.message}`)];
  }
  return changes.sort((a, b) => ORDER[a.kind] - ORDER[b.kind] || a.minor - b.minor);
}

export const KINDS = ['electrical', 'metadata', 'layout'];
