// Loads the live viewer (served by a dev host running with --www <viewer/dist-live> --auto-approve) in headless
// Chromium, lets it play, then reports errors, live stats and screenshots.
// Usage: NODE_PATH=$(npm root -g) node tools/viewer-smoke.cjs [url] [seconds] [screenshot-prefix]
const {chromium} = require('playwright');

(async () => {
	const url = process.argv[2] || 'https://localhost:4280/';
	const seconds = Number(process.argv[3] || 20);
	const shots = process.argv[4] || 'viewer';

	const browser = await chromium.launch({args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
	const page = await browser.newPage({ignoreHTTPSErrors: true, viewport: {width: Number(process.env.VW || 1280), height: Number(process.env.VH || 720)}});
	const errors = [];
	page.on('pageerror', e => errors.push('pageerror: ' + (e.stack || e)));
	page.on('console', m => {
		if ((m.type() === 'error' || m.type() === 'warning') && !m.text().startsWith('THREE.WebGL')) errors.push(m.type() + ': ' + m.text());
	});
	page.on('requestfailed', r => errors.push('requestfailed: ' + r.url() + ' ' + (r.failure() && r.failure().errorText)));
	await page.goto(url);
	// A click is the user gesture browsers require before audio may play.
	await page.waitForTimeout(3000);
	await page.mouse.click(640, 300);

	await page.keyboard.press('l'); // latency readout
	for (let i = 0; i < seconds; i += 5) {
		await page.waitForTimeout(5000);
		await page.mouse.move(600 + i, 400); // shows the controls bar
		await page.screenshot({path: `${shots}-${i + 5}s.png`});
	}

	// Per-frame extrapolation horizon (render time minus newest pose time) over 5 s.
	const horizon = await page.evaluate(() => new Promise(resolve => {
		const out = [];
		const end = performance.now() + 5000;
		(function tick() {
			const h = window.liveSession.horizonMs();
			if (h !== null) out.push(h);
			if (performance.now() < end) requestAnimationFrame(tick); else resolve(out);
		})();
	}));
	const sorted = [...horizon].sort((a, b) => a - b);
	const pct = p => sorted[Math.min(sorted.length - 1, Math.floor(p * sorted.length))];
	console.log(`horizon over ${sorted.length} frames: min ${sorted[0].toFixed(1)} p50 ${pct(0.5).toFixed(1)} p95 ${pct(0.95).toFixed(1)} max ${sorted[sorted.length - 1].toFixed(1)} ms`);

	const result = await page.evaluate(() => {
		const s = window.liveSession;
		const scene = document.querySelector('a-scene');
		const state = (scene && scene.systems && scene.systems.state && scene.systems.state.state) || {score: null, challenge: {}};
		return {
			connection: s && s.connection.state,
			active: s && s.active,
			poses: s && s.stats.poses,
			rttMs: s && s.connection.clock.rttMs,
			songTime: s && s.currentSongTime(),
			audio: s && {context: document.querySelector('a-scene').components.song.context.state, driftMs: s.audio.lastDrift === null ? null : s.audio.lastDrift * 1000},
			scored: s && s.loader.allStructs.length,
			score: state.score && {score: state.score.score, combo: state.score.combo, accuracy: state.score.accuracy, misses: state.score.misses},
			isPlaying: state.isPlaying,
			flags: {isPaused: state.isPaused, songBuffer: state.isSongBufferProcessing, replayLoading: state.replay && state.replay.isLoading, localReplay: state.localReplay, gesture: state.hasReceivedUserGesture, loadError: state.challenge.hasLoadError},
			notesLen: state.notes ? state.notes.length : null,
			challengeLoading: state.challenge.isLoading,
			beatsOnScreen: document.querySelectorAll('#beatContainer > [beat]').length,
		};
	});
	console.log(JSON.stringify(result, null, 2));
	console.log(errors.slice(0, 40).join('\n'));
	await browser.close();
})();
