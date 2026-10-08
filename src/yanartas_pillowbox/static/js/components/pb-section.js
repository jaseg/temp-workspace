// <pb-section>: 2D cross-section of the closed box body (perpendicular to its length), as
// computed by geometry.build_cross_section. The body is a cylinder between the curved folds,
// so this section holds along the whole straight part of the box.

import { DIM_STYLE, drawDims2d, highlightDims } from "../dims2d.js";

const NS = "http://www.w3.org/2000/svg";

const template = document.createElement("template");
template.innerHTML = `
<style>
  :host { display: flex; flex-direction: column; min-height: 0; border: 1px solid var(--border);
          border-radius: var(--radius); background: var(--surface); overflow: hidden;
          box-shadow: var(--panel-shadow); }
  header { display: flex; align-items: center; gap: 10px; padding: 6px 10px;
           border-bottom: 1px solid var(--border); }
  h2 { font-size: 13px; margin: 0; white-space: nowrap; }
  .info { font-family: var(--mono); font-size: 12px; color: var(--text-muted); flex: 1;
          min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .stage { position: relative; flex: 1; min-height: 0; }
  svg { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
  .body { fill: color-mix(in srgb, var(--text) 7%, transparent); stroke: var(--text);
          stroke-width: 2px; stroke-linejoin: round; vector-effect: non-scaling-stroke; }
  .fold { stroke: var(--surface); stroke-width: 1.5px; vector-effect: non-scaling-stroke;
          paint-order: stroke; outline: none; }
  .fold-ring { fill: none; stroke: var(--text); stroke-width: 1px; vector-effect: non-scaling-stroke; }
  .axis { stroke: var(--border); stroke-width: 1px; stroke-dasharray: 4 4;
          vector-effect: non-scaling-stroke; }
  .stage { --dim-color: var(--text-muted); --dim-halo: var(--surface); --dim-hl: var(--accent); }
  ${DIM_STYLE}
  text { fill: var(--text-muted); font-family: system-ui, sans-serif; }
  button { font: inherit; color: inherit; background: var(--surface); border: 1px solid var(--border);
           border-radius: 5px; padding: 2px 9px; cursor: pointer; }
  button[aria-pressed="true"] { background: var(--surface-2); border-color: var(--text-muted); }
  text.name { fill: var(--text); }
  .legend { display: flex; flex-wrap: wrap; gap: 4px 14px; padding: 6px 10px; font-size: 12px;
            border-top: 1px solid var(--border); }
  .legend span { display: inline-flex; align-items: center; gap: 6px; }
  .legend i { width: 9px; height: 9px; border-radius: 50%; display: inline-block;
              box-shadow: 0 0 0 1px var(--text); }
</style>
<header>
  <h2>Body cross-section</h2>
  <div class="info" aria-live="polite"></div>
  <button type="button" data-dims aria-pressed="true" title="Show parameter dimensions">Dimensions</button>
</header>
<div class="stage" role="img" aria-label="Cross-section of the closed box body"></div>
<div class="legend"></div>
`;

export class PbSection extends HTMLElement {
  #stage;
  #info;
  #legend;
  #svg = null;
  #highlight = null;
  #showDims = true;

  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    root.append(template.content.cloneNode(true));
    this.#stage = root.querySelector(".stage");
    this.#info = root.querySelector(".info");
    this.#legend = root.querySelector(".legend");
    const toggle = root.querySelector("[data-dims]");
    toggle.addEventListener("click", () => {
      this.#showDims = !this.#showDims;
      toggle.setAttribute("aria-pressed", String(this.#showDims));
      this.#svg?.querySelector(".dims")?.classList.toggle("off", !this.#showDims);
    });
    this.#stage.addEventListener("click", (e) => {
      const param = e.target.closest?.(".dim")?.dataset.param;
      if (param) {
        this.dispatchEvent(new CustomEvent("pb-dim-click", { bubbles: true, composed: true, detail: { param } }));
      }
    });
  }

  /** Emphasise the dimensions of one parameter (or none). */
  highlight(param) {
    this.#highlight = param;
    if (this.#svg) highlightDims(this.#svg, param);
  }

  /** section: {front, back: [[x, z]...], folds: [{category, point}], width, height};
   *  dims: parameter dimensions in the same (X, Z) frame. */
  update(section, colors, dims = []) {
    const { width, height } = section;
    this.#info.textContent = `${fmt(width)} × ${fmt(height)} mm`;
    this.#info.title = "The body has this cross-section everywhere between the curved folds.";

    // Z points up on screen: plot (x, -z).
    const p = ([x, z]) => [x, -z];
    const span = Math.max(width, height);
    const fs = span / 20; // label size in user units
    const pad = span * 0.06;

    const svg = el("svg", { preserveAspectRatio: "xMidYMid meet" });
    svg.append(
      el("line", { class: "axis", x1: -width / 2 - pad / 2, y1: 0, x2: width / 2 + pad / 2, y2: 0 }),
      el("line", { class: "axis", x1: 0, y1: -height / 2 - pad / 2, x2: 0, y2: height / 2 + pad / 2 }),
    );

    // Closed body outline: front panel (glued edge -> straight fold), then back panel back.
    const outline = [...section.front, ...section.back.slice(1)].map(p);
    svg.append(el("path", { class: "body", d: `M ${outline.map((q) => q.join(",")).join(" L ")} Z` }));


    // Panel names, inside the body (dimensions use the space outside).
    svg.append(
      text(width * 0.2, -height * 0.16, "front", fs * 0.8, "middle", "name"),
      text(width * 0.2, height * 0.24, "back", fs * 0.8, "middle", "name"),
    );

    // Fold markers.
    for (const fold of section.folds) {
      const [x, y] = p(fold.point);
      svg.append(
        el("circle", { class: "fold", cx: x, cy: y, r: fs * 0.32, fill: colors[fold.category] }),
        el("circle", { class: "fold-ring", cx: x, cy: y, r: fs * 0.32 + fs * 0.08 }),
      );
    }

    const { group, bounds } = drawDims2d(dims, { fs: fs * 0.8, flipY: true });
    group.classList.toggle("off", !this.#showDims);
    svg.append(group);
    let [x0, y0, x1, y1] = [-width / 2, -height / 2, width / 2, height / 2];
    if (bounds) [x0, y0, x1, y1] = [Math.min(x0, bounds[0]), Math.min(y0, bounds[1]), Math.max(x1, bounds[2]), Math.max(y1, bounds[3])];
    svg.setAttribute("viewBox", [x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad].join(" "));
    this.#stage.replaceChildren(svg);
    this.#svg = svg;
    this.highlight(this.#highlight);

    this.#legend.replaceChildren(
      legendItem(colors.straight, "Straight fold"),
      legendItem(colors.glue, "Glue-tab fold"),
    );
  }
}

function legendItem(color, label) {
  const item = document.createElement("span");
  const swatch = document.createElement("i");
  swatch.style.background = color;
  item.append(swatch, label);
  return item;
}

function text(x, y, content, size, anchor, cls) {
  const t = el("text", { x, y, "font-size": size, "text-anchor": anchor });
  if (cls) t.setAttribute("class", cls);
  t.textContent = content;
  return t;
}

function el(tag, attrs = {}) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

function fmt(v) {
  return Number(v).toFixed(1).replace(/\.0$/, "");
}

customElements.define("pb-section", PbSection);
