// <kd-viewport>: a pannable, zoomable view of one or more scenes.
//
// Three stacked layers: a WebGL canvas (geometry), a 2D canvas (native-font text) and an SVG
// overlay (highlights, selection, annotations). What is drawn is described by "passes":
//   {scene, handle?, layers: [{name, color: [r, g, b, a]}]}  drawn in order, back to front.

import { createRenderer } from '../render/gl.js';
import { layout } from '../render/text.js';
import { boxContains } from '../geom.js';

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
  }

  /** Set what to draw. Scenes are uploaded to the GPU once and cached on the pass's scene. */
  setPasses(passes, background) {
    for (const p of passes) {
      if (p.scene && !p.scene.glHandle && this.renderer) p.scene.glHandle = this.renderer.upload(p.scene);
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
    for (const p of this.passes) if (p.scene) this.renderer.draw(p.scene.glHandle, this.view, p.layers);
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
      if (!p.scene) continue;
      for (const { name, color } of p.layers) {
        const l = p.scene.layers.get(name);
        if (!l?.texts.length) continue;
        ctx.fillStyle = `rgba(${color[0] * 255}, ${color[1] * 255}, ${color[2] * 255}, ${color[3]})`;
        for (const t of l.texts) {
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
      ctx.fillText(line.str, 0, 0);
      ctx.restore();
    }
    ctx.restore();
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
