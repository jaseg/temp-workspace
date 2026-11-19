// Render every corpus file into a scene: no exceptions, no render errors, only finite coordinates.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { readKicad } from '../../src/kicad/index.js';
import { renderModel } from '../../src/render/index.js';
import { corpus, rel } from './corpus.js';

function finite(scene) {
  for (const l of scene.layers.values()) {
    if (!l.segments.every(Number.isFinite) || !l.triangles.every(Number.isFinite)) return false;
    if (!l.texts.every(t => Number.isFinite(t.x + t.y + t.rot + t.h + t.w))) return false;
  }
  return true;
}

for (const group of corpus()) {
  if (!group.name.startsWith('kicad-1')) continue;
  test(`${group.name}: render`, () => {
    const problems = [];
    for (const file of group.files) {
      const result = readKicad(readFileSync(file, 'utf8'));
      if (!result.model) continue;
      const scene = renderModel(result);
      if (scene.errors.length) problems.push(`${rel(group, file)}: ${scene.errors.length} render errors, first: ${scene.errors[0].message}`);
      if (!finite(scene)) problems.push(`${rel(group, file)}: non-finite coordinates`);
    }
    assert.deepEqual(problems.slice(0, 20), [], `${problems.length} problems`);
  });
}
