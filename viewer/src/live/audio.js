// Keeps the song audio in step with the live song time.
//
// The audio runs on the AudioContext clock while the picture follows the game. Every check compares what is being
// heard right now with the live song time. Small differences are corrected smoothly by playing up to 2 % faster or
// slower for a moment; only a large jump (joining late, a hitch, a pause) re-seeks.
//
// While the rate is adjusted, the position heard can't be derived from the song's start time alone, so this keeps
// its own model: an anchor (context time, song position) plus the rate in effect since then.

const CHECK_INTERVAL_MS = 250;
const DEAD_BAND_S = 0.008; // closer than this is left alone
const SEEK_DRIFT_S = 0.25; // further than this is jumped over rather than caught up
const MAX_RATE_CHANGE = 0.02; // at most 2 % faster or slower
const CATCH_UP_S = 2; // the rate is chosen to remove the drift over about this long

export class LiveAudioSync {
	constructor(scene, session) {
		this.scene = scene;
		this.session = session;
		this.seeking = false;
		this.stoppedForPause = false;
		this.lastDrift = null;
		this.correction = 1; // current rate factor on top of the song speed
		this.seeks = 0;
		this.anchor = null; // {startTime, contextTime, position, rate}
		setInterval(() => this.check(), CHECK_INTERVAL_MS);
	}

	get song() {
		return this.scene.components.song;
	}

	outputLatency(context) {
		return (context.outputLatency || 0) + (context.baseLatency || 0);
	}

	/** Song position scheduled at context time `t` (heard `outputLatency` later). */
	positionAt(t) {
		const a = this.anchor;
		return a.position + (t - a.contextTime) * a.rate;
	}

	check() {
		const song = this.song;
		const session = this.session;
		if (!session.active || !song || !song.source || this.seeking || song.songStartTime === undefined) return;
		const context = song.context;
		if (context.state !== 'running') return;

		const clock = session.songClock;
		if (clock.paused) {
			if (!this.stoppedForPause) {
				this.stoppedForPause = true;
				song.stopAudio();
			}
			return;
		}

		// A new start (song start, seek, speed change) restarts the model at the song's own bookkeeping.
		if (!this.anchor || this.anchor.startTime !== song.songStartTime) {
			this.anchor = {startTime: song.songStartTime, contextTime: song.songStartTime, position: 0, rate: song.speed};
			this.correction = 1;
		}

		const now = performance.now();
		const expected = clock.songTimeAt(now);
		if (expected === null) return;
		const latency = this.outputLatency(context);
		const heard = this.positionAt(context.currentTime - latency);
		const drift = heard - expected;
		this.lastDrift = drift;

		if (this.stoppedForPause || Math.abs(drift) > SEEK_DRIFT_S) {
			this.stoppedForPause = false;
			this.seeks++;
			// Samples scheduled now are heard `latency` later.
			this.seek(clock.songTimeAt(now + latency * 1000));
			return;
		}

		// Audio ahead (positive drift): play slower until it's caught up; behind: faster.
		const correction =
			Math.abs(drift) < DEAD_BAND_S ? 1 : 1 - Math.max(-MAX_RATE_CHANGE, Math.min(MAX_RATE_CHANGE, drift / CATCH_UP_S));
		if (Math.abs(correction - this.correction) > 0.0005) this.setCorrection(correction);
	}

	setCorrection(correction) {
		const song = this.song;
		const t = song.context.currentTime;
		const rate = song.speed * correction;
		this.anchor = {startTime: this.anchor.startTime, contextTime: t, position: this.positionAt(t), rate};
		this.correction = correction;
		// The same nodes the song component sets its speed on. A buffer source shifts pitch slightly (at most a
		// third of a semitone); the media element keeps the pitch.
		if (song.source && song.source.playbackRate) song.source.playbackRate.value = rate;
		if (song.mediaSource && song.mediaSource.playbackRate) song.mediaSource.playbackRate.value = rate;
		if (song.audio) song.audio.playbackRate = Math.max(rate, song.settings.settings.pitchCompensationTreshold);
	}

	seek(time) {
		const song = this.song;
		this.anchor = null;
		this.correction = 1;
		if (time < 0 || (song.getDuration() && time >= song.getDuration())) {
			song.stopAudio();
			return;
		}
		this.seeking = true;
		if (song.source) song.stopAudio();
		song.data.analyserEl.addEventListener(
			'audioanalysersource',
			evt => {
				song.source = evt.detail;
				song.startAudio(time);
				this.seeking = false;
			},
			{once: true}
		);
		song.audioAnalyser.refreshSource(song.speed);
	}
}
