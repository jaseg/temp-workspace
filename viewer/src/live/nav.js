// Top bar: switches between the live view, the level list and the shared playlist (both in the level browser), and
// shows the viewer's name, which can be changed with a click. Shown once the device is approved, since the level
// browser needs an approved connection.
import {saveName, tidyName, MAX_NAME_LENGTH} from './name';
require('./nav.styl');

export class LiveNav {
	constructor(levels, connection) {
		this.levels = levels;
		this.connection = connection;
		const root = document.createElement('nav');
		root.id = 'liveNav';
		root.hidden = true;
		root.setAttribute('aria-label', 'Views');
		this.liveButton = this.button('Live', () => levels.close());
		this.liveDot = document.createElement('span');
		this.liveDot.className = 'navDot';
		this.liveDot.title = 'A song is being played';
		this.liveButton.prepend(this.liveDot);
		this.levelsButton = this.button('Levels', () => levels.show('levels'));
		this.playlistButton = this.button('Playlist', () => levels.show('playlist'));
		this.levelsBadge = this.addBadge(this.levelsButton, 'Installed levels');
		this.badge = this.addBadge(this.playlistButton, 'Levels in the playlist');
		root.append(this.liveButton, this.levelsButton, this.playlistButton, this.buildName());
		document.body.appendChild(root);
		this.root = root;
		levels.onChange = () => this.update();
		this.update();
	}

	buildName() {
		const wrap = document.createElement('div');
		wrap.className = 'navName';
		this.nameButton = this.button('', () => this.editName());
		this.nameButton.title = 'Your name. Click to change it';
		const icon = document.createElement('i');
		icon.className = 'fas fa-user';
		this.nameText = document.createElement('span');
		this.nameButton.append(icon, this.nameText);

		this.nameForm = document.createElement('form');
		this.nameForm.hidden = true;
		this.nameInput = document.createElement('input');
		this.nameInput.type = 'text';
		this.nameInput.maxLength = MAX_NAME_LENGTH;
		this.nameInput.spellcheck = false;
		this.nameInput.setAttribute('aria-label', 'Your name');
		this.nameForm.append(this.nameInput);
		this.nameForm.addEventListener('submit', e => {
			e.preventDefault();
			this.commitName();
		});
		this.nameInput.addEventListener('blur', () => this.commitName());
		this.nameInput.addEventListener('keydown', e => {
			if (e.key === 'Escape') this.endEdit();
			e.stopPropagation(); // typing here isn't for the scene's hotkeys
		});
		wrap.append(this.nameButton, this.nameForm);
		return wrap;
	}

	/** The name the mod uses for this viewer. */
	setName(name) {
		this.name = name;
		this.nameText.textContent = name;
	}

	editName() {
		this.nameInput.value = this.name || '';
		this.nameButton.hidden = true;
		this.nameForm.hidden = false;
		this.nameInput.focus();
		this.nameInput.select();
	}

	commitName() {
		if (this.nameForm.hidden) return;
		const name = tidyName(this.nameInput.value);
		if (name && name !== this.name && this.connection.rename(name)) {
			saveName(name);
			this.setName(name); // the mod's answer replaces it with the cleaned-up name
		}
		this.endEdit();
	}

	endEdit() {
		this.nameForm.hidden = true;
		this.nameButton.hidden = false;
	}

	addBadge(button, title) {
		const badge = document.createElement('span');
		badge.className = 'navBadge';
		badge.title = title;
		badge.hidden = true;
		button.append(badge);
		return badge;
	}

	button(label, onClick) {
		const b = document.createElement('button');
		b.type = 'button';
		b.textContent = label;
		b.addEventListener('click', onClick);
		return b;
	}

	setAvailable(available) {
		this.root.hidden = !available;
	}

	/** A song is being played (shown as a dot on "Live"). */
	setLive(live) {
		this.liveDot.hidden = !live;
	}

	update() {
		const open = this.levels.isOpen;
		this.liveButton.setAttribute('aria-pressed', String(!open));
		this.levelsButton.setAttribute('aria-pressed', String(open && this.levels.view === 'levels'));
		this.playlistButton.setAttribute('aria-pressed', String(open && this.levels.view === 'playlist'));
		const count = this.levels.suggestionCount;
		this.badge.textContent = count ? String(count) : '';
		this.badge.hidden = !count;
		const levels = this.levels.levels.length;
		this.levelsBadge.textContent = levels ? String(levels) : '';
		this.levelsBadge.hidden = !levels;
	}
}
