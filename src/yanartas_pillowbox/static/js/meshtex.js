// The PCB layout's copper (POST /api/pcb), drawn into a canvas once: a bitmap the previews
// show as an image (2D) or a texture (3D). Tens of thousands of trace segments as SVG paths
// or lines would make the browser crawl; one bitmap does not.

export const COPPER = {
  front: "#c2410c", // F.Cu: the pattern's visible side, the box's outside
  back: "#1d4ed8", // B.Cu
  pad: "#d4a017",
};

/** Draw `layers` ("front"/"back", in order) of `pcb` into a new canvas covering `region`
 *  (default: the foil's bounds), at most `maxSize` pixels on its long side. `background`:
 *  fill first (none: transparent); `alpha`: per-layer opacity; `blend`: how each layer after
 *  the first goes over the ones before (a canvas composite operation, e.g. "multiply": where
 *  the layers' traces cross, a colour of their own; the background is not blended into).
 *  Returns {canvas, bbox, scale (px/mm)}. */
export function rasterize(pcb, layers, {
  maxSize = 4096, background = null, alpha = {}, region = null, blend = "source-over",
} = {}) {
  const [x0, y0, x1, y1] = region ?? pcb.bbox;
  const scale = maxSize / Math.max(x1 - x0, y1 - y0);
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.ceil((x1 - x0) * scale));
  canvas.height = Math.max(1, Math.ceil((y1 - y0) * scale));
  // (the copper on a transparent canvas of its own: blended among itself only)
  const copper = background ? document.createElement("canvas") : canvas;
  copper.width = canvas.width;
  copper.height = canvas.height;
  const ctx = copper.getContext("2d");
  ctx.setTransform(scale, 0, 0, scale, -x0 * scale, -y0 * scale);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (const [i, layer] of layers.entries()) {
    ctx.globalAlpha = alpha[layer] ?? 1;
    ctx.globalCompositeOperation = i > 0 ? blend : "source-over";
    ctx.strokeStyle = ctx.fillStyle = COPPER[layer];
    ctx.lineWidth = Math.max(pcb.width, 1 / scale); // at least a pixel
    const path = new Path2D();
    for (const t of pcb.layers[layer]) {
      path.moveTo(t[0], t[1]);
      for (let i = 2; i < t.length; i += 2) path.lineTo(t[i], t[i + 1]);
    }
    ctx.stroke(path);
    const vias = new Path2D();
    for (let i = 0; i < pcb.vias.length; i += 2) {
      vias.moveTo(pcb.vias[i] + pcb.via_size / 2, pcb.vias[i + 1]);
      vias.arc(pcb.vias[i], pcb.vias[i + 1], pcb.via_size / 2, 0, 2 * Math.PI);
    }
    ctx.fill(vias);
    if (layer === "front") {
      ctx.globalCompositeOperation = "source-over";
      ctx.fillStyle = COPPER.pad;
      for (let i = 0; i < pcb.pads.length; i += 4) {
        const [x, y, w, h] = pcb.pads.slice(i, i + 4);
        ctx.fillRect(x - w / 2, y - h / 2, w, h);
      }
    }
  }
  ctx.globalAlpha = 1;
  ctx.globalCompositeOperation = "source-over";
  if (background) {
    const out = canvas.getContext("2d");
    out.fillStyle = background;
    out.fillRect(0, 0, canvas.width, canvas.height);
    out.drawImage(copper, 0, 0);
  }
  return { canvas, bbox: [x0, y0, x1, y1], scale };
}
