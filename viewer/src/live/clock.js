// Clock synchronization with the mod and song-time estimation.

const PONG_WINDOW = 16;
const SONG_OFFSET_SMOOTHING = 0.05;
const SONG_OFFSET_RESET = 0.05; // s; jumps larger than this are taken as-is (seek, restart, hitch)

/**
 * Maps the server's monotonic microsecond clock onto performance.now().
 * Uses the lowest-RTT sample of a sliding window (NTP style).
 */
export class ServerClock {
	constructor() {
		this.samples = [];
		this.offsetUs = null; // server - client
		this.rttMs = null;
	}

	addPong(t0, t1, serverReceiveUs, serverSendUs) {
		const rttUs = (t1 - t0) * 1000 - (serverSendUs - serverReceiveUs);
		const offsetUs = (serverReceiveUs + serverSendUs) / 2 - ((t0 + t1) / 2) * 1000;
		this.samples.push({rttUs, offsetUs});
		if (this.samples.length > PONG_WINDOW) this.samples.shift();
		const best = this.samples.reduce((a, b) => (b.rttUs < a.rttUs ? b : a));
		this.offsetUs = best.offsetUs;
		this.rttMs = best.rttUs / 1000;
	}

	get synced() {
		return this.offsetUs !== null;
	}

	serverUsAt(clientMs) {
		return clientMs * 1000 + this.offsetUs;
	}

	clientMsAt(serverUs) {
		return (serverUs - this.offsetUs) / 1000;
	}
}

/**
 * Song time as a function of server time: songTime = base + serverSeconds * speed.
 * Each pose gives one observation; the base is smoothed to remove capture jitter.
 */
export class SongClock {
	constructor(serverClock) {
		this.server = serverClock;
		this.reset(1);
	}

	reset(speed) {
		this.speed = speed || 1;
		this.base = null;
		this.paused = false;
		this.pausedAt = 0;
	}

	observe(captureUs, songTime) {
		if (this.paused) return;
		const base = songTime - (captureUs / 1e6) * this.speed;
		if (this.base === null || Math.abs(base - this.base) > SONG_OFFSET_RESET) {
			this.base = base;
		} else {
			this.base += (base - this.base) * SONG_OFFSET_SMOOTHING;
		}
	}

	pause(songTime) {
		this.paused = true;
		this.pausedAt = songTime;
	}

	resume() {
		// The next pose re-anchors the clock.
		this.paused = false;
		this.base = null;
	}

	get ready() {
		return this.paused || (this.base !== null && this.server.synced);
	}

	songTimeAt(clientMs) {
		if (this.paused) return this.pausedAt;
		if (!this.ready) return null;
		return this.base + (this.server.serverUsAt(clientMs) / 1e6) * this.speed;
	}
}
