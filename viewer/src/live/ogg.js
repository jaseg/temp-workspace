// Ogg Vorbis decoding everywhere. Browsers decode it natively (Safari from 18.4); older Safari can't, or only
// partly (14.1–18.3 depending on the system), and gets the WebAssembly decoder from upstream (lib/oggdec.js). That
// decoder is a separate file, loaded only by browsers that need it.

/** Whether the bytes are an Ogg file (custom levels' songs, the hit sound). */
export function isOgg(buffer) {
	const head = new Uint8Array(buffer, 0, Math.min(4, buffer.byteLength));
	return String.fromCharCode(...head) === 'OggS';
}

let nativeOgg;

/** Whether the browser says it can play Ogg Vorbis itself (an `<audio>` element or `decodeAudioData`). */
export function canPlayOgg() {
	if (nativeOgg === undefined) nativeOgg = document.createElement('audio').canPlayType('audio/ogg; codecs="vorbis"') !== '';
	return nativeOgg;
}

let wasmDecoder = null;

function loadWasmDecoder() {
	wasmDecoder =
		wasmDecoder ||
		import(/* webpackChunkName: "oggdec" */ '../lib/oggdec').then(module => {
			const factory = module.default || module;
			return factory().decodeOggData;
		});
	return wasmDecoder;
}

function decodeNatively(context, data) {
	return new Promise((resolve, reject) => {
		// Older Safari only has the callback form.
		const result = context.decodeAudioData(data, resolve, reject);
		if (result && result.then) result.then(resolve, reject);
	});
}

/** Decodes an audio file into an AudioBuffer: natively if possible, else (Ogg only) with WebAssembly. */
export async function decodeAudio(context, data) {
	// decodeAudioData detaches the buffer it's given, so each attempt gets a copy.
	if (!isOgg(data)) return decodeNatively(context, data.slice(0));
	if (canPlayOgg()) {
		try {
			return await decodeNatively(context, data.slice(0));
		} catch (e) {
			// Partial support: the browser claims Ogg but can't decode this file. Use the fallback.
		}
	}
	const decode = await loadWasmDecoder();
	return decode(data.slice(0));
}
