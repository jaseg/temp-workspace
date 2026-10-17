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
				<button class="liveRequest" type="button" hidden>Request to watch</button>
			</div>
			<div class="liveStats" hidden></div>`;
		document.body.appendChild(root);
		this.root = root;
		this.card = root.querySelector('.liveCard');
		this.title = root.querySelector('.liveTitle');
		this.code = root.querySelector('.liveCode');
		this.hint = root.querySelector('.liveHint');
		this.statsEl = root.querySelector('.liveStats');
		this.requestButton = root.querySelector('.liveRequest');
		this.connectionState = 'idle';

		document.addEventListener('keydown', e => {
			const typing = e.target.closest && e.target.closest('input, textarea, select');
			if (e.key === 'l' && !e.ctrlKey && !e.metaKey && !e.altKey && !typing) {
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

	/**
	 * First screen: the viewer asks to watch with a click. The click is also the user gesture browsers require
	 * before a page may play audio, so the song can be heard as soon as playback starts.
	 */
	showRequest(onRequest) {
		this.render('Watch live', 'The player approves new viewers in Beat Saber.');
		this.requestButton.hidden = false;
		this.requestButton.focus();
		this.requestButton.addEventListener(
			'click',
			() => {
				this.requestButton.hidden = true;
				onRequest();
			},
			{once: true}
		);
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
