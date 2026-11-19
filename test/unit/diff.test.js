import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readKicad } from '../../src/kicad/index.js';
import { diffFiles } from '../../src/diff/index.js';

// Two resistors, R1 at (100, 50) and R2 at (110, 50), vertical, pins 1 at y-3.81 and 2 at y+3.81.
const LIB = `(lib_symbols (symbol "Device:R" (pin_names (offset 0))
  (property "Reference" "R" (at 2 0 90) (effects (font (size 1.27 1.27))))
  (symbol "R_0_1" (rectangle (start -1 -2.5) (end 1 2.5) (stroke (width 0.25)) (fill (type none))))
  (symbol "R_1_1"
    (pin passive line (at 0 3.81 270) (length 1.27) (name "~" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
    (pin passive line (at 0 -3.81 90) (length 1.27) (name "~" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27))))))))`;

const resistor = (ref, x, value = '10k', uuid = ref) => `(symbol (lib_id "Device:R") (at ${x} 50 0) (unit 1) (uuid "${uuid}")
  (property "Reference" "${ref}" (at ${x + 2} 50 90)) (property "Value" "${value}" (at ${x - 2} 50 90)) (pin "1" (uuid "${uuid}p1")) (pin "2" (uuid "${uuid}p2")))`;

const sch = (...items) => readKicad(`(kicad_sch (version 20260306) ${LIB} ${items.join('\n')})`);
const wire = (x1, y1, x2, y2, uuid = `w${x1}${y1}${x2}${y2}`) => `(wire (pts (xy ${x1} ${y1}) (xy ${x2} ${y2})) (uuid "${uuid}"))`;
const summaries = changes => changes.map(c => `${c.kind}${c.minor ? '/minor' : ''}: ${c.summary}`);

// R1 pin 2 (100, 53.81) wired to R2 pin 2 (110, 53.81).
const base = [resistor('R1', 100), resistor('R2', 110), wire(100, 53.81, 110, 53.81)];

test('identical files have no changes', () => {
  assert.deepEqual(diffFiles(sch(...base), sch(...base)), []);
});

test('value change is one metadata change', () => {
  const changes = diffFiles(sch(...base), sch(resistor('R1', 100, '4k7'), base[1], base[2]));
  assert.deepEqual(summaries(changes), ['metadata: R1 Value: “10k” → “4k7”']);
});

test('removing the wire disconnects both pins', () => {
  const changes = diffFiles(sch(...base), sch(base[0], base[1]));
  const s = summaries(changes);
  assert.ok(s.some(x => /^electrical: 2 pins disconnected from net Net-\(R1-Pad2\)/.test(x)), s.join('\n'));
  assert.ok(changes.every(c => c.kind === 'electrical'), s.join('\n'));
});

test('splitting a wire without changing its shape is not a change', () => {
  const split = sch(base[0], base[1], wire(100, 53.81, 105, 53.81, 'a'), wire(105, 53.81, 110, 53.81, 'b'));
  assert.deepEqual(diffFiles(sch(...base), split), []);
});

test('rerouting a wire with the same connections is a minor layout change', () => {
  const rerouted = sch(base[0], base[1], wire(100, 53.81, 100, 60), wire(100, 60, 110, 60), wire(110, 60, 110, 53.81));
  const changes = diffFiles(sch(...base), rerouted);
  assert.deepEqual(summaries(changes), ['layout/minor: Wiring of net Net-(R1-Pad2) rerouted']);
});

test('moving an unconnected symbol is a minor layout change', () => {
  const a = sch(resistor('R1', 100));
  const b = sch(resistor('R1', 102.54));
  assert.deepEqual(summaries(diffFiles(a, b)), ['layout/minor: R1 moved by (+2.54, 0) mm']);
});

test('matching falls back to references when UUIDs change', () => {
  const b = sch(resistor('R1', 100, '10k', 'new1'), resistor('R2', 110, '10k', 'new2'), wire(100, 53.81, 110, 53.81, 'neww'));
  assert.deepEqual(diffFiles(sch(...base), b), []);
});

test('labels connect wires and name the net', () => {
  const label = name => `(label "${name}" (at 105 53.81 0) (effects (font (size 1.27 1.27))) (uuid "l1"))`;
  const changes = diffFiles(sch(...base, label('SDA')), sch(...base, label('SCL')));
  const s = summaries(changes);
  assert.ok(s.includes('electrical: Label SDA renamed to SCL'), s.join('\n'));
  assert.ok(s.includes('electrical/minor: Net SDA renamed to SCL'), s.join('\n'));
});

const board = (...items) => readKicad(`(kicad_pcb (version 20260206) (layers (0 "F.Cu" signal) (2 "B.Cu" signal)) ${items.join('\n')})`);
const fp = (ref, x, net1 = 'A', net2 = 'B') => `(footprint "R_0603" (layer "F.Cu") (uuid "${ref}") (at ${x} 10)
  (property "Reference" "${ref}" (at 0 -1) (layer "F.SilkS") (effects (font (size 1 1))))
  (pad "1" smd rect (at -0.8 0) (size 0.8 0.9) (layers "F.Cu") (net "${net1}"))
  (pad "2" smd rect (at 0.8 0) (size 0.8 0.9) (layers "F.Cu") (net "${net2}")))`;
const track = (x1, x2, net) => `(segment (start ${x1} 10) (end ${x2} 10) (width 0.2) (layer "F.Cu") (net "${net}") (uuid "t${x1}"))`;

test('board: pad net change and routing change are electrical', () => {
  const a = board(fp('R1', 10), fp('R2', 20, 'B', 'C'), track(10.8, 19.2, 'B'));
  const b = board(fp('R1', 10), fp('R2', 20, 'B', 'C'));
  const s = summaries(diffFiles(a, b));
  assert.ok(s.some(x => /^electrical: 2 pins disconnected from routed net B/.test(x)), s.join('\n'));
});

test('board: moving a footprint is a minor layout change', () => {
  const s = summaries(diffFiles(board(fp('R1', 10)), board(fp('R1', 12))));
  assert.deepEqual(s, ['layout/minor: R1 moved by (+2, 0) mm']);
});

test('UUIDs never appear in change texts', () => {
  const uuid = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
  const id = '8af02e7b-5ac3-4814-bbeb-04f56528ba22';
  const a = sch(resistor('R1', 100, '10k', id));
  const b = sch(resistor('R1', 101, '1k', id));
  for (const c of diffFiles(a, b)) for (const t of [c.summary, c.subject, ...c.details]) assert.doesNotMatch(t, uuid);
});
