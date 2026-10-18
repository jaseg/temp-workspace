// Opens the level browser of the live viewer (dev host running with --www <viewer/dist> --auto-approve and
// --levels <dir>), checks the list, covers, BeatLeader stats and an audio preview, and takes screenshots.
// Usage: NODE_PATH=$(npm root -g) node tools/levels-smoke.cjs [url] [screenshot-prefix] [search]
// NO_STATS=1: the server has BeatLeader stats off (the plugin's default), so don't expect star ratings.
const {chromium} = require('playwright');

(async () => {
	const url = process.argv[2] || 'https://localhost:4280/';
	const shots = process.argv[3] || 'levels';
	const search = process.argv[4] || 'deja';
	const stats = !process.env.NO_STATS;
	const browser = await chromium.launch({args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--autoplay-policy=no-user-gesture-required']});
	const errors = [];
	for (const [width, height, name] of [[1280, 800, 'desktop'], [390, 760, 'phone']]) {
		const page = await browser.newPage({ignoreHTTPSErrors: true, viewport: {width, height}});
		page.on('pageerror', e => errors.push(`${name} pageerror: ${e.message}`));
		page.on('console', m => {
			if (m.type() === 'error' && !m.text().includes('AudioContext')) errors.push(`${name} console: ${m.text()}`);
		});
		await page.goto(url + '#levels');
		await page.click('#liveOverlay .liveRequest', {timeout: 20000});
		await page.waitForSelector('#levelBrowser:not([hidden]) .lbLevel', {timeout: 20000});
		// Covers and stats load lazily for visible rows.
		await page.waitForFunction(() => document.querySelectorAll('#levelBrowser .lbCover img:not([hidden])').length >= 3, null, {timeout: 20000});
		if (stats) {
			await page.waitForFunction(() => document.querySelectorAll('#levelBrowser .lbStars').length >= 3, null, {timeout: 30000}).catch(() => errors.push(`${name}: no stars shown`));
		}
		const summary = await page.evaluate(() => ({
			title: document.querySelector('#levelBrowser .lbTitle').textContent,
			rows: [...document.querySelectorAll('#levelBrowser .lbLevel')].slice(0, 3).map(r => r.querySelector('.lbName').textContent + ' | ' + r.querySelector('.lbChips').textContent),
		}));
		console.log(name, JSON.stringify(summary));
		await page.screenshot({path: `${shots}-${name}-list.png`});

		// Search, expand, preview.
		await page.fill('#levelBrowser .lbSearch', search);
		const row = page.locator('#levelBrowser .lbLevel').first();
		await row.click();
		await page.waitForFunction(stats => (stats ? /Ranked|Unranked/ : /Notes/).test(document.querySelector('#levelBrowser .lbDetails:not([hidden])')?.textContent || ''), stats, {timeout: 15000});
		await row.locator('.lbPlay').click();
		await page.waitForFunction(() => document.querySelector('#levelBrowser .lbLevel.playing'), null, {timeout: 15000});
		await page.waitForTimeout(2500);
		const audio = await page.evaluate(() => {
			const p = window.liveSession.levels.preview;
			return p && {time: p.audio.currentTime, paused: p.audio.paused, volume: p.audio.volume, start: p.level.previewStart};
		});
		console.log(name, 'preview', JSON.stringify(audio));
		if (!audio || audio.paused || audio.time < audio.start) errors.push(`${name}: preview not playing`);
		await page.screenshot({path: `${shots}-${name}-details.png`});
		await page.keyboard.press('Escape');
		const closed = await page.evaluate(() => document.getElementById('levelBrowser').hidden && !window.liveSession.levels.preview);
		if (!closed) errors.push(`${name}: Escape didn't close and stop`);
		await page.close();
	}
	console.log(errors.length ? errors.join('\n') : 'no errors');
	await browser.close();
	process.exit(errors.length ? 1 : 0);
})();
