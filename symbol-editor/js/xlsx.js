// Minimal .xlsx reading and writing: plain cell values only, no formatting.
// A workbook here is { sheetName: rows }, where rows is a list of lists of cell values.
// An .xlsx file is a zip of XML files; see makeZip/readZip in zip.js.

import { makeZip, readZip } from './zip.js';

const MAIN_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';
const RELATIONSHIP_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships';
const PACKAGE_RELATIONSHIP_NS = 'http://schemas.openxmlformats.org/package/2006/relationships';
const XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

// --- Writing ---

export function writeXlsx(workbook) {
  const names = Object.keys(workbook);
  const files = {
    '[Content_Types].xml': xml(`<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
      <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
      <Default Extension="xml" ContentType="application/xml"/>
      <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
      ${names.map((_, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join('')}
    </Types>`),
    '_rels/.rels': xml(`<Relationships xmlns="${PACKAGE_RELATIONSHIP_NS}">
      <Relationship Id="rId1" Type="${RELATIONSHIP_NS}/officeDocument" Target="xl/workbook.xml"/>
    </Relationships>`),
    'xl/workbook.xml': xml(`<workbook xmlns="${MAIN_NS}" xmlns:r="${RELATIONSHIP_NS}"><sheets>
      ${names.map((name, i) => `<sheet name="${escape(name)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join('')}
    </sheets></workbook>`),
    'xl/_rels/workbook.xml.rels': xml(`<Relationships xmlns="${PACKAGE_RELATIONSHIP_NS}">
      ${names.map((_, i) => `<Relationship Id="rId${i + 1}" Type="${RELATIONSHIP_NS}/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join('')}
    </Relationships>`),
  };
  names.forEach((name, i) => {
    files[`xl/worksheets/sheet${i + 1}.xml`] = sheetXml(workbook[name]);
  });
  return makeZip(files, XLSX_MIME);
}

function sheetXml(rows) {
  const rowsXml = rows.map((row, r) => {
    const cells = row.map((value, c) => cellXml(columnLetters(c) + (r + 1), value));
    return `<row r="${r + 1}">${cells.join('')}</row>`;
  });
  return xml(`<worksheet xmlns="${MAIN_NS}"><sheetData>${rowsXml.join('')}</sheetData></worksheet>`);
}

function cellXml(ref, value) {
  if (value === '' || value === null || value === undefined) return '';
  if (typeof value === 'number') return `<c r="${ref}"><v>${value}</v></c>`;
  return `<c r="${ref}" t="inlineStr"><is><t>${escape(value)}</t></is></c>`;
}

// 0 -> A, 25 -> Z, 26 -> AA
function columnLetters(index) {
  let letters = '';
  for (let n = index + 1; n > 0; n = Math.floor((n - 1) / 26)) {
    letters = String.fromCharCode(65 + (n - 1) % 26) + letters;
  }
  return letters;
}

function columnIndex(letters) {
  let index = 0;
  for (const letter of letters) index = index * 26 + letter.charCodeAt(0) - 64;
  return index - 1;
}

function xml(body) {
  return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + body;
}

function escape(text) {
  return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// --- Reading ---

export async function readXlsx(file) {
  const files = await readZip(await file.arrayBuffer());
  const parse = path => new DOMParser().parseFromString(files[path] || '<x/>', 'application/xml');
  const elements = (doc, tag) => [...doc.getElementsByTagNameNS('*', tag)];

  // Text that many cells share is stored once, in sharedStrings.xml.
  const sharedStrings = elements(parse('xl/sharedStrings.xml'), 'si')
    .map(si => elements(si, 't').map(t => t.textContent).join(''));

  // Find each sheet's file through workbook.xml and its relationships file.
  const targets = {};
  for (const rel of elements(parse('xl/_rels/workbook.xml.rels'), 'Relationship')) {
    const target = rel.getAttribute('Target');
    targets[rel.getAttribute('Id')] = target.startsWith('/') ? target.slice(1) : 'xl/' + target;
  }

  const workbook = {};
  for (const sheet of elements(parse('xl/workbook.xml'), 'sheet')) {
    const path = targets[sheet.getAttributeNS(RELATIONSHIP_NS, 'id')];
    workbook[sheet.getAttribute('name')] = readSheet(parse(path), sharedStrings, elements);
  }
  return workbook;
}

function readSheet(doc, sharedStrings, elements) {
  const rows = [];
  for (const rowElement of elements(doc, 'row')) {
    const row = [];
    for (const cell of elements(rowElement, 'c')) {
      const column = columnIndex(cell.getAttribute('r').replace(/\d+/g, ''));
      row[column] = cellValue(cell, sharedStrings, elements);
    }
    rows[Number(rowElement.getAttribute('r')) - 1] = row;
  }
  return Array.from(rows, row => Array.from(row || [], cell => cell ?? ''));
}

function cellValue(cell, sharedStrings, elements) {
  const type = cell.getAttribute('t');
  if (type === 'inlineStr') return elements(cell, 't').map(t => t.textContent).join('');
  const value = elements(cell, 'v')[0]?.textContent ?? '';
  if (type === 's') return sharedStrings[Number(value)];
  return value;
}
