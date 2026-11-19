// Stable internal keys for model elements, shared by the renderer (scene items) and the diff
// engine (which refers to scene items by key). Keys are internal only and never shown to users.

export const itemKey = (item, index) => item.uuid ?? `${item.type}:${index}`;
export const pinKey = (symbolKey, number) => `${symbolKey}:pin:${number}`;
export const fieldKey = (parentKey, name) => `${parentKey}:field:${name}`;
export const padKey = (footprintKey, pad, index) => pad.uuid ?? `${footprintKey}:pad:${pad.number}:${index}`;
export const sheetPinKey = (sheetKey, name) => `${sheetKey}:pin:${name}`;
export const libSymbolKey = name => `symbol:${name}`;
