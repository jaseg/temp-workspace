// Corpus file discovery shared by the corpus tests.

import { existsSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { sourceDir } from './sources.js';

export const FULL = !!process.env.KICAD_CORPUS_FULL;
const MAX_SIZE = FULL ? Infinity : 20e6;
const LIBRARY_SAMPLE = FULL ? 1 : 40; // every Nth library file unless running the full corpus

const KICAD_FILE = /\.kicad_(sch|pcb|sym|mod)$/;
// Import-plugin fixtures are KiCad files converted from other tools; skip their source formats only.
const SKIP_DIRS = new Set(['.git']);

function walk(dir, out = []) {
  for (const name of readdirSync(dir).sort()) {
    if (SKIP_DIRS.has(name)) continue;
    const path = join(dir, name);
    const st = statSync(path);
    if (st.isDirectory()) walk(path, out);
    else if (KICAD_FILE.test(name) && st.size <= MAX_SIZE) out.push(path);
  }
  return out;
}

/** Corpus groups: KiCad's own test data per target version, plus samples of the official libraries. */
export function corpus() {
  const groups = [];
  for (const name of ['kicad-10.0', 'kicad-10.99']) {
    const dir = sourceDir(name);
    if (!existsSync(dir)) continue;
    const files = ['qa/data', 'demos'].map(d => join(dir, d)).filter(existsSync).flatMap(d => walk(d));
    groups.push({ name, dir, files });
  }
  for (const name of ['kicad-symbols', 'kicad-footprints']) {
    const dir = sourceDir(name);
    if (!existsSync(dir)) continue;
    const files = walk(dir).filter((_, i) => i % LIBRARY_SAMPLE === 0);
    groups.push({ name, dir, files });
  }
  return groups;
}

export function rel(group, file) {
  return relative(group.dir, file);
}
