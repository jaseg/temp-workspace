// Command-line inputs: a KiCad file, a project (.kicad_pro or a folder containing one), or either
// of these at a git revision written as "REV:path" (e.g. "HEAD~1:board.kicad_pcb").
//
// An input becomes {kind: 'file' | 'project', entry, name, load(path), list(dir)}, with paths
// relative to the folder that contains the input; nothing outside that folder can be read.

import { execFile } from 'node:child_process';
import { existsSync } from 'node:fs';
import { readdir, readFile } from 'node:fs/promises';
import { basename, dirname, relative, resolve, sep } from 'node:path';
import { promisify } from 'node:util';

const run = promisify(execFile);

/** Files on disk, below the folder containing `spec`. */
function fsSource(spec) {
  const root = dirname(resolve(spec));
  const inside = p => {
    const full = resolve(root, p);
    return full.startsWith(root + sep) ? full : null;
  };
  return {
    name: basename(spec),
    entry: basename(spec),
    load: async p => (inside(p) ? readFile(inside(p), 'utf8').catch(() => null) : null),
    list: async p => (inside(p) ? readdir(inside(p)).catch(() => null) : null),
  };
}

/** Files at a git revision, below the folder containing `path`. */
async function gitSource(rev, path) {
  const cwd = dirname(resolve(path));
  const { stdout } = await run('git', ['rev-parse', '--show-toplevel'], { cwd });
  const dir = relative(stdout.trim(), cwd).split(sep).filter(Boolean).join('/');
  const at = p => `${rev}:${dir ? `${dir}/` : ''}${p}`;
  const safe = p => !p.split('/').includes('..');
  return {
    name: `${rev}:${basename(path)}`,
    entry: basename(path),
    load: p => (safe(p) ? run('git', ['show', at(p)], { cwd, maxBuffer: 1 << 30 }).then(r => r.stdout, () => null) : Promise.resolve(null)),
    list: p => (safe(p) ? run('git', ['ls-tree', '--name-only', at(p)], { cwd }).then(r => r.stdout.split('\n').filter(Boolean).map(f => basename(f)), () => null) : Promise.resolve(null)),
  };
}

/** Resolve one command-line input; `project` treats a .kicad_sch as the root of a project. */
export async function resolveInput(spec, { project = false } = {}) {
  const git = /^([^:\\/]+):(.+)$/.exec(spec);
  const src = git && !existsSync(spec) ? await gitSource(git[1], git[2]) : fsSource(spec);
  const { entry, name, load, list } = src;
  const files = await list(entry);
  if (files) {
    // A folder: compare the project inside it.
    const pro = files.find(f => f.endsWith('.kicad_pro'));
    if (!pro) throw new Error(`${spec}: no .kicad_pro in this folder`);
    const within = p => !p.split(/[/\\]/).includes('..');
    return {
      kind: 'project', entry: pro, name,
      load: async p => (within(p) ? load(`${entry}/${p}`) : null),
      list: async p => (within(p) ? list(`${entry}/${p}`) : null),
    };
  }
  if ((await load(entry)) === null) throw new Error(`${spec}: not found`);
  const kind = entry.endsWith('.kicad_pro') || (project && entry.endsWith('.kicad_sch')) ? 'project' : 'file';
  return { kind, entry, name, load, list };
}
