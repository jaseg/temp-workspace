// <pb-preview2d>: shows the generated SVG with zoom/pan, parameter dimensions and a line-type
// legend. Lines are black, as exported; the backdrop adapts per theme so they stay visible.
// Fold dashes are drawn at a fixed screen size (the export's are in mm). Dimensions are a
// preview-only overlay; they are never part of the downloaded SVG.

import { DIM_STYLE, drawDims2d, highlightDims, labelPx } from "../dims2d.js";
import { LINE_STYLES, lineSwatch } from "../lines.js";
import { attachPanZoom, unitsPerPixel } from "../panzoom.js";

const NS = "http://www.w3.org/2000/svg";

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
  /* The lines are black, as exported: the sheet stays light in both themes. */
  .stage { position: relative; flex: 1; min-height: 0; cursor: grab; touch-action: none;
           background: #ffffff; --dim-color: #4f545b; --dim-halo: #ffffff;
           --dim-hl: #c2410c; --sheet-stroke: #9a9da3; }
  @media (prefers-color-scheme: dark) {
    .stage { background: #eceae4; --dim-halo: #eceae4; }
  }
  .stage.dragging { cursor: grabbing; }
  .stage svg { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
  /* Hairlines would be invisible on screen: draw them at a fixed screen width instead. */
  .stage svg path { vector-effect: non-scaling-stroke; stroke-width: 1.4px; }
  .stage svg #fold-mountain path { stroke-dasharray: ${LINE_STYLES.mountain.dash.join(" ")}; }
  .stage svg #fold-valley path { stroke-dasharray: ${LINE_STYLES.valley.dash.join(" ")}; }
  .stage svg .sheet { fill: none; stroke: var(--sheet-stroke); stroke-dasharray: 4 3;
                      stroke-width: 1px; vector-effect: non-scaling-stroke; }
  ${DIM_STYLE}
  .empty { position: absolute; inset: 0; display: grid; place-items: center; color: var(--text-muted); }
  .legend { display: flex; flex-wrap: wrap; gap: 4px 14px; padding: 6px 10px; font-size: 12px;
            border-top: 1px solid var(--border); }
  .legend span { display: inline-flex; align-items: center; gap: 6px; }
  .legend .swatch { color: var(--text); }
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
<div class="legend" aria-label="Line type legend"></div>
`;

export class PbPreview2d extends HTMLElement {
  #stage;
  #dims;
  #legend;
  #svg = null;
  #base = null; // full sheet viewBox [x, y, w, h]
  #view = null; // current viewBox
  #zoomed = false;
  #zoom; // zoom(factor): about the centre
  #highlight = null;
  #showDims = true;
  #dimData = []; // parameter dimensions in SVG user units
  #sheet = null; // [0, 0, w, h] of the exported sheet
  #overlay = null; // <g> holding the sheet outline and the dimensions
  #dimFs = 0; // label size (user units) the dimensions were last drawn at

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
        if (!this.#zoomed) this.fit();
        return;
      }
      const action = button?.dataset.zoom;
      if (action === "fit") this.fit();
      else if (action && this.#svg) this.#zoom(action === "in" ? 1 / 1.4 : 1.4);
    });
    this.#zoom = attachPanZoom(this.#stage, {
      view: () => (this.#svg ? this.#view : null),
      setView: (v) => {
        this.#zoomed = true;
        this.#setView(v);
      },
      minMax: () => [this.#base[2] / 200, this.#base[2] * 20],
      fit: () => this.fit(),
      dimClick: (param) => this.dispatchEvent(new CustomEvent("pb-dim-click", {
        bubbles: true, composed: true, detail: { param } })),
    }).zoom;
    new ResizeObserver(() => {
      if (!this.#svg) return;
      if (this.#zoomed) this.#drawDims();
      else this.fit();
    }).observe(this.#stage);
  }

  /** Show a new SVG. `info` holds pattern dimensions, `dims` the parameter dimensions in
   *  SVG user units. */
  update(svgText, info, dims = []) {
    const doc = new DOMParser().parseFromString(svgText, "image/svg+xml");
    const svg = document.importNode(doc.documentElement, true);
    if (svg.nodeName !== "svg") return;
    const sheet = svg.getAttribute("viewBox").split(/[\s,]+/).map(Number);
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    svg.removeAttribute("width");
    svg.removeAttribute("height");
    this.#addOverlay(svg, sheet);
    this.#dimData = dims;
    this.#sheet = sheet;

    const keepView = this.#zoomed && this.#view;
    this.#stage.replaceChildren(svg);
    this.#svg = svg;
    this.#dimFs = 0;
    if (keepView) this.#setView(this.#view);
    else this.fit();

    const [, , w, h] = sheet;
    this.#dims.textContent =
      `pattern ${fmt(info.pattern_width)} × ${fmt(info.pattern_height)} mm · ` +
      `sheet ${fmt(w)} × ${fmt(h)} mm (10 mm margin)`;

    // Legend: the line types present in this pattern.
    const present = ["cut", ...["mountain", "valley"].filter((t) => svg.querySelector(`#fold-${t}`))];
    this.#legend.replaceChildren(...present.map((t) => {
      const item = document.createElement("span");
      item.append(lineSwatch(LINE_STYLES[t].dash), LINE_STYLES[t].label);
      return item;
    }));
    this.highlight(this.#highlight);
  }

  /** Emphasise the dimensions of one parameter (or none). */
  highlight(param) {
    this.#highlight = param;
    if (this.#svg) highlightDims(this.#svg, param);
  }

  fit() {
    this.#zoomed = false;
    if (!this.#sheet) return;
    this.#base = this.#fitBox();
    this.#setView([...this.#base]);
  }

  /** viewBox fitting the sheet plus all dimensions. Labels have a fixed on-screen size, so
   *  their extent in user units depends on the fit's scale: iterate to a fixed point. */
  #fitBox() {
    const [, , w, h] = this.#sheet;
    let box = [0, 0, w, h];
    for (let i = 0; i < 4; i++) {
      const fs = labelPx(this) * unitsPerPixel(this.#stage, box);
      const { bounds } = drawDims2d(this.#dimData, { fs });
      let [x0, y0, x1, y1] = [0, 0, w, h];
      if (bounds && this.#showDims) {
        x0 = Math.min(x0, bounds[0] - fs);
        y0 = Math.min(y0, bounds[1] - fs);
        x1 = Math.max(x1, bounds[2] + fs);
        y1 = Math.max(y1, bounds[3] + fs);
      }
      box = [x0, y0, x1 - x0, y1 - y0];
    }
    return box;
  }

  #setView(v) {
    this.#view = v;
    this.#svg?.setAttribute("viewBox", v.map((n) => n.toFixed(4)).join(" "));
    this.#drawDims();
  }

  /** (Re)draw the dimensions so their labels are labelPx() screen pixels tall. */
  #drawDims() {
    if (!this.#overlay || !this.#view) return;
    const fs = labelPx(this) * unitsPerPixel(this.#stage, this.#view);
    if (this.#dimFs && Math.abs(fs / this.#dimFs - 1) < 1e-3) return; // panning only
    this.#dimFs = fs;
    this.#overlay.querySelector(".dims")?.remove();
    const { group } = drawDims2d(this.#dimData, { fs });
    group.classList.toggle("off", !this.#showDims);
    this.#overlay.append(group);
    highlightDims(this.#svg, this.#highlight);
  }

  #addOverlay(svg, [, , w, h]) {
    // Preview-only overlay (never exported): sheet boundary, plus the dimensions (#drawDims).
    const g = document.createElementNS(NS, "g");
    g.setAttribute("class", "preview-overlay");
    const sheet = document.createElementNS(NS, "rect");
    Object.entries({ class: "sheet", x: 0, y: 0, width: w, height: h }).forEach(([k, v]) => sheet.setAttribute(k, v));
    g.append(sheet);
    svg.append(g);
    this.#overlay = g;
  }
}

function fmt(v) {
  return Number(v).toFixed(1).replace(/\.0$/, "");
}

customElements.define("pb-preview2d", PbPreview2d);
