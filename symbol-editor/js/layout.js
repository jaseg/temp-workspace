// Works out where the body and every pin of each unit go.
//
// Units are mil (1/1000 inch). Axes are like in KiCad symbol files: x to the right, y UP.
// The origin is the middle of each unit's body.
//
// Each side is a list of slots, one grid step each. Pins are grouped by their "group"
// column, with one empty slot between groups. Left and right pins start at the top
// edge; top and bottom pins sit centred between the left and right pin names.

import { SIDES } from './pins.js';

export const GRID = 100;
const CHAR_WIDTH = 47; // rough width of one character in KiCad's 50 mil font
const STACKABLE_TYPES = ['power_in', 'power_out'];

// Direction from a pin's connection point towards the body, per KiCad pin angle.
const PIN_ANGLE = { left: 0, right: 180, top: 270, bottom: 90 };

export function layoutSymbol(pins, settings) {
  const pinLength = choosePinLength(pins, settings);
  const unitNumbers = [...new Set(pins.map(pin => pin.unit))].sort((a, b) => a - b);
  // KiCad numbers units 1, 2, 3 ... without gaps, so unit 1 and 5 become 1 and 2.
  return unitNumbers.map((unitNumber, i) => ({
    unit: i + 1,
    pinLength,
    ...layoutUnit(pins.filter(pin => pin.unit === unitNumber), settings, pinLength),
  }));
}

function choosePinLength(pins, settings) {
  if (settings.pinLength !== 'auto') return Number(settings.pinLength);
  // Long pin numbers (like BGA "AA12") don't fit on a short pin.
  return pins.some(pin => pin.number.length > 2) ? 200 : 100;
}

function layoutUnit(pins, settings, pinLength) {
  const slots = {};
  const nameWidth = {};
  for (const side of SIDES) {
    const sidePins = pins.filter(pin => pin.side === side);
    slots[side] = makeSlots(sidePins, settings.stackPowerPins);
    nameWidth[side] = Math.max(0, ...sidePins.map(pin => pin.name.length)) * CHAR_WIDTH;
  }

  // Wide enough for: left names | top/bottom pins | right names.
  // High enough for: the side pins, and for top names above bottom names.
  const middleSlots = Math.max(slots.top.length, slots.bottom.length);
  const sideSlots = Math.max(slots.left.length, slots.right.length);
  const width = roundUp(Math.max(nameWidth.left + middleSlots * GRID + nameWidth.right + 2 * GRID, 4 * GRID));
  const height = roundUp(Math.max(sideSlots * GRID + GRID, nameWidth.top + nameWidth.bottom + 2 * GRID, 2 * GRID));
  const halfWidth = width / 2;
  const halfHeight = height / 2;

  const sideY = i => halfHeight - (i + 1) * GRID;
  const middle = (nameWidth.left - nameWidth.right) / 2;
  const middleX = (i, count) => snap(middle - (count - 1) * GRID / 2) + i * GRID;

  const position = {
    left: (i) => ({ x: -halfWidth - pinLength, y: sideY(i) }),
    right: (i) => ({ x: halfWidth + pinLength, y: sideY(i) }),
    top: (i, count) => ({ x: middleX(i, count), y: halfHeight + pinLength }),
    bottom: (i, count) => ({ x: middleX(i, count), y: -halfHeight - pinLength }),
  };

  const placed = [];
  for (const side of SIDES) {
    slots[side].forEach((slot, i) => {
      if (!slot) return; // gap between groups
      const { x, y } = position[side](i, slots[side].length);
      slot.forEach((pin, k) => placed.push({
        pin, x, y,
        angle: PIN_ANGLE[side],
        stacked: k > 0, // hidden copy behind the first pin in this slot
        stackNumbers: slot.map(p => p.number),
      }));
    });
  }
  return { width, height, pins: placed };
}

// Where KiCad's Reference and Value texts go: above and below the body,
// clear of any top and bottom pins.
export function propertyPositions(unit) {
  const hasPins = angle => unit.pins.some(placed => placed.angle === angle);
  const left = -unit.width / 2;
  return {
    reference: { x: left, y: unit.height / 2 + (hasPins(270) ? unit.pinLength : 0) + GRID },
    value: { x: left, y: -unit.height / 2 - (hasPins(90) ? unit.pinLength : 0) - GRID },
  };
}

// One slot per pin, null between groups. Power pins with the same name share a slot.
export function makeSlots(pins, stackPowerPins) {
  const slots = [];
  const groups = [...new Set(pins.map(pin => pin.group))];
  for (const group of groups) {
    if (slots.length > 0) slots.push(null);
    for (const pin of pins.filter(p => p.group === group)) {
      const canStack = stackPowerPins && STACKABLE_TYPES.includes(pin.etype);
      const stack = canStack && slots.find(slot => slot && slot[0].name === pin.name);
      if (stack) stack.push(pin);
      else slots.push([pin]);
    }
  }
  return slots;
}

// Body sizes are multiples of 200 mil, so that half of them (the edges) lie on the grid.
function roundUp(value) {
  return Math.ceil(value / (2 * GRID)) * 2 * GRID;
}

function snap(value) {
  return Math.round(value / GRID) * GRID;
}
