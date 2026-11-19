import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readKicad, versionStatus } from '../../src/kicad/index.js';
import { parse } from '../../src/sexpr.js';
import { readAll } from '../../src/kicad/read.js';

test('version status', () => {
  assert.equal(versionStatus('board', 20260206), 'ok');
  assert.equal(versionStatus('board', 20261031), 'ok');
  assert.equal(versionStatus('board', 20240108), 'older');
  assert.equal(versionStatus('board', 20241229), 'older'); // KiCad 9.0
  assert.equal(versionStatus('schematic', 20260101), 'ok'); // 10.0 development
  assert.equal(versionStatus('schematic', 20990101), 'newer');
  assert.equal(versionStatus('schematic', undefined), 'unknown');
  assert.equal(readKicad('(kicad_sch (version 20990101))').versionStatus, 'newer');
});

test('a failing element is dropped and recorded, the rest is kept', () => {
  const ctx = { errors: [] };
  const n = parse('(x (a 1) (a 2) (a 3))');
  const out = readAll(n, 'a', c => { if (c[1] === '2') throw new Error('boom'); return Number(c[1]); }, ctx);
  assert.deepEqual(out, [1, 3]);
  assert.equal(ctx.errors.length, 1);
  assert.equal(ctx.errors[0].message, 'boom');
});

test('malformed text is recovered, not fatal', () => {
  const r = readKicad('(kicad_pcb (version 20260206) (segment (start 0 0) (end 1 1) (width 0.2) (layer "F.Cu"))) (net "X")))');
  assert.equal(r.type, 'board');
  assert.equal(r.model.items.length, 1);
  const broken = readKicad('(kicad_pcb (version 20260206) (gr_text "unterminated (at 0 0)\n (segment (start 0 0) (end 1 1)');
  assert.ok(broken.errors.length > 0);
  assert.equal(broken.type, 'board');
});

test('schematic pin and symbol instance', () => {
  const r = readKicad(`(kicad_sch (version 20260306)
    (lib_symbols (symbol "Device:R" (pin_names (offset 0) (hide yes)) (in_bom yes)
      (property "Reference" "R" (at 2 0 90) (effects (font (size 1.27 1.27)) (hide yes)))
      (symbol "R_1_1" (pin passive line (at 0 3.81 270) (length 1.27) (name "~" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27))))))))
    (symbol (lib_id "Device:R") (at 100 50 90) (mirror x) (unit 1) (dnp yes) (uuid "u1")
      (property "Reference" "R7" (at 0 0 0))
      (pin "1" (uuid "p1"))))`);
  assert.deepEqual(r.errors, []);
  assert.deepEqual([...r.unhandled], []);
  const def = r.model.libSymbols[0];
  assert.equal(def.pinNames.hide, true);
  assert.equal(def.properties[0].hide, true);
  const pin = def.units[0].pins[0];
  assert.deepEqual(pin.at, { x: 0, y: 3.81, rot: 270 });
  assert.equal(pin.number.text, '1');
  assert.equal(def.units[0].unit, 1);
  const sym = r.model.items[0];
  assert.equal(sym.mirror, 'x');
  assert.equal(sym.dnp, true);
  assert.equal(sym.properties[0].value, 'R7');
});

test('footprint item angles become footprint-relative; 10.99 transform', () => {
  const legacy = readKicad(`(kicad_pcb (version 20260206)
    (footprint "R" (layer "F.Cu") (at 10 20 90) (pad "1" smd rect (at 1 0 90) (size 1 1) (layers "F.Cu") (net "GND"))))`);
  const transform = readKicad(`(kicad_pcb (version 20261031)
    (footprint "R" (layer "F.Cu") (transform (translate 10 20) (rotate 90) (scale 1 1)) (pad "1" smd rect (at 1 0 90) (size 1 1) (layers "F.Cu") (net "GND"))))`);
  for (const r of [legacy, transform]) {
    const fp = r.model.items[0];
    assert.deepEqual({ x: fp.at.x, y: fp.at.y, rot: fp.at.rot }, { x: 10, y: 20, rot: 90 });
    assert.equal(fp.pads[0].at.rot, 0);
    assert.equal(fp.pads[0].net, 'GND');
  }
});

test('legacy numeric nets resolve through the net table', () => {
  const r = readKicad('(kicad_pcb (version 20240108) (net 0 "") (net 3 "VCC") (segment (start 0 0) (end 1 0) (width 0.2) (layer "F.Cu") (net 3)))');
  assert.equal(r.model.items[0].net, 'VCC');
  assert.equal(r.versionStatus, 'older');
});

test('unknown tokens are reported and kept for diffing', () => {
  const r = readKicad('(kicad_sch (version 20260306) (wire (pts (xy 0 0) (xy 1 0)) (frobnicate 3)))');
  assert.deepEqual([...r.unhandled], [['kicad_sch/wire/frobnicate', 1]]);
  assert.equal(r.model.items[0].extra.frobnicate, '(frobnicate 3)');
});
