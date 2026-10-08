// <pb-preview2d>: shows the generated SVG with zoom/pan, parameter dimensions and a color
// legend. Line colors are shown exactly as exported; only the backdrop adapts (per theme and
// per the configured colors) so that every line color stays visible. Dimensions are a
// preview-only overlay; they are never part of the downloaded SVG.

import { DIM_STYLE, drawDims2d, highlightDims } from "../dims2d.js";

const NS = "http://www.w3.org/2000/svg";

const LIGHT_BACKDROPS = ["#ffffff", "#f1f0ec", "#c9ccd1", "#8d939b", "#3a3f47", "#1d2024"];
const DARK_BACKDROPS = ["#1d2024", "#2b3036", "#4a5058", "#8d939b", "#c9ccd1", "#eceae4"];

const template = document.createElement("template");
template.innerHTML = `
<style>
  :host { display: flex; flex-direction: column; min-height: 0; border: 1px solid var(--border);
          border-radius: var(--radius); background: var(--surface); overflow: hidden;
          box-shadow: var(--panel-shadow); }
  header { display: flex; align-items: center; gap: 10px; padding: 6px 10px;
           border-bottom: 1px solid var(--border); flex-wrap: wrap; }
  h2 { font-size: 13px; margin: 0; }
  .size { font-family: var(--mono); font-size: 12px; color: var(--text-muted); flex: 1; min-width: 0; }
  button[aria-pressed="true"] { background: var(--surface-2); border-color: var(--text-muted); }
  .tools { display: flex; gap: 4px; }
  button { font: inherit; color: inherit; background: var(--surface); border: 1px solid var(--border);
           border-radius: 5px; padding: 2px 9px; cursor: pointer; }
  button:hover { border-color: var(--text-muted); }
  .stage { position: relative; flex: 1; min-height: 0; cursor: grab; touch-action: none;
           transition: background-color 0.2s; }
  .stage.dragging { cursor: grabbing; }
  .stage svg { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
  /* Hairlines would be invisible on screen: draw them at a fixed screen width instead. */
  .stage svg path { vector-effect: non-scaling-stroke; stroke-width: 1.4px; }
  .stage svg .sheet { fill: none; stroke: var(--sheet-stroke); stroke-dasharray: 4 3;
                      stroke-width: 1px; vector-effect: non-scaling-stroke; }
  ${DIM_STYLE}
  .empty { position: absolute; inset: 0; display: grid; place-items: center; color: var(--text-muted); }
  .legend { display: flex; flex-wrap: wrap; gap: 4px 14px; padding: 6px 10px; font-size: 12px;
            border-top: 1px solid var(--border); }
  .legend span { display: inline-flex; align-items: center; gap: 6px; }
  .legend i { width: 22px; height: 0; border-top: 3px solid; border-radius: 2px; display: inline-block; }
  .legend i.fill { height: 10px; border: none; }
  .legend .stale { color: var(--error); }
</style>
<header>
  <h2>Pattern</h2>
  <div class="size" aria-live="polite"></div>
  <div class="tools">
    <button type="button" data-dims aria-pressed="true" title="Show parameter dimensions">Dimensions</button>
    <button type="button" data-zoom="out" title="Zoom out" aria-label="Zoom out">−</button>
    <button type="button" data-zoom="in" title="Zoom in" aria-label="Zoom in">+</button>
    <button type="button" data-zoom="fit" title="Fit to view (double-click)">Fit</button>
  </div>
</header>
<div class="stage" role="img" aria-label="2D pattern preview"><div class="empty">Rendering…</div></div>
<div class="legend" aria-label="Line color legend"></div>
`;

export class PbPreview2d extends HTMLElement {
  #stage;
  #dims;
  #legend;
  #svg = null;
  #base = null; // full sheet viewBox [x, y, w, h]
  #view = null; // current viewBox
  #zoomed = false;
  #colors = [];
  #drag = null;
  #dark = matchMedia("(prefers-color-scheme: dark)");
  #highlight = null;
  #moved = false;
  #downParam = null;
  #showDims = true;

  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    root.append(template.content.cloneNode(true));
    this.#stage = root.querySelector(".stage");
    this.#dims = root.querySelector(".size");
    this.#legend = root.querySelector(".legend");

    root.querySelector(".tools").addEventListener("click", (e) => {
      const button = e.target.closest("button");
      if (button?.hasAttribute("data-dims")) {
        this.#showDims = !this.#showDims;
        button.setAttribute("aria-pressed", String(this.#showDims));
        this.#svg?.querySelector(".dims")?.classList.toggle("off", !this.#showDims);
        return;
      }
      const action = button?.dataset.zoom;
      if (action === "fit") this.fit();
      else if (action) this.#zoomAt(action === "in" ? 1 / 1.4 : 1.4);
    });
    this.#stage.addEventListener("dblclick", () => this.fit());
    // Clicking a dimension asks the app to focus the parameter it shows.
    // (Pointer capture for panning retargets the click to the stage, so remember the
    // dimension that was under the pointer when it went down.)
    this.#stage.addEventListener("click", () => {
      const param = this.#downParam;
      if (param && !this.#moved) {
        this.dispatchEvent(new CustomEvent("pb-dim-click", { bubbles: true, composed: true, detail: { param } }));
      }
    });
    this.#stage.addEventListener("wheel", (e) => {
      e.preventDefault();
      this.#zoomAt(Math.exp(e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.0015)), e);
    }, { passive: false });
    this.#stage.addEventListener("pointerdown", (e) => {
      if (!this.#svg || e.button !== 0) return;
      this.#stage.setPointerCapture(e.pointerId);
      this.#stage.classList.add("dragging");
      this.#drag = { x: e.clientX, y: e.clientY, view: [...this.#view] };
      this.#moved = false;
      this.#downParam = e.target.closest?.(".dim")?.dataset.param ?? null;
    });
    this.#stage.addEventListener("pointermove", (e) => {
      if (!this.#drag) return;
      const scale = this.#unitsPerPixel();
      const [x, y, w, h] = this.#drag.view;
      if (Math.hypot(e.clientX - this.#drag.x, e.clientY - this.#drag.y) > 3) this.#moved = true;
      this.#setView([x - (e.clientX - this.#drag.x) * scale, y - (e.clientY - this.#drag.y) * scale, w, h]);
      this.#zoomed = true;
    });
    const endDrag = () => { this.#drag = null; this.#stage.classList.remove("dragging"); };
    this.#stage.addEventListener("pointerup", endDrag);
    this.#stage.addEventListener("pointercancel", endDrag);
    this.#dark.addEventListener("change", () => this.#applyBackdrop());
  }

  /** Show a new SVG. `info` holds pattern dimensions, `legend` is [{label, color, kind}],
   *  `dims` the parameter dimensions in SVG user units. */
  update(svgText, info, legend, dims = []) {
    const doc = new DOMParser().parseFromString(svgText, "image/svg+xml");
    const svg = document.importNode(doc.documentElement, true);
    if (svg.nodeName !== "svg") return;
    const sheet = svg.getAttribute("viewBox").split(/[\s,]+/).map(Number);
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    svg.removeAttribute("width");
    svg.removeAttribute("height");
    const base = this.#addAnnotations(svg, sheet, dims);

    const keepView = this.#zoomed && this.#view;
    this.#stage.replaceChildren(svg);
    this.#svg = svg;
    this.#base = base;
    if (keepView) this.#setView(this.#view);
    else this.fit();

    const [, , w, h] = sheet;
    this.#dims.textContent =
      `pattern ${fmt(info.pattern_width)} × ${fmt(info.pattern_height)} mm · ` +
      `sheet ${fmt(w)} × ${fmt(h)} mm (10 mm margin)`;

    this.#colors = legend.map((l) => l.color);
    this.#legend.replaceChildren(...legend.map((l) => {
      const item = document.createElement("span");
      const swatch = document.createElement("i");
      if (l.kind === "fill") { swatch.className = "fill"; swatch.style.background = l.color; }
      else swatch.style.borderTopColor = l.color;
      item.append(swatch, `${l.label} `);
      const code = document.createElement("code");
      code.textContent = l.color;
      item.append(code);
      return item;
    }));
    this.#applyBackdrop();
    this.highlight(this.#highlight);
  }

  /** Emphasise the dimensions of one parameter (or none). */
  highlight(param) {
    this.#highlight = param;
    if (this.#svg) highlightDims(this.#svg, param);
  }

  fit() {
    this.#zoomed = false;
    if (this.#base) this.#setView([...this.#base]);
  }

  #setView(v) {
    this.#view = v;
    this.#svg?.setAttribute("viewBox", v.map((n) => n.toFixed(4)).join(" "));
  }

  #unitsPerPixel() {
    const r = this.#stage.getBoundingClientRect();
    const [, , w, h] = this.#view;
    return Math.max(w / r.width, h / r.height);
  }

  #zoomAt(factor, event) {
    if (!this.#svg) return;
    const r = this.#stage.getBoundingClientRect();
    const [x, y, w, h] = this.#view;
    const scale = this.#unitsPerPixel();
    // Point under the cursor (or the centre) in user units; keep it fixed while zooming.
    const px = event ? event.clientX - r.left : r.width / 2;
    const py = event ? event.clientY - r.top : r.height / 2;
    const ux = x + w / 2 + (px - r.width / 2) * scale;
    const uy = y + h / 2 + (py - r.height / 2) * scale;
    const nw = Math.min(Math.max(w * factor, this.#base[2] / 200), this.#base[2] * 20);
    const k = nw / w;
    const nh = h * k;
    this.#setView([ux - (ux - x) * k, uy - (uy - y) * k, nw, nh]);
    this.#zoomed = true;
  }

  #addAnnotations(svg, [, , w, h], dims) {
    // Preview-only overlay (never exported): sheet boundary and parameter dimensions. Returns
    // the viewBox that fits the sheet plus all annotations.
    const g = document.createElementNS(NS, "g");
    g.setAttribute("class", "preview-overlay");
    const sheet = document.createElementNS(NS, "rect");
    Object.entries({ class: "sheet", x: 0, y: 0, width: w, height: h }).forEach(([k, v]) => sheet.setAttribute(k, v));
    g.append(sheet);
    const fs = Math.min(14, Math.max(3, Math.min(w, h) / 26));
    const { group, bounds } = drawDims2d(dims, { fs });
    group.classList.toggle("off", !this.#showDims);
    g.append(group);
    svg.append(g);
    let [x0, y0, x1, y1] = [0, 0, w, h];
    if (bounds) {
      x0 = Math.min(x0, bounds[0] - fs);
      y0 = Math.min(y0, bounds[1] - fs);
      x1 = Math.max(x1, bounds[2] + fs);
      y1 = Math.max(y1, bounds[3] + fs);
    }
    return [x0, y0, x1 - x0, y1 - y0];
  }

  #applyBackdrop() {
    const dark = this.#dark.matches;
    const candidates = dark ? DARK_BACKDROPS : LIGHT_BACKDROPS;
    // Pick the backdrop with the best worst-case contrast against all line colors; earlier
    // (theme-appropriate) candidates win ties within a small tolerance.
    let best = candidates[0];
    let bestScore = -1;
    for (const bg of candidates) {
      const score = Math.min(...this.#colors.map((c) => contrast(bg, c)));
      if (score > bestScore + 0.25) { best = bg; bestScore = score; }
    }
    const lum = luminance(best);
    this.#stage.style.backgroundColor = best;
    this.#stage.style.setProperty("--dim-color", lum > 0.3 ? "#4f545b" : "#c3c7cc");
    this.#stage.style.setProperty("--dim-halo", best);
    this.#stage.style.setProperty("--dim-hl", lum > 0.3 ? "#c2410c" : "#ffb35c");
    this.#stage.style.setProperty("--sheet-stroke", lum > 0.3 ? "#9a9da3" : "#6b7077");
  }
}

function fmt(v) {
  return Number(v).toFixed(1).replace(/\.0$/, "");
}

function luminance(hex) {
  const n = parseInt(hex.slice(1), 16);
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
}

function contrast(a, b) {
  const [l1, l2] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}

customElements.define("pb-preview2d", PbPreview2d);
