// Checks that song audio runs in Firefox from the first song on, across song transitions. Firefox can settle an
// AudioContext suspend() that was followed by resume() after the resume, leaving the song silent; Chromium can't
// show that. Run the dev host with --www ../viewer/dist --auto-approve --loop (a late --start keeps songs short).
//
// Needs Playwright's Firefox, a display and an audio sink (without one, Firefox's resume() hangs):
//   PLAYWRIGHT_BROWSERS_PATH=<dir> npx playwright install firefox
//   pulseaudio -D --exit-idle-time=-1 && pactl load-module module-null-sink sink_name=null && pactl set-default-sink null
//   PLAYWRIGHT_BROWSERS_PATH=<dir> NODE_PATH=$(npm root -g) xvfb-run -a node tools/firefox-audio-smoke.cjs [url] [seconds]
const {firefox} = require('playwright');

(async () => {
	const url = process.argv[2] || 'https://localhost:4280/';
	const seconds = Number(process.argv[3] || 45);
	// Firefox's defaults: audible autoplay blocked until the page has been interacted with.
	const browser = await firefox.launch({
		headless: false,
		firefoxUserPrefs: {'media.autoplay.default': 1, 'media.autoplay.blocking_policy': 0, 'media.autoplay.block-webaudio': true},
	});
	const page = await browser.newPage({ignoreHTTPSErrors: true, viewport: {width: 800, height: 450}});
	const errors = [];
	page.on('pageerror', e => errors.push('pageerror: ' + e.message));
	await page.goto(url);
	await page.click('#liveOverlay .liveRequest', {timeout: 20000});

	// Per session: seconds of play seen, and how many of them had the song's AudioContext running.
	const sessions = {};
	const end = Date.now() + seconds * 1000;
	while (Date.now() < end) {
		const s = await page.evaluate(() => {
			const song = document.querySelector('a-scene').components.song;
			const live = window.liveSession;
			return {id: live.sessionId, active: live.active, ctx: song.context && song.context.state, paused: song.audio.paused};
		});
		if (s.active) {
			const entry = (sessions[s.id] = sessions[s.id] || {seen: 0, running: 0});
			entry.seen++;
			if (s.ctx === 'running' && !s.paused) entry.running++;
		}
		await page.waitForTimeout(1000);
	}
	await browser.close();

	console.log('per session (seconds seen / with audio running):', JSON.stringify(sessions));
	// Allow a few seconds for the context to start (Firefox's audio stream takes a moment to open).
	for (const [id, s] of Object.entries(sessions)) {
		if (s.seen >= 6 && s.running < s.seen - 4) errors.push(`session ${id}: audio running only ${s.running} of ${s.seen} s`);
	}
	if (Object.keys(sessions).length < 2) errors.push('fewer than two songs seen; use --loop and a later --start');
	console.log(errors.length ? errors.join('\n') : 'no errors');
	process.exit(errors.length ? 1 : 0);
})();
