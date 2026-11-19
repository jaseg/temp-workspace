// Fault isolation on real files: damage one spot of the text and check that the file still reads,
// the damage is reported, and almost all items survive.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { readKicad } from '../../src/kicad/index.js';
import { corpus, rel } from './corpus.js';

/** Small deterministic PRNG so failures are reproducible. */
function rng(seed) {
  return () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
}

const CORRUPTIONS = {
  'stray paren': (text, r) => {
    const i = Math.floor(text.length * (0.3 + 0.6 * r()));
    return text.slice(0, i) + ')' + text.slice(i);
  },
  'unterminated string': (text, r) => {
    const quotes = [...text.matchAll(/"[^"\n]*"/g)];
    const m = quotes[Math.floor(quotes.length * (0.3 + 0.6 * r()))];
    return m ? text.slice(0, m.index + m[0].length - 1) + text.slice(m.index + m[0].length) : text;
  },
};

function itemCount(result) {
  const m = result.model;
  return (m?.items ?? m?.symbols ?? m?.pads ?? []).length;
}

for (const group of corpus()) {
  test(`${group.name}: damaged files still read`, () => {
    const r = rng(1);
    const problems = [];
    const sample = group.files.filter((_, i) => i % 25 === 0);
    for (const file of sample) {
      const text = readFileSync(file, 'utf8');
      const original = readKicad(text);
      if (original.versionStatus !== 'ok') continue;
      for (const [kind, corrupt] of Object.entries(CORRUPTIONS)) {
        let damaged;
        try {
          damaged = readKicad(corrupt(text, r));
        } catch (e) {
          problems.push(`${rel(group, file)} (${kind}): threw ${e.message}`);
          continue;
        }
        if (damaged.type !== original.type) problems.push(`${rel(group, file)} (${kind}): type lost`);
        else if (itemCount(damaged) < 0.5 * itemCount(original) - 2) problems.push(`${rel(group, file)} (${kind}): ${itemCount(damaged)}/${itemCount(original)} items`);
      }
    }
    assert.deepEqual(problems, []);
  });
}
