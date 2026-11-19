import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { unzip } from '../../cli/zip.js';
import { fetchPcmTheme } from '../../cli/themes.js';
import { resolveInput } from '../../cli/inputs.js';
import { rewriteImports } from '../../cli/bundle.js';
import { serve } from '../../cli/serve.js';

const fixture = name => new URL(`../${name}`, import.meta.url).pathname;

test('zip reader handles stored and deflated entries', () => {
  const files = unzip(readFileSync(fixture('fixtures/theme-package.zip')));
  assert.deepEqual([...files.keys()].sort(), ['colors/test.json', 'metadata.json']);
  assert.equal(JSON.parse(files.get('colors/test.json')).meta.name, 'Test Theme');
});

test('PCM colour themes are downloaded and verified', async () => {
  const zip = readFileSync(fixture('fixtures/theme-package.zip'));
  const sha = createHash('sha256').update(zip).digest('hex');
  const server = createServer((req, res) => {
    const base = `http://127.0.0.1:${server.address().port}`;
    if (req.url === '/packages.json') {
      res.end(JSON.stringify({ packages: [{ identifier: 'test.theme', type: 'colortheme', name: 'T', versions: [{ download_url: `${base}/t.zip`, download_sha256: sha }] }] }));
    } else res.end(zip);
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const packagesUrl = `http://127.0.0.1:${server.address().port}/packages.json`;
  try {
    const themes = await fetchPcmTheme('test.theme', { packagesUrl });
    assert.equal(themes[0].name, 'Test Theme');
    await assert.rejects(() => fetchPcmTheme('missing', { packagesUrl }), /No colour theme/);
  } finally {
    server.close();
  }
});

test('relative imports become bare module names', () => {
  const src = "import { a } from './a.js';\nimport '../b/c.js';\nconst m = await import('../../vendor/x.js');";
  assert.equal(rewriteImports(src, 'kicad-diff/src/ui/x.js'),
    "import { a } from 'kicad-diff/src/ui/a.js';\nimport 'kicad-diff/src/b/c.js';\nconst m = await import('kicad-diff/vendor/x.js');");
});

test('inputs: files, project folders and git revisions', async () => {
  const file = await resolveInput(fixture('pairs/resistors/new.kicad_sch'));
  assert.equal(file.kind, 'file');
  assert.match(await file.load(file.entry), /kicad_sch/);
  assert.equal(await file.load('../../package.json'), null, 'nothing outside the input folder');

  const project = await resolveInput(fixture('pairs/project-new'));
  assert.deepEqual([project.kind, project.entry], ['project', 'demo.kicad_pro']);
  assert.equal(await project.load('../project-old/demo.kicad_sch'), null);

  const repo = mkdtempSync(join(tmpdir(), 'kicad-diff-'));
  const git = (...args) => execFileSync('git', ['-c', 'user.name=t', '-c', 'user.email=t@example.com', ...args], { cwd: repo });
  git('init', '-q');
  mkdirSync(join(repo, 'hw'));
  copyFileSync(fixture('pairs/resistors/old.kicad_sch'), join(repo, 'hw/r.kicad_sch'));
  git('add', '.');
  git('commit', '-qm', 'a');
  copyFileSync(fixture('pairs/resistors/new.kicad_sch'), join(repo, 'hw/r.kicad_sch'));
  git('commit', '-qam', 'b');
  const old = await resolveInput(`HEAD~1:${join(repo, 'hw/r.kicad_sch')}`);
  assert.equal(old.kind, 'file');
  assert.equal(await old.load(old.entry), readFileSync(fixture('pairs/resistors/old.kicad_sch'), 'utf8'));
});

test('serve: start page, inputs, configuration, and nothing else', async () => {
  const [old, nu] = await Promise.all([resolveInput(fixture('pairs/project-old')), resolveInput(fixture('pairs/project-new'))]);
  const { server, url } = await serve({ old, new: nu, config: { mode: 'split' } });
  const get = path => fetch(url + path.slice(1), { redirect: 'manual' });
  try {
    const start = await get('/');
    assert.equal(start.status, 302);
    assert.match(start.headers.get('location'), /project=1/);
    assert.equal((await (await get('/config.json')).json()).mode, 'split');
    assert.equal((await get('/files/new/resistors.kicad_sch')).status, 200);
    assert.equal((await get('/web/index.html')).status, 200);
    for (const bad of ['/package.json', '/files/new/..%2fproject-old%2fdemo.kicad_sch', '/test/pairs/resistors/old.kicad_sch', '/src/..%2fpackage.json']) {
      assert.equal((await get(bad)).status, 404, bad);
    }
  } finally {
    server.close();
  }
});
