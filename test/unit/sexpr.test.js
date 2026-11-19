import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parse, parseAll, print, SexprError } from '../../src/sexpr.js';

test('atoms, strings and nested lists', () => {
  const t = parse('(pin passive line (at 0 -3.81 90) (name "~" (effects (font (size 1.27 1.27)))))');
  assert.equal(t[0], 'pin');
  assert.equal(t[1], 'passive');
  assert.deepEqual([...t[3]], ['at', '0', '-3.81', '90']);
  assert.deepEqual(t[4][1], { str: '~' });
  assert.equal(t.pos, 0);
  assert.equal(t[3].pos, 18);
});

test('numbers stay verbatim', () => {
  const t = parse('(tstamp 00000001)');
  assert.equal(t[1], '00000001');
});

test('string escapes', () => {
  const t = parse('(text "a \\"b\\" \\\\ c\\nd")');
  assert.equal(t[1].str, 'a "b" \\ c\nd');
});

test('lists without a head atom and empty lists', () => {
  const t = parse('(x ("a" 1) () (2 3))');
  assert.deepEqual(t[1][0], { str: 'a' });
  assert.equal(t[2].length, 0);
  assert.equal(t[3][0], '2');
});

test('print round-trips', () => {
  const src = '(kicad_sch (version 20260306) (lib_symbols (symbol "R" (pin "1" (at 0 0)))) (text "x\\ny"))';
  const once = parse(src);
  const twice = parse(print(once));
  assert.equal(print(twice), print(once));
  assert.equal(twice[2][1][2][0], "pin");
});

test('errors carry offsets', () => {
  assert.throws(() => parse('(a (b "c)'), SexprError);
  assert.throws(() => parse('(a))'), e => e.pos === 3);
  assert.equal(parseAll('').length, 0);
});
