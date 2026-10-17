// Collects the files the live viewer needs at runtime into dist-live/, which the Beat Saber mod serves.
// Run after `LIVE=1 NODE_ENV=production webpack` (npm run build:live does both).
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const out = path.join(root, 'dist-live');

fs.rmSync(out, {recursive: true, force: true});
fs.mkdirSync(out, {recursive: true});

function copy(from, to = from) {
	fs.cpSync(path.join(root, from), path.join(out, to), {recursive: true});
}

let html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
if (!html.includes('live-preamble.js')) {
	throw new Error('index.html is not a live build; run with LIVE=1');
}

// The mod serves the page with a CSP that forbids inline scripts. Move the templates' inline <script> blocks
// into a file, and turn inline event handler attributes into data attributes that live-inline.js binds once
// at load. Only handlers present in this static file are ever bound.
const inlineScripts = [];
html = html.replace(/<script>([\s\S]*?)<\/script>/g, (_, code) => {
	inlineScripts.push(code);
	return '';
});
let handlers = 0;
html = html.replace(/\son(click|input|change|mousedown)="([^"]*)"/g, (_, event, code) => {
	handlers++;
	return ` data-live-on${event}="${code}"`;
});
const binder = `
document.addEventListener('DOMContentLoaded', function () {
	['click', 'input', 'change', 'mousedown'].forEach(function (event) {
		document.querySelectorAll('[data-live-on' + event + ']').forEach(function (el) {
			var handler = new Function('event', el.getAttribute('data-live-on' + event));
			el.removeAttribute('data-live-on' + event);
			el.addEventListener(event, function (e) {
				return handler.call(el, e);
			});
		});
	});
});
`;
fs.writeFileSync(path.join(out, 'live-inline.js'), inlineScripts.join('\n') + binder);
html = html.replace('</body>', '<script src="live-inline.js"></script>\n</body>');
if (/<script(?![^>]*\ssrc=)/.test(html) || /\son[a-z]+="/.test(html)) {
	throw new Error('Inline script left in the live index.html');
}
fs.writeFileSync(path.join(out, 'index.html'), html);
console.log(`moved ${inlineScripts.length} inline scripts and ${handlers} inline handlers out of index.html`);

// Only the bundle that index.html references.
for (const match of html.matchAll(/(?:src|href)="(build\/[^"]+)"/g)) {
	copy(match[1]);
}
copy('src/live/preamble.js', 'live-preamble.js');
copy('vendor/aframe-master.min.js');
for (const dir of ['fonts', 'img', 'models', 'raw', 'shaders', 'sounds']) {
	copy(path.join('assets', dir));
}
copy('node_modules/@fortawesome/fontawesome-free/css/all.min.css', 'assets/fontawesome/css/all.min.css');
copy('node_modules/@fortawesome/fontawesome-free/webfonts', 'assets/fontawesome/webfonts');

let total = 0;
(function walk(dir) {
	for (const entry of fs.readdirSync(dir, {withFileTypes: true})) {
		const p = path.join(dir, entry.name);
		if (entry.isDirectory()) walk(p);
		else total += fs.statSync(p).size;
	}
})(out);
console.log(`dist-live: ${(total / 1024 / 1024).toFixed(1)} MB`);
