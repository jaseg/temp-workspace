// <kicad-diff>: the visual diff viewer.
//
// Attributes: old-src, new-src (URLs), mode (left | right | split | diff), ui-theme (light | dark | auto),
//             config-src (URL of a configuration file, see config.js).
// Properties: config (configuration object, see config.js).
// Methods:    setSources({old: {name, text}, new: {name, text}}) to pass file contents directly.
//
// Colours: left/right show the KiCad colour theme unchanged. The diff view (and the split view
// with its overlay on) tones the theme down, the old version more than the new one, and keeps
// bright colours for changes: a soft shade over each change's area and a bright highlight of the
// changed elements themselves.

import './viewport.js';
import { readKicad } from '../kicad/index.js';
import { isSchematicType, renderModel } from '../render/index.js';
import { boardColor, boardLayerOrder, loadTheme, parseColor, SCHEMATIC_LAYERS, schematicColor, schematicKey } from '../theme/themes.js';
import { diffFiles } from '../diff/index.js';
import { boxContains, unionBox, isEmptyBox } from '../geom.js';
import { changeArea, extract, isDark, itemIndices, PALETTE, tone } from './highlight.js';
import { createChangeList, renderInspector } from './changes.js';
import { annotationsSvg, exportAnnotations, hitAnnotation, importAnnotations, TOOLS } from './annotate.js';
import { STYLE } from './style.js';
import { DEFAULTS, mergeConfig } from '../config.js';

const MODES = [['left', 'Old'], ['right', 'New'], ['split', 'Split'], ['diff', 'Diff']];
const CLASSES = ['layout-minor', 'layout', 'metadata', 'electrical']; // drawn back to front
const classOf = c => (c.kind === 'layout' && c.minor ? 'layout-minor' : c.kind);

const SCHEMATIC_LABELS = {
  wire: 'Wires', bus: 'Buses', bus_entry: 'Bus entries', junction: 'Junctions', no_connect: 'No-connect flags',
  component_outline: 'Symbol graphics', component_body: 'Symbol fills', pin: 'Pins', pin_name: 'Pin names', pin_number: 'Pin numbers',
  reference: 'References', value: 'Values', fields: 'Other fields', label_local: 'Labels', label_global: 'Global labels',
  label_hier: 'Hierarchical labels', netclass_flag: 'Directive labels', sheet: 'Sheets', sheet_background: 'Sheet fills',
  sheet_label: 'Sheet pins', sheet_name: 'Sheet names', sheet_filename: 'Sheet files', sheet_fields: 'Sheet fields',
  notes: 'Text and graphics', note_background: 'Text box fills', rule_area: 'Rule areas', dnp_marker: 'DNP markers',
};

export class KicadDiff extends HTMLElement {
  static observedAttributes = ['old-src', 'new-src', 'mode', 'ui-theme', 'config-src'];

  constructor() {
    super();
    this.root = this.attachShadow({ mode: 'open' });
    this.files = { old: null, new: null };
    this.scenes = { old: null, new: null };
    this.changes = [];
    this.hiddenLayers = new Set();
    this.theme = loadTheme({});
    this.entry = undefined;
    this.overlay = true;
    this.annotations = [];
    this.tool = null;
    this._config = mergeConfig(DEFAULTS);
  }

  get config() {
    return this._config;
  }

  /** Apply a configuration (merged over the defaults). */
  set config(c) {
    this._config = mergeConfig(DEFAULTS, c);
    this.hiddenLayers = new Set(this._config.hiddenLayers);
    if (this.list) {
      Object.assign(this.list.state.filters, this._config.kinds);
      this.renderThemes();
      this.selectTheme(this._config.colorTheme);
      this.applyUiTheme();
      if (this.files.old || this.files.new) this.renderScenes();
    }
  }

  async loadConfig() {
    try {
      const res = await fetch(this.getAttribute('config-src'));
      if (res.ok) this.config = await res.json();
    } catch {
      // A missing configuration file leaves the defaults in place.
    }
  }

  connectedCallback() {
    // Browsers allow only a few WebGL contexts per page (think of a pull request with many KiCad
    // files), so viewports are created only once the viewer scrolls into view.
    this.io ??= new IntersectionObserver(entries => {
      this.inView = entries.some(e => e.isIntersecting);
      if (this.inView && this.pendingUpdate) this.update();
    });
    this.io.observe(this);
    if (!this.shell) {
      this.build();
      this.config = this._config;
      if (this.getAttribute('config-src')) this.loadConfig();
    }
    this.applyUiTheme();
    if (this.getAttribute('old-src') || this.getAttribute('new-src')) this.loadUrls();
    else if (!this.files.old && !this.files.new) this.showPicker();
  }

  attributeChangedCallback(name, before, after) {
    if (!this.shell || before === after) return;
    if (name === 'mode') this.update();
    else if (name === 'ui-theme') this.applyUiTheme();
    else if (name === 'config-src') this.loadConfig();
    else this.loadUrls();
  }

  get mode() {
    return this.getAttribute('mode') || this._config.mode || this.defaultMode || 'diff';
  }

  set mode(v) {
    this.setAttribute('mode', v);
  }

  build() {
    this.root.innerHTML = `<style>${STYLE}</style>
      <div class="toolbar">
        <span class="seg modes"></span>
        <button class="btn overlay" title="Show changes on top of both versions">Highlight changes</button>
        <select class="entry hidden" title="Library entry"></select>
        <select class="color-theme hidden" title="Colour theme"></select>
        <span class="spacer"></span>
        <button class="btn annotate" title="Draw annotations">Annotate</button>
        <button class="btn pdf" title="Download the diff as PDF, with annotations">PDF</button>
        <button class="btn fit" title="Fit to view (double-click)">Fit</button>
        <button class="btn ui-theme" title="Light/dark interface"></button>
      </div>
      <div class="toolbar annotations hidden">
        <span class="seg tools"></span>
        <input type="color" class="ann-color" value="#e53935" title="Colour">
        <button class="btn undo" title="Remove the last annotation">Undo</button>
        <span class="spacer"></span>
        <button class="btn export" title="Download annotations as JSON">Export JSON</button>
        <label class="btn" title="Load annotations from JSON">Import JSON<input type="file" class="import hidden" accept=".json,application/json"></label>
      </div>
      <div class="banner"></div>
      <div class="main"><div class="views"></div>
        <div class="side">
          <section class="changes"></section>
          <section class="inspector"></section>
          <details class="layers"><summary><h3>Layers</h3></summary><div class="list"></div></details>
        </div>
      </div>`;
    this.shell = true;
    this.tabIndex = 0;
    const $ = s => this.root.querySelector(s);
    this.el = {
      modes: $('.modes'), overlay: $('.overlay'), entry: $('.entry'), banner: $('.banner'), views: $('.views'),
      layers: $('.layers .list'), uiTheme: $('.ui-theme'), inspector: $('.inspector'), colorTheme: $('.color-theme'),
    };
    this.el.colorTheme.onchange = () => this.selectTheme(this.el.colorTheme.value);
    this.buildAnnotationTools($);
    for (const [mode, label] of MODES) {
      const b = document.createElement('button');
      b.textContent = label;
      b.dataset.mode = mode;
      b.onclick = () => (this.mode = mode);
      this.el.modes.append(b);
    }
    this.el.overlay.onclick = () => {
      this.overlay = !this.overlay;
      this.update();
    };
    $('.fit').onclick = () => this.fit();
    this.el.uiTheme.onclick = () => this.setAttribute('ui-theme', this.uiDark ? 'light' : 'dark');
    this.el.entry.onchange = () => {
      this.entry = this.el.entry.value;
      this.renderScenes();
    };
    this.list = createChangeList($('.changes'), {
      onSelect: c => this.selectChange(c),
      onFilter: () => this.update(),
    });
    renderInspector(this.el.inspector, {});
    this.addEventListener('keydown', e => {
      if (e.target !== this || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === 'n' || e.key === 'j') this.list.step(1);
      else if (e.key === 'p' || e.key === 'k') this.list.step(-1);
      else if (e.key === 'Escape') this.list.select(null);
      else if (e.key === 'f') this.fit();
      else return;
      e.preventDefault();
    });
  }

  buildAnnotationTools($) {
    const bar = $('.toolbar.annotations');
    $('.annotate').onclick = () => {
      const on = bar.classList.toggle('hidden') === false;
      $('.annotate').setAttribute('aria-pressed', String(on));
      this.setTool(on ? 'pen' : null);
    };
    for (const [tool, icon, title] of TOOLS) {
      const b = document.createElement('button');
      b.textContent = icon;
      b.title = title;
      b.dataset.tool = tool;
      b.onclick = () => this.setTool(tool);
      $('.tools').append(b);
    }
    $('.undo').onclick = () => {
      this.annotations.pop();
      this.redrawOverlays();
    };
    $('.export').onclick = async () => {
      const doc = await exportAnnotations(this.annotations, this.sources, { mode: this.mode, entry: this.entry });
      download('annotations.json', new Blob([JSON.stringify(doc, null, 1)], { type: 'application/json' }));
    };
    $('.import').onchange = async e => {
      const file = e.target.files[0];
      e.target.value = '';
      if (!file) return;
      try {
        const { annotations, warning } = await importAnnotations(await file.text(), this.sources);
        this.annotations = annotations;
        if (warning) this.el.banner.textContent = warning;
      } catch (err) {
        this.el.banner.textContent = `Could not import annotations: ${err.message}`;
      }
      this.redrawOverlays();
    };
    $('.pdf').onclick = () => this.exportPdf();
  }

  setTool(tool) {
    this.tool = tool;
    for (const b of this.root.querySelectorAll('.tools button')) b.setAttribute('aria-pressed', String(b.dataset.tool === tool));
    for (const v of this.viewports ?? []) v.panDisabled = !!tool;
  }

  redrawOverlays() {
    for (const v of this.viewports ?? []) this.drawOverlay(v);
  }

  /** Pointer input for the annotation tools, in model coordinates of viewport `v`. */
  bindAnnotationInput(v) {
    let current = null;
    const at = e => {
      const r = v.getBoundingClientRect();
      return v.toModel(e.clientX - r.left, e.clientY - r.top);
    };
    const px = () => devicePixelRatio / v.view.scale; // one CSS pixel in mm
    v.addEventListener('pointerdown', e => {
      if (!this.tool || e.button !== 0) return;
      const p = at(e);
      const color = this.root.querySelector('.ann-color').value;
      if (this.tool === 'erase') {
        const i = hitAnnotation(this.annotations, p, 4 * px());
        if (i >= 0) this.annotations.splice(i, 1);
        return this.redrawOverlays();
      }
      if (this.tool === 'text') return this.askText(v, e, p, color);
      current = this.tool === 'pen'
        ? { type: 'pen', points: [p], color, width: 2.5 * px() }
        : { type: this.tool, x0: p.x, y0: p.y, x1: p.x, y1: p.y, color, width: 2.5 * px() };
      this.annotations.push(current);
      v.setPointerCapture(e.pointerId);
    });
    v.addEventListener('pointermove', e => {
      if (!current) return;
      const p = at(e);
      if (current.type === 'pen') current.points.push(p);
      else Object.assign(current, { x1: p.x, y1: p.y });
      this.redrawOverlays();
    });
    v.addEventListener('pointerup', () => (current = null));
  }

  /** Text tool: an inline input at the click position. */
  askText(v, e, p, color) {
    const input = document.createElement('input');
    input.className = 'ann-input';
    const r = this.el.views.getBoundingClientRect();
    Object.assign(input.style, { left: `${e.clientX - r.left}px`, top: `${e.clientY - r.top - 14}px`, color });
    this.el.views.append(input);
    setTimeout(() => input.focus());
    const done = commit => {
      if (commit && input.value.trim()) {
        this.annotations.push({ type: 'text', x: p.x, y: p.y, text: input.value.trim(), size: (14 * devicePixelRatio) / v.view.scale, color });
      }
      input.remove();
      this.redrawOverlays();
    };
    input.onkeydown = ev => {
      ev.stopPropagation();
      if (ev.key === 'Enter') done(true);
      if (ev.key === 'Escape') done(false);
    };
    input.onblur = () => input.isConnected && done(true);
  }

  async exportPdf() {
    const { buildPdf } = await import('../render/pdf.js');
    const box = Object.values(this.scenes).filter(Boolean).map(s => s.bbox).reduce(unionBox);
    const bg = this.background();
    const pal = this.palette();
    const shades = this.list.visible().filter(c => c.area).map(c => ({ area: c.area, color: [...pal[c.kind].slice(0, 3), c.minor ? 0.06 : c.kind === 'layout' ? 0.1 : 0.16] }));
    const name = this.sources?.new?.name ?? this.sources?.old?.name ?? 'kicad-diff';
    const pages = [];
    if (this.scenes.old && this.scenes.new) pages.push({ title: `${name} — changes`, box, background: bg, passes: this.passesFor('diff'), shades, annotations: this.annotations });
    for (const side of ['old', 'new']) {
      if (this.scenes[side]) pages.push({ title: `${name} — ${side} version`, box, background: bg, passes: this.passesFor(side, { plain: true }) });
    }
    const json = await exportAnnotations(this.annotations, this.sources, { mode: this.mode, entry: this.entry });
    const bytes = await buildPdf({ title: name, pages, changes: this.list.visible(), attachment: { name: 'annotations.json', json } });
    download(name.replace(/\.kicad_\w+$/, '') + '-diff.pdf', new Blob([bytes], { type: 'application/pdf' }));
  }

  /** Colour themes offered: KiCad's default plus those named in the configuration. */
  renderThemes() {
    const names = ['KiCad Default', ...this._config.colorThemes.map(t => t.name)];
    this.el.colorTheme.classList.toggle('hidden', names.length < 2);
    this.el.colorTheme.replaceChildren(...names.map(n => Object.assign(document.createElement('option'), { textContent: n })));
  }

  async selectTheme(name) {
    const entry = this._config.colorThemes.find(t => t.name === name);
    let json = {};
    try {
      json = entry?.theme ?? (entry?.url ? await (await fetch(entry.url)).json() : {});
    } catch {
      // An unreadable theme falls back to the default colours.
    }
    this.theme = loadTheme(json);
    this.el.colorTheme.value = entry ? name : 'KiCad Default';
    if (this.files.old || this.files.new) {
      this.renderLayers();
      this.updatePasses();
    }
  }

  applyUiTheme() {
    const pref = this.getAttribute('ui-theme') || this._config.uiTheme || 'auto';
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
    this.allChanges = diffFiles(this.files.old, this.files.new);
    const entries = [...new Set(['old', 'new'].flatMap(s => this.files[s]?.model?.symbols?.map(d => d.name) ?? []))];
    this.el.entry.classList.toggle('hidden', entries.length < 2);
    this.el.entry.innerHTML = entries.map(e => `<option>${escapeHtml(e)}</option>`).join('');
    this.entry = this.allChanges.find(c => c.entry)?.entry ?? entries[0];
    this.el.entry.value = this.entry ?? '';
    this.defaultMode = this.files.old && this.files.new ? 'diff' : this.files.old ? 'left' : 'right';
    this.renderScenes();
  }

  renderScenes() {
    for (const side of ['old', 'new']) this.scenes[side] = this.files[side]?.model ? renderModel(this.files[side], { entry: this.entry }) : null;
    this.type = (this.files.new ?? this.files.old)?.type;
    // Library files show one entry at a time; list that entry's changes (and file-level ones).
    this.changes = (this.allChanges ?? []).filter(c => !c.entry || c.entry === this.entry);
    for (const c of this.changes) c.area = changeArea(c, this.scenes);
    this.highlights = this.buildHighlights();
    this.selected = null;
    this.list.setChanges(this.changes);
    renderInspector(this.el.inspector, {});
    this.renderBanner();
    this.renderLayers();
    this.update();
    this.fit();
  }

  /** Per version, one scene per change class holding the primitives of the changed elements. */
  buildHighlights() {
    const out = {};
    for (const side of ['old', 'new']) {
      out[side] = {};
      const scene = this.scenes[side];
      if (!scene) continue;
      for (const cls of CLASSES) {
        const changes = this.changes.filter(c => classOf(c) === cls);
        out[side][cls] = extract(scene, itemIndices(scene, changes.flatMap(c => c[side])), cls);
      }
    }
    return out;
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
    return parseColor(isSchematicType(this.type) ? this.theme.schematic.background : this.theme.board.background) ?? [1, 1, 1];
  }

  palette() {
    return PALETTE[isDark(this.background()) ? 'dark' : 'light'];
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

  disconnectedCallback() {
    this.io?.disconnect();
    this.io = null;
  }

  /** (Re)create the viewports for the current mode. */
  update() {
    for (const b of this.el.modes.children) b.setAttribute('aria-pressed', String(b.dataset.mode === this.mode));
    this.el.overlay.classList.toggle('hidden', this.mode !== 'split');
    this.el.overlay.setAttribute('aria-pressed', String(this.overlay));
    if (!this.files.old && !this.files.new) return;
    this.pendingUpdate = !this.inView;
    if (this.pendingUpdate) return;
    const sides = this.mode === 'split' ? ['old', 'new'] : this.mode === 'left' ? ['old'] : this.mode === 'right' ? ['new'] : ['diff'];
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
      v.addEventListener('kd-draw', () => this.drawOverlay(v));
      this.bindAnnotationInput(v);
      v.panDisabled = !!this.tool;
      v.addEventListener('kd-click', e => this.pickAt(v, e.detail));
      v.onViewChange = view => this.viewports.forEach(o => o !== v && o.setView(view, false));
      return v;
    });
    this.updatePasses();
    requestAnimationFrame(() => (prev && prev.scale !== 1 ? this.viewports.forEach(v => v.setView(prev, false)) : this.fit()));
  }

  /** Whether changes are shown in a viewport of the current mode. */
  showsChanges() {
    return this.mode === 'diff' || (this.mode === 'split' && this.overlay);
  }

  updatePasses() {
    for (const v of this.viewports ?? []) v.setPasses(this.passesFor(v.side), this.background());
  }

  /**
   * What to draw for a view: 'diff' (both versions toned, with highlights), or 'old'/'new' (one
   * version; toned with highlights when the split-view overlay is on, else plain KiCad colours).
   */
  passesFor(side, { plain = false } = {}) {
    const bg = this.background();
    const visible = this.layerNames().filter(n => !this.hiddenLayers.has(n));
    const base = k => visible.map(name => ({ name, color: k ? tone(this.colorOf(name), bg, k) : this.colorOf(name) }));
    const shown = new Set(this.list.visible().map(classOf));
    const pal = this.palette();
    const colorOf = cls => {
      const c = pal[cls === 'layout-minor' ? 'layout' : cls];
      return cls === 'layout-minor' ? [c[0], c[1], c[2], 0.55] : c;
    };
    const highlight = (side, alpha = 1) => CLASSES.filter(cls => shown.has(cls)).map(cls => ({
      scene: this.highlights[side]?.[cls], layers: [{ name: cls, color: colorOf(cls).map((v, i) => (i === 3 ? v * alpha : v)) }],
    }));
    const selection = side => (this.selectionScenes?.[side] ? [
      { scene: this.selectionScenes[side], layers: [{ name: 'sel', color: [...pal[this.selected.kind].slice(0, 3), 0.35] }], glowPx: 6, texts: false },
      { scene: this.selectionScenes[side], layers: [{ name: 'sel', color: pal[this.selected.kind] }] },
    ] : []);

    let passes;
    if (side === 'diff') {
      passes = [
        { scene: this.scenes.old, layers: base(this._config.tone.old) },
        { scene: this.scenes.new, layers: base(this._config.tone.new) },
        ...highlight('old', 0.6), ...highlight('new'), ...selection('old'), ...selection('new'),
      ];
    } else if (this.showsChanges() && !plain) {
      passes = [{ scene: this.scenes[side], layers: base(this._config.tone.new) }, ...highlight(side), ...selection(side)];
    } else {
      passes = [{ scene: this.scenes[side], layers: base(0) }, ...(plain ? [] : selection(side))];
    }
    return passes.filter(p => p.scene);
  }

  /** SVG overlay, redrawn with the view: soft shades over the areas of changes, and annotations. */
  drawOverlay(v) {
    const svg = v.overlay;
    const pal = this.palette();
    const css = (c, a) => `rgba(${Math.round(c[0] * 255)}, ${Math.round(c[1] * 255)}, ${Math.round(c[2] * 255)}, ${a})`;
    const rects = [];
    const changes = this.showsChanges() ? this.list.visible() : this.selected ? [this.selected] : [];
    const r = v.getBoundingClientRect();
    for (const c of changes) {
      if (!c.area) continue;
      const a = v.toScreen(c.area.x0, c.area.y0), b = v.toScreen(c.area.x1, c.area.y1);
      if (b.x < 0 || b.y < 0 || a.x > r.width || a.y > r.height) continue;
      const sel = c === this.selected;
      const alpha = sel ? 0.28 : c.minor ? 0.06 : c.kind === 'layout' ? 0.1 : 0.16;
      const w = Math.max(6, b.x - a.x), h = Math.max(6, b.y - a.y);
      const rad = Math.min(12, w / 4, h / 4);
      rects.push(`<rect x="${a.x}" y="${a.y}" width="${w}" height="${h}" rx="${rad}" fill="${css(pal[c.kind], alpha)}"${sel ? ` stroke="${css(pal[c.kind], 0.9)}" stroke-width="2"` : ''}/>`);
    }
    const s = v.view.scale / devicePixelRatio;
    svg.innerHTML = rects.join('') + annotationsSvg(this.annotations, (x, y) => v.toScreen(x, y), s);
  }

  selectChange(change) {
    this.selected = change;
    this.selectionScenes = change ? {
      old: this.scenes.old && extract(this.scenes.old, itemIndices(this.scenes.old, change.old), 'sel'),
      new: this.scenes.new && extract(this.scenes.new, itemIndices(this.scenes.new, change.new), 'sel'),
    } : null;
    renderInspector(this.el.inspector, { change });
    if (change?.entry && change.entry !== this.entry) {
      this.entry = change.entry;
      this.el.entry.value = change.entry;
    }
    this.updatePasses();
    if (change?.area) this.zoomTo(change.area);
  }

  /** Zoom to an area, but not closer than a sensible minimum size. */
  zoomTo(area) {
    const all = Object.values(this.scenes).filter(Boolean).map(s => s.bbox).reduce(unionBox);
    const min = Math.max(5, 0.08 * Math.max(all.x1 - all.x0, all.y1 - all.y0));
    const cx = (area.x0 + area.x1) / 2, cy = (area.y0 + area.y1) / 2;
    const hw = Math.max(min, area.x1 - area.x0) / 2, hh = Math.max(min, area.y1 - area.y0) / 2;
    this.viewports?.forEach(v => v.fit({ x0: cx - hw, y0: cy - hh, x1: cx + hw, y1: cy + hh }, 0.15));
  }

  /** Click on the canvas: select the change touching the clicked element, or describe the element. */
  pickAt(v, { x, y }) {
    const sides = v.side === 'diff' ? ['new', 'old'] : [v.side];
    for (const side of sides) {
      const scene = this.scenes[side];
      if (!scene) continue;
      const i = v.pick(scene, x, y);
      if (i < 0) continue;
      const item = scene.items[i];
      const keys = new Set([item.key, item.parent].filter(Boolean));
      const related = this.changes.filter(c => c[side].some(k => keys.has(k)));
      if (related.length === 1) return this.list.select(related[0].id);
      this.list.select(null, { notify: false });
      this.selectChange(null);
      return renderInspector(this.el.inspector, { item, related });
    }
    // Nothing under the cursor: maybe inside a change's shaded area.
    const p = v.toModel(x, y);
    const hit = this.list.visible().filter(c => c.area && boxContains(c.area, p.x, p.y));
    if (hit.length) this.list.select(hit[0].id);
  }

  fit() {
    const boxes = Object.values(this.scenes).filter(Boolean).map(s => s.bbox).filter(b => !isEmptyBox(b));
    if (!boxes.length) return;
    const box = boxes.reduce(unionBox);
    this.viewports?.forEach(v => v.fit(box));
  }
}

function download(name, blob) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

customElements.define('kicad-diff', KicadDiff);
