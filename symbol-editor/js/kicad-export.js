// Writes the symbol as a KiCad 8 symbol library (.kicad_sym).
//
// Layout of the file:
//   (kicad_symbol_lib
//     (symbol "NAME"
//       (property "Reference" ...) ... more properties
//       (symbol "NAME_1_1"            <- unit 1: body rectangle and pins
//         (rectangle ...)
//         (pin ...))
//       (symbol "NAME_2_1" ...)))     <- unit 2, ...

import { layoutSymbol, propertyPositions } from './layout.js';

const FONT = '(effects (font (size 1.27 1.27)))';

export function toKicadSym(pins, settings) {
  const units = layoutSymbol(pins, settings);
  const name = settings.name;
  const first = units[0] || { width: 0, height: 0, pinLength: 0, pins: [] };
  const { reference, value } = propertyPositions(first);

  const lines = [
    '(kicad_symbol_lib',
    '  (version 20231120)',
    '  (generator "web_symbol_editor")',
    `  (symbol ${quote(name)}`,
    '    (exclude_from_sim no)',
    '    (in_bom yes)',
    '    (on_board yes)',
    property('Reference', settings.reference, reference.x, reference.y),
    property('Value', name, value.x, value.y),
    property('Footprint', settings.footprint, 0, 0, true),
    property('Datasheet', settings.datasheet, 0, 0, true),
    property('Description', settings.description, 0, 0, true),
    property('ki_keywords', settings.keywords, 0, 0, true),
  ];
  for (const unit of units) lines.push(...unitLines(name, unit));
  lines.push('  )', ')', '');
  return lines.join('\n');
}

function property(key, value, x, y, hidden = false) {
  const effects = hidden
    ? '(effects (font (size 1.27 1.27)) hide)'
    : '(effects (font (size 1.27 1.27)) (justify left))';
  return `    (property ${quote(key)} ${quote(value)} (at ${mm(x)} ${mm(y)} 0) ${effects})`;
}

function unitLines(name, unit) {
  const w = unit.width / 2;
  const h = unit.height / 2;
  return [
    `    (symbol ${quote(`${name}_${unit.unit}_1`)}`,
    `      (rectangle (start ${mm(-w)} ${mm(h)}) (end ${mm(w)} ${mm(-h)}) (stroke (width 0.254) (type default)) (fill (type background)))`,
    ...unit.pins.flatMap(placed => pinLines(placed, unit.pinLength)),
    '    )',
  ];
}

function pinLines({ pin, x, y, angle, stacked }, length) {
  // KiCad convention for stacked pins: one visible pin, the others hidden and passive.
  const etype = stacked ? 'passive' : pin.etype;
  const hide = stacked || pin.hidden ? ' hide' : '';
  const lines = [
    `      (pin ${etype} ${pin.shape} (at ${mm(x)} ${mm(y)} ${angle}) (length ${mm(length)})${hide}`,
    `        (name ${quote(pin.name || '~')} ${FONT})`,
    `        (number ${quote(pin.number)} ${FONT})`,
  ];
  for (const alternate of splitAlternates(pin.alternates)) {
    lines.push(`        (alternate ${quote(alternate)} ${etype} ${pin.shape})`);
  }
  lines.push('      )');
  return lines;
}

export function splitAlternates(text) {
  return String(text).split(/[\s,;]+/).filter(Boolean);
}

function mm(mil) {
  return Number((mil * 0.0254).toFixed(4));
}

function quote(text) {
  return '"' + String(text ?? '').replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';
}
