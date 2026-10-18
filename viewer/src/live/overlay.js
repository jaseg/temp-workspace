// DOM overlay for live mode: the name and "Request to watch" screen, waiting room, connection state, song state and a
// latency readout.
import {loadName, saveName, tidyName, randomName, MAX_NAME_LENGTH} from './name';
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
				<form class="liveRequestForm" hidden>
					<label class="liveNameLabel" for="liveNameInput">Your name</label>
					<input id="liveNameInput" class="liveNameInput" type="text" autocomplete="nickname" spellcheck="false">
					<button class="liveRequest" type="submit">Request to watch</button>
				</form>
			</div>
			<div class="liveStats" hidden></div>`;
		document.body.appendChild(root);
		this.root = root;
		this.card = root.querySelector('.liveCard');
		this.title = root.querySelector('.liveTitle');
		this.code = root.querySelector('.liveCode');
		this.hint = root.querySelector('.liveHint');
		this.statsEl = root.querySelector('.liveStats');
		this.requestForm = root.querySelector('.liveRequestForm');
		this.nameInput = root.querySelector('.liveNameInput');
		this.nameInput.maxLength = MAX_NAME_LENGTH;
		this.requestButton = root.querySelector('.liveRequest');
		this.connectionState = 'idle';

		document.addEventListener('keydown', e => {
			const typing = e.target.closest && e.target.closest('input, textarea, select');
			if (e.key === 'l' && !e.ctrlKey && !e.metaKey && !e.altKey && !typing) {
				this.statsEl.hidden = !this.statsEl.hidden;
			}
		});
	}

	render(title, hint = '', name = null) {
		this.title.textContent = title;
		this.hint.textContent = hint;
		this.code.hidden = !name;
		// One box per word, so a long name wraps between words on narrow screens.
		this.code.replaceChildren();
		(name || '').split(' ').forEach((word, i) => {
			if (i) this.code.append(' ');
			const span = document.createElement('span');
			span.textContent = word;
			this.code.append(span);
		});
		this.card.hidden = !title;
	}

	/**
	 * First screen: the viewer enters a name and asks to watch. The field suggests two random words as a greyed-out
	 * placeholder, so typing replaces them; a name typed before is filled in. The click (or Enter) is also the user
	 * gesture browsers require before a page may play audio, so the song can be heard as soon as playback starts.
	 */
	showRequest(onRequest) {
		this.render('Watch live', 'The player lets new viewers in from Beat Saber, by name.');
		this.nameInput.placeholder = randomName();
		this.nameInput.value = loadName();
		this.requestForm.hidden = false;
		this.nameInput.focus();
		this.requestForm.addEventListener(
			'submit',
			e => {
				e.preventDefault();
				const typed = tidyName(this.nameInput.value);
				saveName(typed);
				this.requestForm.hidden = true;
				onRequest(typed || this.nameInput.placeholder);
			},
			{once: true}
		);
	}

	setConnectionState(state, detail) {
		this.connectionState = state;
		if (state === 'waiting') {
			this.render(STATE_TEXT.waiting, 'The player sees this name in the Live Viewer menu in Beat Saber.', detail.name);
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
