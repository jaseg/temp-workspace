// Live mode: turns the mod's stream into the replay structures the viewer already knows how to render.
//
// The replay-loader component stays the single source of replay data for the rest of the viewer
// (replay, allStructs, bombs, walls); in live mode those arrays grow while the song plays instead of
// being loaded up front.

import {T, Reader, SessionEndReason, readNoteEvent} from './protocol';
import {LiveConnection} from './connection';
import {DemoConnection} from './demo';
import {SongClock} from './clock';
import {LiveOverlay} from './overlay';
import {LevelBrowser} from './levels';
import {LiveNav} from './nav';
import {LiveAudioSync} from './audio';
import {assignNote, computeTotals, noteStructFromEvent, ScoreForNote} from '../components/replay-loader';
import {NoteEventType} from './bsor';
import {Mirror_Horizontal} from '../utils/chirality-support';
import {updateScoringAndTypes} from '../utils/mapPostprocessor';
import {difficultyFromName, getUrlParameter, ScoringType} from '../utils';

// How far ahead of "now" a rendered frame is shown, i.e. the display pipeline latency we predict across.
const DEFAULT_PREDICT_MS = 16;
// Never extrapolate poses further than this past the newest sample (stalled stream: freeze instead).
export const MAX_EXTRAPOLATION_S = 0.05;
// Map note matching tolerance for spawn times (same as the replay matcher).
const SPAWN_TIME_TOLERANCE = 0.0005;

function noteKey(noteId, spawnTime) {
	return noteId + ':' + spawnTime.toFixed(4);
}

// Same as computeTotals' scoreForMaxScore.
function maxScoreFor(scoringType) {
	if (scoringType == ScoringType.ChainHead) return 85;
	if (scoringType == ScoringType.ChainLink || scoringType == ScoringType.ChainLinkArcHead) return 20;
	return 115;
}

export class LiveSession {
	constructor(replayLoader) {
		this.loader = replayLoader;
		this.scene = replayLoader.el.sceneEl;
		this.overlay = new LiveOverlay();
		this.connection = new (LIVE_DEMO ? DemoConnection : LiveConnection)({
			state: (state, detail) => this.onConnectionState(state, detail),
			message: (type, reader, receivedAt) => this.onMessage(type, reader, receivedAt),
			suggestions: doc => this.levels.setSuggestions(doc),
		});
		this.levels = new LevelBrowser(this.connection);
		this.nav = new LiveNav(this.levels);
		this.nav.setLive(false);
		this.songClock = new SongClock(this.connection.clock);
		// ?predict=<ms> overrides the display-latency prediction (0 disables it).
		const predict = parseFloat(getUrlParameter('predict'));
		this.predictMs = isFinite(predict) && predict >= 0 && predict <= 100 ? predict : DEFAULT_PREDICT_MS;
		this.sessionId = 0;
		this.active = false;
		this.stats = {poses: 0, lastPoseAgeMs: null, sessions: 0};
		window.liveSession = this; // for debugging and automated tests

		this.scene.addEventListener('challengeloadend', e => this.onChallengeLoaded(e.detail));
		// The game decides when play pauses; undo pauses triggered from the page (space bar, clicks).
		this.scene.addEventListener('pausegame', () => {
			if (this.active) setTimeout(() => this.scene.emit('gamemenuresume', null, false), 0);
		});
		this.audio = new LiveAudioSync(this.scene, this);
		setInterval(() => this.updateStats(), 250);
		this.overlay.showRequest(() => {
			// Unlocks audio (this runs inside the click) before the waiting room.
			this.scene.emit('usergesturereceive', null, false);
			this.connection.connect();
		});
	}

	/** Song time for the frame being rendered now. */
	currentSongTime() {
		const t = this.songTimeAt(performance.now());
		if (t !== null) return Math.max(0, t);
		const frames = this.replay ? this.replay.frames : [];
		return frames.length ? frames[frames.length - 1].time : 0;
	}

	/** How far past the newest received pose the current frame is rendered (extrapolation horizon). */
	horizonMs() {
		const frames = this.replay ? this.replay.frames : [];
		if (!this.active || frames.length === 0) return null;
		return (this.currentSongTime() - frames[frames.length - 1].time) * 1000;
	}

	// Live play must never stay stuck behind the audio pipeline's "processing" flag: once the map is loaded
	// and the flag has been up for a while, clear it. Live timing doesn't depend on the audio. (Seen rarely in headless tests; cause not pinned down.)
	checkStuckProcessing() {
		const state = this.scene.systems.state.state;
		const song = this.scene.components.song;
		if (!this.active || !this.challengeLoaded || !state.isSongBufferProcessing || !song) {
			this.processingSince = null;
			return;
		}
		const now = performance.now();
		if (this.processingSince == null) this.processingSince = now;
		if (now - this.processingSince > 3000) {
			console.warn('[live] audio processing flag stuck; clearing it');
			this.processingSince = null;
			this.scene.emit('songprocessingfinish', null, false);
		}
	}

	updateStats() {
		this.checkStuckProcessing();
		const clock = this.connection.clock;
		const frames = this.replay ? this.replay.frames : [];
		const last = frames[frames.length - 1];
		const now = performance.now();
		const ageMs = last && clock.synced ? now - clock.clientMsAt(last.captureUs) : null;
		const fmt = x => (x === null || x === undefined ? '–' : x.toFixed(1));
		this.overlay.showStats([
			`poses        ${this.stats.poses}`,
			`rtt          ${fmt(clock.rttMs)} ms`,
			`age@receive  ${fmt(this.stats.lastPoseAgeMs)} ms`,
			`newest pose  ${fmt(ageMs)} ms old`,
			`predict      ${this.predictMs} ms`,
			`horizon      ${fmt(this.horizonMs())} ms`,
			`audio drift  ${this.audio.lastDrift === null ? '–' : (this.audio.lastDrift * 1000).toFixed(1)} ms`,
			`song time    ${fmt(this.active ? this.currentSongTime() : null)} s`,
		]);
	}

	/** Song time to render at a given performance.now(), including the display-latency prediction. */
	songTimeAt(clientMs) {
		return this.songClock.songTimeAt(clientMs + this.predictMs);
	}

	// ---- connection ----

	onConnectionState(state, detail) {
		this.overlay.setConnectionState(state, detail);
		this.levels.setAvailable(state === 'approved');
		this.nav.setAvailable(state === 'approved');
		// #levels opens the level browser as soon as the device is approved.
		if (state === 'approved' && location.hash === '#levels' && !this.levels.isOpen) this.levels.open();
		if (state === 'disconnected') {
			this.endSession('disconnected');
		}
	}

	onMessage(type, r, receivedAt) {
		switch (type) {
			case T.SessionStart:
				this.startSession(r.u32(), JSON.parse(r.str()));
				return;
			case T.SessionEnd: {
				const id = r.u32();
				const reason = SessionEndReason[r.u8()] || 'ended';
				if (id === this.sessionId) this.endSession(reason);
				return;
			}
			case T.Idle:
				this.endSession('idle');
				return;
		}

		if (!this.active) return;
		const captureUs = r.i64();
		switch (type) {
			case T.Pose:
				this.onPose(captureUs, r, receivedAt);
				return;
			case T.NoteCut:
				this.onNoteEvent(readNoteEvent(r), false);
				return;
			case T.NoteFinal:
				this.onNoteEvent(readNoteEvent(r), true);
				return;
			case T.Wall:
				this.onWall({wallID: r.i32(), energy: r.f32(), time: r.f32(), spawnTime: r.f32()});
				return;
			case T.Height:
				this.replay.heights.push({height: r.f32(), time: r.f32()});
				return;
			case T.Pause: {
				const time = r.f32();
				this.songClock.pause(time);
				this.replay.pauses.push({duration: 0, time});
				return;
			}
			case T.Resume:
				r.f32();
				this.songClock.resume();
				return;
		}
	}

	// ---- session lifecycle ----

	startSession(sessionId, info) {
		this.sessionId = sessionId;
		this.active = true;
		this.stats.sessions++;
		this.info = info;
		this.challengeLoaded = false;
		this.pendingByKey = new Map();
		this.byMapIndex = new Map();

		this.songClock.reset(info.songSpeed || 1);
		this.scene.components.song.liveTime = () => this.currentSongTime();

		this.replay = {
			live: true,
			info: {
				hash: info.hash,
				songName: info.songName,
				mapper: info.mapper,
				difficulty: info.difficulty,
				mode: info.mode,
				environment: info.environment,
				modifiers: info.modifiers || '',
				playerName: info.playerName,
				leftHanded: info.leftHanded,
				height: info.playerHeight,
				jumpDistance: info.jumpDistance,
				startTime: info.startTime,
				failTime: 0,
				speed: info.songSpeed,
				gameVersion: info.gameVersion || '',
			},
			frames: [],
			notes: [],
			walls: [],
			heights: [],
			pauses: [],
		};

		const loader = this.loader;
		this.scene.systems.state.dispatch('livesessionstart', null);
		this.scene.emit('replayloadstart', null);
		loader.challenge = null;
		loader.replay = this.replay;
		loader.allStructs = [];
		loader.notes = [];
		loader.bombs = [];
		loader.walls = [];

		this.overlay.setSession(info);
		this.nav.setLive(true);
		this.scene.emit(
			'replayfetched',
			{
				hash: info.hash,
				difficulty: difficultyFromName(info.difficulty),
				mode: info.mode,
				jd: info.jumpDistance > 5 ? info.jumpDistance : undefined,
			},
			null
		);
		this.scene.emit('userloaded', {name: info.playerName, avatar: '', country: '', countryIcon: '', profileLink: '', id: ''}, null);
		this.loadMap(sessionId, info);
	}

	endSession(reason) {
		this.nav.setLive(false);
		if (!this.active) {
			this.overlay.setIdle(reason);
			return;
		}
		this.active = false;
		this.overlay.setEnded(reason, this.info);
		if (reason === 'failed') {
			this.replay.info.failTime = this.lastSongTime || 0;
		}
	}

	// ---- map ----

	async loadMap(sessionId, info) {
		this.scene.emit('challengeloadstart', null, false);
		const files = info.files || {};
		// Only what the selected difficulty needs: other difficulties can be large and aren't shown.
		const wanted = ['info', 'difficulty', 'audioData', 'lightshow', 'cover', 'audio'].filter(role => files[role]);
		const cache = new Map();
		const fetchFile = name => {
			if (!cache.has(name)) cache.set(name, this.connection.fetchMapFile(sessionId, name));
			return cache.get(name);
		};
		// Request everything at once; the server sends files in request order, the big audio last.
		wanted.forEach(role => fetchFile(files[role]));

		const virtualFiles = {};
		for (const role of wanted) {
			const name = files[role];
			virtualFiles[name] = {
				name,
				async: async type => {
					const buffer = await fetchFile(name);
					if (type === 'string') return new TextDecoder().decode(buffer);
					if (type === 'uint8array') return new Uint8Array(buffer);
					return buffer;
				},
			};
		}

		try {
			await fetchFile(files.info);
		} catch (e) {
			if (sessionId === this.sessionId) this.scene.emit('challengeloaderror', {text: 'Could not load the map from the game: ' + e.message});
			return;
		}
		if (sessionId !== this.sessionId) return;

		const mapLoader = this.scene.components['map-loader'];
		mapLoader.data.mode = info.mode;
		mapLoader.data.difficulty = info.difficulty;
		mapLoader.processInfo(virtualFiles);
	}

	onChallengeLoaded(challenge) {
		if (!this.active || this.challengeLoaded) return;
		this.challengeLoaded = true;
		const loader = this.loader;
		loader.challenge = challenge;

		const map = challenge.beatmaps[challenge.mode][challenge.difficulty];
		if (!map) return;
		loader.applyModifiers(map, this.replay);
		if (this.info.leftHanded) {
			Mirror_Horizontal(map, 4, true, false);
			updateScoringAndTypes(map);
		}
		loader.setIds(map, this.replay);
		this.mapNotes = []
			.concat(map._notes, map._chains)
			.sort((a, b) => a._time - b._time)
			.filter(a => a._type == 0 || a._type == 1);

		// The state store reads scores from this array (same object from now on), so publish it first.
		this.scene.emit('replayloaded', {notes: loader.allStructs, replay: this.replay, leftHanded: this.info.leftHanded}, null);

		// Events that arrived while the map was loading.
		const early = this.earlyEvents || [];
		this.earlyEvents = null;
		early.forEach(([event, kind]) => (kind === 'wall' ? this.onWall(event) : this.onNoteEvent(event, kind)));
		// Live play needs no click to start; audio still waits for a gesture (browser autoplay rules).
		this.scene.emit('gamemenuresume', null, false);
	}

	// ---- live data ----

	onPose(captureUs, r, receivedAt) {
		const songTime = r.f32();
		const frame = {time: songTime, fps: 0, head: r.pose(), left: r.pose(), right: r.pose(), captureUs};
		const frames = this.replay.frames;
		if (frames.length && songTime <= frames[frames.length - 1].time) {
			// Paused or restarted song time: keep frames strictly increasing; the newest pose wins.
			if (songTime === frames[frames.length - 1].time) frames[frames.length - 1] = frame;
			return;
		}
		frames.push(frame);
		this.lastSongTime = songTime;
		this.songClock.observe(captureUs, songTime);
		this.stats.poses++;
		if (this.connection.clock.synced) {
			this.stats.lastPoseAgeMs = receivedAt - this.connection.clock.clientMsAt(captureUs);
		}
	}

	onNoteEvent(event, final) {
		if (!this.mapNotes) {
			(this.earlyEvents = this.earlyEvents || []).push([event, final]);
			return;
		}

		const key = noteKey(event.noteID, event.spawnTime);
		let struct = this.pendingByKey.get(key);
		const fresh = noteStructFromEvent(event);
		if (struct) {
			// Final event for a cut we already showed: update in place, objects are referenced by beats.
			struct.eventType = fresh.eventType;
			struct.cutInfo = fresh.cutInfo;
			struct.cutPoint = fresh.cutPoint;
			struct.time = fresh.time;
		} else {
			struct = fresh;
			if (struct.isBlock) this.matchMapNote(struct);
		}

		struct.score = struct.isBlock ? ScoreForNote(struct.eventType, struct.cutInfo, struct.scoringType) : struct.score;
		struct.maxScore = maxScoreFor(struct.scoringType);
		if (struct.cutInfo && struct.cutInfo.timeDeviation) {
			struct.cutTime = struct.spawnTime - struct.cutInfo.timeDeviation;
		}

		if (!final) {
			struct.final = false;
			this.pendingByKey.set(key, struct);
			return;
		}

		this.pendingByKey.delete(key);
		struct.final = true;
		this.replay.notes.push(event);
		if (struct.eventType == NoteEventType.bomb) {
			this.loader.bombs.push(struct);
		} else {
			this.loader.notes.push(struct);
		}
		this.insertScored(struct);

		if (struct.scoreEl && struct.scoreEl.object3D.visible && struct.score > 0) {
			struct.scoreEl.setAttribute('text', 'value', '' + struct.score);
		}
	}

	onWall(wall) {
		if (!this.mapNotes) {
			(this.earlyEvents = this.earlyEvents || []).push([wall, 'wall']);
			return;
		}
		this.replay.walls.push(wall);
		const struct = {time: wall.time, id: wall.wallID, score: -5, final: true};
		this.loader.walls.push(struct);
		this.insertScored(struct);
	}

	/** Finds the map note for a replay note: same id, spawn time within tolerance, nearest unmatched. */
	matchMapNote(struct) {
		let best = null;
		let bestDiff = Infinity;
		for (const mapnote of this.mapNotes) {
			if (mapnote.found) continue;
			const diff = Math.abs(struct.spawnTime - mapnote._songTime);
			if (diff > 1 && mapnote._songTime > struct.spawnTime) break;
			if (
				struct.id == mapnote._id ||
				struct.id == mapnote._idWithScoring ||
				struct.id == mapnote._idWithAlternativeScoring ||
				struct.id == mapnote._idWithLegacyScoring
			) {
				if (diff < SPAWN_TIME_TOLERANCE) {
					best = mapnote;
					break;
				}
				if (diff < bestDiff) {
					best = mapnote;
					bestDiff = diff;
				}
			}
		}
		if (best) {
			assignNote(struct, best);
			this.byMapIndex.set(best._index, struct);
		}
	}

	/** Adds a finished event to the scored list and recomputes the running totals. */
	insertScored(struct) {
		const all = this.loader.allStructs;
		let i = all.length;
		while (i > 0 && all[i - 1].time > struct.time) i--;
		all.splice(i, 0, struct);
		for (const s of all) {
			s.fail = undefined;
			s.maxStreak = undefined;
			s.start = undefined;
		}
		computeTotals(all, this.replay);
		// Show the newest total; force because an earlier event may have changed it.
		this.scene.systems.state.dispatch('scoreChanged', {index: all.length - 1, force: true});
	}

	/** For beats spawned before their outcome was known. */
	structForMapIndex(index) {
		return this.byMapIndex.get(index) || null;
	}
}
