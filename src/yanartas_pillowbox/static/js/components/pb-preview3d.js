// <pb-preview3d>: orbitable, shaded rendering of the closed box. All geometry comes from the
// server (geometry.build_model3d); this component only turns it into three.js meshes.

import * as THREE from "../../vendor/three/three.module.min.js";
import { OrbitControls } from "../../vendor/three/OrbitControls.js";

const template = document.createElement("template");
template.innerHTML = `
<style>
  :host { display: flex; flex-direction: column; min-height: 0; border: 1px solid var(--border);
          border-radius: var(--radius); background: var(--surface); overflow: hidden;
          box-shadow: var(--panel-shadow); }
  header { display: flex; align-items: center; gap: 10px; padding: 6px 10px;
           border-bottom: 1px solid var(--border); }
  h2 { font-size: 13px; margin: 0; }
  .info { font-family: var(--mono); font-size: 12px; color: var(--text-muted); flex: 1; }
  button { font: inherit; color: inherit; background: var(--surface); border: 1px solid var(--border);
           border-radius: 5px; padding: 2px 9px; cursor: pointer; }
  button[aria-pressed="true"] { background: var(--surface-2); border-color: var(--text-muted); }
  .stage { position: relative; flex: 1; min-height: 0; }
  canvas { position: absolute; inset: 0; width: 100%; height: 100%; display: block; outline: none; }
  /* Dimension labels are HTML, positioned over the canvas each frame: crisp, and the same
     font and size as the rest of the UI regardless of camera distance. */
  .labels { position: absolute; inset: 0; pointer-events: none; overflow: hidden; }
  .labels.off { display: none; }
  .lbl { position: absolute; left: 0; top: 0; white-space: nowrap; padding: 0 3px;
         font: var(--label-font-size, 13px)/1.3 var(--ui-font, system-ui, sans-serif);
         color: var(--lbl-color); background: color-mix(in srgb, var(--surface) 80%, transparent);
         border-radius: 3px; will-change: transform; }
  .lbl.hl { color: var(--lbl-hl); font-weight: 650; }
  .fallback { position: absolute; inset: 0; display: grid; place-items: center; padding: 16px;
              color: var(--text-muted); text-align: center; }
</style>
<header>
  <h2>Folded box</h2>
  <div class="info" aria-live="polite"></div>
  <button type="button" data-dims aria-pressed="true" title="Show parameter dimensions">Dimensions</button>
  <button type="button" class="reset" title="Reset camera">Reset view</button>
</header>
<div class="stage" role="img" aria-label="3D preview of the folded box (drag to orbit, scroll to zoom)"></div>
`;

export class PbPreview3d extends HTMLElement {
  #stage;
  #info;
  #renderer = null;
  #scene;
  #camera;
  #controls;
  #group = null;
  #frame = 0;
  #size = 100;
  #dims = null; // THREE.Group of dimension annotations
  #dimItems = []; // [{param, materials, el, pos}]
  #labels = null; // container of the HTML dimension labels
  #highlight = null;
  #showDims = true;
  #dark = matchMedia("(prefers-color-scheme: dark)");
  #lastDims = [];

  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    root.append(template.content.cloneNode(true));
    this.#stage = root.querySelector(".stage");
    this.#info = root.querySelector(".info");
    root.querySelector(".reset").addEventListener("click", () => this.#resetCamera());
    const toggle = root.querySelector("[data-dims]");
    toggle.addEventListener("click", () => {
      this.#showDims = !this.#showDims;
      toggle.setAttribute("aria-pressed", String(this.#showDims));
      if (this.#dims) this.#dims.visible = this.#showDims;
      this.#labels?.classList.toggle("off", !this.#showDims);
      this.#requestRender();
    });
    this.#dark.addEventListener("change", () => {
      if (this.#group) this.#buildDims(this.#lastDims);
    });
  }

  connectedCallback() {
    if (this.#renderer) return;
    try {
      this.#renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      const msg = document.createElement("div");
      msg.className = "fallback";
      msg.textContent = "3D preview unavailable: WebGL is not supported in this browser.";
      this.#stage.append(msg);
      return;
    }
    this.#renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.#stage.append(this.#renderer.domElement);
    this.#labels = document.createElement("div");
    this.#labels.className = "labels";
    this.#stage.append(this.#labels);

    this.#scene = new THREE.Scene();
    this.#camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100000);
    this.#scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8f99, 1.6));
    const key = new THREE.DirectionalLight(0xffffff, 1.8);
    key.position.set(1, 1.4, 2);
    this.#camera.add(key); // light follows the camera so the box is always lit
    const rim = new THREE.DirectionalLight(0xffffff, 0.5);
    rim.position.set(-2, -1, -1);
    this.#camera.add(rim);
    this.#scene.add(this.#camera);

    this.#controls = new OrbitControls(this.#camera, this.#renderer.domElement);
    // Nearly no inertia: the camera stops almost as soon as the pointer does.
    this.#controls.enableDamping = true;
    this.#controls.dampingFactor = 0.6;
    this.#controls.addEventListener("change", () => this.#requestRender());

    new ResizeObserver(() => this.#resize()).observe(this.#stage);
  }

  /** model: {parts:[{kind, positions, indices}], lines:[{category, points}], bounds};
   *  dims: parameter dimensions in the model frame (see dimensions.model_dimensions). */
  update(model, dims = [], payload = null) {
    const inside = model.interior;
    this.#info.textContent = `interior ${fmt(inside.width)} × ${fmt(inside.length)} × ${fmt(inside.height)} mm`;
    this.#info.title = "Interior width × length × height";
    if (!this.#renderer) return;
    const first = !this.#group;
    if (this.#group) {
      this.#scene.remove(this.#group);
      disposeTree(this.#group);
    }
    const group = new THREE.Group();
    // Lay the box on the table: model length (Y) -> world X, height (Z) -> world up (Y),
    // width (X) -> world Z (towards the default camera).
    group.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(
      new THREE.Vector3(0, 0, 1), new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 1, 0)));
    const paper = { panel: 0xeee6d3, flap: 0xd9cdb2, tab: 0xc9bc9c };
    // The model is the material's mid-surface: the two flaps of an end lie only a thickness
    // apart (none at zero thickness), as do the glue tab and the front panel under it. Depth
    // offsets keep the outer surface on top (front flaps over back flaps, tab over panel).
    const depthBias = (part) =>
      part.kind === "tab" ? 1 : part.name.startsWith("back-") && part.kind === "flap" ? 4 : 2;
    for (const part of model.parts) {
      const geom = new THREE.BufferGeometry();
      geom.setAttribute("position", new THREE.Float32BufferAttribute(part.positions, 3));
      geom.setIndex(part.indices);
      geom.computeVertexNormals();
      const mat = new THREE.MeshStandardMaterial({
        color: paper[part.kind] ?? paper.panel,
        roughness: 0.85,
        metalness: 0,
        side: THREE.DoubleSide,
        polygonOffset: true, // also keeps fold lines drawn on the surface visible
        polygonOffsetFactor: depthBias(part),
        polygonOffsetUnits: 4 * depthBias(part),
      });
      group.add(new THREE.Mesh(geom, mat));
    }
    // Fold lines: black, dashed by fold direction like the export (pattern scaled with size).
    const b0 = model.bounds;
    const k = Math.max(1, Math.hypot(b0.width, b0.length, b0.height) / 150);
    const lineMat = new THREE.LineBasicMaterial({ color: 0x111111 });
    for (const line of model.lines) {
      const dash = (DASH_MM[line.direction] ?? [1, 0]).map((v) => v * k);
      const pts = dashSegments(line.points.map((p) => new THREE.Vector3(...p)), dash);
      group.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts), lineMat));
    }
    if (payload && !payload.empty) group.add(this.#payloadMesh(payload));
    this.#group = group;
    this.#scene.add(group);
    const b = model.bounds;
    const newSize = Math.hypot(b.width, b.length, b.height);
    this.#buildDims(dims, newSize);
    if (first || Math.abs(newSize - this.#size) / this.#size > 0.5) {
      this.#size = newSize;
      this.#resetCamera();
    }
    this.#size = newSize;
    this.#requestRender();
  }

  /** Payload box (preview only): drawn through the paper as a translucent box with edges.
   *  Centred in the model frame; width along X, depth along Y (length), height along Z. */
  #payloadMesh({ width, depth, height, fits }) {
    const color = fits ? (this.#dark.matches ? 0xe8a052 : 0xb5651d) : 0xe53935;
    const xray = { depthTest: false, depthWrite: false, transparent: true };
    const geom = new THREE.BoxGeometry(width, depth, height);
    const g = new THREE.Group();
    const fill = new THREE.Mesh(geom, new THREE.MeshBasicMaterial({ color, opacity: 0.18, ...xray }));
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(geom), new THREE.LineBasicMaterial({ color, opacity: 0.95, ...xray }));
    fill.renderOrder = 5;
    edges.renderOrder = 6;
    g.add(fill, edges);
    return g;
  }

  /** Emphasise the dimensions of one parameter (or none). */
  highlight(param) {
    this.#highlight = param;
    const hlColor = this.#dimColors().hl;
    const normal = this.#dimColors().normal;
    for (const item of this.#dimItems) {
      const on = Boolean(param) && item.param === param;
      for (const m of item.materials) m.color.set(on ? hlColor : normal);
      item.el.classList.toggle("hl", on);
    }
    this.#requestRender();
  }

  #dimColors() {
    return this.#dark.matches
      ? { normal: "#c3c7cc", hl: "#ffb35c" }
      : { normal: "#4f545b", hl: "#c2410c" };
  }

  /** Dimension lines, extension lines, arrowheads and text labels; drawn on top of the box. */
  #buildDims(dims, size = this.#size) {
    this.#lastDims = dims;
    if (this.#dims) {
      this.#dims.parent?.remove(this.#dims);
      disposeTree(this.#dims);
    }
    const colors = this.#dimColors();
    this.#labels.replaceChildren();
    this.#labels.style.setProperty("--lbl-color", colors.normal);
    this.#labels.style.setProperty("--lbl-hl", colors.hl);
    const top = { depthTest: false, depthWrite: false, transparent: true };
    const g = new THREE.Group();
    g.renderOrder = 10;
    this.#dimItems = [];
    const v3 = (p) => new THREE.Vector3(...p);
    for (const d of dims) {
      const materials = [];
      const lineMat = new THREE.LineBasicMaterial({ color: colors.normal, ...top });
      const extMat = new THREE.LineBasicMaterial({ color: colors.normal, opacity: 0.6, ...top });
      const coneMat = new THREE.MeshBasicMaterial({ color: colors.normal, ...top });
      materials.push(lineMat, extMat, coneMat);
      const add = (obj) => { obj.renderOrder = 10; g.add(obj); };
      add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(d.line.map(v3)), lineMat));
      for (const [a, b] of d.extensions ?? []) {
        add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([v3(a), v3(b)]), extMat));
      }
      const n = d.line.length;
      for (const [tip, from] of [[d.line[0], d.line[1]], [d.line[n - 1], d.line[n - 2]]]) {
        const h = size * 0.022;
        const cone = new THREE.Mesh(new THREE.ConeGeometry(h * 0.3, h, 12), coneMat);
        const dir = v3(tip).sub(v3(from)).normalize();
        cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
        cone.position.copy(v3(tip).addScaledVector(dir, -h / 2));
        add(cone);
      }
      const el = document.createElement("div");
      el.className = "lbl";
      el.textContent = d.label;
      this.#labels.append(el);
      this.#dimItems.push({ param: d.param, materials, el, pos: v3(d.labelAt) });
    }
    g.visible = this.#showDims;
    this.#dims = g;
    this.#group.add(g);
    this.highlight(this.#highlight);
  }

  /** Place the HTML labels at their anchors' projected screen positions. */
  #placeLabels() {
    if (!this.#showDims || !this.#group) return;
    const { clientWidth: w, clientHeight: h } = this.#renderer.domElement;
    const v = new THREE.Vector3();
    for (const { el, pos } of this.#dimItems) {
      v.copy(pos).applyMatrix4(this.#group.matrixWorld).project(this.#camera);
      el.hidden = v.z > 1; // behind the camera
      const x = ((v.x + 1) / 2) * w;
      const y = ((1 - v.y) / 2) * h;
      el.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) translate(-50%, -50%)`;
    }
  }

  #resetCamera() {
    if (!this.#camera) return;
    const d = this.#size * 1.4;
    this.#camera.position.set(d * 0.35, d * 0.45, d * 0.82);
    this.#controls.target.set(0, 0, 0);
    this.#controls.update();
    this.#requestRender();
  }

  #resize() {
    const { width, height } = this.#stage.getBoundingClientRect();
    if (!width || !height) return;
    this.#renderer.setSize(width, height, false);
    this.#camera.aspect = width / height;
    this.#camera.updateProjectionMatrix();
    this.#requestRender();
  }

  #requestRender() {
    if (this.#frame || !this.#renderer) return;
    this.#frame = requestAnimationFrame(() => {
      this.#frame = 0;
      // Damping keeps the camera moving for a few frames; update() returns true meanwhile.
      if (this.#controls.update()) this.#requestRender();
      this.#renderer.render(this.#scene, this.#camera);
      this.#placeLabels();
    });
  }
}

// Dash patterns (mm, before scaling) matching the SVG export: mountain dash-dot, valley dashed.
const DASH_MM = { mountain: [3, 1.5, 0.5, 1.5], valley: [3, 2] };

/** Split a polyline into the "on" pieces of a repeating dash pattern; returns segment pairs. */
function dashSegments(points, pattern) {
  const out = [];
  let idx = 0;
  let left = pattern[0]; // length remaining in the current dash/gap
  for (let i = 0; i + 1 < points.length; i++) {
    let a = points[i].clone();
    const b = points[i + 1];
    let segLen = a.distanceTo(b);
    while (segLen > 1e-9) {
      const step = Math.min(left, segLen);
      const next = a.clone().lerp(b, step / segLen);
      if (idx % 2 === 0) out.push(a, next); // even entries are dashes, odd are gaps
      a = next;
      segLen -= step;
      left -= step;
      if (left <= 1e-9) {
        idx = (idx + 1) % pattern.length;
        left = pattern[idx];
      }
    }
  }
  return out;
}

function disposeTree(root) {
  root.traverse((o) => {
    o.geometry?.dispose();
    o.material?.dispose();
  });
}

function fmt(v) {
  return Number(v).toFixed(1).replace(/\.0$/, "");
}

customElements.define("pb-preview3d", PbPreview3d);
