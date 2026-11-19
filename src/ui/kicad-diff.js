// <kicad-diff>: the visual diff viewer.
//
// Attributes: old-src, new-src (URLs), mode (left | right | split | diff), ui-theme (light | dark | auto).
// Properties: setSources({old: {name, text}, new: {name, text}}) to pass file contents directly.

import './viewport.js';
import { readKicad } from '../kicad/index.js';
import { isSchematicType, renderModel } from '../render/index.js';
import { boardColor, boardLayerOrder, loadTheme, parseColor, SCHEMATIC_LAYERS, schematicColor, schematicKey } from '../theme/themes.js';
import { unionBox, isEmptyBox } from '../geom.js';
import { STYLE } from './style.js';

const MODES = [['left', 'Old'], ['right', 'New'], ['split', 'Split']];

const SCHEMATIC_LABELS = {
  wire: 'Wires', bus: 'Buses', bus_entry: 'Bus entries', junction: 'Junctions', no_connect: 'No-connect flags',
  component_outline: 'Symbol graphics', component_body: 'Symbol fills', pin: 'Pins', pin_name: 'Pin names', pin_number: 'Pin numbers',
  reference: 'References', value: 'Values', fields: 'Other fields', label_local: 'Labels', label_global: 'Global labels',
  label_hier: 'Hierarchical labels', netclass_flag: 'Directive labels', sheet: 'Sheets', sheet_background: 'Sheet fills',
  sheet_label: 'Sheet pins', sheet_name: 'Sheet names', sheet_filename: 'Sheet files', sheet_fields: 'Sheet fields',
  notes: 'Text and graphics', note_background: 'Text box fills', rule_area: 'Rule areas', dnp_marker: 'DNP markers',
};

export class KicadDiff extends HTMLElement {
  static observedAttributes = ['old-src', 'new-src', 'mode', 'ui-theme'];

  constructor() {
    super();
    this.root = this.attachShadow({ mode: 'open' });
    this.files = { old: null, new: null };
    this.scenes = { old: null, new: null };
    this.hiddenLayers = new Set();
    this.theme = loadTheme({});
    this.entry = undefined;
  }

  connectedCallback() {
    if (!this.shell) this.build();
    this.applyUiTheme();
    if (this.getAttribute('old-src') || this.getAttribute('new-src')) this.loadUrls();
    else if (!this.files.old && !this.files.new) this.showPicker();
  }

  attributeChangedCallback(name, before, after) {
    if (!this.shell || before === after) return;
    if (name === 'mode') this.update();
    else if (name === 'ui-theme') this.applyUiTheme();
    else this.loadUrls();
  }

  get mode() {
    return this.getAttribute('mode') || this.defaultMode || 'split';
  }

  set mode(v) {
    this.setAttribute('mode', v);
  }

  build() {
    this.root.innerHTML = `<style>${STYLE}</style>
      <div class="toolbar">
        <span class="seg modes"></span>
        <select class="entry hidden" title="Library entry"></select>
        <span class="spacer"></span>
        <button class="btn fit" title="Fit to view (double-click)">Fit</button>
        <button class="btn ui-theme" title="Light/dark interface"></button>
      </div>
      <div class="banner"></div>
      <div class="main"><div class="views"></div><div class="side"><section class="layers"><h3>Layers</h3><div class="list"></div></section></div></div>`;
    this.shell = true;
    const $ = s => this.root.querySelector(s);
    this.el = { modes: $('.modes'), entry: $('.entry'), banner: $('.banner'), views: $('.views'), layers: $('.layers .list'), uiTheme: $('.ui-theme') };
    for (const [mode, label] of MODES) {
      const b = document.createElement('button');
      b.textContent = label;
      b.dataset.mode = mode;
      b.onclick = () => (this.mode = mode);
      this.el.modes.append(b);
    }
    $('.fit').onclick = () => this.fit();
    this.el.uiTheme.onclick = () => this.setAttribute('ui-theme', this.uiDark ? 'light' : 'dark');
    this.el.entry.onchange = () => {
      this.entry = this.el.entry.value;
      this.renderScenes();
    };
  }

  applyUiTheme() {
    const pref = this.getAttribute('ui-theme') || 'auto';
    this.uiDark = pref === 'dark' || (pref === 'auto' && matchMedia('(prefers-color-scheme: dark)').matches);
    this.dataset.uiTheme = this.uiDark ? 'dark' : 'light';
    this.el.uiTheme.textContent = this.uiDark ? '☀' : '☾';
  }

  /** Load old-src/new-src; several attribute changes in a row trigger a single load. */
  loadUrls() {
    if (this.loading) return;
    this.loading = true;
    queueMicrotask(() => {
      this.loading = false;
      this.fetchSources();
    });
  }

  async fetchSources() {
    const fetchText = async url => {
      if (!url) return null;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`${url}: ${res.status} ${res.statusText}`);
      return { name: decodeURIComponent(url.split(/[?#]/)[0].split('/').pop()), text: await res.text() };
    };
    try {
      const [o, n] = await Promise.all([fetchText(this.getAttribute('old-src')), fetchText(this.getAttribute('new-src'))]);
      this.setSources({ old: o, new: n });
    } catch (e) {
      this.el.views.innerHTML = `<div class="empty">Could not load: ${escapeHtml(e.message)}</div>`;
    }
  }

  /** Show file inputs when no sources were given. */
  showPicker() {
    this.el.views.innerHTML = `<div class="empty"><div class="pick">
      <label for="o">Old version</label><input id="o" type="file" accept=".kicad_sch,.kicad_pcb,.kicad_sym,.kicad_mod">
      <label for="n">New version</label><input id="n" type="file" accept=".kicad_sch,.kicad_pcb,.kicad_sym,.kicad_mod">
      <span></span><button class="btn">Compare</button></div></div>`;
    const [o, n] = this.el.views.querySelectorAll('input');
    const read = async input => (input.files[0] ? { name: input.files[0].name, text: await input.files[0].text() } : null);
    this.el.views.querySelector('button').onclick = async () => this.setSources({ old: await read(o), new: await read(n) });
  }

  /** Load file contents: {old: {name, text} | null, new: {name, text} | null}. */
  setSources(sources) {
    this.sources = sources;
    for (const side of ['old', 'new']) this.files[side] = sources[side] ? readKicad(sources[side].text) : null;
    const entries = [...new Set(['old', 'new'].flatMap(s => this.files[s]?.model?.symbols?.map(d => d.name) ?? []))];
    this.el.entry.classList.toggle('hidden', entries.length < 2);
    this.el.entry.innerHTML = entries.map(e => `<option>${escapeHtml(e)}</option>`).join('');
    this.entry = entries[0];
    this.defaultMode = this.files.old && this.files.new ? 'split' : this.files.old ? 'left' : 'right';
    this.renderScenes();
  }

  renderScenes() {
    for (const side of ['old', 'new']) this.scenes[side] = this.files[side]?.model ? renderModel(this.files[side], { entry: this.entry }) : null;
    this.type = (this.files.new ?? this.files.old)?.type;
    this.renderBanner();
    this.renderLayers();
    this.update();
    this.fit();
  }

  renderBanner() {
    const msgs = [];
    for (const [side, label] of [['old', 'Old version'], ['new', 'New version']]) {
      const f = this.files[side];
      if (!f) continue;
      if (!f.model) msgs.push(`${label}: not a readable KiCad file.`);
      else if (f.versionStatus === 'older') msgs.push(`${label}: file format ${f.version} predates KiCad 10; shown on a best-effort basis.`);
      else if (f.versionStatus === 'newer') msgs.push(`${label}: file format ${f.version} is newer than this viewer supports; some elements may be missing.`);
      else if (f.versionStatus === 'unknown') msgs.push(`${label}: unknown file format version.`);
      const bad = f.errors.length + (this.scenes[side]?.errors.length ?? 0);
      if (bad) msgs.push(`${label}: ${bad} element${bad > 1 ? 's' : ''} could not be read and ${bad > 1 ? 'are' : 'is'} not shown.`);
      const unknown = [...f.unhandled.values()].reduce((a, b) => a + b, 0);
      if (unknown && f.versionStatus === 'ok') msgs.push(`${label}: ${unknown} unsupported element${unknown > 1 ? 's' : ''} ignored.`);
    }
    this.el.banner.textContent = msgs.join(' ');
  }

  /** Layer names present in either version, back to front. */
  layerNames() {
    const names = new Set();
    for (const s of Object.values(this.scenes)) for (const n of s?.layers.keys() ?? []) names.add(n);
    return isSchematicType(this.type) ? SCHEMATIC_LAYERS.filter(n => names.has(n)) : boardLayerOrder([...names]);
  }

  colorOf(layer) {
    return isSchematicType(this.type) ? schematicColor(this.theme, schematicKey(layer)) : boardColor(this.theme, layer);
  }

  background() {
    const c = parseColor(isSchematicType(this.type) ? this.theme.schematic.background : this.theme.board.background);
    return c ?? [1, 1, 1];
  }

  renderLayers() {
    const list = this.el.layers;
    list.innerHTML = '';
    for (const name of this.layerNames()) {
      const label = document.createElement('label');
      const c = this.colorOf(name);
      label.innerHTML = `<input type="checkbox" ${this.hiddenLayers.has(name) ? '' : 'checked'}><span class="swatch" style="background: rgba(${c[0] * 255},${c[1] * 255},${c[2] * 255},${c[3]})"></span><span></span>`;
      label.lastChild.textContent = isSchematicType(this.type) ? SCHEMATIC_LABELS[name] ?? name : name === 'holes' ? 'Holes' : name;
      label.firstChild.onchange = e => {
        e.target.checked ? this.hiddenLayers.delete(name) : this.hiddenLayers.add(name);
        this.updatePasses();
      };
      list.append(label);
    }
  }

  /** (Re)create the viewports for the current mode. */
  update() {
    for (const b of this.el.modes.children) b.setAttribute('aria-pressed', String(b.dataset.mode === this.mode));
    if (!this.files.old && !this.files.new) return;
    const sides = this.mode === 'split' ? ['old', 'new'] : this.mode === 'left' ? ['old'] : ['new'];
    const prev = this.viewports?.[0]?.view;
    this.el.views.innerHTML = '';
    this.viewports = sides.map(side => {
      const v = document.createElement('kd-viewport');
      v.side = side;
      this.el.views.append(v);
      if (sides.length > 1) {
        const cap = document.createElement('div');
        cap.className = 'caption';
        cap.textContent = side === 'old' ? 'Old' : 'New';
        cap.style.left = side === 'old' ? '6px' : 'calc(50% + 6px)';
        this.el.views.append(cap);
      }
      v.addEventListener('kd-fit', () => this.fit());
      v.onViewChange = view => this.viewports.forEach(o => o !== v && o.setView(view, false));
      return v;
    });
    this.updatePasses();
    requestAnimationFrame(() => (prev && prev.scale !== 1 ? this.viewports.forEach(v => v.setView(prev, false)) : this.fit()));
  }

  updatePasses() {
    const layers = this.layerNames().filter(n => !this.hiddenLayers.has(n)).map(name => ({ name, color: this.colorOf(name) }));
    for (const v of this.viewports ?? []) v.setPasses([{ scene: this.scenes[v.side], layers }], this.background());
  }

  fit() {
    const boxes = Object.values(this.scenes).filter(Boolean).map(s => s.bbox).filter(b => !isEmptyBox(b));
    if (!boxes.length) return;
    const box = boxes.reduce(unionBox);
    this.viewports?.forEach(v => v.fit(box));
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

customElements.define('kicad-diff', KicadDiff);
