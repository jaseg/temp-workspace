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
out vec2 p;
flat out vec4 s;
flat out float r;
void main() {
  float px = 1.0 / view.z;
  float hw = max(width, minWidth) * 0.5;
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
   */
  function draw(handle, view, layers, { minWidthPx = 1 } = {}) {
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
        gl.uniform4fv(segProg.uniforms.color, color);
        gl.bindVertexArray(l.segVao);
        gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, l.segCount);
      }
    }
    gl.bindVertexArray(null);
  }

  return { gl, upload, release, begin, draw };
}
