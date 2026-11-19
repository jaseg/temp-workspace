#!/usr/bin/env node
// Download colour themes from the KiCad add-on repository into JSON files, e.g. to list them in a
// configuration file of a static or Forgejo deployment (browsers do not fetch themes themselves).
// Usage: node tools/fetch-pcm-theme.js <package identifier>... [-o folder]

import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { parseArgs } from 'node:util';
import { fetchPcmTheme } from '../cli/themes.js';

const { values, positionals } = parseArgs({ allowPositionals: true, options: { output: { type: 'string', short: 'o', default: '.' } } });
mkdirSync(values.output, { recursive: true });
for (const id of positionals) {
  for (const { name, theme } of await fetchPcmTheme(id)) {
    const file = join(values.output, `${name.replace(/[^\w.-]+/g, '_')}.json`);
    writeFileSync(file, JSON.stringify(theme, null, 1));
    console.log(`${file}  ({"name": ${JSON.stringify(name)}, "url": "${file}"})`);
  }
}
