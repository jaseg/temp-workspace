#!/usr/bin/env node
// Fetch KiCad's own test files and libraries into .cache/ for corpus tests.
// Each source can be overridden with an existing checkout via its env variable.

import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { CACHE, SOURCES } from './sources.js';

function git(cwd, ...args) {
  execFileSync('git', args, { cwd, stdio: 'inherit' });
}

function fetchSource({ name, url, ref, sparse }) {
  const dir = join(CACHE, name);
  if (existsSync(join(dir, '.git'))) {
    console.log(`${name}: already present`);
    return;
  }
  mkdirSync(dir, { recursive: true });
  git(dir, 'init', '-q');
  git(dir, 'remote', 'add', 'origin', url);
  if (sparse) git(dir, 'sparse-checkout', 'set', ...sparse);
  git(dir, 'fetch', '-q', '--depth', '1', '--filter=blob:none', 'origin', ref);
  git(dir, 'checkout', '-q', 'FETCH_HEAD');
}

const only = process.argv.slice(2);
for (const source of SOURCES) {
  if (only.length && !only.includes(source.name)) continue;
  if (process.env[source.env]) {
    console.log(`${source.name}: using ${process.env[source.env]}`);
    continue;
  }
  fetchSource(source);
}
