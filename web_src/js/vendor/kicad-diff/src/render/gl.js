// WebGL2 renderer for scenes (see scene.js).
//
// Segments are drawn as instanced quads; the fragment shader computes the distance to the segment,
// which gives round caps and antialiasing (a zero-length segment is a disc). Small polygons are
// drawn as triangles; large ones (zone fills) are filled even-odd with the stencil buffer.
// Geometry is uploaded once; panning, zooming, colours and visibility only change uniforms.

const SEGMENT_VS = `#version 300 es
in vec2 corner;
in vec4 seg;
in float width;
uniform vec3 view; // cx, cy, pixels per mm
uniform vec2 size; // canvas size in pixels
uniform float minWidth; // mm
uniform float extraWidth; // mm, added to every width (highlight glow)
out vec2 p;
flat out vec4 s;
flat out float r;
void main() {
  float px = 1.0 / view.z;
  float hw = (max(width, minWidth) + extraWidth) * 0.5;
  vec2 a = seg.xy, b = seg.zw, d = b - a;
  float len = length(d);
  vec2 dir = len > 0.0 ? d / len : vec2(1.0, 0.0);
  vec2 nrm = vec2(-dir.y, dir.x);
  float ext = hw + px;
  p = (corner.x < 0.0 ? a - dir * ext : b + dir * ext) + nrm * corner.y * ext;
  s = seg;
  r = hw;
  gl_Position = vec4((p - view.xy) * view.z * 2.0 / size * vec2(1.0, -1.0), 0.0, 1.0);
}`;

const SEGMENT_FS = `#version 300 es
precision highp float;
in vec2 p;
flat in vec4 s;
flat in float r;
uniform vec3 view;
uniform vec4 color;
out vec4 frag;
void main() {
  vec2 pa = p - s.xy, ba = s.zw - s.xy;
  float h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-12), 0.0, 1.0);
  float d = length(pa - ba * h) - r;
  float alpha = clamp(0.5 - d * view.z, 0.0, 1.0);
  if (alpha <= 0.0) discard;
  frag = vec4(color.rgb, color.a * alpha);
}`;

const FILL_VS = `#version 300 es
in vec2 pos;
uniform vec3 view;
uniform vec2 size;
void main() {
  gl_Position = vec4((pos - view.xy) * view.z * 2.0 / size * vec2(1.0, -1.0), 0.0, 1.0);
}`;

const FILL_FS = `#version 300 es
precision highp float;
uniform vec4 color;
out vec4 frag;
void main() { frag = color; }`;

// Halo: a full-screen pass that blurs an offscreen image along one axis.
const QUAD_VS = `#version 300 es
in vec2 pos;
out vec2 uv;
void main() {
  uv = pos * 0.5 + 0.5;
  gl_Position = vec4(pos, 0.0, 1.0);
}`;

const BLUR_FS = `#version 300 es
precision highp float;
in vec2 uv;
uniform sampler2D image;
uniform vec2 step;   // one texel along the blur axis
uniform float alpha; // overall opacity (applied in the last pass)
out vec4 frag;
void main() {
  vec4 sum = vec4(0.0);
  float total = 0.0;
  for (int i = -12; i <= 12; i++) {
    float w = exp(-float(i * i) / 72.0);
    sum += texture(image, uv + step * float(i)) * w;
    total += w;
  }
  frag = sum / total * alpha;
}`;

function compile(gl, vs, fs) {
  const prog = gl.createProgram();
  for (const [type, src] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]]) {
    const sh = gl.createShader(type);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh));
    gl.attachShader(prog, sh);
  }
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
  const uniforms = {};
  for (let i = 0; i < gl.getProgramParameter(prog, gl.ACTIVE_UNIFORMS); i++) {
    const name = gl.getActiveUniform(prog, i).name;
    uniforms[name] = gl.getUniformLocation(prog, name);
  }
  return { prog, uniforms, attrib: name => gl.getAttribLocation(prog, name) };
}

export function createRenderer(canvas) {
  const gl = canvas.getContext('webgl2', { antialias: true, stencil: true, alpha: false, preserveDrawingBuffer: true });
  if (!gl) throw new Error('WebGL2 is not available');
  const segProg = compile(gl, SEGMENT_VS, SEGMENT_FS);
  const fillProg = compile(gl, FILL_VS, FILL_FS);
  const blurProg = compile(gl, QUAD_VS, BLUR_FS);
  const quadBuf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, quadBuf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const quadVao = gl.createVertexArray();
  gl.bindVertexArray(quadVao);
  gl.enableVertexAttribArray(blurProg.attrib('pos'));
  gl.vertexAttribPointer(blurProg.attrib('pos'), 2, gl.FLOAT, false, 0, 0);
  gl.bindVertexArray(null);
  let targets = null; // two offscreen render targets for the halo, sized like the canvas
  const cornerBuf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, cornerBuf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);

  /** Upload a scene; returns a handle with per-layer GPU buffers. */
  function upload(scene) {
    const layers = new Map();
    for (const [name, l] of scene.layers) {
      const out = { segCount: l.segments.length / 6, triCount: l.triangles.length / 3, fans: [] };
      if (out.segCount) {
        const data = new Float32Array(out.segCount * 5);
        for (let i = 0, j = 0; i < l.segments.length; i += 6, j += 5) {
          data[j] = l.segments[i]; data[j + 1] = l.segments[i + 1]; data[j + 2] = l.segments[i + 2];
          data[j + 3] = l.segments[i + 3]; data[j + 4] = l.segments[i + 4];
        }
        out.segVao = gl.createVertexArray();
        gl.bindVertexArray(out.segVao);
        gl.bindBuffer(gl.ARRAY_BUFFER, cornerBuf);
        gl.enableVertexAttribArray(segProg.attrib('corner'));
        gl.vertexAttribPointer(segProg.attrib('corner'), 2, gl.FLOAT, false, 0, 0);
        out.segBuf = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, out.segBuf);
        gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
        const seg = segProg.attrib('seg'), width = segProg.attrib('width');
        gl.enableVertexAttribArray(seg);
        gl.vertexAttribPointer(seg, 4, gl.FLOAT, false, 20, 0);
        gl.vertexAttribDivisor(seg, 1);
        gl.enableVertexAttribArray(width);
        gl.vertexAttribPointer(width, 1, gl.FLOAT, false, 20, 16);
        gl.vertexAttribDivisor(width, 1);
      }
      const fanVerts = l.fans.reduce((n, f) => n + f.verts.length, 0);
      if (out.triCount || fanVerts) {
        const data = new Float32Array(out.triCount * 2 + fanVerts);
        for (let i = 0, j = 0; i < l.triangles.length; i += 3, j += 2) {
          data[j] = l.triangles[i];
          data[j + 1] = l.triangles[i + 1];
        }
        let offset = out.triCount * 2;
        for (const f of l.fans) {
          data.set(f.verts, offset);
          out.fans.push({ first: offset / 2, count: f.verts.length / 2 });
          offset += f.verts.length;
        }
        out.fillVao = gl.createVertexArray();
        gl.bindVertexArray(out.fillVao);
        out.fillBuf = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, out.fillBuf);
        gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
        gl.enableVertexAttribArray(fillProg.attrib('pos'));
        gl.vertexAttribPointer(fillProg.attrib('pos'), 2, gl.FLOAT, false, 0, 0);
      }
      layers.set(name, out);
    }
    gl.bindVertexArray(null);
    return { layers };
  }

  function release(handle) {
    for (const l of handle.layers.values()) {
      for (const b of [l.segBuf, l.fillBuf]) if (b) gl.deleteBuffer(b);
      for (const v of [l.segVao, l.fillVao]) if (v) gl.deleteVertexArray(v);
    }
  }

  /** Begin a frame: size the canvas and clear to the background colour. */
  function begin(background) {
    const w = canvas.width, h = canvas.height;
    gl.viewport(0, 0, w, h);
    gl.clearColor(background[0], background[1], background[2], 1);
    gl.clearStencil(0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.STENCIL_BUFFER_BIT);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
  }

  /**
   * Draw layers of an uploaded scene. `view` = {cx, cy, scale (px per mm)};
   * `layers` = [{name, color: [r, g, b, a] in 0..1}] back to front.
   * `extraWidthPx` widens every segment (in device pixels), e.g. for a highlight glow.
   */
  function draw(handle, view, layers, { minWidthPx = 1, extraWidthPx = 0 } = {}) {
    const size = [canvas.width, canvas.height];
    const viewVec = [view.cx, view.cy, view.scale];
    for (const { name, color } of layers) {
      const l = handle.layers.get(name);
      if (!l) continue;
      if (l.fillVao) {
        gl.useProgram(fillProg.prog);
        gl.uniform3fv(fillProg.uniforms.view, viewVec);
        gl.uniform2fv(fillProg.uniforms.size, size);
        gl.uniform4fv(fillProg.uniforms.color, color);
        gl.bindVertexArray(l.fillVao);
        if (l.triCount) gl.drawArrays(gl.TRIANGLES, 0, l.triCount);
        if (l.fans.length) {
          gl.enable(gl.STENCIL_TEST);
          for (const f of l.fans) {
            // Pass 1: toggle stencil where covered an odd number of times. Pass 2: paint and reset.
            gl.colorMask(false, false, false, false);
            gl.stencilFunc(gl.ALWAYS, 0, 1);
            gl.stencilOp(gl.KEEP, gl.KEEP, gl.INVERT);
            gl.drawArrays(gl.TRIANGLE_FAN, f.first, f.count);
            gl.colorMask(true, true, true, true);
            gl.stencilFunc(gl.EQUAL, 1, 1);
            gl.stencilOp(gl.ZERO, gl.ZERO, gl.ZERO);
            gl.drawArrays(gl.TRIANGLE_FAN, f.first, f.count);
          }
          gl.disable(gl.STENCIL_TEST);
        }
      }
      if (l.segVao) {
        gl.useProgram(segProg.prog);
        gl.uniform3fv(segProg.uniforms.view, viewVec);
        gl.uniform2fv(segProg.uniforms.size, size);
        gl.uniform1f(segProg.uniforms.minWidth, minWidthPx / view.scale);
        gl.uniform1f(segProg.uniforms.extraWidth, extraWidthPx / view.scale);
        gl.uniform4fv(segProg.uniforms.color, color);
        gl.bindVertexArray(l.segVao);
        gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, l.segCount);
      }
    }
    gl.bindVertexArray(null);
  }

  /** Offscreen colour + stencil targets, recreated when the canvas size changes. */
  function haloTargets() {
    const w = canvas.width, h = canvas.height;
    if (targets?.w === w && targets?.h === h) return targets;
    for (const t of targets?.list ?? []) gl.deleteFramebuffer(t.fb), gl.deleteTexture(t.tex), gl.deleteRenderbuffer(t.rb);
    const list = [0, 1].map(() => {
      const tex = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
      for (const p of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_2D, p, gl.LINEAR);
      for (const p of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T]) gl.texParameteri(gl.TEXTURE_2D, p, gl.CLAMP_TO_EDGE);
      const rb = gl.createRenderbuffer();
      gl.bindRenderbuffer(gl.RENDERBUFFER, rb);
      gl.renderbufferStorage(gl.RENDERBUFFER, gl.DEPTH24_STENCIL8, w, h);
      const fb = gl.createFramebuffer();
      gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
      gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.DEPTH_STENCIL_ATTACHMENT, gl.RENDERBUFFER, rb);
      return { fb, tex, rb };
    });
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    return (targets = { w, h, list });
  }

  /**
   * Soft halo around geometry: `items` = [{handle, layers}] are drawn widened into an offscreen
   * image without blending (where shapes overlap, the later one replaces the earlier, so nothing
   * stacks up), then blurred and laid over the canvas with opacity `alpha`.
   */
  function drawHalo(items, view, { widthPx = 14, alpha = 0.5 } = {}) {
    const [a, b] = haloTargets().list;
    gl.bindFramebuffer(gl.FRAMEBUFFER, a.fb);
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.clearColor(0, 0, 0, 0);
    gl.clearStencil(0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.STENCIL_BUFFER_BIT);
    gl.disable(gl.BLEND);
    for (const it of items) draw(it.handle, view, it.layers, { extraWidthPx: widthPx });
    // Blur along x into b, then along y onto the canvas.
    gl.useProgram(blurProg.prog);
    gl.bindVertexArray(quadVao);
    gl.activeTexture(gl.TEXTURE0);
    gl.uniform1i(blurProg.uniforms.image, 0);
    const spread = Math.max(1, widthPx / 8);
    gl.bindFramebuffer(gl.FRAMEBUFFER, b.fb);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.bindTexture(gl.TEXTURE_2D, a.tex);
    gl.uniform2f(blurProg.uniforms.step, spread / canvas.width, 0);
    gl.uniform1f(blurProg.uniforms.alpha, 1);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA); // the blurred image is premultiplied
    gl.bindTexture(gl.TEXTURE_2D, b.tex);
    gl.uniform2f(blurProg.uniforms.step, 0, spread / canvas.height);
    gl.uniform1f(blurProg.uniforms.alpha, alpha);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.bindVertexArray(null);
  }

  return { gl, upload, release, begin, draw, drawHalo };
}
