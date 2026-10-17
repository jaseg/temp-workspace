// Watches the live viewer across several songs: the dev host must run with --loop and a late --start so songs
// end quickly. Approves the device through the host console if a FIFO path is given (otherwise expects
// --auto-approve). Reports per-session results and errors.
// Usage: NODE_PATH=$(npm root -g) node tools/viewer-transitions.cjs <url> <seconds> [host-stdin-fifo]
const fs = require('fs');
const {chromium} = require('playwright');

(async () => {
	const [url, seconds, fifo] = [process.argv[2], Number(process.argv[3] || 40), process.argv[4]];
	const browser = await chromium.launch({args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
	const page = await browser.newPage({ignoreHTTPSErrors: true, viewport: {width: 480, height: 270}});
	const errors = [];
	page.on('pageerror', e => errors.push('pageerror: ' + e.message));
	page.on('console', m => {
		if (m.type() === 'error' && !m.text().includes('AudioContext')) errors.push('console: ' + m.text());
	});
	await page.goto(url);
	await page.click('#liveOverlay .liveRequest', {timeout: 20000});

	if (fifo) {
		await page.waitForFunction(() => window.liveSession && window.liveSession.connection.state === 'waiting', null, {timeout: 20000});
		const code = await page.textContent('#liveOverlay .liveCode');
		console.log('waiting room code shown:', code);
		fs.writeFileSync(fifo, `a ${code}\n`);
	}
	await page.waitForFunction(() => window.liveSession && window.liveSession.connection.state === 'approved', null, {timeout: 20000});
	console.log('approved');

	const seen = [];
	const end = Date.now() + seconds * 1000;
	while (Date.now() < end) {
		const s = await page.evaluate(() => {
			const st = document.querySelector('a-scene').systems.state.state;
			return {
				sessions: liveSession.stats.sessions,
				active: liveSession.active,
				overlay: document.querySelector('#liveOverlay .liveTitle').textContent,
				score: st.score.score,
				combo: st.score.combo,
				beats: document.querySelectorAll('#beatContainer > [beat]').length,
				songTime: liveSession.active ? +liveSession.currentSongTime().toFixed(1) : null,
			};
		});
		const last = seen[seen.length - 1];
		if (!last || last.sessions !== s.sessions || last.active !== s.active || last.overlay !== s.overlay) {
			console.log(JSON.stringify(s));
		}
		seen.push(s);
		await page.waitForTimeout(500);
	}
	const bySession = {};
	for (const s of seen) if (s.active) bySession[s.sessions] = s;
	console.log('last sample per session:', JSON.stringify(bySession));
	console.log(errors.length ? errors.slice(0, 20).join('\n') : 'no errors');
	await browser.close();
})();
