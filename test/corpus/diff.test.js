// Diff invariants and seeded mutations on KiCad's own files (10.0 and 10.99).
//
// - a file compared with itself has no changes
// - reordering top-level elements is not a change
// - regenerating every UUID causes no electrical or metadata changes (fallback matching works)
// - seeded edits are classified correctly: a Value edit is one metadata change, renaming a label
//   or a pad's net is electrical, and change texts never contain UUIDs

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { parse, print } from '../../src/sexpr.js';
import { readKicad } from '../../src/kicad/index.js';
import { diffFiles } from '../../src/diff/index.js';
import { corpus, rel } from './corpus.js';

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi;

/** mulberry32: small seeded PRNG, so failures are reproducible. */
function rng(seed) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Shuffle the child lists of the top-level list; positional arguments (e.g. a footprint's name) stay first. */
function shuffled(text, r) {
  const t = parse(text);
  const head = t.filter(c => !Array.isArray(c));
  const rest = t.filter(Array.isArray);
  for (let i = rest.length - 1; i > 0; i--) {
    const j = Math.floor(r() * (i + 1));
    [rest[i], rest[j]] = [rest[j], rest[i]];
  }
  return print([...head, ...rest]);
}

/** Replace every UUID consistently (references to a UUID elsewhere in the file follow along). */
function newUuids(text) {
  const map = new Map();
  return text.replace(UUID, u => {
    if (!map.has(u)) map.set(u, randomUUID());
    return map.get(u);
  });
}

/** Find the first list node matching `pred` (depth first). */
function find(n, pred) {
  if (!Array.isArray(n)) return null;
  if (pred(n)) return n;
  for (const c of n) {
    const f = find(c, pred);
    if (f) return f;
  }
  return null;
}

const MUTATIONS = {
  'edit a Value': {
    apply(tree) {
      // Ordinary components only: a power symbol's Value names its net, so editing it is electrical.
      const isPower = n => n.some(c => c[0] === 'property' && c[1]?.str === 'Reference' && c[2]?.str?.startsWith('#'));
      const sym = find(tree, n => ((n[0] === 'symbol' && n.some(c => c[0] === 'lib_id')) || n[0] === 'footprint') && !isPower(n));
      const value = sym && find(sym, n => n[0] === 'property' && n[1]?.str === 'Value');
      if (!value || value[2]?.str === undefined) return false;
      value[2] = { str: value[2].str + '_mut' };
      return true;
    },
    check: changes => changes.length === 1 && changes[0].kind === 'metadata' && /Value/.test(changes[0].summary),
  },
  'rename a label': {
    apply(tree) {
      const label = find(tree, n => n[0] === 'label' && typeof n[1] === 'object');
      if (!label) return false;
      label[1] = { str: label[1].str + '_mut' };
      return true;
    },
    check: changes => changes.length > 0 && changes.every(c => c.kind === 'electrical' || (c.kind === 'layout' && c.minor)),
  },
  "change a pad's net": {
    apply(tree) {
      const pad = find(tree, n => n[0] === 'pad' && n.some(c => c[0] === 'net'));
      if (!pad) return false;
      const net = pad.find(c => c[0] === 'net');
      net.splice(1, net.length - 1, { str: 'MUTATED_NET' });
      return true;
    },
    check: changes => changes.some(c => c.kind === 'electrical' && /MUTATED_NET/.test(c.summary)) && changes.every(c => c.kind === 'electrical'),
  },
};

for (const group of corpus()) {
  if (!group.name.startsWith('kicad-1')) continue;
  test(`${group.name}: diff invariants and mutations`, () => {
    const problems = [];
    const stats = Object.fromEntries(Object.keys(MUTATIONS).map(k => [k, 0]));
    const r = rng(7);
    for (const file of group.files) {
      const text = readFileSync(file, 'utf8');
      const original = readKicad(text);
      if (original.versionStatus !== 'ok' || !original.model || /\/fuzz\//.test(file)) continue;
      const name = rel(group, file);
      const expectNone = (label, other, allow = () => false) => {
        const changes = diffFiles(original, readKicad(other)).filter(c => !allow(c));
        if (changes.length) problems.push(`${name} (${label}): ${changes.length} changes, first: ${changes[0].kind}: ${changes[0].summary}`);
      };
      expectNone('self', text);
      expectNone('shuffled', shuffled(text, r));
      // Text and settings that refer to other elements by UUID (${uuid:Field} cross-references,
      // constraint members, net chain terminals) legitimately change; nothing else may.
      expectNone('new UUIDs', newUuids(text), c => c.kind === 'layout' || /\$\{[0-9a-f-]{36}:/.test(c.summary) || (c.kind === 'metadata' && /settings changed$/.test(c.summary)));

      for (const [label, m] of Object.entries(MUTATIONS)) {
        const tree = parse(text);
        if (!m.apply(tree)) continue;
        stats[label]++;
        const changes = diffFiles(original, readKicad(print(tree)));
        if (!m.check(changes)) problems.push(`${name} (${label}): ${changes.map(c => `${c.kind}: ${c.summary}`).slice(0, 3).join(' | ') || 'no changes'}`);
        for (const c of changes) for (const t of [c.summary, c.subject, ...c.details]) if (UUID.test(t)) problems.push(`${name}: UUID in change text: ${t}`);
      }
    }
    console.log(`${group.name}: mutations applied ${JSON.stringify(stats)}`);
    assert.deepEqual(problems.slice(0, 25), [], `${problems.length} problems`);
  });
}
