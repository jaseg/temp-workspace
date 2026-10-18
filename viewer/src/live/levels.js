// Level browser: the custom levels installed on the Frame, with their map stats, BeatLeader stats (fetched by the
// mod) and an audio-only preview. Everything comes over the live connection; nothing is fetched from elsewhere.
//
// Level data comes from downloaded maps and is untrusted: it is only ever put into the page as text.
import {LevelFile, FileError} from './protocol';
require('./levels.styl');

const DIFFICULTIES = ['Easy', 'Normal', 'Hard', 'Expert', 'ExpertPlus'];
const SHORT = {Easy: 'E', Normal: 'N', Hard: 'H', Expert: 'Ex', ExpertPlus: 'E+'};
const STATUS = {1: 'Nominated', 2: 'Qualified', 3: 'Ranked', 4: 'Unrankable', 5: 'Outdated', 6: 'Event', 7: 'OST'};
const MAX_COVERS = 200; // cached cover images (object URLs)
const FADE_S = 1;

function el(tag, className, text) {
	const e = document.createElement(tag);
	if (className) e.className = className;
	if (text != null) e.textContent = text;
	return e;
}

function formatTime(seconds) {
	if (!(seconds > 0)) return '-:--';
	const s = Math.round(seconds);
	return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

function formatNumber(x, digits = 0) {
	return x == null || !isFinite(x) ? '–' : x.toFixed(digits);
}

function difficultyOrder(d) {
	const i = DIFFICULTIES.indexOf(d.difficulty);
	return (d.mode === 'Standard' ? 0 : 100) + (i < 0 ? 50 : i);
}

/** Runs at most `limit` async jobs at once, newest requests last. */
class Queue {
	constructor(limit) {
		this.limit = limit;
		this.running = 0;
		this.jobs = [];
	}
	push(job) {
		this.jobs.push(job);
		this.next();
	}
	clear() {
		this.jobs = [];
	}
	next() {
		while (this.running < this.limit && this.jobs.length) {
			const job = this.jobs.shift();
			this.running++;
			Promise.resolve()
				.then(job)
				.catch(() => {})
				.then(() => {
					this.running--;
					this.next();
				});
		}
	}
}

export class LevelBrowser {
	constructor(connection) {
		this.connection = connection;
		this.levels = [];
		this.rows = new Map(); // level id -> row element
		this.stats = new Map(); // level id -> stats document, or null while loading/unavailable
		this.covers = new Map(); // level id -> object URL (insertion order = age)
		this.statsEnabled = true;
		this.coverQueue = new Queue(3);
		this.statsQueue = new Queue(2);
		this.available = false;
		this.preview = null;
		this.build();
	}

	build() {
		const root = el('div');
		root.id = 'levelBrowser';
		root.hidden = true;
		root.setAttribute('role', 'dialog');
		root.setAttribute('aria-label', 'Custom levels');

		const header = el('div', 'lbHeader');
		const title = el('h2', 'lbTitle', 'Custom levels');
		this.countEl = el('span', 'lbCount');
		title.append(' ', this.countEl);
		this.search = el('input', 'lbSearch');
		this.search.type = 'search';
		this.search.placeholder = 'Search song, artist or mapper';
		this.search.addEventListener('input', () => this.render());
		this.sort = el('select', 'lbSort');
		this.sort.title = 'Sort by';
		for (const [value, label] of [
			['added', 'Recently added'],
			['name', 'Song name'],
			['artist', 'Artist'],
			['mapper', 'Mapper'],
			['stars', 'Stars (loaded)'],
			['bpm', 'BPM'],
			['duration', 'Length'],
		]) {
			const option = el('option', null, label);
			option.value = value;
			this.sort.append(option);
		}
		this.sort.addEventListener('change', () => this.render());
		const close = el('button', 'lbClose', '×');
		close.type = 'button';
		close.title = 'Close (Esc)';
		close.addEventListener('click', () => this.close());
		header.append(title, this.search, this.sort, close);

		this.statusEl = el('div', 'lbStatus');
		this.list = el('ul', 'lbList');
		root.append(header, this.statusEl, this.list);

		// Keys typed here are for the browser, not the scene's hotkeys.
		root.addEventListener('keydown', e => {
			if (e.key === 'Escape') this.close();
			e.stopPropagation();
		});
		document.body.appendChild(root);
		this.root = root;

		this.observer = new IntersectionObserver(entries => this.onVisible(entries), {root: this.list, rootMargin: '200px'});

		// The controls bar's level button, and B, toggle the browser.
		document.addEventListener('click', e => {
			if (e.target.closest && e.target.closest('.controlsLevels')) this.toggle();
		});
		document.addEventListener('keydown', e => {
			const typing = e.target.closest && e.target.closest('input, textarea, select');
			if ((e.key === 'b' || e.key === 'B') && !e.ctrlKey && !e.metaKey && !e.altKey && !typing) this.toggle();
		});
	}

	get isOpen() {
		return !this.root.hidden;
	}

	/** The connection is approved (or not); the list can only be loaded while it is. */
	setAvailable(available) {
		this.available = available;
		if (!available) {
			this.stopPreview();
			this.coverQueue.clear();
			this.statsQueue.clear();
			if (this.isOpen) this.setStatus('Not connected to Beat Saber.');
		} else if (this.isOpen) {
			this.load();
		}
	}

	open() {
		this.root.hidden = false;
		this.search.focus();
		if (this.available) this.load();
		else this.setStatus('Not connected to Beat Saber.');
	}

	close() {
		this.root.hidden = true;
		this.stopPreview();
		this.coverQueue.clear();
		this.statsQueue.clear();
		// Requests that were queued but not sent are dropped; let rows ask again next time.
		for (const [id, stats] of this.stats) if (stats === null) this.stats.delete(id);
	}

	toggle() {
		if (this.isOpen) this.close();
		else this.open();
	}

	setStatus(text) {
		this.statusEl.textContent = text;
		this.statusEl.hidden = !text;
	}

	async load() {
		if (this.loading) return;
		this.loading = true;
		if (!this.levels.length) this.setStatus('Loading levels…');
		try {
			const list = await this.connection.fetchLevelList();
			this.levels = (list.levels || []).map(level => ({
				...level,
				difficulties: [...(level.difficulties || [])].sort((a, b) => difficultyOrder(a) - difficultyOrder(b)),
				search: [level.songName, level.songSubName, level.songAuthor, level.mapper].join(' ').toLowerCase(),
			}));
			this.setStatus(this.levels.length ? '' : 'No custom levels found.');
			this.render();
		} catch (e) {
			this.setStatus(
				e.code === FileError.notAvailable ? 'The mod has no level folder configured.' : `Couldn't load the level list (${e.message}).`
			);
		} finally {
			this.loading = false;
		}
	}

	maxStars(level) {
		const stats = this.stats.get(level.id);
		if (!stats || !stats.found) return -1;
		return Math.max(-1, ...stats.difficulties.map(d => d.stars || -1));
	}

	render() {
		const query = this.search.value.trim().toLowerCase();
		const words = query ? query.split(/\s+/) : [];
		const levels = this.levels.filter(l => words.every(w => l.search.includes(w)));
		const text = (a, b) => a.localeCompare(b, undefined, {sensitivity: 'base'});
		const by = {
			added: (a, b) => b.added - a.added,
			name: (a, b) => text(a.songName, b.songName),
			artist: (a, b) => text(a.songAuthor, b.songAuthor),
			mapper: (a, b) => text(a.mapper, b.mapper),
			stars: (a, b) => this.maxStars(b) - this.maxStars(a),
			bpm: (a, b) => b.bpm - a.bpm,
			duration: (a, b) => b.duration - a.duration,
		}[this.sort.value];
		levels.sort((a, b) => by(a, b) || text(a.songName, b.songName));

		this.countEl.textContent = words.length ? `${levels.length} of ${this.levels.length}` : `${this.levels.length}`;
		this.observer.disconnect();
		const rows = levels.map(level => {
			let row = this.rows.get(level.id);
			if (!row || row.level !== level) {
				row = this.buildRow(level);
				this.rows.set(level.id, row);
			}
			this.observer.observe(row);
			return row;
		});
		this.list.replaceChildren(...rows);
	}

	buildRow(level) {
		const row = el('li', 'lbLevel');
		row.level = level;

		const cover = el('div', 'lbCover');
		const img = el('img');
		img.alt = '';
		img.hidden = true;
		cover.append(img);
		const url = this.covers.get(level.id);
		if (url) {
			img.src = url;
			img.hidden = false;
		}

		const main = el('div', 'lbMain');
		const name = el('div', 'lbName', level.songName || 'Untitled');
		if (level.songSubName) name.append(' ', el('span', 'lbSub', level.songSubName));
		const meta = el('div', 'lbMeta');
		const parts = [level.songAuthor, level.mapper && `mapped by ${level.mapper}`, level.bpm > 0 && `${Math.round(level.bpm)} BPM`, formatTime(level.duration)];
		meta.textContent = parts.filter(Boolean).join(' · ');
		const chips = el('div', 'lbChips');
		main.append(name, meta, chips);

		const play = el('button', 'lbPlay');
		play.type = 'button';
		play.disabled = !level.hasAudio;
		play.title = level.hasAudio ? 'Play preview' : 'No song file';
		play.addEventListener('click', e => {
			e.stopPropagation();
			this.togglePreview(level, row);
		});
		const progress = el('div', 'lbProgress');

		const details = el('div', 'lbDetails');
		details.hidden = true;

		row.append(cover, main, play, progress, details);
		row.addEventListener('click', () => {
			details.hidden = !details.hidden;
			row.classList.toggle('expanded', !details.hidden);
			if (!details.hidden) this.renderDetails(level, details);
		});
		row.refs = {img, chips, play, progress, details};
		this.renderChips(level, row);
		return row;
	}

	statsFor(level, d) {
		const stats = this.stats.get(level.id);
		if (!stats || !stats.found) return null;
		return stats.difficulties.find(s => s.mode === d.mode && s.difficulty === d.difficulty) || null;
	}

	renderChips(level, row) {
		const {chips} = row.refs;
		chips.replaceChildren();
		const stats = this.stats.get(level.id);
		const ranked = stats && stats.found && Math.max(0, ...stats.difficulties.map(d => (d.status === 3 || d.status === 2 ? d.status : 0)));
		if (ranked) chips.append(el('span', `lbBadge status${ranked}`, STATUS[ranked]));

		const standard = level.difficulties.filter(d => d.mode === 'Standard');
		for (const d of standard) {
			const s = this.statsFor(level, d);
			const chip = el('span', `lbChip d${d.difficulty}`, SHORT[d.difficulty] || d.difficulty);
			if (s && s.stars) chip.append(el('span', 'lbStars', ` ${s.stars.toFixed(2)}★`));
			chip.title = d.label || d.difficulty;
			chips.append(chip);
		}
		const modes = new Set(level.difficulties.filter(d => d.mode !== 'Standard').map(d => d.mode));
		if (modes.size) chips.append(el('span', 'lbMore', `+${modes.size} mode${modes.size > 1 ? 's' : ''}`));
		if (row.refs.details && !row.refs.details.hidden) this.renderDetails(level, row.refs.details);
	}

	renderDetails(level, details) {
		const stats = this.stats.get(level.id);
		const table = el('table', 'lbTable');
		const head = el('tr');
		for (const h of ['Mode', 'Difficulty', 'NJS', 'Notes', 'Bombs', 'Walls', 'NPS', '★', 'Pass', 'Acc', 'Tech', 'Status']) head.append(el('th', null, h));
		table.append(head);
		for (const d of level.difficulties) {
			const s = this.statsFor(level, d);
			const nps = d.notes != null && level.duration > 0 ? d.notes / level.duration : null;
			const cells = [
				d.mode,
				d.label && d.label !== d.difficulty ? `${d.difficulty} (${d.label})` : d.difficulty,
				formatNumber(d.njs, d.njs % 1 ? 1 : 0),
				formatNumber(d.notes),
				formatNumber(d.bombs),
				formatNumber(d.walls),
				formatNumber(nps, 2),
				s ? formatNumber(s.stars, 2) : '–',
				s ? formatNumber(s.pass, 2) : '–',
				s ? formatNumber(s.acc, 2) : '–',
				s ? formatNumber(s.tech, 2) : '–',
				s ? STATUS[s.status] || 'Unranked' : '–',
			];
			const tr = el('tr');
			cells.forEach((c, i) => tr.append(el('td', i === 1 ? `d${d.difficulty}` : null, c)));
			table.append(tr);
		}

		const notes = [];
		if (level.environment) notes.push(`Environment: ${level.environment}`);
		if (!this.statsEnabled) notes.push('BeatLeader stats are turned off in the mod.');
		else if (stats === undefined || stats === null) notes.push('Loading BeatLeader stats…');
		else if (stats.error) notes.push("Couldn't reach BeatLeader.");
		else if (!stats.found) notes.push('Not on BeatLeader.');
		else if (stats.key) notes.push(`BeatSaver key ${stats.key}`);
		const wrap = el('div', 'lbTableWrap');
		wrap.append(table);
		details.replaceChildren(wrap, el('div', 'lbNote', notes.join(' · ')));
	}

	// ---- lazy loading of covers and stats for visible rows ----

	onVisible(entries) {
		for (const entry of entries) {
			if (!entry.isIntersecting) continue;
			const row = entry.target;
			const level = row.level;
			this.observer.unobserve(row);
			if (level.hasCover && !this.covers.has(level.id) && !row.coverRequested) {
				row.coverRequested = true;
				this.coverQueue.push(() => this.loadCover(level));
			}
			if (this.statsEnabled && !this.stats.has(level.id)) {
				this.stats.set(level.id, null);
				this.statsQueue.push(() => this.loadStats(level));
			}
		}
	}

	async loadCover(level) {
		if (!this.isOpen || !this.available) return;
		const buffer = await this.connection.fetchLevelFile(level.id, LevelFile.cover);
		const url = URL.createObjectURL(new Blob([buffer]));
		this.covers.set(level.id, url);
		if (this.covers.size > MAX_COVERS) {
			const [oldId, oldUrl] = this.covers.entries().next().value;
			this.covers.delete(oldId);
			URL.revokeObjectURL(oldUrl);
			const oldRow = this.rows.get(oldId);
			if (oldRow) oldRow.coverRequested = false;
		}
		const row = this.rows.get(level.id);
		if (row) {
			row.refs.img.src = url;
			row.refs.img.hidden = false;
		}
	}

	async loadStats(level) {
		if (!this.isOpen || !this.available || !this.statsEnabled) {
			this.stats.delete(level.id);
			return;
		}
		let stats;
		try {
			stats = await this.connection.fetchLevelStats(level.id);
		} catch (e) {
			if (e.code === FileError.notAvailable) {
				this.statsEnabled = false;
				this.statsQueue.clear();
			}
			stats = {found: false, error: true};
		}
		this.stats.set(level.id, stats);
		const row = this.rows.get(level.id);
		if (row) this.renderChips(level, row);
	}

	// ---- audio preview ----

	togglePreview(level, row) {
		const same = this.preview && this.preview.level === level;
		this.stopPreview();
		if (!same) this.startPreview(level, row);
	}

	async startPreview(level, row) {
		// The element is created and started inside the click, so browsers that want a user gesture for
		// playback (Safari) let it play once the song has arrived.
		const audio = new Audio('assets/sounds/silence.mp3');
		audio.volume = 0;
		audio.play().catch(() => {});
		const preview = {level, row, audio, url: null, timer: null};
		this.preview = preview;
		row.classList.add('loading');
		let buffer;
		try {
			buffer = await this.connection.fetchLevelFile(level.id, LevelFile.audio);
		} catch (e) {
			row.classList.remove('loading');
			if (this.preview === preview) this.stopPreview();
			row.refs.play.title = `Couldn't load the song (${e.message})`;
			return;
		}
		row.classList.remove('loading');
		if (this.preview !== preview) return; // stopped or replaced while loading

		const length = level.previewDuration > 0 ? level.previewDuration : 10;
		let begin = level.previewStart > 0 ? level.previewStart : 0;
		const volume = Math.max(0.1, parseFloat((document.getElementById('musicSlider') || {}).value) || 0.5);
		// Custom levels ship Ogg Vorbis, or WAV for a few converted official songs.
		const wav = new TextDecoder().decode(new Uint8Array(buffer, 0, Math.min(4, buffer.byteLength))) === 'RIFF';
		preview.url = URL.createObjectURL(new Blob([buffer], {type: wav ? 'audio/wav' : 'audio/ogg'}));
		audio.addEventListener('loadedmetadata', () => {
			begin = Math.min(begin, Math.max(0, audio.duration - length));
			audio.currentTime = begin;
			audio.play().catch(() => this.preview === preview && this.stopPreview());
		});
		audio.addEventListener('ended', () => this.preview === preview && this.stopPreview());
		audio.addEventListener('error', () => {
			if (this.preview !== preview) return;
			this.stopPreview();
			row.refs.play.title = "This browser can't play the song file";
		});
		audio.src = preview.url;
		row.classList.add('playing');
		row.refs.play.title = 'Stop preview';

		// Fade in, play the preview section, fade out.
		const tick = () => {
			if (this.preview !== preview) return;
			const t = audio.currentTime - begin;
			const fade = Math.min(1, Math.max(0, t / FADE_S), Math.max(0, (length - t) / FADE_S));
			audio.volume = volume * fade;
			row.refs.progress.style.width = `${Math.min(100, Math.max(0, (t / length) * 100))}%`;
			if (t >= length) this.stopPreview();
			else preview.timer = setTimeout(tick, 50);
		};
		tick();
	}

	stopPreview() {
		const preview = this.preview;
		if (!preview) return;
		this.preview = null;
		clearTimeout(preview.timer);
		preview.audio.pause();
		preview.audio.removeAttribute('src');
		if (preview.url) URL.revokeObjectURL(preview.url);
		preview.row.classList.remove('playing', 'loading');
		preview.row.refs.progress.style.width = '0';
		if (preview.row.refs.play.title === 'Stop preview') preview.row.refs.play.title = 'Play preview';
	}
}
