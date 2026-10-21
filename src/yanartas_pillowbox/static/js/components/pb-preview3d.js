// <pb-preview3d>: orbitable, shaded rendering of the closed box. All geometry comes from the
// server (geometry.build_model3d); this component only turns it into three.js meshes.

import * as THREE from "../../vendor/three/three.module.min.js";
import { OrbitControls } from "../../vendor/three/OrbitControls.js";
import { rasterize } from "../meshtex.js";
import { MAXIMIZE_STYLE, maximizeButton } from "../panels.js";

const template = document.createElement("template");
template.innerHTML = `
<style>
  :host { display: flex; flex-direction: column; min-height: 0; border: 1px solid var(--border);
          border-radius: var(--radius); background: var(--surface); overflow: hidden;
          box-shadow: var(--panel-shadow); }
  header { display: flex; align-items: center; gap: 6px 10px; padding: 6px 10px;
           border-bottom: 1px solid var(--border); flex-wrap: wrap; }
  h2 { font-size: 13px; margin: 0; white-space: nowrap; }
  .info { font-family: var(--mono); font-size: 12px; color: var(--text-muted); flex: 1 1 auto;
          min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  button { font: inherit; color: inherit; background: var(--surface); border: 1px solid var(--border);
           border-radius: 5px; padding: 2px 9px; cursor: pointer; }
  /* Spinner while the PCB layout runs. */
  button[aria-busy="true"]::before { content: ""; display: inline-block; width: 0.8em; height: 0.8em;
    margin-right: 6px; vertical-align: -0.1em; border: 2px solid currentColor;
    border-right-color: transparent; border-radius: 50%; animation: pb-spin 0.8s linear infinite; }
  @keyframes pb-spin { to { transform: rotate(360deg); } }
  @media (prefers-reduced-motion: reduce) { button[aria-busy="true"]::before { animation-duration: 2.4s; } }
  button[aria-pressed="true"] { background: var(--surface-2); border-color: var(--text-muted); }
  .stage { position: relative; flex: 1; min-height: 0; }
  ${MAXIMIZE_STYLE}
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
  .mesh-note { position: absolute; top: 8px; left: 50%; transform: translateX(-50%); z-index: 1;
               background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
               padding: 4px 10px; font-size: 12px; color: var(--text-muted); pointer-events: none;
               white-space: nowrap; }
  .mesh-note[hidden] { display: none; }
  .fallback { position: absolute; inset: 0; display: grid; place-items: center; padding: 16px;
              color: var(--text-muted); text-align: center; }
</style>
<header>
  <h2>Folded box</h2>
  <div class="info" aria-live="polite"></div>
  <button type="button" data-mesh aria-pressed="false" title="Show the PCB layout's security mesh: F.Cu outside, B.Cu inside">Mesh</button>
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
  #surfaces = []; // [{part, geom, outside, inside}]: the paper's two sides, per face
  #textures = null; // {front, back, bbox}: the PCB layout's copper layers as textures
  #note; // a note about the mesh (none laid out yet)

  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    root.append(template.content.cloneNode(true));
    this.#stage = root.querySelector(".stage");
    this.#info = root.querySelector(".info");
    this.#note = Object.assign(document.createElement("div"), { className: "mesh-note", hidden: true });
    this.#stage.append(this.#note);
    root.querySelector("header").append(maximizeButton(this));
    root.querySelector(".reset").addEventListener("click", () => this.#resetCamera());
    root.querySelector("[data-mesh]").addEventListener("click", () => {
      this.dispatchEvent(new CustomEvent("pb-mesh-toggle", { bubbles: true, composed: true }));
    });
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

  /** model: {parts:[{name, kind, positions, indices, outline}], cable:{positions, indices, cuts, lines}|null,
   *  lines:[{direction, points}], cuts:[[point...]], bounds, interior};
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
    // Lay the box on the table, back panel (the lids' side, model -Z) up: model length (Y)
    // -> world X, height (Z) -> world down (-Y), width (X) -> world -Z.
    group.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(
      new THREE.Vector3(0, 0, -1), new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, -1, 0)));
    const paper = { panel: 0xeee6d3, flap: 0xd9cdb2, lid: 0xd9cdb2, tab: 0xc9bc9c };
    // The model is the material's mid-surface: the glue tab lies only a thickness from the
    // front panel under it (none at zero thickness), as do the lids from the back panel.
    // Depth offsets keep the outer surface on top.
    const depthBias = (part) => (part.kind === "tab" || part.kind === "lid" ? 1 : 2);
    this.#surfaces = [];
    for (const part of model.parts) {
      // The inner end flaps stand inside the box (behind the end wall gap): drawn through
      // the paper, like the payload.
      if (part.kind === "flap" && part.name.startsWith("back-")) {
        group.add(this.#interiorMesh(part));
        continue;
      }
      const geom = new THREE.BufferGeometry();
      geom.setAttribute("position", new THREE.Float32BufferAttribute(part.positions, 3));
      geom.setIndex(part.indices);
      geom.computeVertexNormals();
      // The two sides separately, so each can carry its own copper layer (setMesh): the
      // triangles' winding faces into the box, so the pattern's visible side (F.Cu) is
      // their back.
      const side = (s) => new THREE.MeshStandardMaterial({
        color: paper[part.kind] ?? paper.panel,
        roughness: 0.85,
        metalness: 0,
        side: s,
        polygonOffset: true, // also keeps fold lines drawn on the surface visible
        polygonOffsetFactor: depthBias(part),
        polygonOffsetUnits: 4 * depthBias(part),
      });
      const outside = new THREE.Mesh(geom, side(THREE.BackSide));
      const inside = new THREE.Mesh(geom, side(THREE.FrontSide));
      group.add(outside, inside);
      this.#surfaces.push({ part, geom, outside, inside });
    }
    // Fold lines: black, dashed by fold direction like the export (pattern scaled with size).
    const b0 = model.bounds;
    const k = Math.max(1, Math.hypot(b0.width, b0.length, b0.height) / 150);
    // The FPC cable, folded into the box: drawn through the paper, like the inner flaps.
    if (model.cable) group.add(this.#cableMesh(model.cable, k));
    const lineMat = new THREE.LineBasicMaterial({ color: 0x111111 });
    for (const line of model.lines) {
      const dash = (DASH_MM[line.direction] ?? [1, 0]).map((v) => v * k);
      const pts = dashSegments(line.points.map((p) => new THREE.Vector3(...p)), dash);
      group.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts), lineMat));
    }
    // Cut (open) edges: solid, like the export; hidden behind the paper where out of sight.
    for (const cut of model.cuts) {
      const pts = cut.map((p) => new THREE.Vector3(...p));
      group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), lineMat));
    }
    if (payload && !payload.empty) group.add(this.#payloadMesh(payload));
    this.#group = group;
    this.#scene.add(group);
    this.#applyTextures();
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

  /** Whether the Mesh button shows as on (the app owns the state). */
  /** A note over the view about the mesh (none: hidden), e.g. that none is laid out yet. */
  set meshNote(text) {
    this.#note.textContent = text || "";
    this.#note.hidden = !text;
  }

  set meshShown(on) {
    this.shadowRoot.querySelector("[data-mesh]").setAttribute("aria-pressed", String(Boolean(on)));
  }

  /** Spinner on the Mesh button while the layout runs. */
  set meshBusy(busy) {
    this.shadowRoot.querySelector("[data-mesh]").setAttribute("aria-busy", String(Boolean(busy)));
  }

  /** Show the PCB layout's copper (POST /api/pcb) on the paper, or none: each layer drawn
   *  into a texture once, mapped through the faces' flat coordinates. */
  setMesh(pcb) {
    if (this.#textures) {
      this.#textures.front.dispose();
      this.#textures.back.dispose();
      this.#textures = null;
    }
    if (pcb && this.#renderer) {
      const maxSize = Math.min(4096, this.#renderer.capabilities.maxTextureSize);
      const texture = (layer) => {
        const { canvas } = rasterize(pcb, [layer], { maxSize, background: "#ffffff" });
        const tex = new THREE.CanvasTexture(canvas);
        tex.colorSpace = THREE.SRGBColorSpace;
        tex.anisotropy = this.#renderer.capabilities.getMaxAnisotropy();
        return tex;
      };
      this.#textures = { front: texture("front"), back: texture("back"), bbox: pcb.bbox };
    }
    this.#applyTextures();
  }

  #applyTextures() {
    const t = this.#textures;
    for (const { part, geom, outside, inside } of this.#surfaces) {
      if (t) {
        const [x0, y0, x1, y1] = t.bbox;
        const uv = new Float32Array(part.flat.length);
        for (let i = 0; i < part.flat.length; i += 2) {
          uv[i] = (part.flat[i] - x0) / (x1 - x0);
          uv[i + 1] = 1 - (part.flat[i + 1] - y0) / (y1 - y0);
        }
        geom.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
      }
      outside.material.map = t ? t.front : null;
      inside.material.map = t ? t.back : null;
      outside.material.needsUpdate = inside.material.needsUpdate = true;
    }
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

  /** An inner end flap (inside the box): a translucent surface with its outline, drawn
   *  through the paper. */
  #interiorMesh({ positions, indices, outline }) {
    const color = this.#dark.matches ? 0xc792ea : 0x8e44ad;
    const xray = { depthTest: false, depthWrite: false, transparent: true };
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geom.setIndex(indices);
    const g = new THREE.Group();
    const fill = new THREE.Mesh(geom, new THREE.MeshBasicMaterial({
      color, opacity: 0.16, side: THREE.DoubleSide, ...xray }));
    const at = (i) => new THREE.Vector3(positions[3 * i], positions[3 * i + 1], positions[3 * i + 2]);
    const edge = new THREE.LineLoop(
      new THREE.BufferGeometry().setFromPoints(outline.map(at)),
      new THREE.LineBasicMaterial({ color, opacity: 0.9, ...xray }));
    fill.renderOrder = 3;
    edge.renderOrder = 4;
    g.add(fill, edge);
    return g;
  }

  /** The FPC cable (inside the box): a translucent strip with its outline (solid) and
   *  folds (dashed by direction, scaled by k), all drawn through the paper. */
  #cableMesh({ positions, indices, cuts, lines }, k) {
    const color = this.#dark.matches ? 0xf0b429 : 0xc27c0e;
    const ink = this.#dark.matches ? 0xffd27a : 0x6b3f00;
    const xray = { depthTest: false, depthWrite: false, transparent: true };
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geom.setIndex(indices);
    const g = new THREE.Group();
    const fill = new THREE.Mesh(geom, new THREE.MeshBasicMaterial({
      color, opacity: 0.3, side: THREE.DoubleSide, ...xray }));
    fill.renderOrder = 3;
    g.add(fill);
    const lineMat = new THREE.LineBasicMaterial({ color: ink, opacity: 0.95, ...xray });
    const v3 = (p) => new THREE.Vector3(...p);
    for (const cut of cuts) {
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(cut.map(v3)), lineMat);
      line.renderOrder = 4;
      g.add(line);
    }
    for (const fold of lines) {
      const dash = (DASH_MM[fold.direction] ?? [1, 0]).map((v) => v * k);
      const pts = dashSegments(fold.points.map(v3), dash);
      const segs = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts), lineMat);
      segs.renderOrder = 4;
      g.add(segs);
    }
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

  /** Dimension lines, extension lines, arrow tips and text labels; drawn on top of the box. */
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
