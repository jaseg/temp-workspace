// "Balance sides": moves whole groups between the left and right side of each
// unit until both sides are about equally long. Changes the pins' sides in place.
// Top and bottom pins are left alone.

import { makeSlots } from './layout.js';

export function balanceSides(pins, settings) {
  for (const unit of new Set(pins.map(pin => pin.unit))) {
    const sidePins = pins.filter(pin => pin.unit === unit && (pin.side === 'left' || pin.side === 'right'));
    while (moveBestGroup(sidePins, settings)) {
      // keep going while moves make the sides more even
    }
  }
}

// Moves the one group whose move makes the sides most even.
// Returns false if no move helps.
function moveBestGroup(pins, settings) {
  const unevenness = () => Math.abs(sideLength(pins, 'left', settings) - sideLength(pins, 'right', settings));
  let best = null;
  let bestUnevenness = unevenness();

  for (const groupPins of groupsBySide(pins)) {
    const side = groupPins[0].side;
    const otherSide = side === 'left' ? 'right' : 'left';
    setSide(groupPins, otherSide); // try it ...
    const after = unevenness();
    setSide(groupPins, side); // ... and put it back
    if (after < bestUnevenness) {
      best = { groupPins, otherSide };
      bestUnevenness = after;
    }
  }

  if (best) setSide(best.groupPins, best.otherSide);
  return best !== null;
}

// Lists of pins that share a group and a side.
function groupsBySide(pins) {
  const groups = new Map();
  for (const pin of pins) {
    const key = pin.group + '\n' + pin.side;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(pin);
  }
  return [...groups.values()];
}

function sideLength(pins, side, settings) {
  return makeSlots(pins.filter(pin => pin.side === side), settings.stackPowerPins).length;
}

function setSide(pins, side) {
  for (const pin of pins) pin.side = side;
}
