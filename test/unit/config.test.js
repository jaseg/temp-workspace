import { test } from 'node:test';
import assert from 'node:assert/strict';
import { configFromParams, DEFAULTS, mergeConfig } from '../../src/config.js';

test('later layers win, objects merge, arrays replace', () => {
  const file = { mode: 'split', kinds: { minor: false }, hiddenLayers: ['F.Fab'] };
  const flags = { mode: 'diff', hiddenLayers: ['B.Fab'] };
  const c = mergeConfig(DEFAULTS, file, flags);
  assert.equal(c.mode, 'diff');
  assert.deepEqual(c.kinds, { electrical: true, metadata: true, layout: true, minor: false });
  assert.deepEqual(c.hiddenLayers, ['B.Fab']);
  assert.equal(c.tone.old, DEFAULTS.tone.old);
});

test('URL parameters', () => {
  const c = configFromParams(new URLSearchParams('mode=left&ui=dark&hide=F.Fab,B.Fab'));
  assert.deepEqual(mergeConfig(DEFAULTS, c).hiddenLayers, ['F.Fab', 'B.Fab']);
  assert.equal(c.uiTheme, 'dark');
  assert.equal(mergeConfig({ mode: 'split' }, configFromParams(new URLSearchParams(''))).mode, 'split');
});
