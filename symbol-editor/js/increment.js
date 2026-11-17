// Continues a block of pins, for "repeat selected rows":
//
//   names:        PA0, PA1      ->  PA2, PA3
//                 TX0_P, TX0_N  ->  TX1_P, TX1_N
//                 TX0_P         ->  TX0_N    (half a diff pair is followed by its partner)
//                 TX0_N         ->  TX1_P
//   pin numbers:  1, 2          ->  3, 4
//                 A1, A2        ->  A3, A4   (BGA, along a row)
//                 A1, B1        ->  C1, D1   (BGA, down a column; letters I O Q S X Z are skipped)

export function continueBlock(pins) {
  const names = nextNames(pins.map(pin => pin.name));
  const numbers = nextNumbers(pins.map(pin => pin.number));
  return pins.map((pin, i) => ({ ...pin, name: names[i], number: numbers[i], alternates: '' }));
}

// Single steps, used for Tab completion.
export function nextName(name) {
  return nextNames([name])[0];
}

export function nextNumber(number) {
  return nextNumbers([number])[0];
}

// --- Names ---

const DIFF_PAIR = /^(.*[\d_])([PN])$/; // "TX0_P", "CLK1N"

function nextNames(names) {
  // Take the P/N off first, so that TX0_P and TX0_N count as the same sequence.
  const pairs = names.map(name => {
    const match = name.match(DIFF_PAIR);
    return match ? { base: match[1], polarity: match[2] } : { base: name, polarity: '' };
  });
  const parts = pairs.map(pair => splitLastNumber(pair.base));
  const steps = sequenceLengths(parts);

  return pairs.map((pair, i) => {
    const stepped = addToLastNumber(parts[i], steps[i]);
    const partnerInBlock = pairs.some(other => other.base === pair.base && other.polarity && other.polarity !== pair.polarity);
    if (pair.polarity && !partnerInBlock) {
      return pair.polarity === 'P' ? pair.base + 'N' : stepped + 'P';
    }
    return stepped + pair.polarity;
  });
}

// --- Pin numbers ---

const BGA_BALL = /^([A-Z]+)(\d+)$/;
const BGA_ROW_LETTERS = 'ABCDEFGHJKLMNPRTUVWY'; // JEDEC leaves out I, O, Q, S, X and Z

function nextNumbers(numbers) {
  const balls = numbers.map(number => number.match(BGA_BALL));
  const allBalls = balls.every(Boolean);
  const oneColumn = allBalls && balls.every(ball => ball[2] === balls[0][2]);
  const severalRows = allBalls && new Set(balls.map(ball => ball[1])).size > 1;

  if (oneColumn && severalRows) {
    // Going down a column: step the row letters.
    const rows = balls.map(ball => rowIndex(ball[1]));
    const step = Math.max(...rows) - Math.min(...rows) + 1;
    return balls.map((ball, i) => rowLetters(rows[i] + step) + ball[2]);
  }

  const parts = numbers.map(splitLastNumber);
  const steps = sequenceLengths(parts);
  // A pin number without digits (like "EP") can't be continued; leave it empty.
  return parts.map((part, i) => part.number === null ? '' : addToLastNumber(part, steps[i]));
}

// BGA row letters count like spreadsheet columns: A ... Y, AA, AB ... AY, BA ...
function rowIndex(letters) {
  let index = 0;
  for (const letter of letters) index = index * BGA_ROW_LETTERS.length + BGA_ROW_LETTERS.indexOf(letter) + 1;
  return index - 1;
}

function rowLetters(index) {
  const base = BGA_ROW_LETTERS.length;
  let letters = '';
  for (let n = index + 1; n > 0; n = Math.floor((n - 1) / base)) {
    letters = BGA_ROW_LETTERS[(n - 1) % base] + letters;
  }
  return letters;
}

// --- Helpers shared by names and numbers ---

// "TX12_P" -> { head: "TX", number: "12", tail: "_P" }
function splitLastNumber(text) {
  const match = text.match(/^(.*?)(\d+)(\D*)$/);
  if (!match) return { head: text, number: null, tail: '' };
  return { head: match[1], number: match[2], tail: match[3] };
}

function addToLastNumber({ head, number, tail }, amount) {
  if (number === null) return head;
  const sum = String(Number(number) + amount).padStart(number.length, '0'); // keeps "D07" two digits
  return head + sum + tail;
}

// How far each text's number has to jump so the new block follows the old one.
// Texts that differ only in their number form one sequence; the jump is its length.
// E.g. PA0..PA3 jump by 4, while D0 and CLK0 (different sequences) each jump by 1.
function sequenceLengths(parts) {
  const ranges = new Map();
  for (const part of parts) {
    if (part.number === null) continue;
    const key = part.head + '#' + part.tail;
    const n = Number(part.number);
    const range = ranges.get(key) || { min: n, max: n };
    ranges.set(key, { min: Math.min(range.min, n), max: Math.max(range.max, n) });
  }
  return parts.map(part => {
    const range = ranges.get(part.head + '#' + part.tail);
    return range ? range.max - range.min + 1 : 0;
  });
}
