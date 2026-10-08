// <pb-section>: 2D cross-section of the closed box body (perpendicular to its length), as
// computed by geometry.build_cross_section. The body is a cylinder between the curved folds,
// so this section holds along the whole straight part of the box.

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
  .tab { fill: none; stroke: var(--text-muted); stroke-width: 3px; stroke-linecap: round;
         vector-effect: non-scaling-stroke; }
  .axis { stroke: var(--border); stroke-width: 1px; stroke-dasharray: 4 4;
          vector-effect: non-scaling-stroke; }
  .dim line { stroke: var(--text-muted); stroke-width: 1px; vector-effect: non-scaling-stroke; }
  text { fill: var(--text-muted); font-family: system-ui, sans-serif; }
  text.name { fill: var(--text); }
  .legend { display: flex; flex-wrap: wrap; gap: 4px 14px; padding: 6px 10px; font-size: 12px;
            border-top: 1px solid var(--border); }
  .legend span { display: inline-flex; align-items: center; gap: 6px; }
  .legend i { width: 9px; height: 9px; border-radius: 50%; display: inline-block;
              box-shadow: 0 0 0 1px var(--text); }
  .legend i.tab { width: 18px; height: 0; border-radius: 2px; border-top: 3px solid var(--text-muted);
                  box-shadow: none; }
</style>
<header>
  <h2>Body cross-section</h2>
  <div class="info" aria-live="polite"></div>
</header>
<div class="stage" role="img" aria-label="Cross-section of the closed box body"></div>
<div class="legend"></div>
`;

export class PbSection extends HTMLElement {
  #stage;
  #info;
  #legend;

  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    root.append(template.content.cloneNode(true));
    this.#stage = root.querySelector(".stage");
    this.#info = root.querySelector(".info");
    this.#legend = root.querySelector(".legend");
  }

  /** section: {front, back, tab: [[x, z]...], folds: [{category, point}], width, depth}. */
  update(section, colors) {
    const { width, depth } = section;
    this.#info.textContent = `${fmt(width)} × ${fmt(depth)} mm`;
    this.#info.title = "The body has this cross-section everywhere between the curved folds.";

    // Z points up on screen: plot (x, -z).
    const p = ([x, z]) => [x, -z];
    const span = Math.max(width, depth);
    const fs = span / 18; // label size in user units
    const pad = span * 0.12;
    const dimGap = fs * 1.6;
    const vb = [
      -width / 2 - pad,
      -depth / 2 - pad,
      width + 2 * pad + dimGap + fs * 2,
      depth + 2 * pad + dimGap + fs * 1.5,
    ];

    const svg = el("svg", { viewBox: vb.join(" "), preserveAspectRatio: "xMidYMid meet" });
    svg.append(
      el("line", { class: "axis", x1: -width / 2 - pad / 2, y1: 0, x2: width / 2 + pad / 2, y2: 0 }),
      el("line", { class: "axis", x1: 0, y1: -depth / 2 - pad / 2, x2: 0, y2: depth / 2 + pad / 2 }),
    );

    // Closed body outline: front panel (glued edge -> straight fold), then back panel back.
    const outline = [...section.front, ...section.back.slice(1)].map(p);
    svg.append(el("path", { class: "body", d: `M ${outline.map((q) => q.join(",")).join(" L ")} Z` }));

    // The glue tab lies on the inside of the front panel; draw it slightly inset to show it.
    const inset = offsetInward(section.tab, span * 0.025).map(p);
    svg.append(el("path", { class: "tab", d: `M ${inset.map((q) => q.join(",")).join(" L ")}` }));

    // Panel names.
    svg.append(
      text(0, -depth / 2 - fs * 0.6, "front", fs, "middle", "name"),
      text(0, depth / 2 + fs * 1.3, "back", fs, "middle", "name"),
    );

    // Fold markers.
    for (const fold of section.folds) {
      const [x, y] = p(fold.point);
      svg.append(
        el("circle", { class: "fold", cx: x, cy: y, r: fs * 0.32, fill: colors[fold.category] }),
        el("circle", { class: "fold-ring", cx: x, cy: y, r: fs * 0.32 + fs * 0.08 }),
      );
    }

    // Dimensions: closed width below, depth to the right.
    const yDim = depth / 2 + dimGap + fs * 0.6;
    const xDim = width / 2 + dimGap;
    svg.append(
      dimension([-width / 2, yDim], [width / 2, yDim], `≈ ${fmt(width)} mm`, fs, false),
      dimension([xDim, -depth / 2], [xDim, depth / 2], `${fmt(depth)} mm`, fs, true),
    );
    this.#stage.replaceChildren(svg);

    this.#legend.replaceChildren(
      legendItem(colors.straight, "Straight fold"),
      legendItem(colors.glue, "Glue-tab fold"),
      legendItem(null, "Glue tab (inside front panel)"),
    );
  }
}

/** Offset an open polyline by `d` towards the inside of the box (right of travel direction
 *  for the front panel, which runs from -X to +X with the box interior below it). */
function offsetInward(pts, d) {
  return pts.map((q, i) => {
    const a = pts[Math.max(0, i - 1)];
    const b = pts[Math.min(pts.length - 1, i + 1)];
    const tx = b[0] - a[0];
    const tz = b[1] - a[1];
    const n = Math.hypot(tx, tz) || 1;
    return [q[0] + (tz / n) * d, q[1] - (tx / n) * d];
  });
}

function dimension([x1, y1], [x2, y2], label, fs, vertical) {
  const g = el("g", { class: "dim" });
  const tick = fs * 0.35;
  g.append(el("line", { x1, y1, x2, y2 }));
  if (vertical) {
    g.append(el("line", { x1: x1 - tick, y1, x2: x1 + tick, y2: y1 }));
    g.append(el("line", { x1: x2 - tick, y1: y2, x2: x2 + tick, y2 }));
    const t = text(0, 0, label, fs * 0.8, "middle");
    t.setAttribute("transform", `translate(${x1 + fs * 0.9} ${(y1 + y2) / 2}) rotate(90)`);
    g.append(t);
  } else {
    g.append(el("line", { x1, y1: y1 - tick, x2: x1, y2: y1 + tick }));
    g.append(el("line", { x1: x2, y1: y2 - tick, x2, y2: y2 + tick }));
    g.append(text((x1 + x2) / 2, y1 + fs * 1.05, label, fs * 0.8, "middle"));
  }
  return g;
}

function legendItem(color, label) {
  const item = document.createElement("span");
  const swatch = document.createElement("i");
  if (color) swatch.style.background = color;
  else swatch.className = "tab";
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
