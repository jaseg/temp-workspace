const utils = require('../utils');

const GAME_OVER_LENGTH = 3.5;
const ONCE = {once: true};
const BASE_VOLUME = 0.35;
const isSafari = navigator.userAgent.toLowerCase().indexOf('safari') !== -1 && navigator.userAgent.toLowerCase().indexOf('chrome') === -1;

/**
 * Active challenge song / audio.
 *
 * Order of song init in conjuction with beat-generator:
 *
 * 1. previewStartTime is playing
 * 2. songloadfinish
 * 3. beat-generator preloading
 * 4. preloaded beats generated
 * 5. beat-generator preloading finish
 * 6. startAudio / songStartTime is set
 * 7. beat-generator continues off song current time
 */
AFRAME.registerComponent('song', {
	schema: {
		audio: {default: ''},
		analyserEl: {type: 'selector', default: '#audioAnalyser'},
		difficulty: {default: ''},
		isBeatsPreloaded: {default: false},
		isReplayLoading: {default: true},
		isPaused: {default: false},
		isPlaying: {default: false},
		isFinished: {default: false},
		pitchCompensation: {default: true},
		mode: {default: 'Standard'},
	},

	init: function () {
		this.analyserSetter = {};
		this.audioAnalyser = this.data.analyserEl.components.audioanalyser;
		this.context = this.audioAnalyser.context;
		this.isPlaying = false;
		this.songLoadingIndicator = document.getElementById('songLoadingIndicator');
		this.speed = 1; // set by the live session for speed modifiers
		this.hasReceivedUserGesture = false;
		this.audio = document.createElement('audio');
		this.audio.volume = utils.isFirefox() ? 0.0001 : 0; // Firefox really does not like zeros
		this.settings = this.el.sceneEl.components.settings;

		this.audioAnalyser.gainNode.gain.value = this.settings.settings.volume || BASE_VOLUME;

		this.el.addEventListener('wallhitstart', this.onWallHitStart.bind(this));
		this.el.addEventListener('wallhitend', this.onWallHitEnd.bind(this));

		const gestureListener = () => {
			if (!this.hitSound) {
				this.hitSound = this.el.components['beat-hit-sound'];
			}
			this.hasReceivedUserGesture = true;

			this.audioAnalyser.suspendContext();
			this.audioAnalyser.resumeContext();

			this.hitSound.suspendContext();
			this.hitSound.resumeContext();

			if (this.data.isPaused && !this.data.isReplayLoading && this.source && this.songStartTime === undefined) {
				this.startAudio(this.getCurrentTime());
			}

			this.el.removeEventListener('usergesturereceive', gestureListener);
		};

		this.el.addEventListener('usergesturereceive', gestureListener);
	},

	pauseAudio: function () {
		if (this.playRequest) {
			this.playRequest.then(_ => {
				if (!this.isPlaying) {
					this.audio.pause();
				}
			});
		} else {
			this.audio.pause();
		}
	},

	update: function (oldData) {
		const data = this.data;

		if (!this.el.sceneEl.isPlaying) {
			return;
		}

		this.isBufferSource = isSafari || !data.pitchCompensation;

		// Resume.
		if (oldData.isPaused && !data.isPaused) {
			this.audioAnalyser.resumeContext();
			if (this.source) {
				this.playMediaSession();
			}
			this.isPlaying = true;
		}

		// New challenge, load audio and play when ready.
		if (oldData.audio !== data.audio && data.audio) {
			this.el.sceneEl.emit('songprocessingstart', null, false);
			this.getAudio()
				.then(source => {
					if (this.data.isBeatsPreloaded) {
						this.startAudio(this.getCurrentTime());
					}
					this.el.sceneEl.emit('songprocessingfinish', null, false);
				})
				.catch(console.error);
			return;
		}

		// Play if we have loaded and were waiting for beats to preload.
		if (!oldData.isBeatsPreloaded && this.data.isBeatsPreloaded && this.source) {
			if (data.isPaused) {
				this.audioAnalyser.suspendContext();
				this.pauseAudio();
				this.isPlaying = false;
			} else {
				this.startAudio(this.getCurrentTime());
			}
		}

		// Pause / stop.
		if (!oldData.isPaused && data.isPaused) {
			this.audioAnalyser.suspendContext();
			this.pauseAudio();
			this.isPlaying = false;
		}

		if (oldData.pitchCompensation !== data.pitchCompensation) {
			this.setPlaybackRate(this.speed);
		}
	},

	pause: function () {
		if (this.data.isPlaying) {
			this.audioAnalyser.suspendContext();
			this.pauseAudio();
		}
	},

	play: function () {
		if (this.data.isPlaying) {
			this.audioAnalyser.resumeContext();
			this.playMediaSession();
		}
	},

	getAudio: function () {
		const data = this.data;

		this.isPlaying = false;
		return new Promise(resolve => {
			data.analyserEl.addEventListener(
				'audioanalysersource',
				evt => {
					this.source = evt.detail.source;
					this.mediaSource = evt.detail.mediaSource;
					this.duration = evt.detail.duration;
					if (evt.detail.audio) {
						this.audio = evt.detail.audio;
					}
					if (isSafari) {
						this.audio.src = utils.createSilence(this.duration);
					}
					resolve(this.source);
				},
				ONCE
			);
			this.analyserSetter.src = this.data.audio;
			this.analyserSetter.speed = this.speed;
			data.analyserEl.setAttribute('audioanalyser', this.analyserSetter);
		});
	},

	stopAudio: function () {
		if (!this.source) {
			console.warn('[song] Tried to stopAudio, but not playing.');
			return;
		}
		if (this.source && this.source.stop) {
			this.source.stop();
			this.source = null;
		}
		if (this.source != this.mediaSource && this.mediaSource && this.mediaSource.stop) {
			this.mediaSource.stop();
		}
		if (this.audio) {
			this.pauseAudio();
		}

		this.isPlaying = false;
	},

	onWallHitStart: function () {
		const gain = this.audioAnalyser.gainNode.gain;
		const volume = this.el.sceneEl.components.settings.settings.volume || BASE_VOLUME;
		gain.linearRampToValueAtTime(0.35 * volume, this.context.currentTime + 0.1);
	},

	onWallHitEnd: function () {
		const gain = this.audioAnalyser.gainNode.gain;
		const volume = this.el.sceneEl.components.settings.settings.volume || BASE_VOLUME;
		gain.linearRampToValueAtTime(volume, this.context.currentTime + 0.1);
	},

	playMediaSession: function () {
		if (!this.metadataAudioLoading) {
			try {
				this.playRequest = this.audio.play();
				this.playRequest.then(_ => {
					this.playRequest = null;
					this.metadataAudioLoading = false;

					this.el.emit('songstartaudio');
				});

				this.metadataAudioLoading = true;
			} catch (e) {
				console.log(e);
			}
		}
	},

	startAudio: function (time) {
		this.isPlaying = true;
		const playTime = time || 0;

		const duration = this.getDuration();
		const canUseBuffer = duration > 0 ? duration <= 1800 : true;
		if ((this.isBufferSource || this.speed < this.settings.settings.pitchCompensationTreshold) && canUseBuffer) {
			this.source = this.audioAnalyser.activateBufferSource();
		} else {
			this.source = this.audioAnalyser.activateMediaSource();
		}

		this.songStartTime = (this.context.currentTime * this.speed - playTime) / (this.speed > 0.01 ? this.speed : 0.01);
		if (this.source.start) {
			try {
				this.source.start(0, playTime);
			} catch (e) {
				console.log(e);
			}
		}
		if (this.source != this.mediaSource && this.mediaSource && this.mediaSource.start) {
			try {
				this.mediaSource.start(0, playTime);
			} catch (e) {
				console.log(e);
			}
		}

		this.audio.currentTime = playTime;
		if (this.source && this.source.playbackRate) {
			this.source.playbackRate.value = this.speed;
		}
		if (this.mediaSource && this.mediaSource.playbackRate) {
			this.mediaSource.playbackRate.value = this.speed;
		}
		this.audio.playbackRate = Math.max(this.speed, this.settings.settings.pitchCompensationTreshold);

		if (this.speed > 0 && 'mediaSession' in navigator) {
			navigator.mediaSession.setPositionState({
				duration: this.getDuration(),
				playbackRate: this.speed,
				position: playTime,
			});
		}

		this.playMediaSession();
	},

	setPlaybackRate: function (rate) {
		this.speed = rate;

		const duration = this.getDuration();
		const canUseBuffer = duration > 0 ? duration <= 1800 : true;
		var newSource = null;
		if ((this.isBufferSource || this.speed < this.settings.settings.pitchCompensationTreshold) && canUseBuffer) {
			newSource = this.audioAnalyser.activateBufferSource();
		} else {
			newSource = this.audioAnalyser.activateMediaSource();
		}

		if (newSource != this.source) {
			if (this.source && this.source.stop) {
				this.source.stop();
				this.source = null;
			}
			if (this.source != this.mediaSource && this.mediaSource && this.mediaSource.stop) {
				this.mediaSource.stop();
			}

			this.source = newSource;

			if (this.source.start) {
				try {
					this.source.start(0, this.getCurrentTime());
				} catch (e) {
					console.log(e);
				}
			}

			if (this.source != this.mediaSource && this.mediaSource && this.mediaSource.start) {
				try {
					this.mediaSource.start(0, this.getCurrentTime());
				} catch (e) {
					console.log(e);
				}
			}

			this.audio.currentTime = this.getCurrentTime();
		}

		if (this.source && this.source.playbackRate) {
			this.source.playbackRate.value = rate;
		}
		if (this.mediaSource && this.mediaSource.playbackRate) {
			this.mediaSource.playbackRate.value = rate;
		}
		this.audio.playbackRate = Math.max(rate, this.settings.settings.pitchCompensationTreshold);
	},

	getDuration: function () {
		if (this.source && this.source.buffer) {
			return this.source.buffer.duration;
		}
		if (this.duration) return this.duration;
		if (this.audio && isFinite(this.audio.duration)) return this.audio.duration;
		return 0;
	},

	// Song time follows the game (see src/live/session.js), not the audio.
	getCurrentTime: function () {
		return this.liveTime ? this.liveTime() : 0;
	},
});
