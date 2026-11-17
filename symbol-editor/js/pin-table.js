// <pin-table>: the editable, sortable list of pins.
//
// Call table.load(pins) with the pin array. The table edits that array in place
// and fires a "pins-changed" event after every edit.
//
// Rules it keeps:
// - All pins of a group are on the same side.
// - New pin numbers (from Repeat, Enter or Tab) that are already in use are left empty.

import { COLUMNS, newPin, naturalCompare, cellToValue, groupSide, setGroupSide } from './pins.js';
import { guessGroup } from './autocomplete.js';
import { continueBlock, nextName, nextNumber } from './increment.js';

class PinTable extends HTMLElement {
  connectedCallback() {
    this.innerHTML = `
      <div class="toolbar">
        <button data-action="add">Add row</button>
        <button data-action="repeat" title="Insert continued copies of the selected rows: PA0, PA1 → PA2, PA3">Repeat selected</button>
        ×<input class="repeat-count" type="number" min="1" value="1">
        <button data-action="delete">Delete selected</button>
        <span class="hint">
          Shift-click checkboxes to select a range. Enter: next row. Tab in an empty Name or Number
          continues the one above. Paste cells from a spreadsheet or PDF.
        </span>
      </div>
      <div class="table-scroll">
        <table>
          <thead><tr>
            <th></th><th>#</th>
            ${COLUMNS.map(column => `<th data-key="${column.key}" title="Click to sort">${column.title}</th>`).join('')}
          </tr></thead>
          <tbody></tbody>
        </table>
      </div>
      <datalist id="group-names"></datalist>`;

    this.tbody = this.querySelector('tbody');
    this.pins = [];
    this.selected = new Set();

    this.querySelector('.toolbar').addEventListener('click', event => {
      const action = event.target.dataset.action;
      if (action === 'add') this.addRow();
      if (action === 'repeat') this.repeatSelected();
      if (action === 'delete') this.deleteSelected();
    });
    this.querySelector('thead').addEventListener('click', event => {
      if (event.target.dataset.key) this.sortBy(event.target.dataset.key);
    });
    this.tbody.addEventListener('input', event => this.onInput(event));
    this.tbody.addEventListener('change', event => this.onChange(event));
    this.tbody.addEventListener('click', event => this.onClick(event));
    this.tbody.addEventListener('keydown', event => this.onKeydown(event));
    this.tbody.addEventListener('focusin', event => this.showSuggestion(event.target));
    this.tbody.addEventListener('focusout', event => { if (event.target.placeholder) event.target.placeholder = ''; });
    this.tbody.addEventListener('paste', event => this.onPaste(event));
  }

  load(pins) {
    this.pins = pins;
    this.selected = new Set();
    this.render();
  }

  // --- Drawing ---

  render() {
    this.tbody.replaceChildren(...this.pins.map((pin, index) => this.makeRow(pin, index)));
    this.updateGroupNames();
    this.markDuplicateNumbers();
  }

  makeRow(pin, index) {
    const row = document.createElement('tr');
    row.innerHTML = `<td><input type="checkbox" class="select"></td><td class="row-number">${index + 1}</td>`
      + COLUMNS.map(column => `<td>${inputHtml(column)}</td>`).join('');
    this.fillRow(row, pin);
    return row;
  }

  // Put the pin's values into the inputs of an existing row.
  fillRow(row, pin) {
    for (const column of COLUMNS) {
      const input = row.querySelector(`[data-key="${column.key}"]`);
      if (column.input === 'checkbox') input.checked = pin[column.key];
      else input.value = pin[column.key];
    }
    row.querySelector('.select').checked = this.selected.has(pin);
    row.classList.toggle('selected', this.selected.has(pin));
  }

  fillAllRows() {
    this.pins.forEach((pin, i) => this.fillRow(this.tbody.rows[i], pin));
  }

  updateGroupNames() {
    const groups = [...new Set(this.pins.map(pin => pin.group).filter(Boolean))].sort(naturalCompare);
    this.querySelector('#group-names').innerHTML = groups.map(group => `<option value="${escapeHtml(group)}">`).join('');
  }

  // Pin numbers must be unique; show the ones that are not in red.
  markDuplicateNumbers() {
    const counts = new Map();
    for (const pin of this.pins) counts.set(pin.number, (counts.get(pin.number) || 0) + 1);
    this.pins.forEach((pin, i) => {
      const input = this.tbody.rows[i].querySelector('[data-key="number"]');
      input.classList.toggle('duplicate', pin.number !== '' && counts.get(pin.number) > 1);
    });
  }

  // Scroll to a pin's row and flash it (used when a pin is clicked in the preview).
  highlight(pin) {
    const row = this.tbody.rows[this.pins.indexOf(pin)];
    if (!row) return;
    row.scrollIntoView({ block: 'center', behavior: 'smooth' });
    row.classList.remove('flash');
    void row.offsetWidth; // restart the CSS animation
    row.classList.add('flash');
  }

  // `rerender`: rows were added, removed or moved. `typing`: the user is typing in a cell.
  changed({ rerender = false, typing = false } = {}) {
    if (rerender) this.render();
    else this.markDuplicateNumbers();
    this.dispatchEvent(new CustomEvent('pins-changed', { bubbles: true, detail: { typing } }));
  }

  // --- Editing cells ---

  onInput(event) {
    const key = event.target.dataset.key;
    if (!key) return;
    const column = COLUMNS.find(c => c.key === key);
    const pin = this.pins[rowIndexOf(event.target)];
    pin[key] = readInput(event.target, column);
    if (key === 'side') {
      setGroupSide(this.pins, pin.group, pin.side); // the whole group moves along
      this.fillAllRows();
    }
    this.changed({ typing: column.input === 'text' || column.input === 'number' });
  }

  // "change" fires when the user is done with a cell (leaves it, or presses Enter).
  onChange(event) {
    const key = event.target.dataset.key;
    if (key) this.finishEdit(rowIndexOf(event.target), key);
  }

  finishEdit(index, key) {
    const pin = this.pins[index];
    if (key === 'name' && !pin.group) Object.assign(pin, guessGroup(this.pins, pin));
    if (key === 'group') pin.side = groupSide(this.pins, pin.group, pin) || pin.side;
    this.fillRow(this.tbody.rows[index], pin);
    this.updateGroupNames();
    this.changed();
  }

  onKeydown(event) {
    const key = event.target.dataset.key;
    if (!key) return;
    if (event.key === 'Enter') this.moveDown(event, key);
    if (event.key === 'Tab' && !event.shiftKey) this.tabComplete(event, key);
  }

  // Enter moves to the same cell in the next row, adding a row at the end.
  moveDown(event, key) {
    event.preventDefault();
    const index = rowIndexOf(event.target);
    event.target.blur(); // commits the edit, which runs onChange (and so the group guess)
    if (index === this.pins.length - 1) {
      const added = continueBlock([this.pins[index]]);
      this.clearTakenNumbers(added);
      this.pins.push(...added);
      this.changed({ rerender: true });
    }
    this.tbody.rows[index + 1].querySelector(`[data-key="${key}"]`).focus();
  }

  // --- Tab completion ---

  // Tab in an empty Name or Number cell fills in the suggestion; the next Tab moves on.
  tabComplete(event, key) {
    const input = event.target;
    const index = rowIndexOf(input);
    const suggestion = this.suggestion(index, key);
    if (input.value !== '' || suggestion === '') return; // a normal Tab
    event.preventDefault();
    input.value = suggestion;
    this.pins[index][key] = suggestion;
    this.finishEdit(index, key);
  }

  // The nearest name/number above this row, continued: PA3 -> PA4, TX0_P -> TX0_N, 7 -> 8.
  suggestion(index, key) {
    if (key !== 'name' && key !== 'number') return '';
    const above = this.pins.slice(0, index).reverse().find(pin => pin[key] !== '');
    if (!above) return '';
    if (key === 'name') return nextName(above.name);
    const number = nextNumber(above.number);
    return this.isNumberTaken(number) ? '' : number;
  }

  // Shows what Tab would fill in, as grey placeholder text in an empty cell.
  showSuggestion(input) {
    const key = input.dataset.key;
    if (key === 'name' || key === 'number') input.placeholder = this.suggestion(rowIndexOf(input), key);
  }

  isNumberTaken(number) {
    return number !== '' && this.pins.some(pin => pin.number === number);
  }

  // New rows may not reuse a pin number that is in use; such numbers are left empty.
  clearTakenNumbers(newPins) {
    const taken = new Set(this.pins.map(pin => pin.number));
    for (const pin of newPins) {
      if (taken.has(pin.number)) pin.number = '';
      taken.add(pin.number);
    }
  }

  // --- Pasting ---

  // Pasting several cells (from a spreadsheet, or text copied from a PDF) fills the
  // table from the current cell to the right and down, adding rows as needed.
  onPaste(event) {
    const key = event.target.dataset.key;
    const rows = parsePastedCells(event.clipboardData.getData('text/plain'));
    if (!key || rows.length === 0 || (rows.length === 1 && rows[0].length === 1)) return; // a normal paste
    event.preventDefault();

    const firstRow = rowIndexOf(event.target);
    const columns = COLUMNS.slice(COLUMNS.findIndex(column => column.key === key));
    rows.forEach((cells, r) => {
      if (firstRow + r >= this.pins.length) this.pins.push(newPin());
      const pin = this.pins[firstRow + r];
      fitCells(cells, columns.length).forEach((cell, c) => {
        if (cell !== '') pin[columns[c].key] = cellToValue(columns[c], cell);
      });
      if (!pin.group) Object.assign(pin, guessGroup(this.pins, pin));
      pin.side = groupSide(this.pins, pin.group, pin) || pin.side;
    });
    this.changed({ rerender: true });
  }

  // --- Selecting rows ---

  onClick(event) {
    if (!event.target.classList.contains('select')) return;
    const index = rowIndexOf(event.target);
    const shiftRange = event.shiftKey && this.lastClicked !== undefined;
    const from = shiftRange ? Math.min(this.lastClicked, index) : index;
    const to = shiftRange ? Math.max(this.lastClicked, index) : index;
    for (let i = from; i <= to; i++) {
      if (event.target.checked) this.selected.add(this.pins[i]);
      else this.selected.delete(this.pins[i]);
    }
    this.lastClicked = index;
    this.fillAllRows();
  }

  selectedPins() {
    return this.pins.filter(pin => this.selected.has(pin));
  }

  // --- Toolbar actions ---

  addRow() {
    const selected = this.selectedPins();
    const at = selected.length ? this.pins.indexOf(selected.at(-1)) + 1 : this.pins.length;
    this.pins.splice(at, 0, newPin());
    this.changed({ rerender: true });
    this.tbody.rows[at].querySelector('[data-key="number"]').focus();
  }

  // Insert continued copies of the selected rows (or of the last row) after them.
  repeatSelected() {
    let block = this.selectedPins();
    if (block.length === 0) block = this.pins.slice(-1);
    if (block.length === 0) return;
    const at = this.pins.indexOf(block.at(-1)) + 1;
    const times = Math.max(1, parseInt(this.querySelector('.repeat-count').value) || 1);
    const added = [];
    for (let i = 0; i < times; i++) {
      block = continueBlock(block);
      added.push(...block);
    }
    this.clearTakenNumbers(added);
    this.pins.splice(at, 0, ...added);
    this.selected = new Set(block); // so that the next repeat continues from here
    this.changed({ rerender: true });
  }

  deleteSelected() {
    const keep = this.pins.filter(pin => !this.selected.has(pin));
    this.pins.splice(0, this.pins.length, ...keep);
    this.selected = new Set();
    this.changed({ rerender: true });
  }

  // Click a header to sort by that column; click again to reverse.
  sortBy(key) {
    this.sortDirection = this.sortKey === key ? -this.sortDirection : 1;
    this.sortKey = key;
    this.pins.sort((a, b) => this.sortDirection * naturalCompare(a[key], b[key]));
    for (const th of this.querySelectorAll('th[data-key]')) {
      th.dataset.sort = th.dataset.key === key ? (this.sortDirection > 0 ? '▲' : '▼') : '';
    }
    this.changed({ rerender: true });
  }
}

function inputHtml(column) {
  const key = `data-key="${column.key}"`;
  if (column.input === 'select') {
    return `<select ${key}>${column.options.map(option => `<option>${option}</option>`).join('')}</select>`;
  }
  if (column.input === 'checkbox') return `<input type="checkbox" ${key}>`;
  if (column.input === 'number') return `<input type="number" min="1" ${key}>`;
  if (column.key === 'group') return `<input ${key} list="group-names">`;
  return `<input ${key}>`;
}

function readInput(input, column) {
  if (column.input === 'checkbox') return input.checked;
  if (column.input === 'number') return Math.max(1, parseInt(input.value) || 1);
  return input.value;
}

// Spreadsheets separate cells with tabs. Text copied from a PDF only has spaces,
// so then every run of spaces separates two cells.
function parsePastedCells(text) {
  const lines = text.replace(/\r/g, '').split('\n').filter(line => line.trim() !== '');
  if (text.includes('\t')) return lines.map(line => line.split('\t').map(cell => cell.trim()));
  return lines.map(line => line.trim().split(/\s+/));
}

// Cells beyond the last column (like a long list of alternate functions) are joined into it.
function fitCells(cells, columnCount) {
  if (cells.length <= columnCount) return cells;
  const overflow = cells.slice(columnCount - 1).join(', ').replace(/,\s*,/g, ',');
  return [...cells.slice(0, columnCount - 1), overflow];
}

function rowIndexOf(element) {
  return element.closest('tr').sectionRowIndex;
}

function escapeHtml(text) {
  return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
}

customElements.define('pin-table', PinTable);
