// `kicad-diff html`: one self-contained HTML file with the viewer, the compared files and the
// configuration (including colour themes) inlined. Opens offline, from file://.

import { importMap, scriptJson } from './bundle.js';
import { projectTopology } from '../src/kicad/project.js';

/** Contents of a side: a single file, or every file of a project's topology. */
async function collect(input) {
  if (!input) return null;
  if (input.kind === 'file') return { kind: 'file', name: input.name, text: await input.load(input.entry) };
  const files = {};
  const dirs = {};
  const load = async p => (p in files ? files[p] : (files[p] = await input.load(p)));
  const list = async d => (d in dirs ? dirs[d] : (dirs[d] = await input.list(d)));
  await projectTopology(input.entry, { load, list });
  return { kind: 'project', entry: input.entry, name: input.name, files, dirs };
}

// Runs in the page: start the right element with in-memory sources.
const BOOT = `
import 'kicad-diff/src/ui/kicad-diff.js';
import 'kicad-diff/src/ui/project.js';
const data = JSON.parse(document.getElementById('kicad-diff-data').textContent);
const memory = side => side && {
  load: async path => side.files[path] ?? null,
  list: async dir => side.dirs[dir] ?? null,
};
const project = [data.old, data.new].some(s => s?.kind === 'project');
const el = document.createElement(project ? 'kicad-diff-project' : 'kicad-diff');
el.config = data.config;
document.body.append(el);
if (project) {
  el.setProject({ entry: (data.new ?? data.old).entry, old: memory(data.old), new: memory(data.new) });
} else {
  el.setSources({ old: data.old && { name: data.old.name, text: data.old.text }, new: data.new && { name: data.new.name, text: data.new.text } });
}
`;

export async function buildHtml({ old, new: nu, config, title }) {
  const data = { old: await collect(old), new: await collect(nu), config };
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${(title ?? 'KiCad diff').replace(/[<&]/g, c => ({ '<': '&lt;', '&': '&amp;' })[c])}</title>
<style>html, body { height: 100%; margin: 0; } body { padding: 8px; box-sizing: border-box; background: Canvas; color: CanvasText; } kicad-diff, kicad-diff-project { height: 100%; }</style>
<script type="importmap">${scriptJson(await importMap())}</script>
<script type="application/json" id="kicad-diff-data">${scriptJson(data)}</script>
</head>
<body>
<script type="module">${BOOT}</script>
</body>
</html>
`;
}
