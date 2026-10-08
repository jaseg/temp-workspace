// <pb-preview2d>: shows the generated SVG with zoom/pan, overall dimensions and a color legend.
// Line colors are shown exactly as exported; only the backdrop adapts (per theme and per the
// configured colors) so that every line color stays visible.

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
  .dims { font-family: var(--mono); font-size: 12px; color: var(--text-muted); flex: 1; min-width: 0; }
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
  .stage svg .dim line { stroke: var(--dim-color); stroke-width: 1px; vector-effect: non-scaling-stroke; }
  .stage svg .dim text { fill: var(--dim-color); font-family: system-ui, sans-serif; }
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
  <div class="dims" aria-live="polite"></div>
  <div class="tools">
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

  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    root.append(template.content.cloneNode(true));
    this.#stage = root.querySelector(".stage");
    this.#dims = root.querySelector(".dims");
    this.#legend = root.querySelector(".legend");

    root.querySelector(".tools").addEventListener("click", (e) => {
      const action = e.target.closest("button")?.dataset.zoom;
      if (action === "fit") this.fit();
      else if (action) this.#zoomAt(action === "in" ? 1 / 1.4 : 1.4);
    });
    this.#stage.addEventListener("dblclick", () => this.fit());
    this.#stage.addEventListener("wheel", (e) => {
      e.preventDefault();
      this.#zoomAt(Math.exp(e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.0015)), e);
    }, { passive: false });
    this.#stage.addEventListener("pointerdown", (e) => {
      if (!this.#svg || e.button !== 0) return;
      this.#stage.setPointerCapture(e.pointerId);
      this.#stage.classList.add("dragging");
      this.#drag = { x: e.clientX, y: e.clientY, view: [...this.#view] };
    });
    this.#stage.addEventListener("pointermove", (e) => {
      if (!this.#drag) return;
      const scale = this.#unitsPerPixel();
      const [x, y, w, h] = this.#drag.view;
      this.#setView([x - (e.clientX - this.#drag.x) * scale, y - (e.clientY - this.#drag.y) * scale, w, h]);
      this.#zoomed = true;
    });
    const endDrag = () => { this.#drag = null; this.#stage.classList.remove("dragging"); };
    this.#stage.addEventListener("pointerup", endDrag);
    this.#stage.addEventListener("pointercancel", endDrag);
    this.#dark.addEventListener("change", () => this.#applyBackdrop());
  }

  /** Show a new SVG. `info` holds pattern dimensions, `legend` is [{label, color, kind}]. */
  update(svgText, info, legend) {
    const doc = new DOMParser().parseFromString(svgText, "image/svg+xml");
    const svg = document.importNode(doc.documentElement, true);
    if (svg.nodeName !== "svg") return;
    const base = svg.getAttribute("viewBox").split(/[\s,]+/).map(Number);
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    svg.removeAttribute("width");
    svg.removeAttribute("height");
    this.#addAnnotations(svg, base, info);

    const keepView = this.#zoomed && this.#view;
    this.#stage.replaceChildren(svg);
    this.#svg = svg;
    this.#base = base;
    if (keepView) this.#setView(this.#view);
    else this.fit();

    const [, , w, h] = base;
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

  #addAnnotations(svg, [, , w, h], info) {
    // Preview-only overlay (never exported): sheet boundary and overall dimension lines
    // drawn in the 10 mm margin.
    const g = document.createElementNS(NS, "g");
    g.setAttribute("class", "preview-overlay");
    const sheet = document.createElementNS(NS, "rect");
    Object.entries({ class: "sheet", x: 0, y: 0, width: w, height: h }).forEach(([k, v]) => sheet.setAttribute(k, v));
    g.append(sheet);
    const fs = Math.min(4, Math.max(2, Math.min(w, h) / 45));
    g.append(
      dimension(10, 5, 10 + info.pattern_width, 5, `${fmt(info.pattern_width)} mm`, fs, false),
      dimension(5, 10, 5, 10 + info.pattern_height, `${fmt(info.pattern_height)} mm`, fs, true),
    );
    svg.append(g);
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
    this.#stage.style.setProperty("--dim-color", lum > 0.3 ? "#5d6168" : "#b8bcc2");
    this.#stage.style.setProperty("--sheet-stroke", lum > 0.3 ? "#9a9da3" : "#6b7077");
  }
}

function dimension(x1, y1, x2, y2, text, fs, vertical) {
  const g = document.createElementNS(NS, "g");
  g.setAttribute("class", "dim");
  const tick = fs * 0.6;
  const lines = vertical
    ? [[x1, y1, x2, y2], [x1 - tick, y1, x1 + tick, y1], [x2 - tick, y2, x2 + tick, y2]]
    : [[x1, y1, x2, y2], [x1, y1 - tick, x1, y1 + tick], [x2, y2 - tick, x2, y2 + tick]];
  for (const [a, b, c, d] of lines) {
    const l = document.createElementNS(NS, "line");
    l.setAttribute("x1", a); l.setAttribute("y1", b); l.setAttribute("x2", c); l.setAttribute("y2", d);
    g.append(l);
  }
  const t = document.createElementNS(NS, "text");
  const cx = (x1 + x2) / 2;
  const cy = (y1 + y2) / 2;
  t.setAttribute("font-size", fs);
  t.setAttribute("text-anchor", "middle");
  if (vertical) {
    t.setAttribute("transform", `translate(${cx - fs * 0.35} ${cy}) rotate(-90)`);
  } else {
    t.setAttribute("x", cx);
    t.setAttribute("y", cy - fs * 0.35);
  }
  t.textContent = text;
  g.append(t);
  return g;
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
