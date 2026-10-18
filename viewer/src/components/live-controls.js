const utils = require('../utils');

const NoSleep = require('nosleep.js');
const noSleep = new NoSleep();

const deviceHasTouchScreen = utils.hasTouchScreen();

// Hotkeys are ignored while typing into a form control.
const isTyping = e => e.target.closest && e.target.closest('input, textarea, select');

// The game's modifier codes, as the session lists them.
const MODIFIER_NAMES = {
	DA: 'Disappearing Arrows',
	FS: 'Faster Song',
	SS: 'Slower Song',
	SF: 'Super Fast Song',
	GN: 'Ghost Notes',
	NA: 'No Arrows',
	NB: 'No Bombs',
	NF: 'No Fail',
	NO: 'No Walls',
	SA: 'Strict Angles',
	SC: 'Small Notes',
	PM: 'Pro Mode',
	CS: 'Fail on Saber Clash',
	IF: 'One Life',
	BE: 'Four Lives',
};

const DIFFICULTIES = {
	Easy: {name: 'Easy', color: 'MediumSeaGreen'},
	Normal: {name: 'Normal', color: '#59b0f4'},
	Hard: {name: 'Hard', color: 'tomato'},
	Expert: {name: 'Expert', color: '#bf2a42'},
	ExpertPlus: {name: 'Expert+', color: '#8f48db'},
};

function formatSeconds(time) {
	const hrs = ~~(time / 3600);
	const mins = ~~((time % 3600) / 60);
	const secs = ~~time % 60;
	let ret = '';
	if (hrs > 0) {
		ret += '' + hrs + ':' + (mins < 10 ? '0' : '');
	}
	return ret + mins + ':' + (secs < 10 ? '0' : '') + secs;
}

/**
 * The 2D UI around the scene in live mode: song and player info, elapsed time, volume, camera and settings
 * panels, fullscreen and hotkeys. Live play has no seeking, speed control or pausing.
 */
AFRAME.registerComponent('live-controls', {
	dependencies: ['song'],

	schema: {
		isPlaying: {default: false},
		showControls: {default: true},
	},

	init: function () {
		this.song = this.el.components.song;
		this.settings = this.el.components.settings;
		this.hitSound = this.el.components['beat-hit-sound'];
		this.tick = AFRAME.utils.throttleTick(this.tick.bind(this), 100);
		this.songProgress = document.getElementById('songProgress');

		document.getElementById('audioAnalyser').addEventListener('audioanalysersource', evt => {
			document.getElementById('songDuration').textContent = formatSeconds(evt.detail.duration);
		});

		this.el.sceneEl.addEventListener('challengeloadend', evt => this.showSongInfo(evt.detail));
		this.el.sceneEl.addEventListener('userloaded', evt => {
			const name = document.getElementById('playerName');
			name.textContent = evt.detail.name;
			name.setAttribute('title', evt.detail.name);
			document.getElementById('playerInfoOverlay').style.display = 'flex';
		});

		this.el.addEventListener('spawnRotationChanged', event => {
			['scoreContainer', 'lightFixture'].forEach(id => {
				const container = document.getElementById(id);
				container.setAttribute('animation__rotationY', 'from', event.detail.oldSpawnRotation);
				container.setAttribute('animation__rotationY', 'to', event.detail.spawnRotation);
				container.emit('spawnRotationStart', null, false);
			});
		});
	},

	update: function (oldData) {
		const data = this.data;
		document.body.classList.toggle('isPlaying', data.isPlaying);
		document.body.classList.toggle('showControls', data.showControls);
		if (deviceHasTouchScreen && data.isPlaying !== oldData.isPlaying) {
			// Keep the phone's screen on while a song plays.
			if (data.isPlaying) noSleep.enable();
			else noSleep.disable();
		}
	},

	play: function () {
		this.setupPanels();
		this.setupTabs();
		this.setupVolumeControls();
		this.setupOrthoCameraControls();
		this.setupFullscreen();
		this.setupJumpDistance();
		this.setupHitsounds();
		this.setupSettingsFiles();

		document.querySelectorAll('.povswitch').forEach(button => {
			// Don't take focus away from the scene (keyboard shortcuts).
			button.addEventListener('mousedown', e => e.preventDefault());
		});

		document.addEventListener('keydown', e => {
			if (isTyping(e)) return;
			if (e.keyCode === 72) {
				// h
				this.data.showControls = !this.data.showControls;
				document.body.classList.toggle('showControls', this.data.showControls);
				this.el.sceneEl.emit('showHotkeyNotification', {
					text: this.data.showControls ? 'Controls: Visible' : 'Controls: Hidden',
					icon: this.data.showControls ? 'fas fa-eye' : 'fas fa-eye-slash',
				});
			}
		});
	},

	tick: function () {
		if (this.song.isPlaying) {
			this.songProgress.textContent = formatSeconds(this.song.getCurrentTime());
		}
	},

	showSongInfo: function (challenge) {
		const info = challenge.info;
		// The controls bar appears once there is a song.
		document.getElementById('controls').classList.add('challengeLoaded');
		// The live session sets the cover itself, once it has loaded (see LiveSession.loadCover).
		if (challenge.image) document.getElementById('songImage').src = challenge.image;
		const name = document.getElementById('songName');
		name.textContent = info._songName;
		name.setAttribute('title', info._songName);
		const subName = document.getElementById('songSubName');
		subName.textContent = info._songSubName || info._songAuthorName || '';
		subName.setAttribute('title', subName.textContent);

		const difficulty = DIFFICULTIES[challenge.difficulty] || {name: challenge.difficulty, color: 'grey'};
		const difficultyEl = document.getElementById('songDifficulty');
		difficultyEl.textContent = difficulty.name;
		difficultyEl.setAttribute('title', difficulty.name);
		difficultyEl.style.backgroundColor = difficulty.color;

		// Mappers' own label for the difficulty, if any.
		const set = (info._difficultyBeatmapSets || []).find(s => s._beatmapCharacteristicName === challenge.mode);
		const beatmap = set && set._difficultyBeatmaps.find(d => d._difficulty === challenge.difficulty);
		const customLabel = beatmap && beatmap._customData && beatmap._customData._difficultyLabel;
		const customEl = document.getElementById('songCustomDifficulty');
		customEl.textContent = customLabel || '';
		customEl.setAttribute('title', customLabel || '');

		const modeEl = document.getElementById('songMode');
		modeEl.textContent = challenge.mode;
		modeEl.style.display = challenge.mode !== 'Standard' ? 'block' : 'none';

		const replay = this.el.sceneEl.components['replay-loader'].replay;
		const modifiers = replay && replay.info.modifiers ? replay.info.modifiers.split(',') : [];
		document.getElementById('modifiers').textContent = modifiers.map(m => MODIFIER_NAMES[m] || m).join(', ');
		document.getElementById('songInfoOverlay').style.display = 'flex';

		this.applyEnvironmentRemoval(challenge);
	},

	// Maps can switch off parts of the environment; apply that for this song without saving it.
	applyEnvironmentRemoval: function (challenge) {
		const customData = challenge.customData && challenge.customData[challenge.mode][challenge.difficulty];
		const removal = customData && customData._environmentRemoval;
		if (!removal) return;

		const settings = this.settings.settings;
		removal.forEach(element => {
			switch (element) {
				case 'Spectrograms':
					settings.showAudioColumns = false;
					break;
				case 'Floor':
					settings.showFloor = false;
					break;
				case 'TrackLaneRing':
					settings.showTwister = false;
					break;
				case 'BackColumns':
					settings.showLasers = false;
					settings.showPlatform = false;
					break;
				case 'Frame':
					settings.showHud = false;
					break;
			}
		});
		this.el.sceneEl.emit('settingsChanged', {settings}, false);
	},

	// Volume, settings, camera and (on phones) "more" panels: toggled by their buttons, closed by clicking elsewhere.
	setupPanels: function () {
		const panels = [
			{panel: '#volumeSliderContainer', button: '#controlsVolume', active: 'volumeActive'},
			{panel: '#settingsContainer', button: '.controlsSettings', active: 'settingsActive'},
			{panel: '#cameraSettingsContainer', button: '.controlsCamera', active: 'settingsActive'},
			{panel: '#mobileContainer', button: '.controlsMobile', active: 'settingsActive'},
		];
		panels.forEach(({panel, button, active}) => {
			const panelEl = document.querySelector(panel);
			document.querySelectorAll(button).forEach(el => el.addEventListener('click', () => panelEl.classList.toggle(active)));
			document.addEventListener('click', evt => {
				if (!evt.target.closest(panel) && !evt.target.closest(button)) {
					panelEl.classList.remove(active);
				}
			});
		});
	},

	// Tab bars in the settings and camera panels (`data-tabs` containers): buttons and panes pair by position.
	setupTabs: function () {
		document.querySelectorAll('[data-tabs]').forEach(container => {
			const buttons = Array.from(container.querySelector('.tab-buttons').children);
			const panes = Array.from(container.querySelector('.tab-content').children);
			buttons.forEach((button, index) => {
				button.addEventListener('click', () => {
					buttons.forEach((b, i) => {
						b.classList.toggle('active', i === index);
						panes[i].classList.toggle('active', i === index);
					});
				});
			});
		});
	},

	setupVolumeControls: function () {
		const volumeSlider = document.getElementById('volumeSlider');
		const hitsoundSlider = document.getElementById('hitsoundSlider');
		const musicSlider = document.getElementById('musicSlider');
		const mixerButton = document.getElementById('mixer');
		const mixerContainer = document.getElementById('mixerContainer');
		const settings = this.settings;

		const volumeHandler = () => {
			const gainNode = this.song.audioAnalyser.gainNode;
			if (gainNode) {
				gainNode.gain.cancelScheduledValues(0);
				gainNode.gain.value = musicSlider.value;
			}
			settings.settings.volume = musicSlider.value;
			settings.settings.hitSoundVolume = hitsoundSlider.value;
			settings.sync();
			this.hitSound.setVolume(hitsoundSlider.value);
		};

		// The master slider keeps the music/hitsound ratio set in the mixer.
		const masterVolumeHandler = () => {
			hitsoundSlider.value = volumeSlider.value * this.soundRatio;
			musicSlider.value = volumeSlider.value;
			volumeHandler();
		};
		const updateRatio = () => {
			this.soundRatio = hitsoundSlider.value / Math.max(musicSlider.value, 0.01);
		};

		volumeSlider.addEventListener('input', masterVolumeHandler);
		musicSlider.addEventListener('input', () => {
			volumeSlider.value = musicSlider.value;
			updateRatio();
			volumeHandler();
		});
		hitsoundSlider.addEventListener('input', () => {
			updateRatio();
			volumeHandler();
		});

		volumeSlider.value = settings.settings.volume;
		musicSlider.value = settings.settings.volume;
		hitsoundSlider.value = settings.settings.hitSoundVolume;
		updateRatio();

		[volumeSlider, hitsoundSlider, musicSlider].forEach(el => {
			el.addEventListener('wheel', e => {
				if (e.deltaY < 0) {
					el.valueAsNumber += 0.05;
				} else {
					el.valueAsNumber -= 0.05;
				}
				if (el === volumeSlider) {
					masterVolumeHandler();
				} else {
					volumeHandler();
				}
				e.preventDefault();
				e.stopPropagation();
			});
		});

		const showMixer = mixed => {
			mixerButton.classList.toggle('selected', mixed);
			volumeSlider.classList.toggle('volumeHide', mixed);
			mixerContainer.classList.toggle('volumeHide', !mixed);
		};
		mixerButton.addEventListener('click', () => {
			settings.settings.volumeMixed = !settings.settings.volumeMixed;
			settings.sync();
			showMixer(settings.settings.volumeMixed);
		});
		showMixer(!!settings.settings.volumeMixed);

		let mutedVolume = null;
		let mutedHitsoundVolume = null;
		document.addEventListener('keydown', e => {
			if (isTyping(e)) return;
			const notify = (text, icon) => this.el.sceneEl.emit('showHotkeyNotification', {text, icon});
			if (e.keyCode === 38) {
				// up
				volumeSlider.valueAsNumber += e.shiftKey ? 0.025 : 0.05;
				masterVolumeHandler();
				notify(`Volume: ${Math.round(volumeSlider.value * 100)}%`, 'fas fa-volume-up');
			} else if (e.keyCode === 40) {
				// down
				volumeSlider.valueAsNumber -= e.shiftKey ? 0.025 : 0.05;
				masterVolumeHandler();
				notify(`Volume: ${Math.round(volumeSlider.value * 100)}%`, 'fas fa-volume-down');
			} else if (e.keyCode === 77 && !e.ctrlKey) {
				// m
				if (mutedVolume === null) {
					mutedVolume = volumeSlider.value;
					mutedHitsoundVolume = hitsoundSlider.value;
					volumeSlider.valueAsNumber = 0;
					hitsoundSlider.valueAsNumber = 0;
					musicSlider.valueAsNumber = 0;
					notify('Muted', 'fas fa-volume-mute');
				} else {
					volumeSlider.value = mutedVolume;
					musicSlider.value = mutedVolume;
					hitsoundSlider.value = mutedHitsoundVolume;
					mutedVolume = null;
					notify('Unmuted', 'fas fa-volume-up');
				}
				volumeHandler();
			}
		});
	},

	setupOrthoCameraControls: function () {
		const cameraToggles = {};
		let fullscreenCamera = 'Main';
		['Back', 'Right', 'Top', 'Main'].forEach(key => (cameraToggles[key] = document.getElementById('orthographic' + key + 'Fullscreen')));
		const updateToggles = () => {
			Object.keys(cameraToggles).forEach(key => {
				const toggle = cameraToggles[key];
				toggle.style.display = this.settings.settings['orthographic' + key + 'Enabled'] ? 'block' : 'none';
				toggle.classList.toggle('inFullscreen', fullscreenCamera === key);
				if (key !== 'Main') {
					const camera = this.el.sceneEl.querySelectorAll('.orthographic' + key)[0];
					if (camera.components) {
						camera.setAttribute('orthographic-camera', 'fullscreen', fullscreenCamera === key);
					}
				} else {
					['.mainCamera', '.povCamera'].forEach(selector => {
						const camera = this.el.sceneEl.querySelectorAll(selector)[0];
						if (camera.components) {
							camera.components.camera.data.fullscreen = fullscreenCamera === key;
						}
					});
					toggle.style.display = fullscreenCamera !== key ? 'block' : 'none';
				}
			});
		};
		this.el.sceneEl.addEventListener('settingsChanged', () => {
			if (fullscreenCamera !== 'Main' && !this.settings.settings['orthographic' + fullscreenCamera + 'Enabled']) {
				fullscreenCamera = 'Main';
			}
			updateToggles();
		});
		updateToggles();
		Object.keys(cameraToggles).forEach(key => {
			cameraToggles[key].addEventListener('click', () => {
				fullscreenCamera = fullscreenCamera === key ? 'Main' : key;
				updateToggles();
			});
		});
	},

	setupFullscreen: function () {
		const buttons = document.querySelectorAll('.controlsFullscreen');
		const show = inFullscreen => {
			buttons.forEach(button => {
				button.classList.toggle('inFullscreen', inFullscreen);
				button.title = inFullscreen ? 'Exit fullscreen (f)' : 'Enter fullscreen (f)';
			});
		};
		const toggle = () => {
			const inFullscreen = document.fullscreenElement || document.webkitFullscreenElement;
			if (inFullscreen) {
				(document.exitFullscreen || document.webkitExitFullscreen).call(document);
			} else {
				const request = document.body.requestFullscreen || document.body.webkitRequestFullscreen;
				if (request) {
					Promise.resolve(request.call(document.body)).catch(() => {});
				}
			}
		};
		buttons.forEach(button => button.addEventListener('click', toggle));
		document.addEventListener('fullscreenchange', () => show(!!document.fullscreenElement));
		document.addEventListener('webkitfullscreenchange', () => show(!!document.webkitFullscreenElement));
		document.addEventListener('keydown', e => {
			if (!isTyping(e) && e.keyCode === 70 && !e.shiftKey) {
				// f
				this.el.sceneEl.emit('showHotkeyNotification', {
					text: document.fullscreenElement ? 'Exit Fullscreen' : 'Fullscreen',
					icon: 'fas fa-expand',
				});
				toggle();
			}
		});
	},

	setupJumpDistance: function () {
		const jd = document.getElementById('jd');
		const jdLabel = document.getElementById('jdLabel');
		const jdPoint = document.getElementById('jdPoint');
		const jdTick = document.getElementById('jdTick');
		const vnjsjdPoint = document.getElementById('vnjsjdPoint');
		const vnjsjdTick = document.getElementById('vnjsjdTick');
		const percentOf = value => ((value - jd.min) / (jd.max - jd.min)) * 100;

		jd.addEventListener('input', () => {
			this.el.components['beat-generator'].setNewJD(jd.valueAsNumber);
		});
		jdPoint.addEventListener('click', () => {
			this.el.components['beat-generator'].setNewJD(parseFloat(jdPoint.textContent));
		});

		this.el.sceneEl.addEventListener('jdCalculated', e => {
			if (e.detail.jd != null) {
				jd.value = e.detail.jd;
				jdLabel.textContent = e.detail.jd.toFixed(2);
			}
			if (e.detail.defaultJd != null) {
				const percent = percentOf(e.detail.defaultJd);
				jdPoint.attributes.x.value = percent * 0.9 + (50 - percent) / 5 - 10 + '%';
				jdPoint.textContent = e.detail.defaultJd.toFixed(2);
				jdTick.attributes.x.value = percent * 0.9 + '%';
			}
		});

		this.el.sceneEl.addEventListener('vnjsjdCalculated', e => {
			const percent = percentOf(e.detail.jd);
			vnjsjdPoint.parentNode.parentNode.style.display = 'block';
			vnjsjdPoint.attributes.x.value = percent * 0.9 + (50 - percent) / 5 - 10 + '%';
			vnjsjdPoint.textContent = e.detail.jd.toFixed(2);
			vnjsjdTick.parentNode.parentNode.style.display = 'block';
			vnjsjdTick.attributes.x.value = percent * 0.9 + '%';
		});
	},

	setupHitsounds: function () {
		const button = document.getElementById('hitsounds-button');
		const reset = document.getElementById('resetHitsounds');
		const picker = document.getElementById('hitSoundPicker');
		const settings = this.settings;

		if (settings.settings.hitsoundName.length) {
			button.innerText = settings.settings.hitsoundName;
			reset.style.display = 'block';
		}

		button.addEventListener('click', () => picker.click());
		picker.addEventListener('input', e => {
			const sound = e.target.files[0];
			if (!sound) return;
			const reader = new FileReader();
			reader.onload = e => {
				settings.settings.hitsoundName = sound.name;
				settings.settings.hitSound = Buffer.from(e.target.result).toString('base64');
				settings.sync();
				button.innerText = sound.name;
				reset.style.display = 'block';
				this.hitSound.refreshBuffer();
			};
			reader.readAsArrayBuffer(sound);
		});

		reset.addEventListener('click', () => {
			settings.resetHitsound();
			this.hitSound.refreshBuffer();
			button.innerText = 'Change hitsounds';
			reset.style.display = 'none';
		});
	},

	setupSettingsFiles: function () {
		const settings = this.settings;
		document.getElementById('exportSettings').addEventListener('click', () => {
			const blob = new Blob([JSON.stringify(settings.settings, null, 2)], {type: 'application/json'});
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = 'beat-saber-live-settings.json';
			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);
			URL.revokeObjectURL(url);
		});

		const picker = document.getElementById('importSettingsPicker');
		document.getElementById('importSettings').addEventListener('click', () => picker.click());
		picker.addEventListener('input', e => {
			const file = e.target.files[0];
			if (!file) return;
			const reader = new FileReader();
			reader.onload = e => {
				let imported;
				try {
					imported = JSON.parse(e.target.result);
				} catch (error) {
					imported = null;
				}
				if (!imported || ['headsetOpacity', 'reducedDebris', 'noEffects'].some(key => !imported.hasOwnProperty(key))) {
					alert('This file is not a settings export.');
					return;
				}
				settings.settings = Object.assign(settings.settings, imported);
				settings.sync();
				alert('Settings imported. Reload the page to apply all of them.');
			};
			reader.readAsText(file);
		});
	},
});
