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
  .stage { position: relative; flex: 1; min-height: 0; }
  canvas { position: absolute; inset: 0; width: 100%; height: 100%; display: block; outline: none; }
  .fallback { position: absolute; inset: 0; display: grid; place-items: center; padding: 16px;
              color: var(--text-muted); text-align: center; }
</style>
<header>
  <h2>Folded box</h2>
  <div class="info" aria-live="polite"></div>
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

  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    root.append(template.content.cloneNode(true));
    this.#stage = root.querySelector(".stage");
    this.#info = root.querySelector(".info");
    root.querySelector(".reset").addEventListener("click", () => this.#resetCamera());
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
    this.#controls.enableDamping = true;
    this.#controls.addEventListener("change", () => this.#requestRender());

    new ResizeObserver(() => this.#resize()).observe(this.#stage);
  }

  /** model: {parts:[{kind, positions, indices}], lines:[{category, points}], bounds}. */
  update(model, colors) {
    this.#info.textContent =
      `closed ≈ ${fmt(model.bounds.width)} × ${fmt(model.bounds.length)} × ${fmt(model.bounds.depth)} mm`;
    if (!this.#renderer) return;
    const first = !this.#group;
    if (this.#group) {
      this.#scene.remove(this.#group);
      this.#group.traverse((o) => { o.geometry?.dispose(); o.material?.dispose(); });
    }
    const group = new THREE.Group();
    group.rotation.z = -Math.PI / 2; // model length runs along Y; lay the box down lengthwise
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
    const newSize = Math.hypot(b.width, b.length, b.depth);
    if (first || Math.abs(newSize - this.#size) / this.#size > 0.5) {
      this.#size = newSize;
      this.#resetCamera();
    }
    this.#size = newSize;
    this.#requestRender();
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
    });
  }
}

function fmt(v) {
  return Number(v).toFixed(1).replace(/\.0$/, "");
}

customElements.define("pb-preview3d", PbPreview3d);
