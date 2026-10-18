// Ogg fallback: simulates a browser without Ogg Vorbis (Safari before 18.4) by making canPlayType deny it, and checks
// that the live song, the hit sound and the level preview are decoded with the WebAssembly decoder, under the page's
// real CSP. Then checks that a normal browser never loads the decoder. Needs a running server with auto-approval and
// a level named "When Doves Cry" (or pass another name). Don't run it with Playwright's bypassCSP.
// Usage: NODE_PATH=$(npm root -g) node tools/ogg-fallback-smoke.cjs [url] [level name]
const {chromium} = require('playwright');
const poll = async (page, fn, arg, ms = 30000) => {
	for (const end = Date.now() + ms; Date.now() < end; await page.waitForTimeout(250)) if (await page.evaluate(fn, arg)) return true;
	return false;
};
(async () => {
	const url = process.argv[2] || 'https://localhost:4280/';
	const levelName = process.argv[3] || 'When Doves Cry';
	let failed = false;
	const browser = await chromium.launch({args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--autoplay-policy=no-user-gesture-required']});
	for (const oldSafari of [true, false]) {
		const tag = oldSafari ? 'no-ogg' : 'native';
		const page = await browser.newPage({ignoreHTTPSErrors: true, viewport: {width: 1000, height: 700}});
		const errors = [];
		const decoderLoads = [];
		page.on('pageerror', e => errors.push(e.message));
		page.on('console', m => m.type() === 'error' && errors.push(m.text()));
		page.on('request', r => r.url().includes('oggdec') && decoderLoads.push(r.url()));
		if (oldSafari) {
			await page.addInitScript(() => {
				const original = HTMLMediaElement.prototype.canPlayType;
				HTMLMediaElement.prototype.canPlayType = function (type) {
					return /ogg/i.test(type) ? '' : original.call(this, type);
				};
			});
		}
		await page.goto(url);
		await page.click('.liveRequest');
		const song = await poll(page, () => {
			const s = window.liveSession;
			const songEl = document.querySelector('a-scene').components.song;
			return s && s.active && songEl.source && s.audio.lastDrift !== null && (songEl.source.buffer ? 'buffer' : 'element');
		}, null, 60000);
		const hit = await poll(page, () => !!document.querySelector('a-scene').components['beat-hit-sound'].audioBuffer, null, 10000);
		// Level preview.
		await page.click('#liveNav button:nth-child(2)');
		await page.waitForSelector('#levelBrowser .lbLevel');
		await page.locator('#levelBrowser .lbLevel', {hasText: levelName}).locator('.lbPlay').click();
		const preview = await poll(page, () => {
			const p = window.liveSession.levels.preview;
			return p && (p.source ? 'webaudio' : p.url && !p.audio.paused && p.audio.currentTime > 1 ? 'element' : false);
		}, null, 30000);
		const how = await page.evaluate(() => {
			const p = window.liveSession.levels.preview;
			return p ? (p.source ? 'Web Audio (decoded)' : '<audio> element') : 'none';
		});
		const songPath = await page.evaluate(() => (document.querySelector('a-scene').components.song.source.buffer ? 'decoded buffer' : 'media element'));
		const drift = await page.evaluate(() => window.liveSession.audio.lastDrift * 1000);
		const result = {song: song && songPath, driftMs: Math.round(drift), hitSound: hit, preview: preview && how, decoderLoaded: decoderLoads.length > 0, errors: errors.filter(e => !/AudioContext was not allowed/.test(e)).slice(0, 3)};
		console.log(tag, result);
		const ok = oldSafari
			? result.song === 'decoded buffer' && result.preview === 'Web Audio (decoded)' && result.decoderLoaded
			: result.preview === '<audio> element' && !result.decoderLoaded;
		if (!ok || !hit || result.errors.length) failed = true;
		await page.close();
	}
	await browser.close();
	console.log(failed ? 'FAILED' : 'no errors');
	process.exit(failed ? 1 : 0);
})();
