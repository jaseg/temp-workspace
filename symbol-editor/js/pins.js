// The data model.
// A symbol is a settings object plus a flat list of pins.
// Every pin belongs to one unit and sits on one side of that unit's body.

export const ELECTRICAL_TYPES = [
  'input', 'output', 'bidirectional', 'tri_state', 'passive', 'free', 'unspecified',
  'power_in', 'power_out', 'open_collector', 'open_emitter', 'no_connect',
];

export const PIN_SHAPES = [
  'line', 'inverted', 'clock', 'inverted_clock', 'input_low', 'clock_low',
  'output_low', 'edge_clock_high', 'non_logic',
];

export const SIDES = ['left', 'right', 'top', 'bottom'];

// Pin types as datasheets tend to write them, for pasting and xlsx import.
const TYPE_ALIASES = {
  'i': 'input', 'in': 'input', 'o': 'output', 'out': 'output',
  'i/o': 'bidirectional', 'io': 'bidirectional', 'od': 'open_collector',
  'p': 'power_in', 's': 'power_in', 'pwr': 'power_in', 'power': 'power_in',
  'a': 'passive', 'nc': 'no_connect',
};

// The table columns, in order. The titles are also the xlsx column headers.
export const COLUMNS = [
  { key: 'number', title: 'Number', input: 'text' },
  { key: 'name', title: 'Name', input: 'text' },
  { key: 'group', title: 'Group', input: 'text' },
  { key: 'side', title: 'Side', input: 'select', options: SIDES },
  { key: 'unit', title: 'Unit', input: 'number' },
  { key: 'etype', title: 'Type', input: 'select', options: ELECTRICAL_TYPES, aliases: TYPE_ALIASES },
  { key: 'shape', title: 'Shape', input: 'select', options: PIN_SHAPES },
  { key: 'hidden', title: 'Hidden', input: 'checkbox' },
  { key: 'alternates', title: 'Alternate functions', input: 'text' },
];

export function newPin(fields = {}) {
  return {
    number: '',
    name: '',
    group: '',
    side: 'left',
    unit: 1,
    etype: 'bidirectional',
    shape: 'line',
    hidden: false,
    alternates: '', // comma separated, e.g. "USART1_TX, TIM1_CH2"
    ...fields,
  };
}

export function defaultSettings() {
  return {
    name: 'NEW_IC',
    reference: 'U',
    footprint: '',
    datasheet: '',
    description: '',
    keywords: '',
    pinLength: 'auto', // 'auto', or a length in mil
    stackPowerPins: true,
  };
}

// Compare text so that "PA2" comes before "PA10".
export function naturalCompare(a, b) {
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' });
}

// All pins of a group sit on the same side.
// Returns the side a group already has (looking at pins other than `exceptPin`), if any.
export function groupSide(pins, group, exceptPin) {
  const other = group && pins.find(pin => pin !== exceptPin && pin.group === group);
  return other ? other.side : null;
}

export function setGroupSide(pins, group, side) {
  for (const pin of pins) {
    if (group && pin.group === group) pin.side = side;
  }
}

export function parseBool(value) {
  return /^(yes|true|1|x)$/i.test(String(value).trim());
}

// --- Conversion to and from spreadsheet rows (lists of cell values) ---

export function pinsToRows(pins) {
  const header = COLUMNS.map(column => column.title);
  const rows = pins.map(pin => COLUMNS.map(column => {
    if (column.input === 'checkbox') return pin[column.key] ? 'yes' : '';
    return pin[column.key];
  }));
  return [header, ...rows];
}

// Columns are found by their header, so the order in the spreadsheet does not matter.
export function rowsToPins(rows) {
  const header = (rows[0] || []).map(cell => String(cell ?? '').trim().toLowerCase());
  const pins = [];
  for (const row of rows.slice(1)) {
    if (row.every(cell => cell === undefined || cell === '')) continue;
    const pin = newPin();
    for (const column of COLUMNS) {
      const index = header.findIndex(h => h === column.title.toLowerCase() || h === column.key.toLowerCase());
      const cell = row[index];
      if (index < 0 || cell === undefined || cell === '') continue;
      pin[column.key] = cellToValue(column, cell);
    }
    pin.side = groupSide(pins, pin.group) || pin.side;
    pins.push(pin);
  }
  return pins;
}

// Turns a spreadsheet cell (or pasted text) into a value for the given column.
export function cellToValue(column, cell) {
  if (column.input === 'checkbox') return parseBool(cell);
  if (column.input === 'number') return Math.max(1, parseInt(cell) || 1);
  if (column.input === 'select') {
    let value = String(cell).trim().toLowerCase();
    if (column.aliases && column.aliases[value]) value = column.aliases[value];
    return column.options.includes(value) ? value : column.options[0];
  }
  return String(cell).trim();
}

export function settingsToRows(settings) {
  return [['Setting', 'Value'], ...Object.entries(settings)];
}

export function rowsToSettings(rows) {
  const settings = defaultSettings();
  for (const [key, value] of rows.slice(1)) {
    if (!(key in settings) || value === undefined) continue;
    settings[key] = typeof settings[key] === 'boolean' ? parseBool(value) : String(value);
  }
  return settings;
}
