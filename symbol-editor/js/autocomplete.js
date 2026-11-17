// Guesses a new pin's group, side, type and unit from the pins entered so far.
//
// We look for the pins whose names share the longest common start with the new
// name, and copy what most of them use. The common start must be at least
// 3 characters, unless the names only differ in their number (PA0 and PA1).
// VCC and VDD count as the same word, and so do GND and VSS.
// If nothing matches, supply and ground pins get sensible defaults.

const MIN_PREFIX = 3;

const DEFAULTS = [
  { pattern: /^(VCC|VDD)/i, guess: { group: 'power', side: 'top', etype: 'power_in' } },
  { pattern: /^(GND|VSS)/i, guess: { group: 'ground', side: 'bottom', etype: 'power_in' } },
];

export function guessGroup(pins, pin) {
  const name = comparable(pin.name);
  if (name === '') return null;

  let bestLength = 0;
  let matches = [];
  for (const other of pins) {
    if (other === pin || !other.group) continue;
    const otherName = comparable(other.name);
    const length = commonPrefixLength(name, otherName);
    const sameStem = stem(name) !== '' && stem(name) === stem(otherName);
    if ((length < MIN_PREFIX && !sameStem) || length < bestLength) continue;
    if (length > bestLength) matches = [];
    bestLength = length;
    matches.push(other);
  }

  if (matches.length > 0) {
    const group = mostCommon(matches.map(p => p.group));
    const sameGroup = matches.filter(p => p.group === group);
    return {
      group,
      side: mostCommon(sameGroup.map(p => p.side)),
      etype: mostCommon(sameGroup.map(p => p.etype)),
      unit: mostCommon(sameGroup.map(p => p.unit)),
    };
  }

  const rule = DEFAULTS.find(rule => rule.pattern.test(pin.name));
  return rule ? { ...rule.guess } : null;
}

function comparable(name) {
  return name.toUpperCase().replace(/^VCC/, 'VDD').replace(/^GND/, 'VSS');
}

// "PA12" -> "PA"
function stem(name) {
  return name.replace(/\d+$/, '');
}

function commonPrefixLength(a, b) {
  let i = 0;
  while (i < a.length && a[i] === b[i]) i++;
  return i;
}

function mostCommon(values) {
  const counts = new Map();
  for (const value of values) counts.set(value, (counts.get(value) || 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0];
}
