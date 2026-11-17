// Wires the page together: the header buttons, the pin table, the preview and the
// settings dialog. The whole symbol lives in `state` and is saved to the browser's
// localStorage after every change, so a page reload doesn't lose work.

import './pin-table.js';
import './symbol-preview.js';
import './settings-dialog.js';
import { defaultSettings, newPin, pinsToRows, rowsToPins, settingsToRows, rowsToSettings } from './pins.js';
import { layoutSymbol } from './layout.js';
import { toKicadSym } from './kicad-export.js';
import { writeXlsx, readXlsx } from './xlsx.js';
import { padNumbers, footprintName } from './footprint-import.js';

const STORAGE_KEY = 'kicad-symbol-editor';

const table = document.querySelector('pin-table');
const preview = document.querySelector('symbol-preview');
const settingsDialog = document.querySelector('symbol-settings');

let state = loadState();
table.load(state.pins);
update();

table.addEventListener('pins-changed', update);
settingsDialog.addEventListener('settings-changed', update);
preview.addEventListener('pin-click', event => table.highlight(event.detail));

document.querySelector('header').addEventListener('click', event => {
  const action = actions[event.target.dataset.action];
  if (action) action();
});

const actions = {
  new() {
    if (!confirm('Start a new, empty symbol? Unsaved work will be lost.')) return;
    replaceState({ settings: defaultSettings(), pins: [] });
  },

  settings() {
    settingsDialog.open(state.settings);
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

  downloadKicad() {
    const text = toKicadSym(state.pins, state.settings);
    download(new Blob([text], { type: 'text/plain' }), `${state.settings.name}.kicad_sym`);
  },
};

function update() {
  document.querySelector('#symbol-name').textContent = state.settings.name;
  preview.show(layoutSymbol(state.pins, state.settings));
  saveState();
}

function replaceState(newState) {
  state = newState;
  table.load(state.pins);
  update();
  preview.fit();
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
