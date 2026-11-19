// <kicad-diff-project>: compares two versions of a KiCad project file by file.
//
// Attributes: old-src, new-src: URLs of the projects' .kicad_pro (or top-level .kicad_sch) files;
//             config-src, ui-theme as for <kicad-diff>. Property: config.
// Methods:    setProject({entry, old: {load, list?}, new: {load, list?}}) with loaders as in
//             kicad/project.js, e.g. for local folders or the CLI server.
//
// The landing page lists the project's topology (sheet hierarchy, board, libraries) with change
// counts per file; the per-file diffs run one after another in the background. Clicking a file
// opens it in <kicad-diff>.

import './kicad-diff.js';
import { readKicad } from '../kicad/index.js';
import { projectTopology, pairTopologies } from '../kicad/project.js';
import { diffFiles, KINDS } from '../diff/index.js';
import { STYLE } from './style.js';

const TYPE_LABELS = { schematic: 'Sheet', board: 'Board', symbol_lib: 'Symbols', footprint: 'Footprint' };

const PROJECT_STYLE = `
.project { flex: 1; overflow: auto; padding: 12px 16px; }
.project h2 { margin: 0 0 4px; font-size: 16px; }
.files { list-style: none; margin: 8px 0; padding: 0; }
.file { display: flex; gap: 8px; align-items: center; padding: 4px 6px; border-radius: 4px; cursor: pointer; }
.file:hover { background: var(--kd-hover); }
.file .type { font-size: 11px; color: var(--kd-muted); width: 64px; flex: none; }
.file .name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file .path { color: var(--kd-muted); margin-left: 6px; }
.counts { display: inline-flex; gap: 8px; margin-left: 6px; font-variant-numeric: tabular-nums; }
.file .counts { flex: none; margin: 0; }
.file .counts span { display: inline-flex; align-items: center; gap: 3px; }
.file .status { font-size: 11px; padding: 0 6px; border-radius: 8px; border: 1px solid var(--kd-border); flex: none; }
.file.unchanged .name { color: var(--kd-muted); }
.back { margin: 6px 8px; }
.viewer { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.viewer kicad-diff { flex: 1; border: 0; border-top: 1px solid var(--kd-border); border-radius: 0; }
`;

function urlLoader(entryUrl) {
  const base = new URL('.', new URL(entryUrl, location.href));
  return {
    async load(path) {
      const res = await fetch(new URL(path.split('/').map(encodeURIComponent).join('/'), base));
      return res.ok ? res.text() : null;
    },
    // Directory listings are available from the CLI server (?list); plain web servers return null.
    async list(dir) {
      const res = await fetch(new URL(`${dir.split('/').map(encodeURIComponent).join('/')}/?list`, base));
      return res.ok && res.headers.get('content-type')?.includes('json') ? res.json() : null;
    },
  };
}

export class KicadDiffProject extends HTMLElement {
  static observedAttributes = ['old-src', 'new-src', 'ui-theme', 'config-src'];

  constructor() {
    super();
    this.root = this.attachShadow({ mode: 'open' });
  }

  connectedCallback() {
    if (this.built) return;
    this.built = true;
    this.root.innerHTML = `<style>${STYLE}${PROJECT_STYLE}</style><div class="project"><p class="muted">Loading project…</p></div><div class="viewer hidden"></div>`;
    this.el = { project: this.root.querySelector('.project'), viewer: this.root.querySelector('.viewer') };
    const ui = this.getAttribute('ui-theme') ?? this.config?.uiTheme ?? 'auto';
    this.dataset.uiTheme = ui === 'dark' || (ui !== 'light' && matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
    const o = this.getAttribute('old-src'), n = this.getAttribute('new-src');
    if (o || n) {
      const entry = (n ?? o).split(/[?#]/)[0].split('/').pop();
      this.setProject({ entry: decodeURIComponent(entry), old: o && urlLoader(o), new: n && urlLoader(n) });
    }
  }

  /** {entry: 'name.kicad_pro', old: loader | null, new: loader | null} */
  async setProject({ entry, old, new: nu }) {
    this.loaders = { old, new: nu };
    const none = { name: '', nodes: [] };
    const [a, b] = await Promise.all([old ? projectTopology(entry, old) : none, nu ? projectTopology(entry, nu) : none]);
    this.name = b.name || a.name;
    this.nodes = pairTopologies(a, b).filter(n => !n.missing);
    this.results = new Map();
    this.renderList();
    for (const node of this.nodes) {
      if (!this.results.has(node.path)) this.results.set(node.path, await this.diffNode(node));
      this.renderList();
      await new Promise(r => setTimeout(r)); // keep the page responsive between files
    }
  }

  async diffNode(node) {
    const texts = {
      old: node.status !== 'added' ? await this.loaders.old?.load(node.path) : null,
      new: node.status !== 'removed' ? await this.loaders.new?.load(node.path) : null,
    };
    const files = { old: texts.old ? readKicad(texts.old) : null, new: texts.new ? readKicad(texts.new) : null };
    const changes = diffFiles(files.old, files.new);
    const warn = Object.values(files).some(f => f && (f.versionStatus !== 'ok' || f.errors.length));
    return { texts, changes, warn, unchanged: texts.old !== null && texts.old === texts.new };
  }

  renderList() {
    const total = Object.fromEntries(KINDS.map(k => [k, 0]));
    for (const r of new Set(this.results.values())) for (const c of r.changes) total[c.kind]++;
    const done = this.nodes.filter(n => this.results.has(n.path)).length;
    const counts = byKind => `<span class="counts">${KINDS.map(k => `<span title="${k}"><span class="dot ${k}"></span>${byKind[k]}</span>`).join('')}</span>`;
    const tally = changes => Object.fromEntries(KINDS.map(k => [k, changes.filter(c => c.kind === k).length]));
    this.el.project.innerHTML = `<h2></h2><p class="muted">${done < this.nodes.length ? `Comparing ${done + 1} of ${this.nodes.length} files…` : `${this.nodes.length} files compared.`} ${counts(total)}</p><ol class="files"></ol>`;
    this.el.project.querySelector('h2').textContent = this.name;
    const list = this.el.project.querySelector('.files');
    for (const node of this.nodes) {
      const r = this.results.get(node.path);
      const status = node.status === 'both' ? (r ? (r.unchanged || !r.changes.length ? 'unchanged' : 'changed') : '…') : node.status;
      const li = document.createElement('li');
      li.className = `file ${status}`;
      li.style.paddingLeft = `${6 + node.depth * 18}px`;
      li.innerHTML = `<span class="type">${TYPE_LABELS[node.type]}</span><span class="name"></span><span class="status">${status}</span>${r ? counts(tally(r.changes)) : ''}${r?.warn ? '<span title="Unsupported version or unreadable elements">⚠</span>' : ''}`;
      li.querySelector('.name').textContent = node.name;
      if (node.name !== node.path) {
        const p = document.createElement('span');
        p.className = 'path';
        p.textContent = node.path;
        li.querySelector('.name').append(p);
      }
      li.onclick = () => this.open(node);
      list.append(li);
    }
  }

  async open(node) {
    const r = this.results.get(node.path) ?? (await this.diffNode(node));
    this.el.project.classList.add('hidden');
    this.el.viewer.classList.remove('hidden');
    this.el.viewer.innerHTML = '<button class="btn back">← Project overview</button><kicad-diff></kicad-diff>';
    this.el.viewer.querySelector('.back').onclick = () => {
      this.el.viewer.classList.add('hidden');
      this.el.viewer.innerHTML = '';
      this.el.project.classList.remove('hidden');
    };
    const viewer = this.el.viewer.querySelector('kicad-diff');
    if (this.config) viewer.config = this.config;
    for (const a of ['ui-theme', 'config-src']) if (this.getAttribute(a)) viewer.setAttribute(a, this.getAttribute(a));
    viewer.setSources({ old: r.texts.old && { name: node.path, text: r.texts.old }, new: r.texts.new && { name: node.path, text: r.texts.new } });
  }
}

customElements.define('kicad-diff-project', KicadDiffProject);
