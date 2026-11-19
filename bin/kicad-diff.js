#!/usr/bin/env node
// kicad-diff command line: build an offline HTML diff, or serve the viewer locally.

import { readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { DEFAULTS, mergeConfig } from '../src/config.js';
import { resolveInput } from '../cli/inputs.js';
import { resolveThemes } from '../cli/themes.js';
import { buildHtml } from '../cli/html.js';
import { openBrowser, serve } from '../cli/serve.js';

const USAGE = `Usage:
  kicad-diff html OLD NEW [-o FILE] [options]   write a self-contained HTML diff
  kicad-diff serve [OLD NEW] [options]          serve the viewer on localhost and open it

OLD and NEW are KiCad files (.kicad_sch, .kicad_pcb, .kicad_sym, .kicad_mod), projects
(.kicad_pro, or a folder containing one), or either at a git revision: REV:path.
Use "-" for a side that does not exist (an added or removed file).

Options:
  -o, --output FILE        output file (html; default: kicad-diff.html)
  -c, --config FILE        configuration file (JSON, see src/config.js)
      --mode MODE          left | right | split | diff
      --ui THEME           light | dark | auto (interface colours)
      --color-theme SPEC   KiCad colour theme: a .json file, or pcm:<identifier> from the
                           KiCad add-on repository; repeat for several (users pick among them)
      --theme NAME         colour theme to start with
      --hide LAYERS        comma-separated layers or object classes to hide
      --project            treat a .kicad_sch as the root of a project
      --port N             port to serve on (default: any free port)
      --no-open            do not open a browser
  -h, --help               show this help`;

const { values: opts, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    output: { type: 'string', short: 'o' },
    config: { type: 'string', short: 'c' },
    mode: { type: 'string' },
    ui: { type: 'string' },
    'color-theme': { type: 'string', multiple: true, default: [] },
    theme: { type: 'string' },
    hide: { type: 'string' },
    project: { type: 'boolean', default: false },
    port: { type: 'string', default: '0' },
    'no-open': { type: 'boolean', default: false },
    help: { type: 'boolean', short: 'h' },
  },
});

/** DEFAULTS < config file < flags. Theme files and PCM packages are resolved into the config. */
async function buildConfig() {
  let file = {};
  if (opts.config) {
    file = JSON.parse(await readFile(opts.config, 'utf8'));
    // Theme files named in the config file are relative to it; embed them.
    const base = dirname(resolve(opts.config));
    file.colorThemes = await Promise.all((file.colorThemes ?? []).map(async t =>
      t.url && !/^[a-z]+:/.test(t.url) ? { name: t.name, theme: JSON.parse(await readFile(resolve(base, t.url), 'utf8')) } : t));
  }
  const themes = await resolveThemes(opts['color-theme']);
  return mergeConfig(DEFAULTS, file, {
    mode: opts.mode,
    uiTheme: opts.ui,
    colorTheme: opts.theme ?? themes[0]?.name,
    colorThemes: themes.length ? [...(file.colorThemes ?? []), ...themes] : undefined,
    hiddenLayers: opts.hide?.split(',').filter(Boolean),
  });
}

async function main() {
  const [command, oldSpec, newSpec] = positionals;
  if (opts.help || !['html', 'serve'].includes(command)) {
    console.log(USAGE);
    return opts.help ? 0 : 2;
  }
  const input = spec => (spec && spec !== '-' ? resolveInput(spec, { project: opts.project }) : null);
  const [old, nu] = await Promise.all([input(oldSpec), input(newSpec)]);
  if (command === 'html' && !old && !nu) throw new Error('html needs at least one input');
  const config = await buildConfig();

  if (command === 'html') {
    const out = opts.output ?? 'kicad-diff.html';
    await writeFile(out, await buildHtml({ old, new: nu, config, title: `${old?.name ?? '(none)'} → ${nu?.name ?? '(none)'}` }));
    console.log(`Wrote ${out}`);
    return 0;
  }
  const { url } = await serve({ old, new: nu, config, port: Number(opts.port), project: opts.project });
  console.log(`kicad-diff is running at ${url} (Ctrl+C to stop)`);
  if (!opts['no-open']) openBrowser(url);
  return null;
}

main().then(
  code => code !== null && process.exit(code),
  e => {
    console.error(`kicad-diff: ${e.message}`);
    process.exit(1);
  },
);
