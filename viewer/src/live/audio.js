// Keeps the song audio in step with the live song time.
//
// The audio element/buffer runs on the AudioContext clock while the picture follows the game. Every check
// compares what is being heard right now with the live song time and re-seeks when they drift apart.

const CHECK_INTERVAL_MS = 500;
const MAX_DRIFT_S = 0.04;

export class LiveAudioSync {
	constructor(scene, session) {
		this.scene = scene;
		this.session = session;
		this.seeking = false;
		this.stoppedForPause = false;
		this.lastDrift = null;
		setInterval(() => this.check(), CHECK_INTERVAL_MS);
	}

	get song() {
		return this.scene.components.song;
	}

	outputLatency(context) {
		return (context.outputLatency || 0) + (context.baseLatency || 0);
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

		const now = performance.now();
		const expected = clock.songTimeAt(now);
		if (expected === null) return;
		const latency = this.outputLatency(context);
		const heard = (context.currentTime - latency - song.songStartTime) * song.speed;
		this.lastDrift = heard - expected;

		if (this.stoppedForPause || Math.abs(this.lastDrift) > MAX_DRIFT_S) {
			this.stoppedForPause = false;
			// Samples scheduled now are heard `latency` later.
			this.seek(clock.songTimeAt(now + latency * 1000));
		}
	}

	seek(time) {
		const song = this.song;
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
