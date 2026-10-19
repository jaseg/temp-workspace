// <pb-preview2d>: shows the generated SVG with zoom/pan, parameter dimensions and a line-type
// legend. Lines are black, as exported; the backdrop adapts per theme so they stay visible.
// Fold dashes are drawn at a fixed screen size (the export's are in mm). Dimensions are a
// preview-only overlay; they are never part of the downloaded SVG. So is the PCB layout's
// copper (the security mesh), drawn into one bitmap under the lines (see meshtex.js).

import { DIM_STYLE, drawDims2d, highlightDims, labelPx } from "../dims2d.js";
import { LINE_STYLES, lineSwatch } from "../lines.js";
import { COPPER, rasterize } from "../meshtex.js";
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
  .legend .copper { width: 14px; height: 8px; border-radius: 2px; display: inline-block; }
  .stage svg image.mesh { image-rendering: auto; }
</style>
<header>
  <h2>Pattern</h2>
  <div class="size" aria-live="polite"></div>
  <div class="tools">
    <button type="button" data-mesh aria-pressed="false" title="Show the PCB layout's security mesh (both copper layers)">Mesh</button>
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
  #mesh = null; // {url, x, y, w, h}: the copper bitmap, in SVG user units
  #meshData = null; // the layout itself, for sharper bitmaps of a zoomed-in view
  #detail = null; // {url, x, y, w, h}: the visible part at screen resolution
  #detailTimer = 0;
  #meshButton;

  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    root.append(template.content.cloneNode(true));
    this.#stage = root.querySelector(".stage");
    this.#dims = root.querySelector(".size");
    this.#legend = root.querySelector(".legend");
    this.#meshButton = root.querySelector("[data-mesh]");

    root.querySelector(".tools").addEventListener("click", (e) => {
      const button = e.target.closest("button");
      if (button?.hasAttribute("data-mesh")) {
        this.dispatchEvent(new CustomEvent("pb-mesh-toggle", { bubbles: true, composed: true }));
        return;
      }
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

    this.#placeMesh();
    this.#drawLegend();
    this.highlight(this.#highlight);
  }

  /** Whether the Mesh button shows as on (the app owns the state). */
  set meshShown(on) {
    this.#meshButton.setAttribute("aria-pressed", String(Boolean(on)));
  }

  /** Show the PCB layout's copper (POST /api/pcb), or none. */
  setMesh(pcb) {
    if (this.#mesh?.url) URL.revokeObjectURL(this.#mesh.url);
    this.#mesh = null;
    this.#meshData = pcb;
    this.#dropDetail();
    if (!pcb) {
      this.#placeMesh();
      this.#drawLegend();
      return;
    }
    const { canvas, bbox } = rasterize(pcb, ["back", "front"], { alpha: { back: 0.55, front: 0.8 } });
    const [x0, y0, x1, y1] = bbox;
    const [dx, dy] = pcb.offset;
    const mesh = { url: null, x: x0 + dx, y: y0 + dy, w: x1 - x0, h: y1 - y0 };
    this.#mesh = mesh;
    canvas.toBlob((blob) => {
      if (this.#mesh !== mesh) return; // superseded meanwhile
      mesh.url = URL.createObjectURL(blob);
      this.#placeMesh();
      this.#drawLegend();
      this.#scheduleDetail();
    });
  }

  #dropDetail() {
    clearTimeout(this.#detailTimer);
    if (this.#detail?.url) URL.revokeObjectURL(this.#detail.url);
    this.#detail = null;
    this.#svg?.querySelector("image.mesh-detail")?.remove();
  }

  /** Zoomed in past the whole bitmap's resolution: draw the visible part again at screen
   *  resolution, once the view settles. */
  #scheduleDetail() {
    clearTimeout(this.#detailTimer);
    this.#detailTimer = setTimeout(() => this.#drawDetail(), 150);
  }

  #drawDetail() {
    const pcb = this.#meshData;
    const mesh = this.#mesh;
    if (!pcb || !mesh?.url || !this.#view || !this.#svg) return;
    // The visible area: the viewBox, grown to the stage's aspect ratio (it is "meet"-fitted).
    const [bx, by, bw, bh] = this.#view;
    const cw = this.#stage.clientWidth || 1;
    const ch = this.#stage.clientHeight || 1;
    const upp = Math.max(bw / cw, bh / ch);
    const [vw, vh] = [cw * upp, ch * upp];
    const [vx, vy] = [bx - (vw - bw) / 2, by - (vh - bh) / 2];
    const px = Math.max(cw, ch) * Math.min(devicePixelRatio, 2);
    const base = 4096 / Math.max(mesh.w, mesh.h); // px per mm of the whole bitmap
    if (px / Math.max(vw, vh) <= base * 1.2) {
      this.#dropDetail();
      return;
    }
    const [dx, dy] = pcb.offset;
    const region = [vx - dx, vy - dy, vx + vw - dx, vy + vh - dy];
    // Opaque, on the stage's colour: the blurrier whole bitmap must not show through.
    const background = getComputedStyle(this.#stage).backgroundColor;
    const { canvas } = rasterize(pcb, ["back", "front"], {
      maxSize: Math.ceil(px), region, background, alpha: { back: 0.55, front: 0.8 } });
    const detail = { url: null, x: vx, y: vy, w: vw, h: vh };
    canvas.toBlob((blob) => {
      if (this.#mesh !== mesh || this.#meshData !== pcb) return;
      this.#dropDetail();
      detail.url = URL.createObjectURL(blob);
      this.#detail = detail;
      const img = document.createElementNS(NS, "image");
      Object.entries({ class: "mesh-detail", href: detail.url, x: vx, y: vy, width: vw, height: vh,
        preserveAspectRatio: "none" }).forEach(([k, v]) => img.setAttribute(k, v));
      this.#svg.querySelector("image.mesh")?.after(img);
    });
  }

  /** (Re)insert the copper bitmap under the pattern's lines. */
  #placeMesh() {
    this.#svg?.querySelector("image.mesh")?.remove();
    this.#dropDetail();
    if (!this.#svg || !this.#mesh?.url) return;
    const img = document.createElementNS(NS, "image");
    const { url, x, y, w, h } = this.#mesh;
    Object.entries({ class: "mesh", href: url, x, y, width: w, height: h, preserveAspectRatio: "none" })
      .forEach(([k, v]) => img.setAttribute(k, v));
    this.#svg.insertBefore(img, this.#svg.firstChild);
  }

  /** Legend: the line types present in this pattern (and the copper layers, if shown). */
  #drawLegend() {
    if (!this.#svg) return;
    const present = ["cut", ...["mountain", "valley"].filter((t) => this.#svg.querySelector(`#fold-${t}`))];
    const items = present.map((t) => {
      const item = document.createElement("span");
      item.append(lineSwatch(LINE_STYLES[t].dash), LINE_STYLES[t].label);
      return item;
    });
    if (this.#mesh?.url) {
      for (const [layer, label] of [["front", "F.Cu (outside)"], ["back", "B.Cu (inside)"]]) {
        const item = document.createElement("span");
        const swatch = Object.assign(document.createElement("i"), { className: "copper" });
        swatch.style.background = COPPER[layer];
        item.append(swatch, label);
        items.push(item);
      }
    }
    this.#legend.replaceChildren(...items);
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
    if (this.#mesh?.url) this.#scheduleDetail();
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
