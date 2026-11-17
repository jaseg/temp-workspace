// Minimal ZIP reading and writing, just enough for .xlsx files.
// Writing stores files uncompressed. Reading also handles compressed ("deflate")
// files, using the browser's built-in DecompressionStream.
// Format reference: https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT

const LOCAL_HEADER = 0x04034b50;
const CENTRAL_HEADER = 0x02014b50;
const END_OF_CENTRAL_DIRECTORY = 0x06054b50;
const DOS_DATE_1980_01_01 = 33;

// files: { "path/in/zip.xml": "text content" }  ->  Blob
export function makeZip(files, mimeType) {
  const encoder = new TextEncoder();
  const localParts = [];
  const centralParts = [];
  let offset = 0;
  let centralSize = 0;

  for (const [path, text] of Object.entries(files)) {
    const name = encoder.encode(path);
    const data = encoder.encode(text);
    const crc = crc32(data);

    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, LOCAL_HEADER, true);
    local.setUint16(4, 20, true); // version needed to extract
    local.setUint16(12, DOS_DATE_1980_01_01, true);
    local.setUint32(14, crc, true);
    local.setUint32(18, data.length, true); // compressed size
    local.setUint32(22, data.length, true); // uncompressed size
    local.setUint16(26, name.length, true);
    localParts.push(local, name, data);

    const central = new DataView(new ArrayBuffer(46));
    central.setUint32(0, CENTRAL_HEADER, true);
    central.setUint16(4, 20, true); // version made by
    central.setUint16(6, 20, true); // version needed to extract
    central.setUint16(14, DOS_DATE_1980_01_01, true);
    central.setUint32(16, crc, true);
    central.setUint32(20, data.length, true);
    central.setUint32(24, data.length, true);
    central.setUint16(28, name.length, true);
    central.setUint32(42, offset, true); // where the local header starts
    centralParts.push(central, name);

    offset += 30 + name.length + data.length;
    centralSize += 46 + name.length;
  }

  const count = Object.keys(files).length;
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, END_OF_CENTRAL_DIRECTORY, true);
  end.setUint16(8, count, true);
  end.setUint16(10, count, true);
  end.setUint32(12, centralSize, true);
  end.setUint32(16, offset, true);

  return new Blob([...localParts, ...centralParts, end], { type: mimeType });
}

// ArrayBuffer  ->  { "path/in/zip.xml": "text content" }
export async function readZip(buffer) {
  const view = new DataView(buffer);
  const bytes = new Uint8Array(buffer);
  const decoder = new TextDecoder();

  // The end record sits at the very end, possibly followed by a comment.
  let end = buffer.byteLength - 22;
  while (end >= 0 && view.getUint32(end, true) !== END_OF_CENTRAL_DIRECTORY) end--;
  if (end < 0) throw new Error('Not a zip file');

  const files = {};
  const count = view.getUint16(end + 10, true);
  let entry = view.getUint32(end + 16, true);
  for (let i = 0; i < count; i++) {
    const method = view.getUint16(entry + 10, true);
    const compressedSize = view.getUint32(entry + 20, true);
    const nameLength = view.getUint16(entry + 28, true);
    const extraLength = view.getUint16(entry + 30, true);
    const commentLength = view.getUint16(entry + 32, true);
    const localOffset = view.getUint32(entry + 42, true);
    const name = decoder.decode(bytes.subarray(entry + 46, entry + 46 + nameLength));

    const dataStart = localOffset + 30 + view.getUint16(localOffset + 26, true) + view.getUint16(localOffset + 28, true);
    const data = bytes.subarray(dataStart, dataStart + compressedSize);
    files[name] = method === 0 ? decoder.decode(data) : await inflate(data);

    entry += 46 + nameLength + extraLength + commentLength;
  }
  return files;
}

async function inflate(data) {
  const stream = new Blob([data]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
  return new Response(stream).text();
}

function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
  }
  return (crc ^ 0xffffffff) >>> 0;
}
