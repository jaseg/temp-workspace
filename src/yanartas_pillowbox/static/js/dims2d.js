// Draws server-computed 2D dimension annotations (see dimensions.py) into an SVG group.
// Shared by the pattern and cross-section previews. Each dimension is a <g class="dim">
// tagged with data-param so views can highlight the dimensions of one input parameter.

const NS = "http://www.w3.org/2000/svg";

export const DIM_STYLE = `
  .dim line, .dim path.ln { stroke: var(--dim-color); stroke-width: 1px; fill: none;
                            vector-effect: non-scaling-stroke; }
  .dim line.ext { stroke-dasharray: 3 2; opacity: 0.8; }
  .dim path.arrow { fill: var(--dim-color); stroke: none; }
  .dim text { fill: var(--dim-color); font-family: var(--ui-font, system-ui, sans-serif); }
  .dim rect.plate { fill: var(--dim-halo); stroke: none; }
  .dim[data-param] { cursor: pointer; }
  .dim.hl line, .dim.hl path.ln { stroke: var(--dim-hl); stroke-width: 2px; }
  .dim.hl path.arrow { fill: var(--dim-hl); }
  .dim.hl text { fill: var(--dim-hl); font-weight: 650; }
  .dims.off { display: none; }
`;

/**
 * @param dims    list from /api/render (kinds horizontal, vertical, radius, path)
 * @param fs      label font size in user units
 * @param flipY   true when the data frame has y up (plotted as -y)
 * @returns {{group: SVGGElement, bounds: number[]}} bounds = [minX, minY, maxX, maxY]
 */
export function drawDims2d(dims, { fs, flipY = false }) {
  const T = ([x, y]) => [x, flipY ? -y : y];
  const group = el("g", { class: "dims" });
  const xs = [];
  const ys = [];
  const track = (...pts) => pts.forEach(([x, y]) => { xs.push(x); ys.push(y); });
  const a = fs * 0.55; // arrowhead length

  for (const d of dims) {
    const g = el("g", { class: "dim" });
    if (d.param) g.dataset.param = d.param;
    const title = el("title");
    title.textContent = d.param ? `${d.label} mm (${d.param})` : `${d.label} mm (derived)`;
    g.append(title);

    if (d.kind === "horizontal" || d.kind === "vertical") {
      const [p1, p2] = d.points.map(T);
      const horiz = d.kind === "horizontal";
      const at = horiz && flipY ? -d.at : d.at;
      const q1 = horiz ? [p1[0], at] : [at, p1[1]];
      const q2 = horiz ? [p2[0], at] : [at, p2[1]];
      for (const [p, q] of [[p1, q1], [p2, q2]]) {
        const dir = Math.sign(horiz ? q[1] - p[1] : q[0] - p[0]) || 1;
        const over = horiz ? [q[0], q[1] + dir * fs * 0.4] : [q[0] + dir * fs * 0.4, q[1]];
        if (Math.hypot(q[0] - p[0], q[1] - p[1]) > 1e-6) g.append(line(p, over, "ext"));
      }
      g.append(line(q1, q2), ...arrows(q1, q2, a));
      const mid = [(q1[0] + q2[0]) / 2, (q1[1] + q2[1]) / 2];
      g.append(label(mid, d.label, fs, horiz ? 0 : -90));
      track(p1, p2, q1, q2);
      const half = d.label.length * fs * 0.3;
      track(horiz ? [mid[0] - half, mid[1] - fs] : [mid[0] - fs, mid[1] - half],
            horiz ? [mid[0] + half, mid[1] + fs] : [mid[0] + fs, mid[1] + half]);
    } else if (d.kind === "radius") {
      const [c, p] = d.points.map(T);
      const cross = fs * 0.3;
      g.append(line([c[0] - cross, c[1]], [c[0] + cross, c[1]]),
               line([c[0], c[1] - cross], [c[0], c[1] + cross]),
               line(c, p), arrowhead(p, unit(c, p), a));
      // Label beyond the arc, along the radius direction.
      const u = unit(c, p);
      const at = [p[0] + u[0] * fs * 1.4, p[1] + u[1] * fs * 1.4];
      g.append(label(at, d.label, fs, 0));
      track(c, p, [at[0] - fs * 2, at[1] - fs], [at[0] + fs * 2, at[1] + fs]);
    } else if (d.kind === "path") {
      // Offset the measured curve to the left of its direction of travel (in data frame).
      const src = d.points;
      const off = src.map((q, i) => {
        const p0 = src[Math.max(0, i - 1)];
        const p1 = src[Math.min(src.length - 1, i + 1)];
        const t = unit(p0, p1);
        return T([q[0] - t[1] * d.offset, q[1] + t[0] * d.offset]);
      });
      const ends = [T(src[0]), T(src[src.length - 1])];
      g.append(line(ends[0], off[0], "ext"), line(ends[1], off[off.length - 1], "ext"));
      g.append(el("path", { class: "ln", d: `M ${off.map((q) => q.join(",")).join(" L ")}` }));
      g.append(arrowhead(off[0], unit(off[1], off[0]), a),
               arrowhead(off[off.length - 1], unit(off[off.length - 2], off[off.length - 1]), a));
      const m = Math.floor(off.length / 2);
      const t = unit(off[m - 1], off[m + 1]);
      // Put the label on the far side of the dimension line from the measured curve.
      const side = Math.sign(d.offset) * (flipY ? -1 : 1);
      const at = [off[m][0] - t[1] * fs * 0.9 * side, off[m][1] + t[0] * fs * 0.9 * side];
      g.append(label(at, d.label, fs, 0));
      track(...off, ...ends, [at[0] - fs * 3, at[1] - fs], [at[0] + fs * 3, at[1] + fs]);
    }
    group.append(g);
  }
  const bounds = xs.length ? [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)] : null;
  return { group, bounds };
}

/** On-screen size (px) of dimension labels: the UI's --label-font-size, so labels match the
 *  rest of the interface. */
export function labelPx(el) {
  const v = parseFloat(getComputedStyle(el).getPropertyValue("--label-font-size"));
  return Number.isFinite(v) && v > 0 ? v : 13;
}

export function highlightDims(root, param) {
  root.querySelectorAll(".dim").forEach((g) => {
    g.classList.toggle("hl", Boolean(param) && g.dataset.param === param);
  });
}

function arrows(q1, q2, a) {
  return [arrowhead(q1, unit(q2, q1), a), arrowhead(q2, unit(q1, q2), a)];
}

/** Filled arrowhead with its tip at `tip`, pointing along unit vector `d`. */
function arrowhead(tip, d, a) {
  const n = [-d[1], d[0]];
  const b = [tip[0] - d[0] * a, tip[1] - d[1] * a];
  const w = a * 0.32;
  const pts = [tip, [b[0] + n[0] * w, b[1] + n[1] * w], [b[0] - n[0] * w, b[1] - n[1] * w]];
  return el("path", { class: "arrow", d: `M ${pts.map((p) => p.join(",")).join(" L ")} Z` });
}

function unit(p, q) {
  const dx = q[0] - p[0];
  const dy = q[1] - p[1];
  const n = Math.hypot(dx, dy) || 1;
  return [dx / n, dy / n];
}

function line([x1, y1], [x2, y2], cls) {
  const l = el("line", { x1, y1, x2, y2 });
  if (cls) l.setAttribute("class", cls);
  return l;
}

/** Label centred at (x, y) on a backdrop-coloured plate, so lines never run through it. */
function label([x, y], content, fs, rotate) {
  const g = el("g", { transform: `translate(${x} ${y}) rotate(${rotate})` });
  const w = content.length * fs * 0.56 + fs * 0.5; // generous estimate of the text width
  g.append(el("rect", { class: "plate", x: -w / 2, y: -fs * 0.65, width: w, height: fs * 1.3, rx: fs * 0.2 }));
  const t = el("text", { "font-size": fs, "text-anchor": "middle", "dominant-baseline": "central" });
  t.textContent = content;
  g.append(t);
  return g;
}

function el(tag, attrs = {}) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}
