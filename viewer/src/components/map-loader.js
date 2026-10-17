import {postprocess, processNoodle} from '../utils/mapPostprocessor';

const chiralityModes = ['VerticalStandard', 'HorizontalStandard', 'InverseStandard', 'InvertedStandard'];

/**
 * Turns a map's files (Info.dat v2 or v4, the played difficulty, audio, cover) into the challenge the scene plays.
 * `files` maps file names to objects with an `async(type)` method ('string', 'uint8array' or 'arraybuffer'), the
 * interface JSZip entries have; the live session provides them from the mod's WebSocket.
 */
AFRAME.registerComponent('map-loader', {
	schema: {
		difficulty: {default: 'ExpertPlus'},
		mode: {default: 'Standard'},
	},

	processFiles: async function (files, info) {
		const event = {
			audio: '',
			beatmaps: {Standard: {}},
			beatSpeeds: {Standard: {}},
			beatOffsets: {Standard: {}},
			difficulties: {Standard: []},
			customData: {Standard: []},
			image: '',
			info,
			mappingExtensions: {isEnabled: false},
		};

		if (info._audioDataFile) {
			const fileArray = await files[Object.keys(files).find(f => f.toLowerCase() == info._audioDataFile.toLowerCase())].async('uint8array');
			var audioDataJson;
			try {
				var fileData = new TextDecoder().decode(fileArray);
				audioDataJson = JSON.parse(fileData);
			} catch (e) {
				var fileData = new TextDecoder('UTF-16LE').decode(fileArray);
				audioDataJson = JSON.parse(fileData);
			}
			info.audioData = audioDataJson;
		}

		// See whether we need mapping extensions (per difficulty).
		const customData = event.info._customData;
		if (
			customData &&
			customData._editorSettings &&
			customData._editorSettings.modSettings &&
			customData._editorSettings.modSettings.mappingExtensions &&
			customData._editorSettings.modSettings.mappingExtensions.isEnabled
		) {
			event.mappingExtensions = event.info._customData._editorSettings.modSettings.mappingExtensions;
		}

		if (!event.info._difficultyBeatmapSets) return;

		// Index beatmaps (modes + difficulties).
		const beatmapSets = event.info._difficultyBeatmapSets.reduce((acc, curr) => {
			const existing = acc.find(x => x._beatmapCharacteristicName === curr._beatmapCharacteristicName);
			if (!existing || curr._difficultyBeatmaps.length > existing._difficultyBeatmaps.length) {
				const filtered = acc.filter(x => x._beatmapCharacteristicName !== curr._beatmapCharacteristicName);
				return [...filtered, curr];
			}
			return acc;
		}, []);

		try {
			for (let index = 0; index < beatmapSets.length; index++) {
				const set = beatmapSets[index];
				var mode = set._beatmapCharacteristicName;

				if (mode == 'Standard' && this.data.mode && chiralityModes.includes(this.data.mode)) {
					mode = this.data.mode;
				}

				event.beatmaps[mode] = {};
				event.beatSpeeds[mode] = {};
				event.beatOffsets[mode] = {};
				event.customData[mode] = {};

				// Only the difficulty being played is provided; skip the others.
				const diffBeatmaps = set._difficultyBeatmaps
					.sort(d => d._difficultyRank)
					.filter(diff => Object.keys(files).some(f => f.toLowerCase() == diff._beatmapFilename.toLowerCase()));
				for (let index = 0; index < diffBeatmaps.length; index++) {
					const diff = diffBeatmaps[index];
					const fileArray =
						await files[Object.keys(files).find(f => f.toLowerCase() == diff._beatmapFilename.toLowerCase())].async('uint8array');

					var mapJson;
					try {
						var fileData = new TextDecoder().decode(fileArray);
						mapJson = JSON.parse(fileData.replaceAll('NaN', '0'));
					} catch (e) {
						var fileData = new TextDecoder('UTF-16LE').decode(fileArray);
						mapJson = JSON.parse(fileData);
					}
					mapJson.info = event.info;
					mapJson.audioData = info.audioData;
					let map = postprocess(mapJson, mode);
					event.beatmaps[mode][diff._difficulty] = map;
					event.beatSpeeds[mode][diff._difficulty] = diff._noteJumpMovementSpeed;
					event.beatOffsets[mode][diff._difficulty] = diff._noteJumpStartBeatOffset;
					event.customData[mode][diff._difficulty] = diff._customData;

					// TODO: Assume for now if one difficulty wants extensions, they all do. Fix later.
					if (diff._customData && diff._customData._requirements && diff._customData._requirements.indexOf('Mapping Extensions') !== -1) {
						event.mappingExtensions = {isEnabled: true};
					}

					if (diff._customData && diff._customData._requirements && diff._customData._requirements.indexOf('Noodle Extensions') !== -1) {
						map = processNoodle(map);
					}
				}

				// Get difficulties.
				event.difficulties[mode] = diffBeatmaps;
			}
		} catch (e) {
			this.loadError('The map could not be read.');
			return;
		}

		if (!event.beatmaps[this.data.mode]) {
			generateMode(event, this.data.difficulty, this.data.mode);
		}

		// Default to hardest of first beatmap.
		if (!event.difficulty) {
			event.difficulty = this.data.difficulty || event.difficulties[this.data.mode][0]._difficulty;
		}
		event.mode = this.data.mode;

		let extractAsBlobUrl = async (name, type) => {
			return URL.createObjectURL(new Blob([await files[name].async('arraybuffer')], {type}));
		};

		let extractAudioAsBlobUrl = async name => {
			const buffer = await files[name].async('arraybuffer');
			const type = detectAudioMimeType(new Uint8Array(buffer.slice(0, 16)), name);
			return URL.createObjectURL(new Blob([buffer], {type}));
		};

		// Resolve the song audio. Prefer the filename declared in the map info and detect its
		// encoding from the file contents, since file extensions can be missing or misspelled.
		if (event.info._songFilename) {
			const songFilename = event.info._songFilename.toLowerCase();
			const songKey = Object.keys(files).find(f => f.toLowerCase() === songFilename);
			if (songKey) {
				event.audio = await extractAudioAsBlobUrl(songKey);
			}
		}

		let keys = Object.keys(files);
		for (let index = 0; index < keys.length; index++) {
			const filename = keys[index];
			const lowerFilename = filename.toLowerCase();
			// Fallback: scan for any audio file if it could not be resolved from the map info.
			if (
				!event.audio &&
				(lowerFilename.endsWith('egg') || lowerFilename.endsWith('ogg') || lowerFilename.endsWith('wav') || lowerFilename.endsWith('mp3'))
			) {
				event.audio = await extractAudioAsBlobUrl(filename);
			}
			if (!event.image) {
				if (lowerFilename.endsWith('jpg') || lowerFilename.endsWith('jpeg')) {
					event.image = await extractAsBlobUrl(filename, 'image/jpeg');
				}
				if (lowerFilename.endsWith('png')) {
					event.image = await extractAsBlobUrl(filename, 'image/png');
				}
			}
		}

		this.el.emit('challengeloadend', event, false);
	},

	processInfo: function (files) {
		let captureSelf = this;
		var processed = false;
		Object.keys(files).forEach(filename => {
			if (filename.toLowerCase().endsWith('info.dat')) {
				processed = true;
				files[filename].async('string').then(function (fileData) {
					let info = jsonParseClean(fileData);

					if (info.version && info.version.startsWith('4')) {
						let v2Info = {
							_version: '2.1.0',
							_songName: info.song.title,
							_songSubName: info.song.subTitle || '',
							_songAuthorName: info.song.author,
							_levelAuthorName: info.difficultyBeatmaps[0].beatmapAuthors.mappers[0],
							_beatsPerMinute: info.audio.bpm,
							_audioDataFile: info.audio.audioDataFilename,
							_songTimeOffset: 0,
							_shuffle: 0,
							_shufflePeriod: 0,
							_previewStartTime: info.audio.previewStartTime,
							_previewDuration: info.audio.previewDuration,
							_songFilename: info.audio.songFilename,
							_coverImageFilename: info.coverImageFilename,
							_environmentName: info.environmentNames[0],
							_allDirectionsEnvironmentName: info.environmentNames[1],
							_environmentNames: info.environmentNames,
							_colorSchemes: info.colorSchemes,
							_difficultyBeatmapSets: info.difficultyBeatmaps.reduce((sets, diff) => {
								const characteristic = diff.characteristic || 'Standard';
								const existingSet = sets.find(set => set._beatmapCharacteristicName === characteristic);

								const beatmap = {
									_difficulty: diff.difficulty,
									_difficultyRank:
										diff.difficulty === 'Easy'
											? 1
											: diff.difficulty === 'Normal'
												? 3
												: diff.difficulty === 'Hard'
													? 5
													: diff.difficulty === 'Expert'
														? 7
														: diff.difficulty === 'ExpertPlus'
															? 9
															: 1,
									_beatmapFilename: diff.beatmapDataFilename,
									_noteJumpMovementSpeed: diff.noteJumpMovementSpeed,
									_noteJumpStartBeatOffset: diff.noteJumpStartBeatOffset,
									_beatmapColorSchemeIdx: diff.beatmapColorSchemeIdx,
									_environmentNameIdx: diff.environmentNameIdx,
								};

								if (existingSet) {
									existingSet._difficultyBeatmaps.push(beatmap);
								} else {
									sets.push({
										_beatmapCharacteristicName: characteristic,
										_difficultyBeatmaps: [beatmap],
									});
								}
								return sets;
							}, []),
						};
						captureSelf.processFiles(files, v2Info);
					} else {
						captureSelf.processFiles(files, info);
					}
				});
			}
		});

		if (!processed) {
			this.loadError('The map has no Info.dat.');
		}
	},

	loadError: function (text) {
		this.el.sceneEl.emit('challengeloaderror', {text}, null);
	},
});

function jsonParseClean(str) {
	try {
		str = str.trim();
		str = str.replace(/\u0000/g, '').replace(/\u\d\d\d\d/g, '');
		str = str.replace('\b', ' ');
		if (str[0] !== '{') {
			str = str.substring(str.indexOf('{'), str.length);
		}

		// Remove Unicode escape sequences.
		// stringified = stringified.replace(/\\u..../g, ' ');
		return jsonParseLoop(str, 0);
	} catch (e) {
		// Should not reach here.
		console.log(e, str);
		return null;
	}
}

const errorRe1 = /column (\d+)/m;
const errorRe2 = /position (\d+)/m;

function jsonParseLoop(str, i) {
	try {
		return JSON.parse(str);
	} catch (e) {
		let match = e.toString().match(errorRe1);
		if (!match) {
			match = e.toString().match(errorRe2);
		}
		if (!match) {
			throw e;
		}
		const errorPos = parseInt(match[1]);
		str = str.replace(str[errorPos], 'x');
		str = str.replace(str[errorPos + 1], 'x');
		str = str.replace(str[errorPos + 2], 'x');
		return jsonParseLoop(str, i + 1);
	}
}

function detectAudioMimeType(bytes, filename) {
	if (bytes && bytes.length >= 4) {
		// OGG: "OggS" (Beat Saber `.egg` files are Ogg Vorbis).
		if (bytes[0] === 0x4f && bytes[1] === 0x67 && bytes[2] === 0x67 && bytes[3] === 0x53) {
			return 'audio/ogg';
		}
		// WAV: "RIFF" container.
		if (bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x46) {
			return 'audio/wav';
		}
		// MP3: "ID3" tag.
		if (bytes[0] === 0x49 && bytes[1] === 0x44 && bytes[2] === 0x33) {
			return 'audio/mpeg';
		}
		// MP3: MPEG frame sync (11 set bits).
		if (bytes[0] === 0xff && (bytes[1] & 0xe0) === 0xe0) {
			return 'audio/mpeg';
		}
		// FLAC: "fLaC".
		if (bytes[0] === 0x66 && bytes[1] === 0x4c && bytes[2] === 0x61 && bytes[3] === 0x43) {
			return 'audio/flac';
		}
	}
	// M4A/MP4 audio: "ftyp" box at offset 4.
	if (bytes && bytes.length >= 8 && bytes[4] === 0x66 && bytes[5] === 0x74 && bytes[6] === 0x79 && bytes[7] === 0x70) {
		return 'audio/mp4';
	}

	const lower = (filename || '').toLowerCase();
	if (lower.endsWith('wav')) return 'audio/wav';
	if (lower.endsWith('mp3')) return 'audio/mpeg';
	if (lower.endsWith('flac')) return 'audio/flac';
	if (lower.endsWith('m4a')) return 'audio/mp4';
	return 'audio/ogg';
}

function generateMode(event, difficulty, mode) {
	var modeNames = Object.keys(event.beatmaps);
	for (let i = 0; i < modeNames.length; i++) {
		const defaultMode = modeNames[i];
		if (mode.toLowerCase().includes(defaultMode.toLowerCase())) {
			event.beatmaps[mode] = {};
			event.beatSpeeds[mode] = {};
			event.beatOffsets[mode] = {};

			event.beatmaps[mode][difficulty] = event.beatmaps[defaultMode][difficulty];
			event.beatSpeeds[mode][difficulty] = event.beatSpeeds[defaultMode][difficulty];
			event.beatOffsets[mode][difficulty] = event.beatOffsets[defaultMode][difficulty];
			event.difficulties[mode] = event.difficulties[defaultMode];
			event.customData[mode] = event.customData[defaultMode];

			break;
		}
	}
}
