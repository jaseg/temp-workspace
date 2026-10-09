// <pb-section>: 2D cross-section of the closed box body (perpendicular to its length), as
// computed by geometry.build_cross_section. The body is a cylinder between the curved folds,
// so this section holds along the whole straight part of the box.

import { DIM_STYLE, drawDims2d, highlightDims, labelPx } from "../dims2d.js";

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
  .interior { fill: var(--interior-fill); stroke: var(--text); stroke-width: 1.4px;
              stroke-linejoin: round; vector-effect: non-scaling-stroke; }
  .glue-tab { fill: none; stroke: var(--glue-color); stroke-width: 1.4px; stroke-linecap: round;
              stroke-linejoin: round; vector-effect: non-scaling-stroke; }
  .axis { stroke: var(--border); stroke-width: 1px; stroke-dasharray: 4 4;
          vector-effect: non-scaling-stroke; }
  .stage { --dim-color: var(--text-muted); --dim-halo: var(--surface); --dim-hl: var(--accent); }
  :host { --interior-fill: color-mix(in srgb, var(--text) 9%, transparent);
          --glue-color: var(--focus);
          --payload-fill: color-mix(in srgb, var(--accent) 22%, transparent); }
  ${DIM_STYLE}
  .payload { fill: var(--payload-fill); stroke: var(--accent);
             stroke-width: 1.5px; vector-effect: non-scaling-stroke; }
  .payload-margin { fill: none; stroke: var(--accent); stroke-width: 1px; stroke-dasharray: 4 3;
                    vector-effect: non-scaling-stroke; }
  .payload-margin.bad { stroke: var(--error); }
  .payload.bad { fill: color-mix(in srgb, var(--error) 22%, transparent); stroke: var(--error); }
  .legend i { width: 14px; height: 9px; display: inline-block; border-radius: 2px; }
  .legend i.interior { background: var(--interior-fill); border: 1px solid var(--text); }
  .legend i.payload { background: var(--payload-fill); border: 1.5px solid var(--accent); }
  .legend i.payload.bad { background: color-mix(in srgb, var(--error) 22%, transparent);
                          border-color: var(--error); }
  .legend i.margin { height: 0; border-radius: 0; border-top: 1.5px dashed var(--accent); }
  .legend i.margin.bad { border-top-color: var(--error); }
  .legend i.glue-tab { height: 0; border-radius: 0; border-top: 1.4px solid var(--glue-color); }
  text { fill: var(--text-muted); font-family: var(--ui-font, system-ui, sans-serif); }
  button { font: inherit; color: inherit; background: var(--surface); border: 1px solid var(--border);
           border-radius: 5px; padding: 2px 9px; cursor: pointer; }
  button[aria-pressed="true"] { background: var(--surface-2); border-color: var(--text-muted); }
  .legend { display: flex; flex-wrap: wrap; gap: 4px 14px; padding: 6px 10px; font-size: 12px;
            border-top: 1px solid var(--border); }
  .legend span { display: inline-flex; align-items: center; gap: 6px; }
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
  #data = null; // {section, colors, dims} of the last update

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
      this.#render();
    });
    new ResizeObserver(() => this.#render()).observe(this.#stage);
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

  /** section: {front, back: [[x, z]...] (mid-surfaces), interior: [[x, z]...] (closed),
   *  glue_tab: [[x, z]...], width, height (interior), bbox};
   *  dims: parameter dimensions in the same (X, Z) frame. */
  update(section, dims = [], payload = null) {
    const { width, height } = section;
    this.#info.textContent = `${fmt(width)} × ${fmt(height)} mm`;
    this.#info.title = "Interior width × height. The body has this cross-section everywhere "
      + "between the curved folds.";
    this.#data = { section, dims, payload };
    this.#render();
    this.#legend.replaceChildren(legendItem("interior", "Box interior"), legendItem("glue-tab", "Glue tab"));
    if (payload && !payload.empty) {
      const bad = payload.fits ? "" : " bad";
      this.#legend.append(
        legendItem(`payload${bad}`, payload.fits ? "Payload space" : "Payload space (does not fit)"));
      if (payload.margin > 0) this.#legend.append(legendItem(`margin${bad}`, "Payload margin"));
    }
  }

  /** Draw the section scaled to fit, with text at labelPx() screen pixels. The text's size
   *  in drawing units depends on the fit's scale, so the fit is iterated to a fixed point. */
  #render() {
    if (!this.#data) return;
    const { section, dims, payload } = this.#data;
    const [bx0, bz0, bx1, bz1] = section.bbox;
    const r = this.#stage.getBoundingClientRect();
    const px = labelPx(this);
    let box = [bx0, -bz1, bx1 - bx0, bz1 - bz0];
    let svg;
    for (let i = 0; i < 4; i++) {
      const upp = r.width && r.height ? Math.max(box[2] / r.width, box[3] / r.height) : box[2] / 400;
      ({ svg, box } = this.#draw(section, dims, payload, px * upp));
    }
    svg.setAttribute("viewBox", box.join(" "));
    this.#stage.replaceChildren(svg);
    this.#svg = svg;
    this.highlight(this.#highlight);
  }

  #draw(section, dims, payload, fs) {
    const { width, height } = section;
    const [bx0, bz0, bx1, bz1] = section.bbox;
    // Z points up on screen: plot (x, -z).
    const p = ([x, z]) => [x, -z];
    const pad = fs * 1.2;

    const svg = el("svg", { preserveAspectRatio: "xMidYMid meet" });
    svg.append(
      el("line", { class: "axis", x1: -width / 2 - pad / 2, y1: 0, x2: width / 2 + pad / 2, y2: 0 }),
      el("line", { class: "axis", x1: 0, y1: -height / 2 - pad / 2, x2: 0, y2: height / 2 + pad / 2 }),
    );

    // The interior: the panels' inner surfaces.
    const interior = section.interior.map(p);
    svg.append(el("path", { class: "interior", d: `M ${interior.map((q) => q.join(",")).join(" L ")} Z` }));
    // The glue tab, wrapped around the front panel's free edge onto its outside.
    const tab = section.glue_tab.map(p);
    svg.append(el("path", { class: "glue-tab", d: `M ${tab.map((q) => q.join(",")).join(" L ")}` }));

    // Payload: preview only, centred in the section.
    if (payload && !payload.empty) {
      const { width: pw, height: ph, margin: m } = payload;
      if (m > 0) {
        // The margin envelope: every point within m of the payload (rounded corners).
        svg.append(el("rect", {
          class: payload.fits ? "payload-margin" : "payload-margin bad",
          x: -pw / 2 - m, y: -ph / 2 - m, width: pw + 2 * m, height: ph + 2 * m, rx: m, ry: m,
        }));
      }
      svg.append(el("rect", {
        class: payload.fits ? "payload" : "payload bad", x: -pw / 2, y: -ph / 2, width: pw, height: ph,
      }));
    }

    const { group, bounds } = drawDims2d(dims, { fs, flipY: true });
    group.classList.toggle("off", !this.#showDims);
    svg.append(group);
    let [x0, y0, x1, y1] = [bx0, -bz1, bx1, -bz0];
    if (bounds && this.#showDims) {
      [x0, y0, x1, y1] = [Math.min(x0, bounds[0]), Math.min(y0, bounds[1]), Math.max(x1, bounds[2]), Math.max(y1, bounds[3])];
    }
    return { svg, box: [x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad] };
  }
}

function legendItem(swatchClass, label) {
  const item = document.createElement("span");
  const swatch = document.createElement("i");
  swatch.className = swatchClass;
  item.append(swatch, label);
  return item;
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
