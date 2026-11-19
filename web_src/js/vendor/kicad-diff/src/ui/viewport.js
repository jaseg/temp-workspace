// <kd-viewport>: a pannable, zoomable view of one or more scenes.
//
// Three stacked layers: a WebGL canvas (geometry), a 2D canvas (native-font text) and an SVG
// overlay (annotations). What is drawn is described by "passes", drawn in order:
//   {scene, layers: [{name, color: [r, g, b, a]}], glowPx?: extra line width, texts?: false to skip text,
//    skipTexts?: Set of scene item indices whose text is not drawn}
//   {halo: [{scene, layers}], widthPx, alpha}: a soft blurred glow around the scenes' geometry
// A text record with `rich: [{str, color?, strike?}]` is drawn as coloured runs (e.g. "old → new").

import { createRenderer } from '../render/gl.js';
import { layout } from '../render/text.js';
import { boxContains } from '../geom.js';

const rgba = c => `rgba(${c[0] * 255}, ${c[1] * 255}, ${c[2] * 255}, ${c[3] ?? 1})`;
const FONT = 'ui-monospace, "DejaVu Sans Mono", Menlo, Consolas, monospace';
const MIN_TEXT_PX = 3;

const css = `
:host { display: block; position: relative; overflow: hidden; touch-action: none; cursor: grab; }
:host(.dragging) { cursor: grabbing; }
canvas, svg { position: absolute; inset: 0; width: 100%; height: 100%; }
svg { overflow: visible; pointer-events: none; }
`;

export class KdViewport extends HTMLElement {
  constructor() {
    super();
    const root = this.attachShadow({ mode: 'open' });
    root.innerHTML = `<style>${css}</style><canvas class="gl"></canvas><canvas class="text"></canvas><svg class="overlay"></svg>`;
    this.glCanvas = root.querySelector('.gl');
    this.textCanvas = root.querySelector('.text');
    this.overlay = root.querySelector('.overlay');
    this.passes = [];
    this.background = [1, 1, 1];
    this.view = { cx: 0, cy: 0, scale: 1 };
    this.widthCache = new Map();
    this.handles = new WeakMap(); // scene → GPU buffers in this viewport's WebGL context
    this.onViewChange = null;
    this.frame = 0;
  }

  connectedCallback() {
    if (!this.renderer) {
      try {
        this.renderer = createRenderer(this.glCanvas);
      } catch (e) {
        this.dispatchEvent(new CustomEvent('kd-error', { detail: e.message, bubbles: true, composed: true }));
        return;
      }
    }
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(this);
    this.bindInput();
    this.resize();
  }

  disconnectedCallback() {
    this.resizeObserver?.disconnect();
    // Browsers allow only a few WebGL contexts; release ours right away.
    this.renderer?.gl.getExtension('WEBGL_lose_context')?.loseContext();
    this.renderer = null;
  }

  /** Set what to draw. Scenes are uploaded to the GPU once per viewport. */
  setPasses(passes, background) {
    for (const s of passes.flatMap(p => [p.scene, ...(p.halo ?? []).map(h => h.scene)])) {
      if (s && this.renderer && !this.handles.has(s)) this.handles.set(s, this.renderer.upload(s));
    }
    this.passes = passes;
    if (background) this.background = background;
    this.redraw();
  }

  /** Model → CSS pixel coordinates. */
  toScreen(x, y) {
    const r = this.getBoundingClientRect();
    const s = this.view.scale / devicePixelRatio;
    return { x: (x - this.view.cx) * s + r.width / 2, y: (y - this.view.cy) * s + r.height / 2 };
  }

  /** CSS pixel (relative to the element) → model coordinates. */
  toModel(px, py) {
    const r = this.getBoundingClientRect();
    const s = this.view.scale / devicePixelRatio;
    return { x: (px - r.width / 2) / s + this.view.cx, y: (py - r.height / 2) / s + this.view.cy };
  }

  /** Fit a model-space box into the view. */
  fit(box, margin = 0.05) {
    if (!(box.x1 > box.x0)) return;
    const r = this.getBoundingClientRect();
    const w = (box.x1 - box.x0) * (1 + 2 * margin);
    const h = (box.y1 - box.y0) * (1 + 2 * margin);
    const scale = Math.min((r.width || 800) / w, (r.height || 600) / h) * devicePixelRatio;
    this.setView({ cx: (box.x0 + box.x1) / 2, cy: (box.y0 + box.y1) / 2, scale });
  }

  setView(view, notify = true) {
    this.view = { ...view };
    this.redraw();
    if (notify) this.onViewChange?.(this.view);
  }

  resize() {
    const r = this.getBoundingClientRect();
    for (const c of [this.glCanvas, this.textCanvas]) {
      c.width = Math.max(1, Math.round(r.width * devicePixelRatio));
      c.height = Math.max(1, Math.round(r.height * devicePixelRatio));
    }
    this.redraw();
  }

  redraw() {
    if (this.frame) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = 0;
      this.draw();
    });
  }

  draw() {
    if (!this.renderer) return;
    this.renderer.begin(this.background);
    for (const p of this.passes) {
      if (p.halo) {
        const items = p.halo.map(h => ({ handle: this.handles.get(h.scene), layers: h.layers }));
        this.renderer.drawHalo(items, this.view, { widthPx: p.widthPx * devicePixelRatio, alpha: p.alpha });
      } else if (p.scene) {
        this.renderer.draw(this.handles.get(p.scene), this.view, p.layers, { extraWidthPx: (p.glowPx ?? 0) * devicePixelRatio });
      }
    }
    this.drawTexts();
    this.dispatchEvent(new CustomEvent('kd-draw'));
  }

  /** Native-font text on the 2D canvas, culled to the viewport and to a minimum size. */
  drawTexts() {
    const ctx = this.textCanvas.getContext('2d');
    const W = this.textCanvas.width, H = this.textCanvas.height;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const { cx, cy, scale } = this.view;
    for (const p of this.passes) {
      if (!p.scene || p.texts === false) continue;
      for (const { name, color } of p.layers) {
        const l = p.scene.layers.get(name);
        if (!l?.texts.length) continue;
        ctx.fillStyle = rgba(color);
        for (const t of l.texts) {
          if (p.skipTexts?.has(t.item)) continue;
          const hPx = t.h * scale;
          if (hPx < MIN_TEXT_PX) continue;
          const sx = (t.x - cx) * scale + W / 2;
          const sy = (t.y - cy) * scale + H / 2;
          const reach = hPx * (t.str.length + 2);
          if (sx < -reach || sx > W + reach || sy < -reach || sy > H + reach) continue;
          this.fillText(ctx, t, sx, sy, scale);
        }
      }
    }
  }

  fillText(ctx, t, sx, sy, scale) {
    const em = 100;
    const font = `${t.bold ? 'bold ' : ''}${t.italic ? 'italic ' : ''}${em}px ${FONT}`;
    // Glyph widths scale linearly with the font size: measure once at 100px, then scale.
    const measure = line => {
      const key = font + '\u0000' + line;
      let w = this.widthCache.get(key);
      if (w === undefined) {
        ctx.font = font;
        this.widthCache.set(key, (w = ctx.measureText(line).width / em));
      }
      return w * t.h * 1.37 * (t.w / t.h);
    };
    const { lines } = layout(t, measure);
    ctx.save();
    ctx.translate(sx, sy);
    ctx.rotate((-t.rot * Math.PI) / 180);
    if (t.mirror) ctx.scale(-1, 1);
    ctx.scale(scale, scale);
    const px = t.h * 1.37; // cap height ≈ 0.73 em
    ctx.font = font;
    ctx.textBaseline = 'alphabetic';
    for (const line of lines) {
      ctx.save();
      ctx.translate(line.x, line.y);
      ctx.scale((px / em) * (t.w / t.h), px / em);
      if (t.rich) this.fillRuns(ctx, t.rich, em);
      else ctx.fillText(line.str, 0, 0);
      ctx.restore();
    }
    ctx.restore();
  }

  /** Coloured runs of one line, optionally struck through (in em units of the current transform). */
  fillRuns(ctx, runs, em) {
    let x = 0;
    for (const run of runs) {
      if (run.color) ctx.fillStyle = rgba(run.color);
      ctx.fillText(run.str, x, 0);
      const w = ctx.measureText(run.str).width;
      if (run.strike) ctx.fillRect(x, -0.3 * em, w, 0.07 * em);
      x += w;
    }
  }

  /** Topmost item of a scene under a CSS-pixel position (smallest bounding box wins). */
  pick(scene, px, py, tolerancePx = 4) {
    const p = this.toModel(px, py);
    const tol = (tolerancePx * devicePixelRatio) / this.view.scale;
    let best = -1, bestArea = Infinity;
    scene.items.forEach((it, i) => {
      const b = it.bbox;
      if (!boxContains({ x0: b.x0 - tol, y0: b.y0 - tol, x1: b.x1 + tol, y1: b.y1 + tol }, p.x, p.y)) return;
      const area = (b.x1 - b.x0 + tol) * (b.y1 - b.y0 + tol);
      if (area < bestArea) (best = i), (bestArea = area);
    });
    return best;
  }

  bindInput() {
    if (this.bound) return;
    this.bound = true;
    let drag = null;
    this.addEventListener('pointerdown', e => {
      if (e.button !== 0 || this.panDisabled) return;
      drag = { x: e.clientX, y: e.clientY, view: { ...this.view }, moved: false };
      this.setPointerCapture(e.pointerId);
    });
    this.addEventListener('pointermove', e => {
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (!drag.moved && Math.hypot(dx, dy) < 3) return;
      drag.moved = true;
      this.classList.add('dragging');
      const s = drag.view.scale / devicePixelRatio;
      this.setView({ ...drag.view, cx: drag.view.cx - dx / s, cy: drag.view.cy - dy / s });
    });
    this.addEventListener('pointerup', e => {
      if (drag && !drag.moved) {
        const r = this.getBoundingClientRect();
        this.dispatchEvent(new CustomEvent('kd-click', { detail: { x: e.clientX - r.left, y: e.clientY - r.top, shift: e.shiftKey } }));
      }
      drag = null;
      this.classList.remove('dragging');
    });
    this.addEventListener('wheel', e => {
      e.preventDefault();
      const r = this.getBoundingClientRect();
      const at = this.toModel(e.clientX - r.left, e.clientY - r.top);
      const f = Math.exp(-e.deltaY * (e.deltaMode ? 0.05 : 0.0015));
      const scale = this.view.scale * f;
      // Keep the point under the cursor fixed.
      this.setView({ scale, cx: at.x - (at.x - this.view.cx) / f, cy: at.y - (at.y - this.view.cy) / f });
    }, { passive: false });
    this.addEventListener('dblclick', () => this.dispatchEvent(new CustomEvent('kd-fit')));
  }
}

customElements.define('kd-viewport', KdViewport);
