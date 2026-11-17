// Reads the first symbol of a KiCad symbol library (.kicad_sym) into pins and settings.
//
// KiCad files don't store our groups, so they are rebuilt from the pin positions:
// pins one grid step apart belong together, a bigger gap starts a new group.

import { SIDES, newPin, defaultSettings } from './pins.js';
import { GRID } from './layout.js';

const SIDE_OF_ANGLE = { 0: 'left', 180: 'right', 270: 'top', 90: 'bottom' };

const SETTING_OF_PROPERTY = {
  Reference: 'reference',
  Footprint: 'footprint',
  Datasheet: 'datasheet',
  Description: 'description',
  ki_description: 'description', // older KiCad versions
  ki_keywords: 'keywords',
};

export function fromKicadSym(text) {
  const library = parseSexpr(text);
  const symbol = children(library, 'symbol')[0];
  if (!symbol) throw new Error('No symbol found in this file');

  const settings = defaultSettings();
  settings.name = symbol[1];
  for (const property of children(symbol, 'property')) {
    const key = SETTING_OF_PROPERTY[property[1]];
    if (key) settings[key] = property[2];
  }

  // Units are sub-symbols named NAME_<unit>_<style>. Unit 0 is shared by all units;
  // style 2 is the alternative "De Morgan" drawing, which we skip.
  const found = [];
  for (const unitSymbol of children(symbol, 'symbol')) {
    const [, unit, style] = unitSymbol[1].match(/_(\d+)_(\d+)$/) || [];
    if (style === '2') continue;
    for (const pinNode of children(unitSymbol, 'pin')) {
      found.push(readPin(pinNode, Math.max(1, Number(unit) || 1)));
    }
  }
  return { settings, pins: groupByGaps(found) };
}

// A pin with its position in mil.
function readPin(node, unit) {
  const [x, y, angle] = child(node, 'at').slice(1).map(Number);
  const name = child(node, 'name')[1];
  const hidden = node.includes('hide') || child(node, 'hide')?.[1] === 'yes'; // KiCad 8 and 9 style
  const pin = newPin({
    number: child(node, 'number')[1],
    name: name === '~' ? '' : name,
    unit,
    side: SIDE_OF_ANGLE[angle] || 'left',
    etype: node[1],
    shape: node[2],
    hidden,
    alternates: children(node, 'alternate').map(alternate => alternate[1]).join(', '),
  });
  return { pin, x: Math.round(x / 0.0254), y: Math.round(y / 0.0254) };
}

function groupByGaps(found) {
  const pins = [];
  const usedGroupNames = new Set();
  const units = [...new Set(found.map(f => f.pin.unit))].sort((a, b) => a - b);

  for (const unit of units) {
    for (const side of SIDES) {
      // Position along the edge: top to bottom for left/right, left to right for top/bottom.
      const along = side === 'left' || side === 'right' ? f => -f.y : f => f.x;
      const onSide = found
        .filter(f => f.pin.unit === unit && f.pin.side === side)
        .sort((a, b) => along(a) - along(b));

      let group = [];
      onSide.forEach((f, i) => {
        if (i > 0 && along(f) - along(onSide[i - 1]) > GRID) {
          pins.push(...finishGroup(group, side, usedGroupNames));
          group = [];
        }
        group.push(f);
      });
      if (group.length) pins.push(...finishGroup(group, side, usedGroupNames));
    }
  }
  return pins;
}

function finishGroup(group, side, usedGroupNames) {
  const name = uniqueName(groupName(group.map(f => f.pin.name)) || side, usedGroupNames);
  for (const f of group) {
    f.pin.group = name;
    // A hidden pin right behind a visible one of the same name is a stacked pin.
    // We stack pins ourselves, so it becomes a normal pin of the visible pin's type.
    const visibleTwin = group.find(o => !o.pin.hidden && o.x === f.x && o.y === f.y && o.pin.name === f.pin.name);
    if (f.pin.hidden && visibleTwin) {
      f.pin.hidden = false;
      f.pin.etype = visibleTwin.pin.etype;
    }
  }
  return group.map(f => f.pin);
}

// The common start of the names ("PA0", "PA1" -> "PA"), or else the first name.
function groupName(names) {
  let prefix = names[0];
  for (const name of names) {
    while (!name.startsWith(prefix)) prefix = prefix.slice(0, -1);
  }
  prefix = prefix.replace(/[_\-\s]+$/, '');
  return prefix.length >= 2 ? prefix : names[0];
}

function uniqueName(name, usedNames) {
  let unique = name;
  for (let i = 2; usedNames.has(unique); i++) unique = `${name}_${i}`;
  usedNames.add(unique);
  return unique;
}

// --- A tiny S-expression reader ---

// '(a "b c" (d 1))'  ->  ['a', 'b c', ['d', '1']]
function parseSexpr(text) {
  const tokens = text.match(/"(?:[^"\\]|\\.)*"|[()]|[^\s()"]+/g) || [];
  const stack = [[]];
  for (const token of tokens) {
    if (token === '(') {
      stack.push([]);
    } else if (token === ')') {
      const finished = stack.pop();
      stack.at(-1).push(finished);
    } else if (token.startsWith('"')) {
      stack.at(-1).push(token.slice(1, -1).replace(/\\(.)/g, '$1'));
    } else {
      stack.at(-1).push(token);
    }
  }
  return stack[0][0] || [];
}

function children(node, tag) {
  return node.filter(item => Array.isArray(item) && item[0] === tag);
}

function child(node, tag) {
  return children(node, tag)[0];
}
