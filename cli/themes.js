// Colour themes given on the command line: KiCad colour-theme JSON files, or packages from the
// KiCad Plugin and Content Manager (PCM) as "pcm:<package identifier>", downloaded and verified
// here (the browser never fetches themes from elsewhere).

import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { basename } from 'node:path';
import { unzip } from './zip.js';

export const PCM_PACKAGES = 'https://gitlab.com/kicad/addons/repository/-/raw/main/packages.json';

async function fetchBuffer(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status} ${res.statusText}`);
  return Buffer.from(await res.arrayBuffer());
}

/** Download a PCM colour-theme package and return the themes in it: [{name, theme}]. */
export async function fetchPcmTheme(identifier, { packagesUrl = PCM_PACKAGES } = {}) {
  const { packages } = JSON.parse(await fetchBuffer(packagesUrl));
  const pkg = packages.find(p => p.identifier === identifier && p.type === 'colortheme');
  if (!pkg) throw new Error(`No colour theme "${identifier}" in the KiCad add-on repository`);
  const version = pkg.versions?.at(-1);
  if (!version?.download_url) throw new Error(`Colour theme "${identifier}" has no download`);
  const zip = await fetchBuffer(version.download_url);
  if (version.download_sha256 && createHash('sha256').update(zip).digest('hex') !== version.download_sha256) {
    throw new Error(`Colour theme "${identifier}": checksum mismatch`);
  }
  const themes = [];
  for (const [name, data] of unzip(zip)) {
    if (!/^colors\/[^/]+\.json$/.test(name) || !data) continue;
    const theme = JSON.parse(data.toString('utf8'));
    themes.push({ name: theme.meta?.name ?? pkg.name, theme });
  }
  if (!themes.length) throw new Error(`Colour theme "${identifier}" contains no colours/*.json`);
  return themes;
}

/** Resolve --color-theme arguments to [{name, theme}]. */
export async function resolveThemes(specs) {
  const out = [];
  for (const spec of specs) {
    if (spec.startsWith('pcm:')) out.push(...(await fetchPcmTheme(spec.slice(4))));
    else {
      const theme = JSON.parse(await readFile(spec, 'utf8'));
      out.push({ name: theme.meta?.name ?? basename(spec, '.json'), theme });
    }
  }
  return out;
}
