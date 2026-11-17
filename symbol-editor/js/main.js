// Wires the page together: the header buttons, the pin table, the preview and the
// settings dialog. The whole symbol lives in `state`. After every change it is
// recorded for undo and saved to the browser's localStorage, so a reload keeps it.

import './pin-table.js';
import './symbol-preview.js';
import './settings-dialog.js';
import { defaultSettings, newPin, pinsToRows, rowsToPins, settingsToRows, rowsToSettings } from './pins.js';
import { layoutSymbol } from './layout.js';
import { balanceSides } from './balance.js';
import { toKicadSym } from './kicad-export.js';
import { fromKicadSym } from './kicad-import.js';
import { writeXlsx, readXlsx } from './xlsx.js';
import { padNumbers, footprintName } from './footprint-import.js';
import { History } from './history.js';

const STORAGE_KEY = 'kicad-symbol-editor';

const table = document.querySelector('pin-table');
const preview = document.querySelector('symbol-preview');
const settingsDialog = document.querySelector('symbol-settings');

let state = loadState();
const history = new History(state);
table.load(state.pins);
redraw();

table.addEventListener('pins-changed', event => update({ typing: event.detail.typing }));
settingsDialog.addEventListener('settings-changed', () => update());
preview.addEventListener('pin-click', event => table.highlight(event.detail));

document.querySelector('header').addEventListener('click', event => {
  const action = actions[event.target.dataset.action];
  if (action) action();
});

const actions = {
  undo() {
    const snapshot = history.undo();
    if (snapshot) showSnapshot(snapshot);
  },

  redo() {
    const snapshot = history.redo();
    if (snapshot) showSnapshot(snapshot);
  },

  new() {
    if (!confirm('Start a new, empty symbol? (Undo brings the old one back.)')) return;
    replaceState({ settings: defaultSettings(), pins: [] });
  },

  settings() {
    settingsDialog.open(state.settings);
  },

  balanceSides() {
    balanceSides(state.pins, state.settings);
    table.load(state.pins);
    update();
  },

  async uploadXlsx() {
    const workbook = await readXlsx(await pickFile('.xlsx'));
    const pinRows = workbook.Pins || Object.values(workbook)[0] || [];
    const settingRows = workbook.Symbol;
    replaceState({
      settings: settingRows ? rowsToSettings(settingRows) : state.settings,
      pins: rowsToPins(pinRows),
    });
  },

  downloadXlsx() {
    const workbook = { Pins: pinsToRows(state.pins), Symbol: settingsToRows(state.settings) };
    download(writeXlsx(workbook), `${state.settings.name}.xlsx`);
  },

  // Adds a row for every pad number of the footprint that isn't in the table yet.
  async importFootprint() {
    const text = await (await pickFile('.kicad_mod')).text();
    const known = new Set(state.pins.map(pin => pin.number));
    const missing = padNumbers(text).filter(number => !known.has(number));
    state.pins.push(...missing.map(number => newPin({ number })));
    if (!state.settings.footprint) state.settings.footprint = footprintName(text);
    table.load(state.pins);
    update();
    preview.fit();
  },

  async importKicad() {
    const text = await (await pickFile('.kicad_sym')).text();
    try {
      replaceState(fromKicadSym(text));
    } catch (error) {
      alert(`Could not read this file: ${error.message}`);
    }
  },

  downloadKicad() {
    const text = toKicadSym(state.pins, state.settings);
    download(new Blob([text], { type: 'text/plain' }), `${state.settings.name}.kicad_sym`);
  },
};

// Ctrl+Z undoes, Ctrl+Y or Ctrl+Shift+Z redoes (Cmd on a Mac).
document.addEventListener('keydown', event => {
  if (!(event.ctrlKey || event.metaKey) || event.target.closest('dialog')) return;
  const key = event.key.toLowerCase();
  if (key === 'z' && !event.shiftKey) {
    event.preventDefault();
    actions.undo();
  } else if (key === 'y' || (key === 'z' && event.shiftKey)) {
    event.preventDefault();
    actions.redo();
  }
});

// Drag the bar between table and preview to resize them.
const splitter = document.querySelector('.splitter');
splitter.addEventListener('pointerdown', event => {
  splitter.setPointerCapture(event.pointerId);
  const resize = moveEvent => {
    document.querySelector('main').style.setProperty('--table-width', `${moveEvent.clientX}px`);
  };
  splitter.addEventListener('pointermove', resize);
  splitter.addEventListener('pointerup', () => splitter.removeEventListener('pointermove', resize), { once: true });
});

// --- Showing and changing the state ---

// Call after every change: records it for undo, saves it and redraws.
function update({ typing = false } = {}) {
  history.record(state, typing);
  saveState();
  redraw();
}

function redraw() {
  document.querySelector('#symbol-name').textContent = state.settings.name;
  preview.show(layoutSymbol(state.pins, state.settings), state.settings);
}

function replaceState(newState) {
  state = newState;
  table.load(state.pins);
  update();
  preview.fit();
}

// For undo/redo: show an earlier state without recording it again.
function showSnapshot(snapshot) {
  state = snapshot;
  table.load(state.pins);
  saveState();
  redraw();
}

// --- Saving in the browser ---

function loadState() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (saved) return { settings: { ...defaultSettings(), ...saved.settings }, pins: saved.pins.map(newPin) };
  } catch (error) {
    console.warn('Could not load the saved symbol:', error);
  }
  return { settings: defaultSettings(), pins: [] };
}

function saveState() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (error) {
    console.warn('Could not save the symbol:', error);
  }
}

// --- Files ---

function pickFile(accept) {
  return new Promise(resolve => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = accept;
    input.addEventListener('change', () => resolve(input.files[0]));
    input.click();
  });
}

function download(blob, filename) {
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}
