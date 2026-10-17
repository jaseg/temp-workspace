// DOM overlay for live mode: waiting room, connection state, song state and a latency readout.
require('./live.styl');

const STATE_TEXT = {
	connecting: 'Connecting to Beat Saber…',
	waiting: 'Waiting for approval',
	approved: 'Connected',
	denied: 'Not allowed. Reload the page to ask again.',
	revoked: 'Access was revoked. Reload the page to ask again.',
	disconnected: 'Connection lost, reconnecting…',
};

const END_TEXT = {
	cleared: 'Song cleared',
	failed: 'Song failed',
	quit: 'Song left',
	restarted: 'Song restarting…',
	idle: 'Waiting for the next song',
	disconnected: 'Connection lost',
	ended: 'Song ended',
};

export class LiveOverlay {
	constructor() {
		const root = document.createElement('div');
		root.id = 'liveOverlay';
		root.innerHTML = `
			<div class="liveCard">
				<div class="liveTitle"></div>
				<div class="liveCode" hidden></div>
				<div class="liveHint"></div>
			</div>
			<div class="liveStats" hidden></div>`;
		document.body.appendChild(root);
		document.body.classList.add('liveMode');
		this.root = root;
		this.card = root.querySelector('.liveCard');
		this.title = root.querySelector('.liveTitle');
		this.code = root.querySelector('.liveCode');
		this.hint = root.querySelector('.liveHint');
		this.statsEl = root.querySelector('.liveStats');
		this.connectionState = 'connecting';
		this.render(STATE_TEXT.connecting);

		document.addEventListener('keydown', e => {
			if (e.key === 'l' && !e.ctrlKey && !e.metaKey && !e.altKey && e.target === document.body) {
				this.statsEl.hidden = !this.statsEl.hidden;
			}
		});
	}

	render(title, hint = '', code = null) {
		this.title.textContent = title;
		this.hint.textContent = hint;
		this.code.hidden = !code;
		this.code.textContent = code || '';
		this.card.hidden = !title;
	}

	setConnectionState(state, detail) {
		this.connectionState = state;
		if (state === 'waiting') {
			this.render(STATE_TEXT.waiting, 'Ask the player to allow this code in the Live Viewer menu in Beat Saber.', detail.code);
		} else if (state === 'approved') {
			this.render(this.session ? '' : END_TEXT.idle);
		} else {
			this.render(STATE_TEXT[state] || state);
		}
	}

	setSession(info) {
		this.session = info;
		this.render('');
	}

	setEnded(reason, info) {
		this.session = null;
		const song = info ? `${info.songName} (${info.difficulty})` : '';
		this.render(END_TEXT[reason] || END_TEXT.ended, reason === 'idle' ? '' : song);
	}

	setIdle(reason) {
		if (this.connectionState === 'approved') this.render(END_TEXT[reason] || END_TEXT.idle);
	}

	showStats(lines) {
		if (!this.statsEl.hidden) this.statsEl.textContent = lines.join('\n');
	}
}
