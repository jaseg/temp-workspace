// Collects the files the viewer needs at runtime into dist/, which the Beat Saber mod serves.
// Run after the webpack production build (`npm run build` does both).
//
// With `--demo <map folder> <replay.bsor>` (after a LIVE_DEMO=1 build) it writes dist-demo/ instead: a fully
// static page that plays that replay through the live code path, no game or mod needed.
// `--levels <dump.json> <levels folder>` adds a level list for the level browser: the dump comes from
// `LiveViewer.Host --dump-levels`, covers are copied from the folder, and song files while they fit a small budget.
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const demoArg = process.argv.indexOf('--demo');
const demo = demoArg >= 0 ? {map: process.argv[demoArg + 1], replay: process.argv[demoArg + 2]} : null;
const levelsArg = process.argv.indexOf('--levels');
const levels = levelsArg >= 0 ? {dump: process.argv[levelsArg + 1], folder: process.argv[levelsArg + 2]} : null;
const DEMO_AUDIO_BUDGET = 12 * 1024 * 1024;
const out = path.join(root, demo ? 'dist-demo' : 'dist');

fs.rmSync(out, {recursive: true, force: true});
fs.mkdirSync(out, {recursive: true});

function copy(from, to = from) {
	fs.cpSync(path.join(root, from), path.join(out, to), {recursive: true});
}

function copyWithSourceMap(from, to = from) {
	copy(from, to);
	if (fs.existsSync(path.join(root, from + '.map'))) copy(from + '.map', to + '.map');
}

// The mod serves the page with a CSP that forbids inline scripts and event handlers; keep it that way.
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
if (/<script(?![^>]*\ssrc=)/.test(html) || /\son[a-z]+="/.test(html)) {
	throw new Error('index.html contains an inline script or event handler');
}
fs.writeFileSync(path.join(out, 'index.html'), html);

// Only the bundle that index.html references, and the parts it loads on demand (same build timestamp).
for (const match of html.matchAll(/(?:src|href)="(build\/[^"]+)"/g)) {
	copyWithSourceMap(match[1]);
	const stamp = match[1].match(/\.(\d+)\.js$/);
	if (stamp) {
		for (const name of fs.readdirSync(path.join(root, 'build'))) {
			if (name.endsWith(`.${stamp[1]}.js`) && !match[1].endsWith(name)) copyWithSourceMap(path.join('build', name));
		}
	}
}
copy('src/preamble.js', 'preamble.js');

// A-Frame builds trivial getters with new Function; replace that with a closure so the page needs no eval.
const aframe = fs.readFileSync(path.join(root, 'vendor/aframe-master.min.js'), 'utf8');
const evalGetter = 'function wrapper(t){return new Function(["return function "+t+"() {","  return this._"+t,"}"].join("\\n"))()}';
if (!aframe.includes(evalGetter)) throw new Error('A-Frame getter factory not found; update the patch in scripts/package.js');
fs.mkdirSync(path.join(out, 'vendor'), {recursive: true});
const patchedAframe = aframe
	.replace(evalGetter, 'function wrapper(t){return function(){return this["_"+t]}}')
	.replace('resetMesh:function(){this.el.removeObject3D("mesh")}', 'resetMesh:function(){this.el.getObject3D("mesh")&&this.el.removeObject3D("mesh")}')
	.replace(/\n\/\/# sourceMappingURL=aframe-master\.min\.js\.map\s*$/, '');
fs.writeFileSync(path.join(out, 'vendor/aframe-master.min.js'), patchedAframe);
// Shaders and the default hit sound are bundled by webpack; the rest is loaded at runtime.
for (const dir of ['fonts', 'img', 'models']) {
	copy(path.join('assets', dir));
}
copy('assets/sounds/silence.mp3');
// Blender source files aren't loaded by the page.
for (const f of fs.readdirSync(path.join(out, 'assets/models'))) {
	if (f.endsWith('.blend')) fs.rmSync(path.join(out, 'assets/models', f));
}
copy('node_modules/@fortawesome/fontawesome-free/css/all.min.css', 'assets/fontawesome/css/all.min.css');
copy('node_modules/@fortawesome/fontawesome-free/webfonts', 'assets/fontawesome/webfonts');

if (demo) {
	// Map files under plain names (no spaces or case issues), with the original names in the manifest.
	const mapDir = path.join(out, 'demo', 'map');
	fs.mkdirSync(mapDir, {recursive: true});
	const infoName = fs.readdirSync(demo.map).find(n => n.toLowerCase() === 'info.dat');
	const info = JSON.parse(fs.readFileSync(path.join(demo.map, infoName), 'utf8'));
	const replay = fs.readFileSync(demo.replay);
	// BSOR info: difficulty and mode are the 13th and 14th strings, with the score (int32) between them.
	const strings = [];
	for (let p = 6; strings.length < 15; ) {
		const n = replay.readInt32LE(p);
		strings.push(replay.toString('utf8', p + 4, p + 4 + n));
		p += 4 + n + (strings.length === 13 ? 4 : 0); // the score int follows the difficulty
	}
	const [difficulty, mode] = [strings[12], strings[13]];
	const set = info._difficultyBeatmapSets.find(s => s._beatmapCharacteristicName === mode);
	const diff = set._difficultyBeatmaps.find(d => d._difficulty === difficulty);
	const files = {info: infoName, difficulty: diff._beatmapFilename, audio: info._songFilename, cover: info._coverImageFilename};
	const paths = {};
	Object.entries(files).forEach(([role, name]) => {
		// Standard extensions for the static host: map .dat files are JSON, .egg is Ogg Vorbis.
		const ext = {'.dat': '.json', '.egg': '.ogg'}[path.extname(name).toLowerCase()] || path.extname(name).toLowerCase();
		const safe = role + ext;
		fs.copyFileSync(path.join(demo.map, name), path.join(mapDir, safe));
		paths[name] = safe;
	});
	// Base64 text, so static hosts that only serve text and media types can serve it.
	fs.writeFileSync(path.join(out, 'demo', 'replay.txt'), replay.toString('base64'));
	const levelFiles = levels ? packageLevels() : null;
	fs.writeFileSync(
		path.join(out, 'demo', 'manifest.json'),
		JSON.stringify({songName: info._songName, songAuthor: info._songAuthorName, bpm: info._beatsPerMinute || (info.audio && info.audio.bpm) || 120, files, paths, levels: levelFiles}, null, 1)
	);
	console.log(`demo: ${info._songName} ${mode} ${difficulty}`);
}

/** Copies covers (and songs, within the budget) for the level browser; returns their paths by level id. */
function packageLevels() {
	const dump = JSON.parse(fs.readFileSync(levels.dump, 'utf8'));
	const dir = path.join(out, 'demo', 'levels');
	fs.mkdirSync(dir, {recursive: true});
	const result = {covers: {}, audio: {}};
	let audioBytes = 0;
	// Smallest songs first, so the budget covers as many levels as possible.
	const entries = dump.list.levels
		.map(level => {
			const folder = path.join(levels.folder, dump.folders[level.id]);
			const infoName = fs.readdirSync(folder).find(n => n.toLowerCase() === 'info.dat');
			const info = JSON.parse(fs.readFileSync(path.join(folder, infoName), 'utf8').replace(/^\uFEFF/, ''));
			const actual = name => name && fs.readdirSync(folder).find(n => n.toLowerCase() === name.toLowerCase());
			const cover = actual(info._coverImageFilename || info.coverImageFilename);
			const audio = actual(info._songFilename || (info.audio && info.audio.songFilename));
			return {level, folder, cover, audio, audioSize: audio ? fs.statSync(path.join(folder, audio)).size : Infinity};
		})
		.sort((a, b) => a.audioSize - b.audioSize);
	for (const {level, folder, cover, audio, audioSize} of entries) {
		if (cover) {
			const name = level.id + (path.extname(cover).toLowerCase() || '.jpg');
			fs.copyFileSync(path.join(folder, cover), path.join(dir, name));
			result.covers[level.id] = 'levels/' + name;
		}
		if (audio && audioBytes + audioSize <= DEMO_AUDIO_BUDGET) {
			fs.copyFileSync(path.join(folder, audio), path.join(dir, level.id + '.ogg'));
			result.audio[level.id] = 'levels/' + level.id + '.ogg';
			audioBytes += audioSize;
		}
		level.hasCover = !!result.covers[level.id];
		level.hasAudio = !!result.audio[level.id];
	}
	fs.writeFileSync(path.join(out, 'demo', 'levels.json'), JSON.stringify({list: dump.list, stats: dump.stats}));
	console.log(`demo: ${entries.length} levels, ${Object.keys(result.audio).length} with songs (${(audioBytes / 1048576).toFixed(1)} MB)`);
	return result;
}

let total = 0;
(function walk(dir) {
	for (const entry of fs.readdirSync(dir, {withFileTypes: true})) {
		const p = path.join(dir, entry.name);
		if (entry.isDirectory()) walk(p);
		else total += fs.statSync(p).size;
	}
})(out);
console.log(`${path.basename(out)}: ${(total / 1024 / 1024).toFixed(1)} MB`);
