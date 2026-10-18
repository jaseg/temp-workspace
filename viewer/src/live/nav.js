// Top bar: switches between the live view, the level list and the shared playlist (both in the level browser).
// Shown once the device is approved, since the level browser needs an approved connection.
require('./nav.styl');

export class LiveNav {
	constructor(levels) {
		this.levels = levels;
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
		this.badge = document.createElement('span');
		this.badge.className = 'navBadge';
		this.badge.title = 'Levels in the playlist';
		this.playlistButton.append(this.badge);
		root.append(this.liveButton, this.levelsButton, this.playlistButton);
		document.body.appendChild(root);
		this.root = root;
		levels.onChange = () => this.update();
		this.update();
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
	}
}
