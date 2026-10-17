// Opens the test page in headless Chromium against a running dev host and reports live stats.
// Usage: NODE_PATH=$(npm root -g) node tools/browser-smoke.cjs [url] [seconds]
// Requires the host to run with --auto-approve (or someone approving the printed code).
const {chromium} = require('playwright');

(async () => {

const url = process.argv[2] || 'https://localhost:4280/';
const seconds = Number(process.argv[3] || 15);

const browser = await chromium.launch();
const page = await browser.newPage({ignoreHTTPSErrors: true});
const errors = [];
page.on('pageerror', e => errors.push(String(e)));
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
await page.goto(url);

const deadline = Date.now() + 60000;
let printed = false;
while (Date.now() < deadline) {
	const s = await page.evaluate(() => ({state: window.liveStats.state, code: window.liveStats.code}));
	if (s.state === 'approved') break;
	if (s.state === 'waiting' && !printed) { console.log(`waiting, code ${s.code}`); printed = true; }
	if (s.state === 'denied') { console.log('denied'); await browser.close(); process.exit(1); }
	await page.waitForTimeout(200);
}
if ((await page.evaluate(() => window.liveStats.state)) !== 'approved') {
	console.log('not approved within 60 s');
	await browser.close();
	process.exit(1);
}

// Sample display age every animation frame for the measurement window.
const samples = await page.evaluate(seconds => new Promise(resolve => {
	const out = [];
	const end = performance.now() + seconds * 1000;
	function tick() {
		const s = window.liveStats;
		if (s.displayAgeMs !== null && s.lastPose) out.push({display: s.displayAgeMs, receive: s.receiveAgeMs});
		if (performance.now() < end) requestAnimationFrame(tick); else resolve(out);
	}
	requestAnimationFrame(tick);
}), seconds);

const stats = await page.evaluate(() => {
	const s = window.liveStats;
	return {state: s.state, session: s.session && s.session.songName, poses: s.poses, posesPerSecond: s.posesPerSecond,
		noteCuts: s.noteCuts, noteFinals: s.noteFinals, rttMs: s.rttMs, maxReceiveAgeMs: s.maxReceiveAgeMs};
});

await page.click('#maptest');
await page.waitForFunction(() => document.getElementById('maplog').textContent.split('\n').filter(Boolean).length >= Object.keys(window.liveStats.session ? window.liveStats.session.files : {}).length, null, {timeout: 30000}).catch(() => {});
const maplog = await page.textContent('#maplog');

const pct = (arr, p) => { const a = [...arr].sort((x, y) => x - y); return a.length ? a[Math.min(a.length - 1, Math.floor(p * a.length))] : null; };
const disp = samples.map(s => s.display), recv = samples.map(s => s.receive);
console.log(JSON.stringify({
	...stats,
	frames: samples.length,
	receiveAgeMs: {p50: pct(recv, 0.5), p95: pct(recv, 0.95), max: Math.max(...recv)},
	displayAgeMs: {p50: pct(disp, 0.5), p95: pct(disp, 0.95), max: Math.max(...disp)},
	errors,
}, null, 2));
console.log(maplog);
await browser.close();
})();
