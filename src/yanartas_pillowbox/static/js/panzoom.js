// Pointer handling shared by the 2D previews: wheel zooms about the cursor, one pointer
// pans, two pinch-zoom about their midpoint (and pan with it), double-click fits, and a
// click on a dimension (one that did not pan) asks the app to focus its parameter.
//
// The view is an SVG viewBox [x, y, w, h]; the host keeps it and supplies:
//   view()             the current view, or null while there is nothing to show
//   setView(v)         show a new view (the user zoomed or panned)
//   minMax()           [smallest, largest] view width allowed
//   fit()              back to the fitted view
//   dimClick(param)    a dimension of `param` was clicked

/** Screen pixels to view units for `view` shown (aspect-fitted) in `stage`. */
export function unitsPerPixel(stage, [, , w, h], fallback = 600) {
  const r = stage.getBoundingClientRect();
  return r.width && r.height ? Math.max(w / r.width, h / r.height) : w / fallback;
}

/** `view` zoomed by `factor` about the screen point (clientX, clientY) of `at` (the stage's
 *  centre without), the width kept within [min, max]. */
export function zoomView(stage, view, factor, at, [min, max]) {
  const r = stage.getBoundingClientRect();
  const [x, y, w, h] = view;
  const scale = unitsPerPixel(stage, view);
  // The point under the cursor stays fixed.
  const px = at ? at.clientX - r.left : r.width / 2;
  const py = at ? at.clientY - r.top : r.height / 2;
  const ux = x + w / 2 + (px - r.width / 2) * scale;
  const uy = y + h / 2 + (py - r.height / 2) * scale;
  const k = Math.min(Math.max(w * factor, min), max) / w;
  return [ux - (ux - x) * k, uy - (uy - y) * k, w * k, h * k];
}

/** `view` moved by a screen-pixel offset. */
export function panView(stage, [x, y, w, h], dx, dy) {
  const scale = unitsPerPixel(stage, [x, y, w, h]);
  return [x - dx * scale, y - dy * scale, w, h];
}

export function attachPanZoom(stage, host) {
  const zoom = (factor, at, from = host.view()) =>
    host.setView(zoomView(stage, from, factor, at, host.minMax()));
  let drag = null; // {x, y, view} where the pan started
  let pinch = null; // {dist, x, y, view} where the pinch started
  let moved = false;
  let downParam = null;
  const pointers = new Map();
  const pinchState = () => {
    const [a, b] = [...pointers.values()];
    return { dist: Math.hypot(a.x - b.x, a.y - b.y), x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
  };
  const startDrag = (p) => { drag = { x: p.x, y: p.y, view: [...host.view()] }; };

  stage.addEventListener("dblclick", () => host.fit());
  // (Pointer capture retargets the click to the stage, so remember the dimension that was
  // under the pointer when it went down.)
  stage.addEventListener("click", () => {
    if (downParam && !moved) host.dimClick(downParam);
  });
  stage.addEventListener("wheel", (e) => {
    e.preventDefault();
    if (host.view()) zoom(Math.exp(e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.0015)), e);
  }, { passive: false });
  stage.addEventListener("pointerdown", (e) => {
    if (!host.view() || e.button !== 0) return;
    stage.setPointerCapture(e.pointerId);
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.size === 2) {
      pinch = { ...pinchState(), view: [...host.view()] };
      drag = null;
      moved = true; // a pinch never counts as a click
      return;
    }
    if (pointers.size > 2) return;
    stage.classList.add("dragging");
    startDrag(pointers.get(e.pointerId));
    moved = false;
    downParam = e.target.closest?.(".dim")?.dataset.param ?? null;
  });
  stage.addEventListener("pointermove", (e) => {
    if (!pointers.has(e.pointerId)) return;
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pinch && pointers.size >= 2) {
      const now = pinchState();
      if (!now.dist || !pinch.dist) return;
      const zoomed = zoomView(stage, pinch.view, pinch.dist / now.dist,
        { clientX: pinch.x, clientY: pinch.y }, host.minMax());
      host.setView(panView(stage, zoomed, now.x - pinch.x, now.y - pinch.y));
      return;
    }
    if (!drag) return;
    if (Math.hypot(e.clientX - drag.x, e.clientY - drag.y) > 3) moved = true;
    host.setView(panView(stage, drag.view, e.clientX - drag.x, e.clientY - drag.y));
  });
  const endPointer = (e) => {
    pointers.delete(e.pointerId);
    if (pointers.size < 2) pinch = null;
    if (pointers.size === 1) startDrag([...pointers.values()][0]); // carry on panning
    if (pointers.size === 0) {
      drag = null;
      stage.classList.remove("dragging");
    }
  };
  stage.addEventListener("pointerup", endPointer);
  stage.addEventListener("pointercancel", endPointer);
  return { zoom };
}
