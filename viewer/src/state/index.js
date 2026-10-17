/* global localStorage */
var utils = require('../utils');

let lastMediaMetadata = null;

const emptyChallenge = {
	audio: '',
	author: '',
	difficulty: '',
	id: '',
	image: '',
	songName: '',
	songNameMedium: '',
	songNameShort: '',
	songSubName: '',
	songSubNameShort: '',
};

const emptyScore = {
	time: -1,
	accuracy: 0,
	beatsHit: 0,
	beatsMissed: 0,
	beatsText: '',
	combo: 0,
	maxCombo: 0,
	multiplier: 1,
	energy: 0.5,
	rank: '',
	score: 0,
	scoreDescription: '',
	misses: 0,
};

const isSafari = navigator.userAgent.toLowerCase().indexOf('safari') !== -1 && navigator.userAgent.toLowerCase().indexOf('chrome') === -1;

if (isSafari) {
	var module = require('../lib/oggdec');
	const decodeOggData = module().decodeOggData;
	const decodeAudioData = (data, completion) => {
		decodeOggData(data).then(completion);
	};
	(window.AudioContext || window.webkitAudioContext).prototype.decodeOggData = decodeAudioData;
}

let beatmaps;
let difficulties;

AFRAME.utils.extendDeep = function deepAssign(original, extension) {
	Object.keys(extension).forEach(key => {
		original[key] = extension[key];
	});

	return original;
};

/**
 * State handler.
 *
 * 1. `handlers` is an object of events that when emitted to the scene will run the handler.
 *
 * 2. The handler function modifies the state.
 *
 * 3. Entities and components that are `bind`ed automatically update:
 *    `bind__<componentName>="<propertyName>: some.item.in.state"`
 */
AFRAME.registerState({
	initialState: {
		activeHand: localStorage.getItem('hand') || 'right',
		challenge: Object.assign(
			{
				// Actively playing challenge.
				hasLoadError: false,
				isLoading: false,
				isBeatsPreloaded: false, // Whether we have passed the negative time.
				loadErrorText: '',
			},
			emptyChallenge
		),
		score: emptyScore,
		notes: null,
		replay: {
			isLoading: false,
			hasError: false,
			errorText: '',
		},
		player: {
			name: '',
			avatar: '',
		},
		controllerType: '',
		inVR: false,
		pov: false,
		isPaused: true, // Playing, but paused.
		isPlaying: false, // Actively playing.
		isFinished: false,
		isSafari: isSafari,
		isSongBufferProcessing: false,
		useractive: false,
		showControls: true,
		spawnRotation: 0,
		saberScale: new THREE.Vector3(1, 1, 1),
		saberGlowScale: new THREE.Vector3(1, 1.1, 1),
		settings: {headsetOpacity: 0, volume: 0.0},
		hiddenSaber: '',
	},

	handlers: {
		beatloaderpreloadfinish: state => {
			state.challenge.isBeatsPreloaded = true;
		},

		challengeloadstart: (state, payload) => {
			state.challenge.hasLoadError = false;
			state.challenge.isLoading = true;
		},

		challengeloadend: (state, payload) => {
			beatmaps = payload.beatmaps;
			difficulties = payload.difficulties;

			state.challenge.audio = payload.audio;

			const mode = payload.mode;
			state.challenge.mode = mode;
			state.challenge.difficulties = difficulties[mode];
			state.challenge.difficulty = payload.difficulty;

			state.challenge.id = payload.isDragDrop ? '' : payload.id;

			state.challenge.songName = payload.info._songName;
			state.challenge.songNameShort = truncate(payload.info._songName, 18);
			state.challenge.songNameMedium = truncate(payload.info._songName, 30);

			state.challenge.songSubName = payload.info._songSubName || payload.info._songAuthorName;
			state.challenge.songSubNameShort = truncate(state.challenge.songSubName, 21);

			if (!state.challenge.image) {
				state.challenge.image = payload.image;
			}

			document.title = `${payload.info._songName} | Beat Saber Live`;
			state.challenge.isLoading = false;
		},

		songstartaudio: (state, payload) => {
			if (!window.MediaMetadata || !navigator.mediaSession) return;

			const metadata = {
				title: state.challenge.songName,
				artist: state.challenge.songSubName,
				album: state.player.name,
				image: state.challenge.image,
			};
			if (
				navigator.mediaSession.metadata &&
				lastMediaMetadata &&
				lastMediaMetadata.title === metadata.title &&
				lastMediaMetadata.artist === metadata.artist &&
				lastMediaMetadata.album === metadata.album &&
				lastMediaMetadata.image === metadata.image
			) {
				return;
			}
			lastMediaMetadata = metadata;

			navigator.mediaSession.metadata = new MediaMetadata({
				title: metadata.title,
				artist: metadata.artist,
				album: metadata.album,
				artwork: [
					{
						src: metadata.image,
					},
				],
			});
		},

		replayloadstart: (state, payload) => {
			state.replay.isLoading = true;
			state.replay.hasError = false;
			state.replay.errorText = null;
		},

		replayloaded: (state, payload) => {
			state.replay.isLoading = false;
			state.notes = payload.notes;
			if (state.challenge.mode == 'OneSaber') {
				state.hiddenSaber = payload.leftHanded ? 'right' : 'left';
			}
		},

		userloaded: (state, payload) => {
			state.player = payload;
		},

		challengeloaderror: (state, payload) => {
			state.challenge.hasLoadError = true;
			state.challenge.isLoading = false;
			state.challenge.loadErrorText = payload && payload.text ? payload.text : `Map was not found. Drop or click to select zip locally`;
		},

		controllerconnected: (state, payload) => {
			state.controllerType = payload.name;
		},

		scoreChanged: (state, payload) => {
			updateScore(state, {index: payload.index}, !!payload.force);
		},

		gamemenuresume: state => {
			state.isPaused = false;
		},

		// Live mode: a new song started in the game.
		livesessionstart: state => {
			state.isFinished = false;
			resetScore(state);
		},

		pausegame: state => {
			if (!state.isPlaying) {
				return;
			}
			state.isPaused = true;
		},

		songprocessingfinish: state => {
			state.isSongBufferProcessing = false;
		},

		songprocessingstart: state => {
			state.isSongBufferProcessing = true;
		},

		settingsChanged: (state, payload) => {
			state.settings = payload.settings;

			const saberScale = payload.settings.saberWidth / 100;

			state.saberScale = new THREE.Vector3(saberScale, 1, saberScale);
			state.saberGlowScale = new THREE.Vector3(saberScale, 1.1, saberScale);

			document.body.style.backgroundColor = payload.settings.backgroundColor;
		},

		povchanged: (state, payload) => {
			state.pov = payload.newPov;
		},

		useractive: (state, payload) => {
			state.useractive = payload.isActive;
		},

		'enter-vr': state => {
			state.inVR = true;
		},

		'exit-vr': state => {
			state.inVR = false;
		},
	},

	/**
	 * Post-process the state after each action.
	 */
	computeState: (state, action, payload) => {
		state.isPlaying =
			!state.isPaused &&
			!state.isSongBufferProcessing &&
			!state.challenge.isLoading &&
			!state.replay.isLoading &&
			!state.challenge.hasLoadError &&
			!state.replay.hasError;

		state.showControls = state.useractive || !state.isPlaying;
	},
});

function truncate(str, length) {
	if (!str) {
		return '';
	}
	if (str.length >= length) {
		return str.substring(0, length - 2) + '..';
	}
	return str;
}

function updateScore(state, payload, force) {
	let note = state.notes[payload.index];

	if (note.time > state.score.time || force) {
		state.score.time = note.time;
		state.score.score = note.totalScore;
		state.score.scoreDescription = (note.totalScore + '').replace(/(\d)(?=(\d{3})+$)/g, '$1 ');
		state.score.combo = note.combo;
		state.score.multiplier = note.multiplier;
		state.score.accuracy = note.accuracy.toFixed(2);
		state.score.fcAccuracy = note.fcAccuracy.toFixed(2);
		state.score.misses = note.misses;
		state.score.energy = note.energy;
		state.lastNoteTime = note.time;
	}
}

function resetScore(state) {
	state.score.time = emptyScore.time;
	state.score.score = emptyScore.score;
	state.score.scoreDescription = emptyScore.scoreDescription;
	state.score.combo = emptyScore.combo;
	state.score.multiplier = emptyScore.multiplier;
	state.score.accuracy = emptyScore.accuracy;
	state.score.fcAccuracy = emptyScore.fcAccuracy;
	state.score.misses = emptyScore.misses;
	state.score.energy = emptyScore.energy;
	state.lastNoteTime = 0;
}
