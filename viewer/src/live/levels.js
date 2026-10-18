// Level browser: the custom levels installed on the Frame, with their map stats, BeatLeader stats (fetched by the
// mod), an audio-only preview and the shared list of levels viewers suggest to the player. Everything comes over the
// live connection; nothing is fetched from elsewhere.
//
// Level data comes from downloaded maps and is untrusted: it is only ever put into the page as text.
import {LevelFile, FileError} from './protocol';
import {isOgg, canPlayOgg, decodeAudio} from './ogg';
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

function formatAgo(unixSeconds) {
	const s = Date.now() / 1000 - unixSeconds;
	if (s < 60) return 'just now';
	if (s < 3600) return `${Math.floor(s / 60)} min ago`;
	if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
	return `${Math.floor(s / 86400)} d ago`;
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
		this.view = 'levels'; // or 'playlist': the shared suggestion list
		this.suggestions = []; // [{id, by, added}], oldest first, as the mod sends them
		this.suggestionMax = 100;
		this.pending = new Set(); // level ids with a suggestion change sent but not answered yet
		this.drag = null; // the suggestion being dragged
		this.deferredSuggestions = null; // a list that arrived during a drag, applied on drop
		this.onChange = null; // called when the browser opens or closes, or the suggestions change
		this.build();
	}

	build() {
		const root = el('div');
		root.id = 'levelBrowser';
		root.hidden = true;
		root.setAttribute('role', 'dialog');
		root.setAttribute('aria-label', 'Levels');

		const header = el('div', 'lbHeader');
		// "19 levels", "3 of 19 levels" while searching, "Playlist · 3 levels".
		const title = el('h2', 'lbTitle');
		this.titleEl = title;
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
		header.append(title, this.search, this.sort);

		this.hint = el('div', 'lbHint');
		header.append(this.hint);

		this.statusEl = el('div', 'lbStatus');
		this.list = el('ul', 'lbList');
		root.append(header, this.statusEl, this.list);

		// Keys typed here are for the browser, not the scene's hotkeys. Escape goes back to the live view.
		root.addEventListener('keydown', e => {
			if (e.key === 'Escape') this.close();
			e.stopPropagation();
		});
		document.body.appendChild(root);
		this.root = root;

		this.observer = new IntersectionObserver(entries => this.onVisible(entries), {root: this.list, rootMargin: '200px'});

		// B toggles the browser (the top bar's buttons do the same).
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
		} else {
			// Loaded right away, so the top bar can show how many levels there are.
			this.load();
		}
	}

	get suggestionCount() {
		return this.suggestions.length;
	}

	open() {
		if (this.isOpen) return;
		this.root.hidden = false;
		this.search.focus();
		if (this.available) this.load();
		else this.setStatus('Not connected to Beat Saber.');
		if (this.onChange) this.onChange();
	}

	close() {
		if (!this.isOpen) return;
		this.root.hidden = true;
		if (this.onChange) this.onChange();
		this.stopPreview();
		this.coverQueue.clear();
		this.statsQueue.clear();
		// Requests that were queued but not sent are dropped; let rows ask again next time.
		for (const [id, stats] of this.stats) if (stats === null) this.stats.delete(id);
	}

	/** Shows the levels or the playlist (opening the browser if needed). */
	show(view) {
		if (view !== this.view) {
			this.view = view;
			this.list.scrollTop = 0;
			if (this.isOpen) this.render();
		}
		if (this.isOpen) {
			if (this.onChange) this.onChange();
		} else {
			this.open();
		}
	}

	/** The mod's suggestion list (see "Suggestions" in PROTOCOL.md): on approval and after every change. */
	setSuggestions(doc) {
		if (this.drag) {
			this.deferredSuggestions = doc;
			return;
		}
		this.suggestions = Array.isArray(doc.levels) ? doc.levels.filter(s => typeof s.id === 'string') : [];
		this.suggestionMax = doc.max || this.suggestionMax;
		this.pending.clear();
		for (const row of this.rows.values()) this.renderSuggest(row);
		if (this.view === 'playlist' && this.isOpen) this.render();
		if (this.onChange) this.onChange();
	}

	suggestion(levelId) {
		return this.suggestions.find(s => s.id === levelId);
	}

	toggleSuggestion(levelId) {
		if (this.pending.has(levelId)) return;
		const add = !this.suggestion(levelId);
		if (add && this.suggestions.length >= this.suggestionMax) {
			this.setStatus(`The playlist is full (${this.suggestionMax} levels). Remove one first.`);
			return;
		}
		if (!this.connection.suggest(levelId, add)) return;
		this.pending.add(levelId);
		const row = this.rows.get(levelId);
		if (row) this.renderSuggest(row);
	}

	/** Can the playlist be reordered right now? Not while a search filters it: positions would be ambiguous. */
	get canReorder() {
		return this.view === 'playlist' && !this.search.value.trim();
	}

	/** Moves a suggestion to position `index` of the shared list, here at once and then on the mod. */
	moveSuggestion(levelId, index) {
		const from = this.suggestions.findIndex(s => s.id === levelId);
		const to = Math.max(0, Math.min(index, this.suggestions.length - 1));
		if (from < 0 || from === to || !this.connection.moveSuggestion(levelId, to)) return;
		// Optimistic: the mod's answer (to everyone) replaces this with the real order.
		const entry = this.suggestions.splice(from, 1)[0];
		this.suggestions.splice(to, 0, entry);
		const focused = document.activeElement;
		this.render();
		// Keep keyboard focus on the button that was pressed, so it can be pressed again.
		if (focused && this.list.contains(focused)) focused.focus();
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
			if (this.onChange) this.onChange();
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
		let pool = this.levels;
		if (this.view === 'playlist') {
			// Playlist entries whose level is no longer installed still get a row, so they can be removed.
			const byId = new Map(this.levels.map(l => [l.id, l]));
			pool = this.suggestions.map(
				s => byId.get(s.id) || {id: s.id, missing: true, songName: 'Level no longer installed', songSubName: '', songAuthor: '', mapper: '', difficulties: [], search: '', added: 0, bpm: 0, duration: 0}
			);
		}
		const levels = pool.filter(l => words.every(w => l.search.includes(w)));
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
		// The suggestion list keeps its own order (oldest first, like the playlist in the game).
		if (this.view === 'levels') levels.sort((a, b) => by(a, b) || text(a.songName, b.songName));
		this.sort.disabled = this.view !== 'levels';

		const count = words.length ? `${levels.length} of ${pool.length}` : `${pool.length}`;
		const noun = pool.length === 1 ? 'level' : 'levels';
		this.titleEl.textContent = this.view === 'playlist' ? `Playlist · ${count} ${noun}` : `${count} ${noun}`;
		if (this.view === 'playlist' && !pool.length && this.levels.length) {
			this.setStatus('The playlist is empty. Use “Add to playlist” on a level to suggest it to the player.');
		} else if (this.statusEl.textContent.startsWith('The playlist is empty')) {
			this.setStatus('');
		}
		this.observer.disconnect();
		const rows = levels.map(level => {
			let row = this.rows.get(level.id);
			if (!row || row.level !== level) {
				row = this.buildRow(level);
				this.rows.set(level.id, row);
			} else {
				this.renderSuggest(row); // the label depends on the view
			}
			this.observer.observe(row);
			return row;
		});
		this.list.replaceChildren(...rows);
		this.list.classList.toggle('reorder', this.view === 'playlist');
		this.hint.textContent =
			this.view === 'playlist' && !this.canReorder && pool.length > 1
				? 'Clear the search to reorder.'
				: this.view === 'playlist'
				? 'Shared by all viewers; the player sees it in Beat Saber as “Suggested by viewers”, in this order, and levels leave it once played. Drag ⠿ or use the arrows to reorder.'
				: 'Add levels to the playlist to suggest them to the player.';
	}

	buildRow(level) {
		const row = el('li', 'lbLevel');
		row.level = level;

		const handle = el('div', 'lbHandle');
		handle.title = 'Drag to reorder';
		handle.setAttribute('aria-hidden', 'true');
		handle.addEventListener('pointerdown', e => this.startDrag(e, row));
		handle.addEventListener('click', e => e.stopPropagation());

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

		const suggested = el('div', 'lbSuggested');

		const actions = el('div', 'lbActions');
		const play = el('button', 'lbPlay', 'Preview');
		play.type = 'button';
		play.disabled = !level.hasAudio;
		play.title = level.hasAudio ? 'Listen to the preview section' : 'No song file';
		play.addEventListener('click', e => {
			e.stopPropagation();
			this.togglePreview(level, row);
		});
		// All labels share one grid cell, so the button is as wide as the longest and doesn't jump when toggled.
		const suggest = el('button', 'lbSuggest');
		suggest.type = 'button';
		for (const [state, label] of [
			['add', 'Add to playlist'],
			['on', '✓ In playlist'],
			['remove', 'Remove'],
		]) {
			const span = el('span', null, label);
			span.dataset.state = state;
			suggest.append(span);
		}
		suggest.addEventListener('click', e => {
			e.stopPropagation();
			this.toggleSuggestion(level.id);
		});
		actions.append(play, suggest);
		const order = el('div', 'lbOrder');
		const orderButtons = {};
		for (const [key, icon, text, title, index] of [
			['top', '⤒', 'Top', 'Move to the top', () => 0],
			['up', '▲', '', 'Move up', i => i - 1],
			['down', '▼', '', 'Move down', i => i + 1],
			['bottom', '⤓', 'Bottom', 'Move to the bottom', () => this.suggestions.length - 1],
		]) {
			const b = el('button', `lbMove lbMove-${key}`, icon);
			if (text) b.append(el('span', 'lbMoveText', ` ${text}`));
			b.type = 'button';
			b.title = title;
			b.setAttribute('aria-label', title);
			b.addEventListener('click', e => {
				e.stopPropagation();
				const i = this.suggestions.findIndex(s => s.id === level.id);
				if (i >= 0) this.moveSuggestion(level.id, index(i));
			});
			orderButtons[key] = b;
			order.append(b);
		}
		actions.append(order);
		if (level.missing) play.hidden = true;
		main.append(suggested);
		const progress = el('div', 'lbProgress');

		const details = el('div', 'lbDetails');
		details.hidden = true;

		row.append(handle, cover, main, actions, progress, details);
		row.addEventListener('click', () => {
			if (level.missing) return;
			details.hidden = !details.hidden;
			row.classList.toggle('expanded', !details.hidden);
			if (!details.hidden) this.renderDetails(level, details);
		});
		row.refs = {img, chips, play, suggest, suggested, progress, details, handle, order, orderButtons};
		this.renderChips(level, row);
		this.renderSuggest(row);
		return row;
	}

	renderSuggest(row) {
		const {suggest, suggested} = row.refs;
		const entry = this.suggestion(row.level.id);
		const pending = this.pending.has(row.level.id);
		suggest.disabled = pending;
		suggest.classList.toggle('on', !!entry);
		suggest.dataset.state = entry ? (this.view === 'playlist' ? 'remove' : 'on') : 'add';
		suggest.title = entry ? 'Remove from the playlist' : 'Suggest this level to the player: adds it to the shared playlist, which shows up in Beat Saber';
		suggested.textContent = entry ? `Added by ${entry.by || 'a viewer'}, ${formatAgo(entry.added)}` : '';
		suggested.hidden = !entry;

		const {order, orderButtons} = row.refs;
		const index = this.suggestions.indexOf(entry);
		const reorder = this.view === 'playlist' && !!entry;
		order.hidden = !reorder;
		row.classList.toggle('reorderable', reorder && this.canReorder);
		const last = this.suggestions.length - 1;
		const off = !this.canReorder;
		orderButtons.top.disabled = orderButtons.up.disabled = off || index <= 0;
		orderButtons.bottom.disabled = orderButtons.down.disabled = off || index >= last;
	}

	// ---- dragging suggestions (pointer events: mouse, touch and pen) ----

	startDrag(e, row) {
		if (!this.canReorder || this.drag || (e.pointerType === 'mouse' && e.button !== 0)) return;
		e.preventDefault();
		const rows = [...this.list.children];
		const indicator = el('div', 'lbDropLine');
		this.list.append(indicator);
		this.drag = {row, id: row.level.id, pointerId: e.pointerId, startY: e.clientY, y: e.clientY, startScroll: this.list.scrollTop, rows, indicator, target: rows.indexOf(row), raf: 0};
		row.classList.add('dragging');
		row.refs.handle.setPointerCapture(e.pointerId);
		const move = ev => {
			if (ev.pointerId !== this.drag.pointerId) return;
			this.drag.y = ev.clientY;
			this.updateDrag();
		};
		const end = ev => {
			if (ev.pointerId !== this.drag.pointerId) return;
			row.refs.handle.removeEventListener('pointermove', move);
			row.refs.handle.removeEventListener('pointerup', end);
			row.refs.handle.removeEventListener('pointercancel', end);
			this.endDrag(ev.type === 'pointerup');
		};
		row.refs.handle.addEventListener('pointermove', move);
		row.refs.handle.addEventListener('pointerup', end);
		row.refs.handle.addEventListener('pointercancel', end);
		// Scrolls the list while the pointer is near its top or bottom edge.
		const scroll = () => {
			const d = this.drag;
			if (!d) return;
			const box = this.list.getBoundingClientRect();
			const edge = 48;
			const speed = d.y < box.top + edge ? -(box.top + edge - d.y) : d.y > box.bottom - edge ? d.y - (box.bottom - edge) : 0;
			if (speed) {
				this.list.scrollTop += Math.max(-24, Math.min(24, speed / 2));
				this.updateDrag();
			}
			d.raf = requestAnimationFrame(scroll);
		};
		this.drag.raf = requestAnimationFrame(scroll);
		this.updateDrag();
	}

	updateDrag() {
		const d = this.drag;
		const listBox = this.list.getBoundingClientRect();
		d.row.style.transform = `translateY(${d.y - d.startY + this.list.scrollTop - d.startScroll}px)`;
		// The new position is the number of other rows whose middle is above the pointer.
		const others = d.rows.filter(r => r !== d.row);
		let target = 0;
		for (const r of others) {
			const box = r.getBoundingClientRect();
			if (box.top + box.height / 2 < d.y) target++;
		}
		d.target = target;
		const ref = others[target] || others[others.length - 1];
		let y = 0;
		if (ref) {
			const box = ref.getBoundingClientRect();
			y = (target < others.length ? box.top : box.bottom) - listBox.top + this.list.scrollTop;
		}
		d.indicator.style.top = `${y - 1}px`;
	}

	endDrag(drop) {
		const d = this.drag;
		cancelAnimationFrame(d.raf);
		d.row.classList.remove('dragging');
		d.row.style.transform = '';
		d.indicator.remove();
		this.drag = null;
		const deferred = this.deferredSuggestions;
		this.deferredSuggestions = null;
		if (deferred) this.setSuggestions(deferred);
		if (drop) this.moveSuggestion(d.id, d.target);
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
			if (this.statsEnabled && !level.missing && !this.stats.has(level.id)) {
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
		// The Web Audio fallback for browsers without Ogg (old Safari) also needs the gesture to start its context.
		const context = this.audioContext();
		const preview = {level, row, audio, context, url: null, timer: null, source: null};
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
		if (isOgg(buffer) && !canPlayOgg()) {
			this.playDecoded(preview, buffer, begin, length, volume);
			return;
		}
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
			if (isOgg(buffer) && !preview.triedDecoding) {
				// Partial Ogg support (Safari before 18.4 on some systems): decode it ourselves instead.
				preview.triedDecoding = true;
				clearTimeout(preview.timer);
				audio.removeAttribute('src');
				this.playDecoded(preview, buffer, begin, length, volume);
				return;
			}
			this.stopPreview();
			row.refs.play.title = "This browser can't play the song file";
		});
		audio.src = preview.url;
		this.showPlaying(row);

		// Fade in, play the preview section, fade out.
		const tick = () => {
			if (this.preview !== preview || preview.triedDecoding) return;
			const t = audio.currentTime - begin;
			const fade = Math.min(1, Math.max(0, t / FADE_S), Math.max(0, (length - t) / FADE_S));
			audio.volume = volume * fade;
			row.refs.progress.style.width = `${Math.min(100, Math.max(0, (t / length) * 100))}%`;
			if (t >= length) this.stopPreview();
			else preview.timer = setTimeout(tick, 50);
		};
		tick();
	}

	audioContext() {
		if (!this.context) this.context = new (window.AudioContext || window.webkitAudioContext)();
		this.context.resume().catch(() => {});
		return this.context;
	}

	showPlaying(row) {
		row.classList.add('playing');
		row.refs.play.textContent = 'Stop';
		row.refs.play.title = 'Stop the preview';
	}

	/** Plays the preview section through Web Audio, decoding the song with the WebAssembly fallback if needed. */
	async playDecoded(preview, buffer, begin, length, volume) {
		const {row, context} = preview;
		row.classList.add('loading');
		let song;
		try {
			song = await decodeAudio(context, buffer);
		} catch (e) {
			if (this.preview === preview) this.stopPreview();
			row.refs.play.title = `Couldn't decode the song (${e.message})`;
			return;
		} finally {
			row.classList.remove('loading');
		}
		if (this.preview !== preview) return;

		begin = Math.min(begin, Math.max(0, song.duration - length));
		const gain = context.createGain();
		gain.connect(context.destination);
		const source = context.createBufferSource();
		source.buffer = song;
		source.connect(gain);
		// Fade in, play the preview section, fade out, all scheduled on the audio clock.
		const start = context.currentTime + 0.05;
		gain.gain.setValueAtTime(0, start);
		gain.gain.linearRampToValueAtTime(volume, start + FADE_S);
		gain.gain.setValueAtTime(volume, start + Math.max(FADE_S, length - FADE_S));
		gain.gain.linearRampToValueAtTime(0, start + length);
		source.start(start, begin, length);
		source.onended = () => this.preview === preview && this.stopPreview();
		preview.source = source;
		preview.gain = gain;
		this.showPlaying(row);

		const tick = () => {
			if (this.preview !== preview) return;
			const t = context.currentTime - start;
			row.refs.progress.style.width = `${Math.min(100, Math.max(0, (t / length) * 100))}%`;
			preview.timer = setTimeout(tick, 50);
		};
		tick();
	}

	stopPreview() {
		const preview = this.preview;
		if (!preview) return;
		this.preview = null;
		clearTimeout(preview.timer);
		if (preview.source) {
			preview.source.onended = null;
			try {
				preview.source.stop();
			} catch (e) {
				// Already ended.
			}
			preview.gain.disconnect();
		}
		preview.audio.pause();
		preview.audio.removeAttribute('src');
		if (preview.url) URL.revokeObjectURL(preview.url);
		preview.row.classList.remove('playing', 'loading');
		preview.row.refs.progress.style.width = '0';
		preview.row.refs.play.textContent = 'Preview';
		if (preview.row.refs.play.title === 'Stop the preview') preview.row.refs.play.title = 'Listen to the preview section';
	}
}
