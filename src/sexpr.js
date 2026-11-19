// Generic s-expression reader for KiCad files.
//
// The result is a plain tree:
//   list         → Array (with a `pos` property: source offset of its '(')
//   bare token   → string, kept verbatim (numbers too: `00000001` must stay distinct from `1`)
//   quoted text  → {str: '...'}
// Nothing here assumes the `(tag args...)` shape; readers decide how to interpret a list.

export class SexprError extends Error {
  constructor(message, pos) {
    super(`${message} at offset ${pos}`);
    this.pos = pos;
  }
}

const ESCAPES = { n: '\n', t: '\t', r: '\r' };

/**
 * Parse text containing one or more s-expressions; returns the list of top-level values.
 * With `first`, stop after the first complete top-level list (KiCad ignores trailing text).
 */
export function parseAll(text, first = false) {
  let i = 0;
  const n = text.length;
  const root = [];
  const stack = [root];

  while (i < n) {
    const c = text.charCodeAt(i);
    if (c === 40) { // (
      const list = [];
      list.pos = i;
      stack[stack.length - 1].push(list);
      stack.push(list);
      i++;
    } else if (c === 41) { // )
      if (stack.length === 1) throw new SexprError('Unbalanced ")"', i);
      stack.pop();
      i++;
      if (first && stack.length === 1) break;
    } else if (c === 32 || c === 10 || c === 13 || c === 9) {
      i++;
    } else if (c === 34) { // "
      let out = '';
      let j = ++i;
      for (;;) {
        if (j >= n) throw new SexprError('Unterminated string', i - 1);
        const d = text.charCodeAt(j);
        if (d === 34) break;
        if (d === 92) { // backslash
          out += text.slice(i, j);
          const e = text[j + 1];
          out += ESCAPES[e] ?? e;
          j += 2;
          i = j;
        } else {
          j++;
        }
      }
      out += text.slice(i, j);
      stack[stack.length - 1].push({ str: out });
      i = j + 1;
    } else {
      let j = i;
      while (j < n) {
        const d = text.charCodeAt(j);
        if (d === 40 || d === 41 || d === 32 || d === 10 || d === 13 || d === 9 || d === 34) break;
        j++;
      }
      stack[stack.length - 1].push(text.slice(i, j));
      i = j;
    }
  }
  if (stack.length !== 1) throw new SexprError('Unterminated list', stack[stack.length - 1].pos);
  return root;
}

/** Parse the first top-level list of a file; anything after it is ignored, as KiCad does. */
export function parse(text) {
  const [list] = parseAll(text, true);
  if (!Array.isArray(list)) throw new SexprError('Expected a list', 0);
  return list;
}

function quote(s) {
  return '"' + s.replace(/[\\"\n\t\r]/g, c => ({ '\\': '\\\\', '"': '\\"', '\n': '\\n', '\t': '\\t', '\r': '\\r' })[c]) + '"';
}

/** Serialize a tree back to text (single line per list nesting level; used for tests and debugging). */
export function print(value, indent = '') {
  if (typeof value === 'string') return value;
  if (!Array.isArray(value)) return quote(value.str);
  const simple = value.every(v => !Array.isArray(v));
  if (simple) return '(' + value.map(v => print(v)).join(' ') + ')';
  const inner = indent + '  ';
  return '(' + value.map(v => Array.isArray(v) ? '\n' + inner + print(v, inner) : print(v)).join(' ') + ')';
}
