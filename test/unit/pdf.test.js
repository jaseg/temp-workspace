import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { readKicad } from '../../src/kicad/index.js';
import { renderModel } from '../../src/render/index.js';
import { buildPdf } from '../../src/render/pdf.js';
import { diffFiles } from '../../src/diff/index.js';
import { PDFDocument, PDFName } from '../../vendor/pdf-lib.esm.min.js';

const read = side => readKicad(readFileSync(new URL(`../pairs/resistors/${side}.kicad_sch`, import.meta.url), 'utf8'));

test('PDF with drawing, change list, annotations and attachment', async () => {
  const old = read('old'), nu = read('new');
  const scene = renderModel(nu);
  const layers = [...scene.layers.keys()].map(name => ({ name, color: [0.5, 0, 0, name === 'wire' ? 0.5 : 1] }));
  const annotations = [
    { type: 'rect', x0: 95, y0: 40, x1: 115, y1: 60, color: '#ff0000', width: 0.3 },
    { type: 'ellipse', x0: 118, y0: 44, x1: 126, y1: 56, color: '#0000ff', width: 0.3 },
    { type: 'pen', points: [{ x: 100, y: 62 }, { x: 105, y: 64 }, { x: 110, y: 62 }], color: '#00aa00', width: 0.3 },
    { type: 'text', x: 100, y: 38, text: 'Check R1', size: 2, color: '#000000' },
  ];
  const bytes = await buildPdf({
    title: 'test',
    pages: [{ title: 'Diff', box: scene.bbox, background: [1, 1, 1], passes: [{ scene, layers }], shades: [{ area: scene.bbox, color: [1, 0, 0, 0.1] }], annotations }],
    changes: diffFiles(old, nu),
    attachment: { name: 'annotations.json', json: { annotations } },
  });
  assert.equal(new TextDecoder().decode(bytes.slice(0, 5)), '%PDF-');
  const doc = await PDFDocument.load(bytes);
  assert.equal(doc.getPageCount(), 2);
  const annots = doc.getPage(0).node.lookup(PDFName.of('Annots'));
  const subtypes = annots.asArray().map(r => doc.context.lookup(r).get(PDFName.of('Subtype')).asString());
  assert.deepEqual(subtypes, ['/Square', '/Circle', '/Ink', '/FreeText']);
  const names = doc.catalog.lookup(PDFName.of('Names'));
  assert.ok(names.lookup(PDFName.of('EmbeddedFiles')), 'annotations attached');
});
