// Two viewers on one server: the top bar switches between live view and levels, a suggestion made in one page shows
// up in the other, and it can be removed there. Needs a server that approves automatically (dev host with
// --auto-approve, or the plugin with DevAutoApprove) and has at least one level.
// Usage: NODE_PATH=$(npm root -g) node tools/suggestions-smoke.cjs [url] [screenshot-prefix]
const {chromium} = require('playwright');

(async () => {
	const url = process.argv[2] || 'https://localhost:4280/';
	const shots = process.argv[3] || 'suggestions';
	const browser = await chromium.launch({args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--autoplay-policy=no-user-gesture-required']});
	const errors = [];
	const open = async (name, width, height) => {
		const page = await browser.newPage({ignoreHTTPSErrors: true, viewport: {width, height}});
		page.on('pageerror', e => errors.push(`${name} pageerror: ${e.message}`));
		await page.goto(url);
		await page.click('#liveOverlay .liveRequest', {timeout: 20000});
		await page.waitForSelector('#liveNav:not([hidden])', {timeout: 20000});
		return page;
	};
	const badge = page => page.evaluate(() => {
		const b = document.querySelector('#liveNav .navBadge');
		return b.hidden ? 0 : Number(b.textContent);
	});
	const check = (ok, message) => ok || errors.push(message);

	const a = await open('a', 1280, 800);
	const b = await open('b', 390, 760);
	const start = await badge(a);

	// A: open the levels with the top bar, suggest the first level that isn't suggested yet.
	await a.click('#liveNav button:nth-child(2)');
	await a.waitForSelector('#levelBrowser:not([hidden]) .lbLevel', {timeout: 20000});
	const name = (await a.locator('#levelBrowser .lbLevel:has(.lbSuggest:not(.on)) .lbName').first().textContent()).trim();
	const row = a.locator('#levelBrowser .lbLevel', {hasText: name}).first();
	check((await row.locator('.lbPlay').textContent()) === 'Preview', 'a: preview button not labelled "Preview"');
	await row.locator('.lbSuggest').click();
	await a.waitForFunction(n => document.querySelector('#liveNav .navBadge').textContent === String(n), start + 1, {timeout: 10000});
	await b.waitForFunction(n => document.querySelector('#liveNav .navBadge').textContent === String(n), start + 1, {timeout: 10000})
		.catch(() => errors.push("b: didn't see a's suggestion"));
	check((await row.locator('.lbSuggest').textContent()).includes('Suggested'), 'a: button not showing "Suggested"');
	await a.screenshot({path: `${shots}-a-all.png`});

	// B: the Suggested tab lists it with who suggested it; remove it there.
	await b.click('#liveNav button:nth-child(2)');
	await b.click('#levelBrowser .lbTab:nth-child(2)');
	const suggested = b.locator('#levelBrowser .lbLevel', {hasText: name});
	await suggested.waitFor({timeout: 10000});
	check(/Suggested by/.test(await suggested.locator('.lbSuggested').textContent()), 'b: no "Suggested by" line');
	await b.screenshot({path: `${shots}-b-suggested.png`});
	await suggested.locator('.lbSuggest').click();
	await a.waitForFunction(n => {
		const el = document.querySelector('#liveNav .navBadge');
		return (el.hidden ? 0 : Number(el.textContent)) === n;
	}, start, {timeout: 10000}).catch(() => errors.push("a: didn't see b's removal"));

	// Reordering: A suggests three levels; B moves them with the buttons and by dragging; A sees each new order.
	const ids = page => page.evaluate(() => window.liveSession.levels.suggestions.map(x => x.id));
	const names = await a.$$eval('#levelBrowser .lbLevel:has(.lbSuggest:not(.on)) .lbName', els => els.slice(0, 3).map(e => e.textContent.trim()));
	for (const n of names) {
		const before = (await ids(a)).length;
		await a.locator('#levelBrowser .lbLevel', {hasText: n}).first().locator('.lbSuggest').click();
		await a.waitForFunction(k => window.liveSession.levels.suggestions.length === k, before + 1);
	}
	const three = (await ids(a)).slice(-3);
	await b.waitForFunction(k => window.liveSession.levels.suggestions.length === k, (await ids(a)).length);
	const same = async (expected, what) => {
		await a.waitForFunction(e => JSON.stringify(window.liveSession.levels.suggestions.map(x => x.id).slice(-3)) === e, JSON.stringify(expected), {timeout: 5000})
			.catch(() => errors.push(`a: wrong order after ${what}`));
	};
	const bRow = async id => {
		const index = (await ids(b)).indexOf(id);
		return b.locator('#levelBrowser .lbList > .lbLevel').nth(index);
	};
	await (await bRow(three[0])).locator('.lbMove-down').click();
	await same([three[1], three[0], three[2]], 'move down');
	await (await bRow(three[2])).locator('.lbMove-up').click();
	await same([three[1], three[2], three[0]], 'move up');
	await (await bRow(three[0])).locator('.lbMove-top').click();
	await a.waitForFunction(id => window.liveSession.levels.suggestions[0].id === id, three[0], {timeout: 5000}).catch(() => errors.push('a: to top'));
	await (await bRow(three[0])).locator('.lbMove-bottom').click();
	await same([three[1], three[2], three[0]], 'to bottom');

	// Drag the last of the three above the other two (B is phone-sized: drag with touch-like pointer moves).
	const source = await (await bRow(three[2])).locator('.lbHandle').boundingBox();
	const dest = await (await bRow(three[1])).boundingBox();
	await b.mouse.move(source.x + source.width / 2, source.y + source.height / 2);
	await b.mouse.down();
	for (let i = 1; i <= 10; i++) await b.mouse.move(source.x + source.width / 2, source.y + source.height / 2 + ((dest.y + 4 - source.y - source.height / 2) * i) / 10);
	await b.screenshot({path: `${shots}-b-dragging.png`});
	await b.mouse.up();
	await same([three[2], three[1], three[0]], 'drag');

	// A search locks the order.
	await b.fill('#levelBrowser .lbSearch', 'a');
	check(await b.locator('#levelBrowser .lbMove-up:not([disabled])').count() === 0, 'b: move buttons enabled during a search');
	await b.fill('#levelBrowser .lbSearch', '');
	await b.screenshot({path: `${shots}-b-reorder.png`});
	await a.click('#levelBrowser .lbTab:nth-child(2)');
	await a.screenshot({path: `${shots}-a-reorder.png`});
	for (const id of three) {
		await a.evaluate(i => window.liveSession.connection.suggest(i, false), id);
	}
	await a.waitForFunction(t => !window.liveSession.levels.suggestions.some(x => t.includes(x.id)), three);

	// The top bar's Live button goes back to the live view; B toggles too.
	await a.click('#liveNav button:nth-child(1)');
	check(await a.evaluate(() => document.getElementById('levelBrowser').hidden), 'a: Live button did not close the level browser');
	check((await a.getAttribute('#liveNav button:nth-child(1)', 'aria-pressed')) === 'true', 'a: Live not marked as current');
	await a.screenshot({path: `${shots}-a-live.png`});

	console.log(errors.length ? errors.join('\n') : `no errors (badge ${start} -> ${start + 1} -> ${await badge(a)}; level "${name}")`);
	await browser.close();
	process.exit(errors.length ? 1 : 0);
})();
