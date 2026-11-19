// Render a read KiCad file (see kicad/index.js) into a scene.

import { createScene } from './scene.js';
import { renderSchematic, renderLibSymbol } from './schematic.js';
import { renderBoard, renderFootprintFile } from './board.js';

/**
 * @param {{type: string, model: object}} file  result of readKicad()
 * @param {{entry?: string}} options  library files: name of the symbol to show (default: first)
 */
export function renderModel(file, { entry } = {}) {
  const scene = createScene();
  const m = file.model;
  switch (file.type) {
    case 'schematic':
      return renderSchematic(scene, m);
    case 'board':
      return renderBoard(scene, m);
    case 'footprint':
      return renderFootprintFile(scene, m);
    case 'symbol_lib': {
      const def = m.symbols.find(s => s.name === entry) ?? m.symbols[0];
      if (def) scene.safely(() => renderLibSymbol(scene, def, { version: m.version }), 'symbol');
      return scene;
    }
  }
  return scene;
}

/** Whether a scene uses schematic-style layers (theme keys) or board layers. */
export function isSchematicType(type) {
  return type === 'schematic' || type === 'symbol_lib';
}
