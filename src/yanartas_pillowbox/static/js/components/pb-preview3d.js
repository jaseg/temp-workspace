// <pb-preview3d>: orbitable, shaded rendering of the closed box. All geometry comes from the
// server (geometry.build_model3d); this component only turns it into three.js meshes.

import * as THREE from "../../vendor/three/three.module.min.js";
import { OrbitControls } from "../../vendor/three/OrbitControls.js";

const LABEL_PX = 15; // on-screen height of dimension labels

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
  #dimItems = []; // [{param, materials, sprite, textures: {normal, hl}}]
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
  update(model, colors, dims = []) {
    this.#info.textContent =
      `closed ${fmt(model.bounds.width)} × ${fmt(model.bounds.length)} × ${fmt(model.bounds.height)} mm`;
    this.#info.title = "width × overall length (corner to corner) × height";
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
    // The model is zero-thickness: the two flaps of an end lie on the same wall and the glue
    // tab lies on the front panel. Depth offsets decide which coincident surface shows
    // (front flaps over back flaps; the tab stays hidden under the front panel).
    const depthBias = (part) =>
      part.kind === "tab" ? 6 : part.name.startsWith("back-") && part.kind === "flap" ? 3 : 1;
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
    for (const line of model.lines) {
      const geom = new THREE.BufferGeometry().setFromPoints(line.points.map((p) => new THREE.Vector3(...p)));
      const mat = new THREE.LineBasicMaterial({ color: new THREE.Color(colors[line.category]) });
      group.add(new THREE.Line(geom, mat));
    }
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

  /** Emphasise the dimensions of one parameter (or none). */
  highlight(param) {
    this.#highlight = param;
    const hlColor = this.#dimColors().hl;
    const normal = this.#dimColors().normal;
    for (const item of this.#dimItems) {
      const on = Boolean(param) && item.param === param;
      for (const m of item.materials) m.color.set(on ? hlColor : normal);
      item.sprite.material.map = on ? item.textures.hl : item.textures.normal;
      item.sprite.material.needsUpdate = true;
    }
    this.#requestRender();
  }

  #dimColors() {
    return this.#dark.matches
      ? { normal: "#c3c7cc", hl: "#ffb35c", halo: "#1d2024" }
      : { normal: "#4f545b", hl: "#c2410c", halo: "#ffffff" };
  }

  /** Dimension lines, extension lines, arrowheads and text labels; drawn on top of the box. */
  #buildDims(dims, size = this.#size) {
    this.#lastDims = dims;
    if (this.#dims) {
      this.#dims.parent?.remove(this.#dims);
      disposeTree(this.#dims);
    }
    for (const item of this.#dimItems) {
      item.textures.normal.dispose();
      item.textures.hl.dispose();
    }
    const colors = this.#dimColors();
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
      const textures = {
        normal: labelTexture(d.label, colors.normal, colors.halo),
        hl: labelTexture(d.label, colors.hl, colors.halo),
      };
      // Constant on-screen size regardless of camera distance (scaled in #scaleLabels).
      const sprite = new THREE.Sprite(
        new THREE.SpriteMaterial({ map: textures.normal, sizeAttenuation: false, ...top }));
      sprite.position.copy(v3(d.labelAt));
      add(sprite);
      this.#dimItems.push({ param: d.param, materials, sprite, textures });
    }
    g.visible = this.#showDims;
    this.#dims = g;
    this.#scaleLabels();
    this.#group.add(g);
    this.highlight(this.#highlight);
  }

  /** Size the (non-attenuated) label sprites to LABEL_PX screen pixels tall. With
   *  sizeAttenuation off, a sprite of scale s spans s / tan(fov / 2) in clip space. */
  #scaleLabels() {
    const h = this.#renderer?.domElement.clientHeight;
    if (!h) return;
    const k = (2 * LABEL_PX * Math.tan(THREE.MathUtils.degToRad(this.#camera.fov) / 2)) / h;
    for (const { sprite, textures } of this.#dimItems) {
      sprite.scale.set(k * textures.normal.userData.aspect, k, 1);
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
    this.#scaleLabels();
    this.#requestRender();
  }

  #requestRender() {
    if (this.#frame || !this.#renderer) return;
    this.#frame = requestAnimationFrame(() => {
      this.#frame = 0;
      // Damping keeps the camera moving for a few frames; update() returns true meanwhile.
      if (this.#controls.update()) this.#requestRender();
      this.#renderer.render(this.#scene, this.#camera);
    });
  }
}

function labelTexture(text, color, halo) {
  const px = 48;
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  const font = `600 ${px}px system-ui, sans-serif`;
  ctx.font = font;
  const w = Math.ceil(ctx.measureText(text).width) + px * 0.6;
  canvas.width = w;
  canvas.height = Math.ceil(px * 1.4);
  ctx.font = font;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.lineJoin = "round";
  ctx.lineWidth = px * 0.22;
  ctx.strokeStyle = halo;
  ctx.strokeText(text, w / 2, canvas.height / 2);
  ctx.fillStyle = color;
  ctx.fillText(text, w / 2, canvas.height / 2);
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.userData.aspect = w / canvas.height;
  return tex;
}

function disposeTree(root) {
  root.traverse((o) => {
    o.geometry?.dispose();
    o.material?.map?.dispose();
    o.material?.dispose();
  });
}

function fmt(v) {
  return Number(v).toFixed(1).replace(/\.0$/, "");
}

customElements.define("pb-preview3d", PbPreview3d);
