// WebSocket connection to the mod: waiting room, clock sync, message dispatch, map file and level library downloads.
import {T, Reader, SUBPROTOCOL, hello, ping, mapRequest, levelListRequest, levelFileRequest, levelStatsRequest} from './protocol';
import {ServerClock} from './clock';

const CREDENTIAL_KEY = 'bslive.credential';
const PING_INTERVAL_MS = 1000;
const FAST_PINGS = 8; // pings sent quickly after connecting, for a fast initial sync
const RECONNECT_MS = 2000;

function loadCredential() {
	try {
		const hex = localStorage.getItem(CREDENTIAL_KEY);
		if (!hex || !/^[0-9a-f]{64}$/.test(hex)) return null;
		return Uint8Array.from(hex.match(/../g).map(h => parseInt(h, 16)));
	} catch (e) {
		return null;
	}
}

function parseJson(buffer) {
	return JSON.parse(new TextDecoder().decode(buffer));
}

function saveCredential(bytes) {
	try {
		if (bytes) localStorage.setItem(CREDENTIAL_KEY, Array.from(bytes, b => b.toString(16).padStart(2, '0')).join(''));
		else localStorage.removeItem(CREDENTIAL_KEY);
	} catch (e) {
		// Storage unavailable: the device just has to be approved again next time.
	}
}

/**
 * Events (via `handlers`): state(state, detail), message(type, reader, receivedAt).
 * States: connecting, waiting (detail.code), approved, denied, revoked, disconnected.
 */
export class LiveConnection {
	constructor(handlers) {
		this.handlers = handlers;
		this.clock = new ServerClock();
		this.state = 'connecting';
		this.transfers = new Map();
		this.nextRequestId = 1;
		this.ws = null;
		this.pingTimer = null;
	}

	connect() {
		this.setState('connecting');
		const ws = new WebSocket(`wss://${location.host}/ws`, SUBPROTOCOL);
		ws.binaryType = 'arraybuffer';
		this.ws = ws;
		ws.onopen = () => {
			ws.send(hello(loadCredential()));
			this.startPings();
		};
		ws.onmessage = e => this.onMessage(e.data, performance.now());
		ws.onclose = () => {
			clearTimeout(this.pingTimer);
			this.failTransfers('Connection closed');
			if (this.state === 'denied' || this.state === 'revoked') return;
			this.setState('disconnected');
			setTimeout(() => this.connect(), RECONNECT_MS);
		};
	}

	setState(state, detail = {}) {
		this.state = state;
		this.handlers.state(state, detail);
	}

	startPings() {
		let sent = 0;
		const tick = () => {
			if (this.ws.readyState !== WebSocket.OPEN) return;
			this.ws.send(ping(performance.now()));
			sent++;
			this.pingTimer = setTimeout(tick, sent < FAST_PINGS ? 100 : PING_INTERVAL_MS);
		};
		tick();
	}

	onMessage(data, receivedAt) {
		const r = new Reader(data);
		const type = r.u8();
		switch (type) {
			case T.Welcome:
				return;
			case T.Waiting:
				// A stored credential, if we sent one, wasn't accepted.
				saveCredential(null);
				this.setState('waiting', {code: r.str()});
				return;
			case T.Approved:
				if (r.u8()) saveCredential(r.bytes(32).slice());
				this.setState('approved');
				return;
			case T.Denied:
				this.setState('denied');
				return;
			case T.Revoked:
				saveCredential(null);
				this.setState('revoked');
				return;
			case T.Pong: {
				const t0 = r.f64();
				this.clock.addPong(t0, receivedAt, r.i64(), r.i64());
				return;
			}
			case T.MapChunk:
				this.onMapChunk(r, data);
				return;
			case T.MapError: {
				const id = r.u16();
				const code = r.u8();
				const t = this.transfers.get(id);
				if (t) {
					this.transfers.delete(id);
					const error = new Error(`${t.name} unavailable (code ${code})`);
					error.code = code;
					t.reject(error);
				}
				return;
			}
			default:
				this.handlers.message(type, r, receivedAt);
		}
	}

	/** Sends a request answered by a file transfer; resolves with the file's bytes (an ArrayBuffer). */
	request(name, build) {
		return new Promise((resolve, reject) => {
			if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
				reject(new Error('Not connected'));
				return;
			}
			const id = this.nextRequestId++ & 0xffff || this.nextRequestId++;
			this.transfers.set(id, {name, resolve, reject, buffer: null, received: 0});
			this.ws.send(build(id));
		});
	}

	/** Downloads one file of the current session's map. */
	fetchMapFile(sessionId, name) {
		return this.request(`Map file ${name}`, id => mapRequest(id, sessionId, name));
	}

	/** The installed custom levels (see "Level library" in PROTOCOL.md). */
	fetchLevelList() {
		return this.request('Level list', id => levelListRequest(id)).then(parseJson);
	}

	/** A level's cover or song file (`LevelFile.cover` / `LevelFile.audio`), as an ArrayBuffer. */
	fetchLevelFile(levelId, kind) {
		return this.request(`Level file ${kind}`, id => levelFileRequest(id, kind, levelId));
	}

	/** A level's BeatLeader stats, fetched by the mod. */
	fetchLevelStats(levelId) {
		return this.request('Level stats', id => levelStatsRequest(id, levelId)).then(parseJson);
	}

	onMapChunk(r, data) {
		const id = r.u16();
		const total = r.u32();
		const offset = r.u32();
		const t = this.transfers.get(id);
		if (!t) return;
		if (!t.buffer) t.buffer = new Uint8Array(total);
		const chunk = new Uint8Array(data, r.p);
		if (offset + chunk.length > total) {
			this.transfers.delete(id);
			t.reject(new Error('Bad map chunk'));
			return;
		}
		t.buffer.set(chunk, offset);
		t.received += chunk.length;
		if (t.received >= total) {
			this.transfers.delete(id);
			t.resolve(t.buffer.buffer);
		}
	}

	failTransfers(reason) {
		for (const t of this.transfers.values()) t.reject(new Error(reason));
		this.transfers.clear();
	}
}
