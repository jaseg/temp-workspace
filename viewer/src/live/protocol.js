// Binary protocol of the mod's live server. Layouts are documented in mod/PROTOCOL.md.

export const PROTOCOL_VERSION = 3;
export const SUBPROTOCOL = 'bslive.v1';

export const T = {
	Welcome: 0x01,
	Waiting: 0x02,
	Approved: 0x03,
	Denied: 0x04,
	Revoked: 0x05,
	Pong: 0x06,
	Name: 0x07,
	SessionStart: 0x10,
	SessionEnd: 0x11,
	Idle: 0x12,
	SongSelected: 0x13,
	Pose: 0x20,
	NoteCut: 0x21,
	NoteFinal: 0x22,
	Wall: 0x23,
	Height: 0x24,
	Pause: 0x25,
	Resume: 0x26,
	NoteSpawn: 0x27,
	WallSpawn: 0x28,
	MapChunk: 0x30,
	MapError: 0x31,
	Suggestions: 0x40,
	Hello: 0x81,
	Ping: 0x82,
	LevelListRequest: 0x84,
	LevelFileRequest: 0x85,
	LevelStatsRequest: 0x86,
	SuggestionAdd: 0x87,
	SuggestionRemove: 0x88,
	SuggestionMove: 0x89,
	Rename: 0x8a,
};

export const LevelFile = {cover: 1, audio: 2};

// MapError codes.
export const FileError = {notAvailable: 1, noSession: 2, readFailed: 3, tooManyRequests: 4};

export const SessionEndReason = {1: 'cleared', 2: 'failed', 3: 'quit', 4: 'restarted'};

const utf8 = new TextDecoder();

export class Reader {
	constructor(buffer, offset = 0) {
		this.v = new DataView(buffer);
		this.p = offset;
	}
	get remaining() {
		return this.v.byteLength - this.p;
	}
	u8() {
		return this.v.getUint8(this.p++);
	}
	bool() {
		return this.u8() !== 0;
	}
	u16() {
		const x = this.v.getUint16(this.p, true);
		this.p += 2;
		return x;
	}
	u32() {
		const x = this.v.getUint32(this.p, true);
		this.p += 4;
		return x;
	}
	i32() {
		const x = this.v.getInt32(this.p, true);
		this.p += 4;
		return x;
	}
	// Microsecond timestamps stay far below 2^53, so a Number is exact.
	i64() {
		const lo = this.v.getUint32(this.p, true);
		const hi = this.v.getInt32(this.p + 4, true);
		this.p += 8;
		return hi * 4294967296 + lo;
	}
	f32() {
		const x = this.v.getFloat32(this.p, true);
		this.p += 4;
		return x;
	}
	f64() {
		const x = this.v.getFloat64(this.p, true);
		this.p += 8;
		return x;
	}
	bytes(n) {
		const b = new Uint8Array(this.v.buffer, this.v.byteOffset + this.p, n);
		this.p += n;
		return b;
	}
	str() {
		return utf8.decode(this.bytes(this.i32()));
	}
	vec3() {
		return {x: this.f32(), y: this.f32(), z: this.f32()};
	}
	quat() {
		return {x: this.f32(), y: this.f32(), z: this.f32(), w: this.f32()};
	}
	// Same shape as the BSOR decoder's "euler" objects.
	pose() {
		return {position: this.vec3(), rotation: this.quat()};
	}
}

// Same shape as open-replay-decoder's DecodeNote.
export function readNoteEvent(r) {
	const note = {noteID: r.i32(), eventTime: r.f32(), spawnTime: r.f32(), eventType: r.i32()};
	if (note.eventType === 0 || note.eventType === 1) {
		note.noteCutInfo = {
			speedOK: r.bool(),
			directionOK: r.bool(),
			saberTypeOK: r.bool(),
			wasCutTooSoon: r.bool(),
			saberSpeed: r.f32(),
			saberDir: r.vec3(),
			saberType: r.i32(),
			timeDeviation: r.f32(),
			cutDirDeviation: r.f32(),
			cutPoint: r.vec3(),
			cutNormal: r.vec3(),
			cutDistanceToCenter: r.f32(),
			cutAngle: r.f32(),
			beforeCutRating: r.f32(),
			afterCutRating: r.f32(),
		};
	}
	return note;
}

function message(type, size, fill) {
	const buffer = new ArrayBuffer(1 + size);
	const view = new DataView(buffer);
	view.setUint8(0, type);
	fill(view, new Uint8Array(buffer));
	return buffer;
}

export function hello(credential, name) {
	const nameBytes = new TextEncoder().encode(name).slice(0, 128);
	const at = 4 + (credential ? 32 : 0);
	return message(T.Hello, at - 1 + 4 + nameBytes.length, (v, b) => {
		v.setUint16(1, PROTOCOL_VERSION, true);
		v.setUint8(3, credential ? 1 : 0);
		if (credential) b.set(credential, 4);
		v.setInt32(at, nameBytes.length, true);
		b.set(nameBytes, at + 4);
	});
}

export function ping(clientTime) {
	return message(T.Ping, 8, v => v.setFloat64(1, clientTime, true));
}

export function levelListRequest(requestId) {
	return message(T.LevelListRequest, 2, v => v.setUint16(1, requestId, true));
}

export function levelFileRequest(requestId, kind, levelId) {
	const id = new TextEncoder().encode(levelId);
	return message(T.LevelFileRequest, 2 + 1 + 4 + id.length, (v, b) => {
		v.setUint16(1, requestId, true);
		v.setUint8(3, kind);
		v.setInt32(4, id.length, true);
		b.set(id, 8);
	});
}

export function levelStatsRequest(requestId, levelId) {
	const id = new TextEncoder().encode(levelId);
	return message(T.LevelStatsRequest, 2 + 4 + id.length, (v, b) => {
		v.setUint16(1, requestId, true);
		v.setInt32(3, id.length, true);
		b.set(id, 7);
	});
}

export function suggestionChange(add, levelId) {
	const id = new TextEncoder().encode(levelId);
	return message(add ? T.SuggestionAdd : T.SuggestionRemove, 4 + id.length, (v, b) => {
		v.setInt32(1, id.length, true);
		b.set(id, 5);
	});
}

export function suggestionMove(levelId, index) {
	const id = new TextEncoder().encode(levelId);
	return message(T.SuggestionMove, 4 + id.length + 2, (v, b) => {
		v.setInt32(1, id.length, true);
		b.set(id, 5);
		v.setUint16(5 + id.length, index, true);
	});
}

export function rename(name) {
	const bytes = new TextEncoder().encode(name).slice(0, 128);
	return message(T.Rename, 4 + bytes.length, (v, b) => {
		v.setInt32(1, bytes.length, true);
		b.set(bytes, 5);
	});
}
