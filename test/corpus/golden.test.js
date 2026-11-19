// Golden change lists for real file pairs: KiCad's own visual-diff fixtures and demo files that
// differ between 10.0 and 10.99. Review changes to test/golden/*.json by hand.
// Regenerate with: UPDATE_GOLDEN=1 npm run test:corpus

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { readKicad } from '../../src/kicad/index.js';
import { diffFiles } from '../../src/diff/index.js';
import { sourceDir } from './sources.js';

const GOLDEN = new URL('../golden/', import.meta.url).pathname;
const V = 'qa/data/diff_merge/visual_diff';
const PAIRS = [
  ['visual-diff-pcb', ['kicad-10.99', `${V}/pcb_a.kicad_pcb`], ['kicad-10.99', `${V}/pcb_b.kicad_pcb`]],
  ['visual-diff-sch', ['kicad-10.99', `${V}/sch_a.kicad_sch`], ['kicad-10.99', `${V}/sch_b.kicad_sch`]],
  ['visual-diff-sym', ['kicad-10.99', `${V}/sym_a.kicad_sym`], ['kicad-10.99', `${V}/sym_b.kicad_sym`]],
  ['pic-programmer-sch', ['kicad-10.0', 'demos/pic_programmer/pic_programmer.kicad_sch'], ['kicad-10.99', 'demos/pic_programmer/pic_programmer.kicad_sch']],
  ['video-pcb', ['kicad-10.0', 'demos/video/video.kicad_pcb'], ['kicad-10.99', 'demos/video/video.kicad_pcb']],
  ['video-sch', ['kicad-10.0', 'demos/video/video.kicad_sch'], ['kicad-10.99', 'demos/video/video.kicad_sch']],
];
const LIMIT = 60;

const read = ([source, path]) => {
  const file = join(sourceDir(source), path);
  return existsSync(file) ? readKicad(readFileSync(file, 'utf8')) : null;
};

for (const [name, a, b] of PAIRS) {
  test(`golden: ${name}`, t => {
    const fa = read(a), fb = read(b);
    if (!fa || !fb) return t.skip('corpus not fetched');
    const changes = diffFiles(fa, fb);
    const counts = {};
    for (const c of changes) counts[`${c.kind}${c.minor ? ' (minor)' : ''}`] = (counts[`${c.kind}${c.minor ? ' (minor)' : ''}`] ?? 0) + 1;
    const actual = { counts, first: changes.slice(0, LIMIT).map(c => `${c.kind}${c.minor ? '/minor' : ''}: ${c.summary}`) };
    const path = join(GOLDEN, `${name}.json`);
    if (process.env.UPDATE_GOLDEN || !existsSync(path)) {
      mkdirSync(GOLDEN, { recursive: true });
      writeFileSync(path, JSON.stringify(actual, null, 1) + '\n');
    }
    assert.deepEqual(actual, JSON.parse(readFileSync(path, 'utf8')));
  });
}
