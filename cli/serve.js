// `kicad-diff serve`: serve the viewer on localhost and open it in a browser. With inputs, only
// those files (and the files of their projects) are served, under /files/old/ and /files/new/.

import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize, sep } from 'node:path';
import { spawn } from 'node:child_process';
import { PACKAGE_ROOT } from './bundle.js';

const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.json': 'application/json', '.css': 'text/css' };
const STATIC = ['web', 'src', 'vendor'];

function send(res, status, body, type = 'text/plain; charset=utf-8') {
  res.writeHead(status, { 'content-type': type, 'cache-control': 'no-store', 'x-content-type-options': 'nosniff' });
  res.end(body);
}

/** Start the server. Returns {server, url}. */
export async function serve({ old, new: nu, config, port = 0, host = '127.0.0.1', project = false }) {
  const inputs = { old, new: nu };
  const entry = (nu ?? old)?.entry;
  const isProject = [old, nu].some(i => i?.kind === 'project');
  const start = new URLSearchParams({ config: '/config.json' });
  if (old) start.set('old', `/files/old/${entry}`);
  if (nu) start.set('new', `/files/new/${entry}`);
  if (isProject || project) start.set('project', '1');

  const server = createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://localhost');
      const path = decodeURIComponent(url.pathname);
      if (path === '/') return res.writeHead(302, { location: `/web/index.html?${start}` }).end();
      if (path === '/config.json') return send(res, 200, JSON.stringify(config), TYPES['.json']);
      const files = /^\/files\/(old|new)\/(.*)$/.exec(path);
      if (files) {
        const input = inputs[files[1]];
        const rel = files[2].replace(/\/$/, '');
        if (!input || rel.split(/[/\\]/).includes('..')) return send(res, 404, 'Not found');
        if (url.searchParams.has('list')) {
          const list = await input.list(rel);
          return list ? send(res, 200, JSON.stringify(list), TYPES['.json']) : send(res, 404, 'Not found');
        }
        const text = await input.load(rel);
        return text === null ? send(res, 404, 'Not found') : send(res, 200, text);
      }
      // The viewer's own files.
      const rel = normalize(path).replace(/^[/\\]+/, '');
      if (!STATIC.includes(rel.split(sep)[0]) || rel.split(sep).includes('..')) return send(res, 404, 'Not found');
      return send(res, 200, await readFile(join(PACKAGE_ROOT, rel)), TYPES[extname(rel)] ?? 'application/octet-stream');
    } catch {
      return send(res, 404, 'Not found');
    }
  });
  await new Promise((resolve, reject) => server.once('error', reject).listen(port, host, resolve));
  const url = `http://${host}:${server.address().port}/`;
  return { server, url };
}

/** Open a URL in the default browser (best effort). */
export function openBrowser(url) {
  const [cmd, args] = process.platform === 'darwin' ? ['open', [url]] : process.platform === 'win32' ? ['cmd', ['/c', 'start', '', url]] : ['xdg-open', [url]];
  try {
    spawn(cmd, args, { stdio: 'ignore', detached: true }).on('error', () => {}).unref();
  } catch {
    // No browser available: the URL is printed anyway.
  }
}
