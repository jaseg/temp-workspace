import { test } from 'node:test';
import assert from 'node:assert/strict';
import { annotationsSvg, exportAnnotations, hitAnnotation, importAnnotations } from '../../src/ui/annotate.js';

const list = [
  { type: 'rect', x0: 0, y0: 0, x1: 10, y1: 5, color: '#f00', width: 0.2 },
  { type: 'pen', points: [{ x: 20, y: 20 }, { x: 25, y: 22 }], color: '#00f', width: 0.2 },
  { type: 'text', x: 30, y: 30, text: 'check <this>', size: 2, color: '#000' },
];

test('hit testing finds the topmost annotation', () => {
  assert.equal(hitAnnotation(list, { x: 5, y: 2 }, 0.1), 0);
  assert.equal(hitAnnotation(list, { x: 22, y: 21 }, 0.1), 1);
  assert.equal(hitAnnotation(list, { x: 100, y: 100 }, 0.1), -1);
});

test('SVG output escapes text', () => {
  const svg = annotationsSvg(list, (x, y) => ({ x: x * 2, y: y * 2 }), 2);
  assert.match(svg, /<rect x="0" y="0" width="20" height="10"/);
  assert.match(svg, /check &lt;this&gt;/);
});

test('export and import round-trip, with a warning for other file versions', async () => {
  const sources = { old: { name: 'a.kicad_sch', text: 'A' }, new: { name: 'a.kicad_sch', text: 'B' } };
  const doc = await exportAnnotations(list, sources);
  assert.equal(doc.files.new.sha256.length, 64);
  const same = await importAnnotations(JSON.stringify(doc), sources);
  assert.deepEqual(same.annotations, list);
  assert.equal(same.warning, '');
  const other = await importAnnotations(doc, { ...sources, new: { name: 'a.kicad_sch', text: 'C' } });
  assert.match(other.warning, /different versions/);
  await assert.rejects(() => importAnnotations('{"format": "x"}', sources));
});
