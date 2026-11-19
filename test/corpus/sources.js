// KiCad corpus sources: the two target versions (10.0 stable, 10.99 development).

import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

export const CACHE = fileURLToPath(new URL('../../.cache/', import.meta.url));

const KICAD = 'https://gitlab.com/kicad/code/kicad.git';
const KICAD_DIRS = ['qa/data', 'demos'];

export const SOURCES = [
  { name: 'kicad-10.0', env: 'KICAD_SOURCE_10', url: KICAD, ref: 'refs/tags/10.0.8', sparse: KICAD_DIRS },
  // Pinned master commit (10.99); bump deliberately.
  { name: 'kicad-10.99', env: 'KICAD_SOURCE_1099', url: KICAD, ref: 'c80c825b44c0113aa019f6d709e77074cbb665fb', sparse: KICAD_DIRS },
  { name: 'kicad-symbols', env: 'KICAD_SYMBOLS', url: 'https://gitlab.com/kicad/libraries/kicad-symbols.git', ref: 'refs/tags/10.0.8' },
  { name: 'kicad-footprints', env: 'KICAD_FOOTPRINTS', url: 'https://gitlab.com/kicad/libraries/kicad-footprints.git', ref: 'refs/tags/10.0.8' },
];

export function sourceDir(name) {
  const source = SOURCES.find(s => s.name === name);
  return process.env[source.env] || join(CACHE, name);
}
