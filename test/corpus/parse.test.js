// Parse KiCad's own test files (10.0 and 10.99) and library samples.
//
// - every file tokenizes and round-trips through the printer
// - files in a supported version read without errors
// - every token in supported files is understood, except those listed in known-unhandled.json
//
// The current unhandled report is written to .cache/unhandled-report.json for inspection.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { parse, print } from '../../src/sexpr.js';
import { readKicad } from '../../src/kicad/index.js';
import { corpus, rel } from './corpus.js';
import { CACHE } from './sources.js';

const KNOWN_UNHANDLED = new Set(JSON.parse(readFileSync(new URL('./known-unhandled.json', import.meta.url), 'utf8')));
// Files that are malformed on purpose or by accident upstream; they must still not crash the reader.
const KNOWN_BROKEN = [
  /RoyalBlue54L-Feather-Connector_FFC-FPC\.pretty\/CONN-SMD_5P-P0\.50_HCTL_HC-FPC-05-09-5RLTAG\.kicad_mod$/,
  /fakeboard\.kicad_pcb$/,
  /\/fuzz\//,
];

const report = {};

for (const group of corpus()) {
  test(`${group.name}: ${group.files.length} files`, () => {
    const problems = [];
    const stats = { ok: 0, older: 0, newer: 0, unknown: 0 };
    for (const file of group.files) {
      const name = rel(group, file);
      const text = readFileSync(file, 'utf8');
      const broken = KNOWN_BROKEN.some(re => re.test(file));

      if (!broken) {
        try {
          const once = print(parse(text));
          if (print(parse(once)) !== once) problems.push(`${name}: printer round-trip differs`);
        } catch (e) {
          problems.push(`${name}: tokenizer: ${e.message}`);
          continue;
        }
      }

      const result = readKicad(text);
      stats[result.versionStatus]++;
      if (broken) continue;
      if (result.versionStatus === 'ok' && result.errors.length) {
        problems.push(`${name}: ${result.errors.length} read errors, first: ${result.errors[0].message}`);
      }
      if (result.versionStatus !== 'ok') continue;
      for (const [path, count] of result.unhandled) {
        const key = `${result.type}: ${path}`;
        report[key] ??= { count: 0, example: `${group.name}/${name}` };
        report[key].count += count;
      }
    }
    const unexpected = Object.keys(report).filter(k => !KNOWN_UNHANDLED.has(k));
    writeFileSync(CACHE + 'unhandled-report.json', JSON.stringify(report, null, 2));
    console.log(`${group.name}: versions ${JSON.stringify(stats)}`);
    assert.deepEqual(problems.slice(0, 20), [], `${problems.length} problems`);
    assert.deepEqual(unexpected.slice(0, 40).map(k => `${k} (e.g. ${report[k].example})`), [], `${unexpected.length} unhandled token paths`);
  });
}
