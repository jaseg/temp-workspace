// Demo source for the live viewer: plays a bundled replay through the live protocol entirely in the page,
// so the live rendering path can be checked without the game or the mod. Built with LIVE_DEMO=1.
//
// It produces the same binary messages the mod sends, with the same timing (one pose per recorded frame, a
// note's cut immediately and its final score 0.3 s later) and feeds them to the real LiveConnection message
// handling. ?latency=<ms> adds simulated network delay (default 5), ?jitter=<ms> random extra delay.
import {LiveConnection} from './connection';
import {T} from './protocol';
import {decode} from '../open-replay-decoder';
import {getUrlParameter} from '../utils';

const SWING_RATING_DELAY = 0.3;
const SERVER_CLOCK_OFFSET_US = 987654321; // the demo "server" clock is deliberately not performance.now()
const GAP_BETWEEN_SONGS_MS = 4000;

class Writer {
	constructor(type) {
		this.bytes = [type];
		this.view = new DataView(new ArrayBuffer(8));
	}
	push(n) {
		for (let i = 0; i < n; i++) this.bytes.push(this.view.getUint8(i));
		return this;
	}
	u8(x) {
		this.bytes.push(x & 0xff);
		return this;
	}
	u32(x) {
		this.view.setUint32(0, x, true);
		return this.push(4);
	}
	i32(x) {
		this.view.setInt32(0, x, true);
		return this.push(4);
	}
	i64(x) {
		this.view.setUint32(0, x % 4294967296, true);
		this.view.setUint32(4, Math.floor(x / 4294967296), true);
		return this.push(8);
	}
	f32(x) {
		this.view.setFloat32(0, x, true);
		return this.push(4);
	}
	f64(x) {
		this.view.setFloat64(0, x, true);
		return this.push(8);
	}
	str(s) {
		const b = new TextEncoder().encode(s);
		this.i32(b.length);
		b.forEach(x => this.bytes.push(x));
		return this;
	}
	vec3(v) {
		return this.f32(v.x).f32(v.y).f32(v.z);
	}
	pose(p) {
		return this.vec3(p.position).f32(p.rotation.x).f32(p.rotation.y).f32(p.rotation.z).f32(p.rotation.w);
	}
	buffer() {
		return new Uint8Array(this.bytes).buffer;
	}
}

function noteMessage(type, captureUs, note, finalCut) {
	const w = new Writer(type).i64(captureUs).i32(note.noteID).f32(note.eventTime).f32(note.spawnTime).i32(note.eventType);
	const c = note.noteCutInfo;
	if (c) {
		w.u8(c.speedOK ? 1 : 0).u8(c.directionOK ? 1 : 0).u8(c.saberTypeOK ? 1 : 0).u8(c.wasCutTooSoon ? 1 : 0);
		w.f32(c.saberSpeed).vec3(c.saberDir).i32(c.saberType).f32(c.timeDeviation).f32(c.cutDirDeviation);
		w.vec3(c.cutPoint).vec3(c.cutNormal).f32(c.cutDistanceToCenter).f32(c.cutAngle);
		// The game only knows the after-cut rating once the swing has finished.
		w.f32(c.beforeCutRating).f32(finalCut ? c.afterCutRating : 0);
	}
	return w.buffer();
}

export class DemoConnection extends LiveConnection {
	constructor(handlers) {
		super(handlers);
		this.latencyMs = parseFloat(getUrlParameter('latency')) || 5;
		this.jitterMs = parseFloat(getUrlParameter('jitter')) || 0;
		this.sessionId = 0;
	}

	serverNowUs() {
		return performance.now() * 1000 + SERVER_CLOCK_OFFSET_US;
	}

	// Delivers a message as if it had travelled over the network.
	deliver(buffer, delayMs = this.latencyMs + Math.random() * this.jitterMs) {
		setTimeout(() => this.onMessage(buffer, performance.now()), delayMs);
	}

	async connect() {
		this.setState('connecting');
		const [manifest, replay] = await Promise.all([
			fetch('demo/manifest.json').then(r => r.json()),
			fetch('demo/replay.txt')
				.then(r => r.text())
				.then(base64 => Uint8Array.from(atob(base64.trim()), c => c.charCodeAt(0)).buffer)
				.then(buffer => new Promise(resolve => decode(buffer, resolve))),
		]);
		this.manifest = manifest;
		this.replay = replay;

		// Clock sync, as the real connection does it.
		for (let i = 0; i < 8; i++) {
			const t0 = performance.now();
			const sr = this.serverNowUs() + this.latencyMs * 500;
			this.deliver(new Writer(T.Pong).f64(t0).i64(sr).i64(sr + 20).buffer(), this.latencyMs);
		}

		// The waiting room, with an approval after a moment.
		this.deliver(new Writer(T.Waiting).str('K7-4Q').buffer(), 400);
		setTimeout(() => {
			this.deliver(new Writer(T.Approved).u8(0).buffer(), 0);
			setTimeout(() => this.playSong(), 300);
		}, 2500);
	}

	fetchMapFile(sessionId, name) {
		return fetch('demo/map/' + this.manifest.paths[name]).then(r => {
			if (!r.ok) throw new Error(`${name}: ${r.status}`);
			return r.arrayBuffer();
		});
	}

	playSong() {
		const replay = this.replay;
		const info = replay.info;
		const id = ++this.sessionId;
		const session = {
			hash: info.hash,
			songName: this.manifest.songName,
			songSubName: '',
			songAuthor: this.manifest.songAuthor,
			mapper: info.mapper,
			difficulty: info.difficulty,
			mode: info.mode,
			environment: info.environment,
			modifiers: info.modifiers,
			playerName: info.playerName,
			leftHanded: info.leftHanded,
			playerHeight: info.height,
			jumpDistance: info.jumpDistance,
			noteJumpSpeed: 0,
			startTime: info.startTime,
			songSpeed: info.speed > 0 ? info.speed : 1,
			gameVersion: info.gameVersion,
			files: this.manifest.files,
		};
		this.deliver(new Writer(T.SessionStart).u32(id).str(JSON.stringify(session)).buffer());

		// Everything the game would send, ordered by song time.
		const events = [];
		replay.frames.forEach(f => events.push({time: f.time, kind: 'pose', f}));
		replay.notes.forEach(n => {
			if (n.eventType === 0) {
				events.push({time: n.eventTime, kind: 'cut', n});
				events.push({time: n.eventTime + SWING_RATING_DELAY, kind: 'final', n});
			} else {
				events.push({time: n.eventTime, kind: 'final', n});
			}
		});
		replay.walls.forEach(w => events.push({time: w.time, kind: 'wall', w}));
		replay.heights.forEach(h => events.push({time: h.time, kind: 'height', h}));
		events.sort((a, b) => a.time - b.time);

		const songStart = replay.frames[0].time;
		const startMs = performance.now() + 1500; // the song starts shortly after the map is announced
		let next = 0;
		const tick = () => {
			if (id !== this.sessionId) return;
			const songNow = songStart + (performance.now() - startMs) / 1000;
			while (next < events.length && events[next].time <= songNow) {
				const e = events[next++];
				const captureUs = this.serverNowUs();
				if (e.kind === 'pose') {
					const f = e.f;
					this.deliver(new Writer(T.Pose).i64(captureUs).f32(f.time).pose(f.head).pose(f.left).pose(f.right).buffer());
				} else if (e.kind === 'cut') {
					this.deliver(noteMessage(T.NoteCut, captureUs, e.n, false));
				} else if (e.kind === 'final') {
					this.deliver(noteMessage(T.NoteFinal, captureUs, e.n, true));
				} else if (e.kind === 'wall') {
					const w = e.w;
					this.deliver(new Writer(T.Wall).i64(captureUs).i32(w.wallID).f32(w.energy).f32(w.time).f32(w.spawnTime).buffer());
				} else if (e.kind === 'height') {
					this.deliver(new Writer(T.Height).i64(captureUs).f32(e.h.height).f32(e.h.time).buffer());
				}
			}
			if (next < events.length) {
				setTimeout(tick, 1);
			} else {
				const reason = info.failTime > 0 ? 2 : 1;
				this.deliver(new Writer(T.SessionEnd).u32(id).u8(reason).f32(songNow).buffer());
				setTimeout(() => this.playSong(), GAP_BETWEEN_SONGS_MS);
			}
		};
		setTimeout(tick, startMs - performance.now());
	}
}
