// Level covers kept across page loads, in the browser's Cache Storage. A level id is the hash of its files, so a
// stored cover never goes stale. Bounded: the oldest covers go first. Any storage failure (private windows,
// blocked site data, quota) just means fetching again.

const CACHE_NAME = 'bslive-covers-v1';
const MAX_STORED = 2000;

let opened = null;
let trimming = null;

function open() {
	if (!opened) {
		opened = (typeof caches !== 'undefined' ? caches.open(CACHE_NAME) : Promise.reject(new Error('no Cache Storage'))).catch(() => null);
	}
	return opened;
}

// Synthetic same-origin URLs as cache keys; nothing is ever requested from them.
const key = id => new Request(`${location.origin}/cover-cache/${encodeURIComponent(id)}`);

/** The stored cover as a Blob, or null. */
export async function getCover(id) {
	try {
		const cache = await open();
		const response = cache && (await cache.match(key(id)));
		return response ? await response.blob() : null;
	} catch (e) {
		return null;
	}
}

export async function putCover(id, buffer) {
	try {
		const cache = await open();
		if (!cache) return;
		await cache.put(key(id), new Response(buffer, {headers: {'Content-Type': 'application/octet-stream'}}));
		trimming = trimming || trim(cache).finally(() => (trimming = null));
	} catch (e) {
		// Not stored; it's fetched again next time.
	}
}

async function trim(cache) {
	const keys = await cache.keys(); // insertion order
	for (let i = 0; i < keys.length - MAX_STORED; i++) await cache.delete(keys[i]);
}
