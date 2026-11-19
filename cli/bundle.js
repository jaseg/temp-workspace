// Inline the viewer's ES modules into one HTML file. Each module becomes a data: URL listed in an
// import map; relative imports are rewritten to the bare names used as import map keys. No
// bundler needed, and the result works from file://.

import { readdir, readFile } from 'node:fs/promises';
import { join, posix, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

export const PACKAGE_ROOT = fileURLToPath(new URL('../', import.meta.url));
const NAME = 'kicad-diff';

async function walk(dir) {
  const out = [];
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) out.push(...(await walk(p)));
    else if (e.name.endsWith('.js')) out.push(p);
  }
  return out;
}

/** Bare module name for a file, e.g. "kicad-diff/src/ui/kicad-diff.js". */
const moduleName = file => `${NAME}/${relative(PACKAGE_ROOT, file).split('\\').join('/')}`;

/** Rewrite relative import specifiers ('./x.js', '../y.js') in a module to bare module names. */
export function rewriteImports(source, name) {
  const dir = posix.dirname(name);
  const fix = spec => (spec.startsWith('.') ? posix.normalize(posix.join(dir, spec)) : spec);
  return source
    .replace(/(\bfrom\s*|\bimport\s*)(['"])(\.{1,2}\/[^'"]+)\2/g, (_, kw, q, spec) => `${kw}${q}${fix(spec)}${q}`)
    .replace(/(\bimport\s*\(\s*)(['"])(\.{1,2}\/[^'"]+)\2/g, (_, kw, q, spec) => `${kw}${q}${fix(spec)}${q}`);
}

/** Import map with every module of src/ and vendor/ as a data: URL. */
export async function importMap() {
  const imports = {};
  for (const file of [...(await walk(join(PACKAGE_ROOT, 'src'))), ...(await walk(join(PACKAGE_ROOT, 'vendor')))]) {
    const name = moduleName(file);
    const code = rewriteImports(await readFile(file, 'utf8'), name);
    imports[name] = `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`;
  }
  return { imports };
}

/** JSON that is safe inside a <script> element. */
export const scriptJson = value => JSON.stringify(value).replace(/</g, '\\u003c');


