using System;
using System.Collections.Generic;
using IPA.Utilities;
using LiveViewer.Server.Live;
using LiveViewer.Server.Protocol;
using UnityEngine;
using Zenject;
using Pose = LiveViewer.Server.Protocol.Pose;

namespace LiveViewer.Plugin.Recording
{
    /// <summary>
    /// Streams one play of a level into the server's <see cref="LiveFeed"/>. Adapted from BeatLeader's
    /// ReplayRecorder (MIT, https://github.com/BeatLeader/beatleader-mod): the same capture points and ids, but every
    /// event goes out as it happens instead of into a replay file. Runs on the game thread only.
    /// </summary>
    internal sealed class LiveRecorder : IInitializable, IDisposable, ILateTickable
    {
        private readonly LiveFeed _feed;
        private readonly LiveService _service;
        private readonly GameplayCoreSceneSetupData _setup;
        private readonly SaberManager _saberManager;
        private readonly PlayerTransforms _playerTransforms;
        private readonly BeatmapObjectManager _beatmapObjectManager;
        private readonly AudioTimeSyncController _timeSync;
        private readonly ScoreController _scoreController;
        private readonly PlayerHeadAndObstacleInteraction _headObstacles;
        private readonly GameEnergyCounter _energyCounter;
        private readonly IVariableMovementDataProvider _movementData;
        private readonly StandardLevelScenesTransitionSetupDataSO _transitionSetup;
        private readonly PauseController? _pauseController;
        private readonly PlayerHeightDetector? _heightDetector;
        private readonly PlayerDataModel _playerData;
        private readonly IReadonlyBeatmapData _beatmapData;

        // Arcs and chains go out this long before their time: earlier than the game spawns them (its jump and move
        // time), as the game has no spawn event for chains. Sorted by time; _nextSlider is the first not sent yet.
        private const float SliderLead = 3f;
        private readonly List<SliderSpawn> _sliders = new List<SliderSpawn>();
        private int _nextSlider;

        // Note and wall ids as in BeatLeader's recorder, kept per object so each later event can find them.
        private readonly Dictionary<NoteData, NoteEvent> _notes = new Dictionary<NoteData, NoteEvent>();
        private readonly Dictionary<ObstacleController, WallEvent> _walls = new Dictionary<ObstacleController, WallEvent>();
        private readonly List<NoteSpawn> _pendingNotes = new List<NoteSpawn>();
        private readonly List<WallSpawn> _pendingWalls = new List<WallSpawn>();

        private Transform? _origin, _head, _leftSaber, _rightSaber;
        private SessionInfo? _session;
        private bool _started, _ended, _paused, _inWall;
        private WallEvent _currentWall;

        public LiveRecorder(
            LiveService service,
            GameplayCoreSceneSetupData setup,
            SaberManager saberManager,
            PlayerTransforms playerTransforms,
            BeatmapObjectManager beatmapObjectManager,
            AudioTimeSyncController timeSync,
            ScoreController scoreController,
            PlayerHeadAndObstacleInteraction headObstacles,
            GameEnergyCounter energyCounter,
            IVariableMovementDataProvider movementData,
            StandardLevelScenesTransitionSetupDataSO transitionSetup,
            PlayerDataModel playerData,
            IReadonlyBeatmapData beatmapData,
            [InjectOptional] PauseController? pauseController,
            [InjectOptional] PlayerHeightDetector? heightDetector)
        {
            _service = service;
            _feed = service.Server!.Feed;
            _setup = setup;
            _saberManager = saberManager;
            _playerTransforms = playerTransforms;
            _beatmapObjectManager = beatmapObjectManager;
            _timeSync = timeSync;
            _scoreController = scoreController;
            _headObstacles = headObstacles;
            _energyCounter = energyCounter;
            _movementData = movementData;
            _transitionSetup = transitionSetup;
            _playerData = playerData;
            _beatmapData = beatmapData;
            _pauseController = pauseController;
            _heightDetector = heightDetector;
        }

        public void Initialize()
        {
            // The game's garbage collector is off during songs (HMLib's DisableGCWhileEnabled), streamed or not.
            _service.Server!.InGameplay = true;

            // The configured name, else the Steam name, else the game's own (a placeholder in the ARM64 build).
            var playerName = _service.Config.PlayerName;
            if (string.IsNullOrEmpty(playerName))
            {
                playerName = _service.PlatformPlayerName;
            }

            if (string.IsNullOrEmpty(playerName) && _playerData.playerData.playerName != "<NO NAME!>")
            {
                playerName = _playerData.playerData.playerName ?? "";
            }

            var level = SessionBuilder.TryDescribe(_setup, playerName, out var selection, out var reason);
            if (level == null)
            {
                Plugin.Log?.Info("Not streaming this level: " + reason);
                _ended = true;
                return;
            }

            _session = level;
            CollectSliders();
            _feed.SelectSong(selection!);
            _beatmapObjectManager.noteWasAddedEvent += OnNoteWasAdded;
            _beatmapObjectManager.noteWasCutEvent += OnNoteWasCut;
            _beatmapObjectManager.obstacleWasSpawnedEvent += OnObstacleWasSpawned;
            _scoreController.scoringForNoteFinishedEvent += OnScoringFinished;
            _headObstacles.headDidEnterObstacleEvent += OnHeadEnteredObstacle;
            _transitionSetup.didFinishEvent += OnLevelFinished;
            if (_pauseController != null)
            {
                _pauseController.didPauseEvent += OnPause;
                _pauseController.didResumeEvent += OnResume;
            }

            if (_heightDetector != null)
            {
                _heightDetector.playerHeightDidChangeEvent += OnPlayerHeightChanged;
            }
        }

        public void Dispose()
        {
            _service.Server!.InGameplay = false;
            if (_session == null)
            {
                return;
            }

            _beatmapObjectManager.noteWasAddedEvent -= OnNoteWasAdded;
            _beatmapObjectManager.noteWasCutEvent -= OnNoteWasCut;
            _beatmapObjectManager.obstacleWasSpawnedEvent -= OnObstacleWasSpawned;
            _scoreController.scoringForNoteFinishedEvent -= OnScoringFinished;
            _headObstacles.headDidEnterObstacleEvent -= OnHeadEnteredObstacle;
            _transitionSetup.didFinishEvent -= OnLevelFinished;
            if (_pauseController != null)
            {
                _pauseController.didPauseEvent -= OnPause;
                _pauseController.didResumeEvent -= OnResume;
            }

            if (_heightDetector != null)
            {
                _heightDetector.playerHeightDidChangeEvent -= OnPlayerHeightChanged;
            }

            // Torn down without a result (e.g. the game quit from the pause menu in a way that skipped didFinish).
            End(SessionEndReason.Quit);
        }

        public void LateTick()
        {
            if (_ended || _paused)
            {
                return;
            }

            if (!_started)
            {
                // The jump distance is known once the spawn controller has initialised, which happens before the
                // first gameplay frame.
                _session!.JumpDistance = _movementData.jumpDistance;
                _feed.BeginSession(_session);
                _started = true;
                foreach (var note in _pendingNotes) _feed.SpawnNote(LiveClock.NowUs(), note);
                foreach (var wall in _pendingWalls) _feed.SpawnWall(LiveClock.NowUs(), wall);
                _pendingNotes.Clear();
                _pendingWalls.Clear();
                _origin = _playerTransforms.GetField<Transform, PlayerTransforms>("_originParentTransform");
                _head = _playerTransforms.GetField<Transform, PlayerTransforms>("_headTransform");
                _leftSaber = _saberManager.leftSaber.transform;
                _rightSaber = _saberManager.rightSaber.transform;
            }

            var songTime = _timeSync.songTime;
            while (_nextSlider < _sliders.Count && _sliders[_nextSlider].Time - SliderLead <= songTime)
            {
                // Arcs and chains already over (e.g. a practice start time) are skipped.
                if (_sliders[_nextSlider].TailTime >= songTime)
                {
                    _feed.SpawnSlider(LiveClock.NowUs(), _sliders[_nextSlider]);
                }

                _nextSlider++;
            }

            var origin = _origin!;
            _feed.Pose(LiveClock.NowUs(), _timeSync.songTime,
                Local(origin, _head!), Local(origin, _leftSaber!), Local(origin, _rightSaber!));

            if (_inWall && !_headObstacles.playerHeadIsInObstacle)
            {
                // Like BeatLeader: a wall event carries the energy left once the head is out of the wall again.
                _inWall = false;
                _currentWall.Energy = _energyCounter.energy;
                _feed.Wall(LiveClock.NowUs(), _currentWall);
            }
        }

        private void CollectSliders()
        {
            foreach (var data in _beatmapData.GetBeatmapDataItems<SliderData>(0))
            {
                var chain = data.sliderType == SliderData.Type.Burst;
                _sliders.Add(new SliderSpawn
                {
                    Kind = chain ? SliderKind.Chain : SliderKind.Arc,
                    ColorType = (int) data.colorType,
                    Time = data.time,
                    LineIndex = data.headLineIndex,
                    LineLayer = (int) data.headLineLayer,
                    CutDirection = (int) data.headCutDirection,
                    TailTime = data.tailTime,
                    TailLineIndex = data.tailLineIndex,
                    TailLineLayer = (int) data.tailLineLayer,
                    TailCutDirection = (int) data.tailCutDirection,
                    HeadControlPointLengthMultiplier = data.headControlPointLengthMultiplier,
                    TailControlPointLengthMultiplier = data.tailControlPointLengthMultiplier,
                    MidAnchorMode = (int) data.midAnchorMode,
                    HasTailNote = data.hasTailNote,
                    SliceCount = data.sliceCount,
                    SquishAmount = data.squishAmount,
                });
            }

            _sliders.Sort((a, b) => a.Time.CompareTo(b.Time));
        }

        private static Pose Local(Transform origin, Transform t)
        {
            var p = origin.InverseTransformPoint(t.position);
            var r = Quaternion.Inverse(origin.rotation) * t.rotation;
            return new Pose(new Vec3(p.x, p.y, p.z), new Quat(r.x, r.y, r.z, r.w));
        }

        private static Vec3 V(Vector3 v) => new Vec3(v.x, v.y, v.z);

        private void OnNoteWasAdded(NoteData noteData, NoteSpawnData spawnData)
        {
            var note = new NoteEvent
            {
                NoteId = ((int) noteData.scoringType + 2) * 10000
                         + noteData.lineIndex * 1000
                         + (int) noteData.noteLineLayer * 100
                         + (int) noteData.colorType * 10
                         + (int) noteData.cutDirection,
                SpawnTime = noteData.time,
            };
            _notes[noteData] = note;
            var spawn = new NoteSpawn
            {
                NoteId = note.NoteId,
                Time = noteData.time,
                LineIndex = noteData.lineIndex,
                LineLayer = (int) noteData.noteLineLayer,
                BeforeJumpLineLayer = (int) noteData.beforeJumpNoteLineLayer,
                ColorType = (int) noteData.colorType,
                CutDirection = (int) noteData.cutDirection,
                ScoringType = (int) noteData.scoringType,
                CutDirectionAngleOffset = noteData.cutDirectionAngleOffset,
                HasFlip = noteData.flipLineIndex >= 0,
                FlipLineIndex = noteData.flipLineIndex,
                FlipYSide = noteData.flipYSide,
            };
            if (_started) _feed.SpawnNote(LiveClock.NowUs(), spawn);
            else _pendingNotes.Add(spawn);
        }

        private void OnNoteWasCut(NoteController noteController, in global::NoteCutInfo info)
        {
            if (!_started || _ended || !_notes.TryGetValue(info.noteData, out var note))
            {
                return;
            }

            note.EventTime = _timeSync.songTime;
            note.EventType = info.noteData.colorType == ColorType.None ? NoteEventType.Bomb
                : info.allIsOK ? NoteEventType.Good : NoteEventType.Bad;
            note.CutInfo = new LiveViewer.Server.Protocol.NoteCutInfo
            {
                SpeedOk = info.speedOK,
                DirectionOk = info.directionOK,
                SaberTypeOk = info.saberTypeOK,
                WasCutTooSoon = info.wasCutTooSoon,
                SaberSpeed = info.saberSpeed,
                SaberDirection = V(info.saberDir),
                SaberType = (int) info.saberType,
                TimeDeviation = info.timeDeviation,
                CutDirectionDeviation = info.cutDirDeviation,
                CutPoint = V(info.cutPoint),
                CutNormal = V(info.cutNormal),
                CutDistanceToCenter = info.cutDistanceToCenter,
                CutAngle = info.cutAngle,
            };
            _notes[info.noteData] = note;

            // The immediate event shows the cut right away; its swing rating is still incomplete. Bad cuts and bombs
            // are final already (their scoring finishes in the same frame) and only go out from OnScoringFinished.
            if (note.EventType == NoteEventType.Good)
            {
                _feed.Note(false, LiveClock.NowUs(), note);
            }
        }

        private void OnScoringFinished(ScoringElement element)
        {
            var noteData = element.noteData;
            if (!_started || _ended || !_notes.TryGetValue(noteData, out var note))
            {
                return;
            }

            var isBomb = noteData.colorType == ColorType.None;
            switch (element)
            {
                case MissScoringElement _:
                    if (isBomb || noteData.scoringType == NoteData.ScoringType.NoScore)
                    {
                        return;
                    }

                    note.EventType = NoteEventType.Miss;
                    note.EventTime = _timeSync.songTime;
                    break;
                case BadCutScoringElement _:
                    note.EventType = isBomb ? NoteEventType.Bomb : NoteEventType.Bad;
                    break;
                case GoodCutScoringElement good:
                    note.EventType = NoteEventType.Good;
                    note.CutInfo.BeforeCutRating = good.cutScoreBuffer.beforeCutSwingRating;
                    note.CutInfo.AfterCutRating = good.cutScoreBuffer.afterCutSwingRating;
                    break;
                default:
                    return;
            }

            _notes.Remove(noteData);
            _feed.Note(true, LiveClock.NowUs(), note);
        }

        private void OnObstacleWasSpawned(ObstacleController obstacle)
        {
            var data = obstacle.obstacleData;
            _walls[obstacle] = new WallEvent
            {
                WallId = data.lineIndex * 100 + (int) data.type * 10 + data.width,
                SpawnTime = data.time,
            };
            var spawn = new WallSpawn
            {
                WallId = data.lineIndex * 100 + (int) data.type * 10 + data.width,
                Time = data.time,
                Duration = data.duration,
                LineIndex = data.lineIndex,
                LineLayer = (int) data.lineLayer,
                Width = data.width,
                Height = data.height,
            };
            if (_started) _feed.SpawnWall(LiveClock.NowUs(), spawn);
            else _pendingWalls.Add(spawn);
        }

        private void OnHeadEnteredObstacle(ObstacleController obstacle)
        {
            if (!_started || _ended || _inWall || !_walls.TryGetValue(obstacle, out var wall))
            {
                return;
            }

            wall.Time = _timeSync.songTime;
            _currentWall = wall;
            _inWall = true;
        }

        private void OnPause()
        {
            if (!_started || _ended)
            {
                return;
            }

            _paused = true;
            _feed.Pause(LiveClock.NowUs(), _timeSync.songTime);
        }

        private void OnResume()
        {
            if (!_paused || _ended)
            {
                return;
            }

            _paused = false;
            _feed.Resume(LiveClock.NowUs(), _timeSync.songTime);
        }

        private void OnPlayerHeightChanged(float height)
        {
            if (_started && !_ended)
            {
                _feed.Height(LiveClock.NowUs(), height, _timeSync.songTime);
            }
        }

        private void OnLevelFinished(StandardLevelScenesTransitionSetupDataSO data, LevelCompletionResults results)
        {
            End(results.levelEndAction == LevelCompletionResults.LevelEndAction.Restart ? SessionEndReason.Restarted
                : results.levelEndStateType == LevelCompletionResults.LevelEndStateType.Cleared ? SessionEndReason.Cleared
                : results.levelEndStateType == LevelCompletionResults.LevelEndStateType.Failed ? SessionEndReason.Failed
                : SessionEndReason.Quit);
        }

        private void End(SessionEndReason reason)
        {
            if (_ended)
            {
                return;
            }

            _ended = true;
            if (_started)
            {
                _feed.EndSession(reason, _timeSync.songTime);
            }
        }
    }
}
