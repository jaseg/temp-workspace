import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { joinPath, pairTopologies, projectTopology } from '../../src/kicad/project.js';

const loader = dir => ({
  load: path => readFile(new URL(`../pairs/${dir}/${path}`, import.meta.url), 'utf8').catch(() => null),
});

test('joinPath resolves relative sheet paths', () => {
  assert.equal(joinPath('a/b/', '../c.kicad_sch'), 'a/c.kicad_sch');
  assert.equal(joinPath('', './x/y.kicad_sch'), 'x/y.kicad_sch');
});

test('topology follows the sheet hierarchy', async () => {
  const t = await projectTopology('demo.kicad_pro', loader('project-new'));
  assert.equal(t.name, 'demo');
  assert.deepEqual(t.nodes.map(n => [n.depth, n.name, n.path]), [
    [0, 'demo (root sheet)', 'demo.kicad_sch'],
    [1, 'resistors', 'resistors.kicad_sch'],
  ]);
});

test('pairing marks added and removed files in place', () => {
  const node = (path, name = path) => ({ path, name, type: 'schematic', depth: 0 });
  const a = { nodes: [node('root'), node('gone'), node('kept')] };
  const b = { nodes: [node('root'), node('kept'), node('new')] };
  assert.deepEqual(pairTopologies(a, b).map(n => `${n.path}:${n.status}`), ['root:both', 'gone:removed', 'kept:both', 'new:added']);
});
