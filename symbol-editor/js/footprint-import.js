// Reads pad numbers out of a KiCad footprint file (.kicad_mod).
// We don't parse the whole file; we only look for `(pad "NUMBER" ...` and `(footprint "NAME"`.

export function padNumbers(text) {
  const numbers = [...text.matchAll(/\(pad\s+"?([^"\s)]*)"?/g)]
    .map(match => match[1])
    .filter(number => number !== ''); // mechanical holes have no number
  return [...new Set(numbers)].sort(comparePads);
}

export function footprintName(text) {
  const match = text.match(/\((?:footprint|module)\s+"?([^"\s)]+)"?/);
  return match ? match[1] : '';
}

// Sorts 1, 2, ..., 10 and BGA balls A1, A2, ..., Y1, AA1 (AA after Y, not after A).
function comparePads(a, b) {
  const lettersA = a.match(/^[A-Z]*/)[0].length;
  const lettersB = b.match(/^[A-Z]*/)[0].length;
  return lettersA - lettersB || a.localeCompare(b, undefined, { numeric: true });
}
