import {NoteEventType} from '../live/bsor';
import {MultiplierCounter} from '../utils/MultiplierCounter';
import {NoteCutDirection, clamp, ScoringType} from '../utils';
import {LiveSession} from '../live/session';

export function assignNote(replaynote, mapnote) {
	const scoringType = mapnote._scoringType ? mapnote._scoringType + 2 : 3;
	replaynote.index = mapnote._index;
	replaynote.colorType = mapnote._type;
	replaynote.lineIndex = mapnote._lineIndex;
	replaynote.cutDirection = mapnote._cutDirection;
	replaynote.lineLayer = mapnote._lineLayer;
	replaynote.mapnote = mapnote;
	replaynote.scoringType = scoringType - 2;
	mapnote.found = true;
}

/**
 * Replay data for the rest of the viewer (replay, allStructs, notes, bombs, walls). In live mode these grow while
 * the song is played; LiveSession (src/live/session.js) fills them from the mod's stream.
 */
AFRAME.registerComponent('replay-loader', {
	init: function () {
		this.replay = null;
		this.challenge = null;
		this.allStructs = [];
		this.notes = [];
		this.bombs = [];
		this.walls = [];
		this.live = new LiveSession(this);
	},

	applyModifiers: function (map, replay) {
		if (replay.info.modifiers.includes('NA')) {
			map._notes.forEach(note => {
				note._cutDirection = NoteCutDirection.Any;
			});
		}
		if (replay.info.modifiers.includes('NB')) {
			map._notes = map._notes.filter(a => a._type == 0 || a._type == 1);
		}
		if (replay.info.modifiers.includes('NO')) {
			map._obstacles = [];
		}
	},

	setIds: function (map, replay) {
		[].concat(map._notes, map._chains).forEach((mapnote, i) => {
			var lineIndex = mapnote._lineIndex;
			var colorType = mapnote._type;
			var cutDirection = colorType != 3 ? mapnote._cutDirection : NoteCutDirection.Any;
			var lineLayer = mapnote._lineLayer;
			var scoringType = mapnote._scoringType !== undefined ? mapnote._scoringType + 2 : colorType == 3 ? 2 : 3;

			var id = lineIndex * 1000 + lineLayer * 100 + colorType * 10 + cutDirection;
			mapnote._id = id;
			mapnote._idWithScoring = id + scoringType * 10000;

			var gameVersion = 0;
			if (replay.info.gameVersion && replay.info.gameVersion.split('.').length == 3) {
				gameVersion = parseInt(replay.info.gameVersion.split('.')[1]);
			}

			var altscoringType = scoringType;
			var legacyScoringType = scoringType;
			if (mapnote._scoringType == ScoringType.ChainHead) {
				altscoringType = ScoringType.ArcHead + 2;
			} else if (mapnote._scoringType == ScoringType.ArcHead) {
				altscoringType = ScoringType.ChainHead + 2;
			} else if (mapnote._scoringType == ScoringType.ChainHeadArcTail) {
				altscoringType = ScoringType.ArcTail + 2;
			} else if (mapnote._scoringType == ScoringType.ChainHeadArcHead) {
				altscoringType = ScoringType.ArcHead + 2;
			} else if (mapnote._scoringType == ScoringType.ChainHeadArcHeadArcTail) {
				altscoringType = ScoringType.ArcTail + 2;
			} else if (mapnote._scoringType == ScoringType.ChainLinkArcHead) {
				altscoringType = ScoringType.ChainLink + 2;
				if (gameVersion >= 29 && mapnote._sliceIndex == mapnote._sliceCount - 1) {
					id = mapnote._tailLineIndex * 1000 + mapnote._tailLineLayer * 100 + colorType * 10 + cutDirection;
				}
			} else if (mapnote._scoringType == ScoringType.ArcHeadArcTail) {
				altscoringType = ScoringType.ArcHead + 2;
			} else if (gameVersion >= 29 && mapnote._scoringType == ScoringType.ChainLink && mapnote._sliceIndex == mapnote._sliceCount - 1) {
				id = mapnote._tailLineIndex * 1000 + mapnote._tailLineLayer * 100 + colorType * 10 + cutDirection;
			}

			if (mapnote._scoringType == ScoringType.ArcTail) {
				legacyScoringType = ScoringType.Normal + 2;
			} else if (mapnote._scoringType == ScoringType.ArcHeadArcTail) {
				legacyScoringType = ScoringType.ArcTail + 2;
			} else if (mapnote._scoringType == ScoringType.ChainHeadArcTail) {
				legacyScoringType = ScoringType.ChainHead + 2;
			} else if (mapnote._scoringType == ScoringType.ChainLinkArcHead) {
				legacyScoringType = ScoringType.ChainLink + 2;
			} else if (mapnote._scoringType == ScoringType.ChainHeadArcHead) {
				legacyScoringType = ScoringType.ChainHead + 2;
			} else if (mapnote._scoringType == ScoringType.ChainHeadArcHeadArcTail) {
				legacyScoringType = ScoringType.ChainHeadArcTail + 2;
			}

			mapnote._idWithAlternativeScoring = id + altscoringType * 10000;
			mapnote._idWithLegacyScoring = id + legacyScoringType * 10000;
		});
	},
});

// Fills in the running score, combo, multiplier, energy and accuracy of every struct, in order.
// allStructs must be sorted by time.
export function computeTotals(allStructs, replay) {
	for (var i = 0; i < allStructs.length; i++) {
		var note = allStructs[i];
		note.i = i;
		if (!note.score) {
			note.score = ScoreForNote(note.eventType, note.cutInfo, note.scoringType);
		}
	}

	if (replay.info.startTime && allStructs.length) {
		allStructs[0].start = true;
	}

	var energy = 0.5;
	var score = 0,
		maxScore = 0,
		fcScore = 0,
		combo = 0,
		misses = 0;
	var streak = 0,
		maxStreak = 0,
		streakId = -1,
		maxStreakId = -1;

	var failRecorded = false;

	const maxCounter = new MultiplierCounter();
	const normalCounter = new MultiplierCounter();

	for (var i = 0; i < allStructs.length; i++) {
		let note = allStructs[i];

		var scoreForMaxScore = 115;
		if (note.scoringType == ScoringType.ChainHead) {
			scoreForMaxScore = 85;
		} else if (note.scoringType == ScoringType.ChainLink || note.scoringType == ScoringType.ChainLinkArcHead) {
			scoreForMaxScore = 20;
		}

		if (note.isBlock) {
			maxCounter.Increase();
			maxScore += maxCounter.Multiplier * scoreForMaxScore;
		}

		if (note.score < 0) {
			if (note.isBlock) {
				if (i == 0) {
					fcScore += maxCounter.Multiplier * scoreForMaxScore;
				} else {
					fcScore += (maxCounter.Multiplier * allStructs[i - 1].accuracy * scoreForMaxScore) / 100;
				}
			}
			normalCounter.Decrease();
			combo = 0;
			misses++;
			switch (note.score) {
				case -2: // badcut
					if (note.scoringType == ScoringType.ChainLink) {
						energy -= 0.025;
					} else {
						energy -= 0.1;
					}
					break;
				case -3: // miss
				case -4: // bomb
					if (note.scoringType == ScoringType.ChainLink) {
						energy -= 0.03;
					} else {
						energy -= 0.15;
					}
					break;

				default:
					break;
			}
		} else {
			normalCounter.Increase();
			score += normalCounter.Multiplier * note.score;
			fcScore += maxCounter.Multiplier * note.score;

			if (energy > 0 || (!replay.info.modifiers.includes('NF') && !replay.info.failTime)) {
				if (note.scoringType == ScoringType.ChainLink) {
					energy += 1 / 500;
				} else {
					energy += 0.01;
				}
			}
			if (energy > 1) {
				energy = 1;
			}
			combo++;

			if (note.scoringType != ScoringType.ChainLink) {
				if (note.score == 115) {
					streak++;
					if (streakId == -1) {
						streakId = i;
					}
				} else if (note.isBlock) {
					if (streak > maxStreak) {
						maxStreak = streak;
						maxStreakId = streakId;
					}
					streak = 0;
					streakId = -1;
				}
			}
		}

		note.multiplier = normalCounter.Multiplier;
		note.totalScore = score;
		note.combo = combo;
		note.misses = misses;
		note.energy = energy;
		note.maxScore = scoreForMaxScore;

		if (energy <= 0 && !failRecorded) {
			failRecorded = true;
			note.fail = true;
		}

		if (note.isBlock) {
			note.accuracy = (note.totalScore / maxScore) * 100;
			note.fcAccuracy = (fcScore / maxScore) * 100;
		} else {
			note.accuracy = i == 0 ? 0 : allStructs[i - 1].accuracy;
			note.fcAccuracy = i == 0 ? 100 : allStructs[i - 1].fcAccuracy;
		}
	}
	if (streak > maxStreak) {
		maxStreak = streak;
		maxStreakId = streakId;
	}

	if (maxStreakId > -1) {
		allStructs[maxStreakId].maxStreak = maxStreak;
	}
}

// Turns a BSOR note event into the struct the viewer scores and renders. Bomb events are recognized by id.
export function noteStructFromEvent(info) {
	let note = {
		eventType: info.eventType,
		cutInfo: info.noteCutInfo,
		spawnTime: info.spawnTime,
		time: info.eventTime,
		id: info.noteID,
		score: info.score,
		cutPoint: info.noteCutInfo ? info.noteCutInfo.cutPoint : null,
	};

	if (note.id == -1) {
		note.eventType = NoteEventType.bomb;
		note.id += 39;
		note.score = -4;
	}
	if (note.id > 0 && note.id < 100000) {
		if (note.id % 100 == 99) {
			note.eventType = NoteEventType.bomb;
			note.id += 39;
			note.score = -4;
		} else if (note.id % 10 == 9) {
			note.eventType = NoteEventType.bomb;
			note.id -= 1;
			note.score = -4;
		}
	}
	if (note.eventType != NoteEventType.bomb) {
		note.isBlock = true;
	}
	return note;
}

function CutScoresForNote(cut, scoringType) {
	var beforeCutRawScore = 0;
	if (scoringType != ScoringType.ChainLink && scoringType != ScoringType.ChainLinkArcHead) {
		if (scoringType == ScoringType.ArcTail || scoringType == ScoringType.ArcHeadArcTail || scoringType == ScoringType.ChainHeadArcTail) {
			beforeCutRawScore = 70;
		} else {
			beforeCutRawScore = clamp(Math.round(70 * cut.beforeCutRating), 0, 70);
		}
	}
	var afterCutRawScore = 0;
	if (scoringType != ScoringType.ChainLink && scoringType != ScoringType.ChainLinkArcHead) {
		if (scoringType == ScoringType.ChainHead) {
			afterCutRawScore = 0;
		} else if (
			scoringType == ScoringType.ArcHead ||
			scoringType == ScoringType.ArcHeadArcTail ||
			scoringType == ScoringType.ChainHeadArcTail
		) {
			afterCutRawScore = 30;
		} else {
			afterCutRawScore = clamp(Math.round(30 * cut.afterCutRating), 0, 30);
		}
	}
	var cutDistanceRawScore = 0;
	if (scoringType == ScoringType.ChainLink || scoringType == ScoringType.ChainLinkArcHead) {
		cutDistanceRawScore = 20;
	} else {
		var num = 1 - clamp(cut.cutDistanceToCenter / 0.3, 0, 1);
		cutDistanceRawScore = Math.round(15 * num);
	}

	return [beforeCutRawScore, afterCutRawScore, cutDistanceRawScore];
}

export function ScoreForNote(eventType, cutInfo, scoringType) {
	if (eventType == NoteEventType.good) {
		const scores = CutScoresForNote(cutInfo, scoringType);
		const result = scores[0] + scores[1] + scores[2];

		return result > 115 ? -2 : result;
	} else {
		switch (eventType) {
			case NoteEventType.bad:
				return -2;
			case NoteEventType.miss:
				return -3;
			case NoteEventType.bomb:
				return -4;
		}
	}
}
