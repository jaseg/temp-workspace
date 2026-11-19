// Project discovery: from a .kicad_pro (or a top-level .kicad_sch), find the schematic hierarchy,
// the board and project-local libraries.
//
// Files are fetched through `load(path) → Promise<string | null>` (paths relative to the project
// directory, "/"-separated) and, optionally, `list(dir) → Promise<string[]>` for library folders.

import { parse } from '../sexpr.js';
import { readKicad } from './index.js';

const dirname = p => (p.includes('/') ? p.slice(0, p.lastIndexOf('/') + 1) : '');
const basename = p => p.slice(p.lastIndexOf('/') + 1);

/** Normalise "a/b/../c" → "a/c". */
export function joinPath(dir, rel) {
  const parts = [];
  for (const s of (dir + rel).split('/')) {
    if (s === '..') parts.pop();
    else if (s && s !== '.') parts.push(s);
  }
  return parts.join('/');
}

/** Project-local library paths from a sym-lib-table/fp-lib-table (only ${KIPRJMOD} URIs). */
function libTable(text) {
  try {
    return parse(text)
      .filter(e => Array.isArray(e) && e[0] === 'lib')
      .map(e => e.find(c => Array.isArray(c) && c[0] === 'uri'))
      .map(u => (u?.[1]?.str ?? u?.[1] ?? ''))
      .filter(u => u.startsWith('${KIPRJMOD}/'))
      .map(u => u.slice('${KIPRJMOD}/'.length));
  } catch {
    return [];
  }
}

/**
 * Project topology.
 * @returns {Promise<{name: string, nodes: {path, type, name, depth, sheet?}[]}>} nodes in display order:
 *   the schematic hierarchy (depth-first, with sheet names), then the board, then libraries.
 */
export async function projectTopology(entry, { load, list }) {
  const nodes = [];
  const base = entry.replace(/\.kicad_(pro|sch)$/, '');
  const name = basename(base);
  const rootSch = `${base}.kicad_sch`;

  const seen = new Set();
  async function walk(path, depth, sheet) {
    const text = await load(path);
    nodes.push({ path, type: 'schematic', name: sheet ?? basename(path), depth, missing: text === null });
    if (text === null || seen.has(path)) return; // shared sheets are listed per instance, expanded once
    seen.add(path);
    const r = readKicad(text);
    for (const s of r.model?.items.filter(i => i.type === 'sheet') ?? []) {
      const prop = n => s.properties.find(p => p.name === n || p.name === n.replace('name', ' name').replace('file', ' file'))?.value;
      const file = prop('Sheetfile');
      if (file) await walk(joinPath(dirname(path), file), depth + 1, prop('Sheetname') ?? basename(file));
    }
  }
  await walk(rootSch, 0, `${name} (root sheet)`);

  const board = `${base}.kicad_pcb`;
  if ((await load(board)) !== null) nodes.push({ path: board, type: 'board', name: basename(board), depth: 0 });

  const dir = dirname(entry);
  for (const lib of libTable((await load(`${dir}sym-lib-table`)) ?? '')) {
    nodes.push({ path: joinPath(dir, lib), type: 'symbol_lib', name: basename(lib), depth: 0 });
  }
  for (const lib of libTable((await load(`${dir}fp-lib-table`)) ?? '')) {
    const files = list ? (await list(joinPath(dir, lib))) ?? [] : [];
    for (const f of files.filter(f => f.endsWith('.kicad_mod')).sort()) {
      nodes.push({ path: joinPath(dir, `${lib}/${f}`), type: 'footprint', name: `${basename(lib)}/${f}`, depth: 0 });
    }
  }
  return { name, nodes };
}

/**
 * Pair the topologies of two project versions by file path. Nodes keep the new version's order,
 * with files only in the old version inserted where they were.
 */
export function pairTopologies(a, b) {
  const out = [];
  const inB = new Set(b.nodes.map(n => n.path + '|' + n.name));
  const inA = new Set(a.nodes.map(n => n.path + '|' + n.name));
  let ia = 0;
  for (const n of b.nodes) {
    while (ia < a.nodes.length && !inB.has(a.nodes[ia].path + '|' + a.nodes[ia].name)) out.push({ ...a.nodes[ia++], status: 'removed' });
    if (ia < a.nodes.length && a.nodes[ia].path + '|' + a.nodes[ia].name === n.path + '|' + n.name) ia++;
    out.push({ ...n, status: inA.has(n.path + '|' + n.name) ? 'both' : 'added' });
  }
  while (ia < a.nodes.length) out.push({ ...a.nodes[ia++], status: 'removed' });
  return out;
}
