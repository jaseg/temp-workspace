using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using LiveViewer.Server.Live;
using LiveViewer.Server.Protocol;

namespace LiveViewer.Host
{
    /// <summary>
    /// Plays a BSOR replay into a <see cref="LiveFeed"/> in real time, emitting events the way the game would:
    /// one pose per recorded frame at its moment, note cuts immediately and their final scores a little later.
    /// </summary>
    public sealed class FakeLive
    {
        /// <summary>How long after a good cut the game finishes the swing rating (approximation).</summary>
        public const float SwingRatingDelay = 0.3f;

        /// <summary>
        /// How long before its time a note or wall is spawned. The game spawns them about a half jump plus the move
        /// time early (around 1 s); less than that tests late arrivals.
        /// </summary>
        public float SpawnLead { get; set; } = 3f;

        private readonly LiveFeed _feed;
        private readonly BsorReplay _replay;
        private readonly SessionInfo _session;
        private readonly IMapFileSource _map;
        private readonly double _speed;
        private readonly float _startAt;
        private readonly List<NoteSpawn> _noteSpawns;
        private readonly List<WallSpawn> _wallSpawns;
        private readonly List<SliderSpawn> _sliderSpawns;

        public FakeLive(LiveFeed feed, BsorReplay replay, SessionInfo session, IMapFileSource map,
            List<NoteSpawn> noteSpawns, List<WallSpawn> wallSpawns, List<SliderSpawn> sliderSpawns, double speed, float startAt = 0)
        {
            _sliderSpawns = sliderSpawns;
            _noteSpawns = noteSpawns;
            _wallSpawns = wallSpawns;
            _startAt = startAt;
            _feed = feed;
            _replay = replay;
            _session = session;
            _map = map;
            _speed = speed;
        }

        private enum Kind
        {
            Pose,
            NoteCut,
            NoteFinal,
            Wall,
            Height,
            Pause,
            NoteSpawn,
            WallSpawn,
            SliderSpawn,
        }

        private struct Scheduled
        {
            public float Time;
            public Kind Kind;
            public int Index;
        }

        public void Run(CancellationToken token)
        {
            var schedule = BuildSchedule();
            var frames = _replay.Frames;
            if (frames.Count == 0)
            {
                throw new InvalidOperationException("Replay has no frames.");
            }

            // Starting late skips everything before that point, as if the viewer had joined then.
            var songStart = Math.Max(frames[0].Time, _startAt);
            schedule = schedule.Where(item => item.Time >= _startAt || IsSpawn(item.Kind) && item.Time + SpawnLead >= _startAt)
                .Select(item => IsSpawn(item.Kind) && item.Time < songStart ? new Scheduled { Time = songStart, Kind = item.Kind, Index = item.Index } : item)
                .ToList();
            _feed.BeginSession(_session, _map);

            var clock = Stopwatch.StartNew();
            var pausedSeconds = 0.0;
            foreach (var item in schedule)
            {
                // Wall-clock moment this event happens at, accounting for song speed and pauses.
                var due = (item.Time - songStart) / _speed + pausedSeconds;
                if (!WaitUntil(clock, due, token))
                {
                    _feed.EndSession(SessionEndReason.Quit, item.Time);
                    return;
                }

                var now = LiveClock.NowUs();
                switch (item.Kind)
                {
                    case Kind.Pose:
                        var f = frames[item.Index];
                        _feed.Pose(now, f.Time, f.Head, f.Left, f.Right);
                        break;
                    case Kind.NoteCut:
                        var cut = _replay.Notes[item.Index];
                        cut.CutInfo.AfterCutRating = 0;
                        _feed.Note(false, now, cut);
                        break;
                    case Kind.NoteFinal:
                        _feed.Note(true, now, _replay.Notes[item.Index]);
                        break;
                    case Kind.Wall:
                        _feed.Wall(now, _replay.Walls[item.Index]);
                        break;
                    case Kind.Height:
                        var h = _replay.Heights[item.Index];
                        _feed.Height(now, h.Height, h.Time);
                        break;
                    case Kind.Pause:
                        var p = _replay.Pauses[item.Index];
                        _feed.Pause(now, p.Time);
                        var duration = Math.Min(p.Duration, 5);
                        pausedSeconds += duration;
                        if (!WaitUntil(clock, due + duration, token))
                        {
                            _feed.EndSession(SessionEndReason.Quit, p.Time);
                            return;
                        }

                        _feed.Resume(LiveClock.NowUs(), p.Time);
                        break;
                    case Kind.NoteSpawn:
                        _feed.SpawnNote(now, _noteSpawns[item.Index]);
                        break;
                    case Kind.WallSpawn:
                        _feed.SpawnWall(now, _wallSpawns[item.Index]);
                        break;
                    case Kind.SliderSpawn:
                        _feed.SpawnSlider(now, _sliderSpawns[item.Index]);
                        break;
                }
            }

            var failed = _replay.Info.FailTime > 0;
            _feed.EndSession(failed ? SessionEndReason.Failed : SessionEndReason.Cleared, frames[frames.Count - 1].Time);
        }

        private List<Scheduled> BuildSchedule()
        {
            var items = new List<Scheduled>();
            for (var i = 0; i < _replay.Frames.Count; i++)
            {
                items.Add(new Scheduled { Time = _replay.Frames[i].Time, Kind = Kind.Pose, Index = i });
            }

            for (var i = 0; i < _replay.Notes.Count; i++)
            {
                var note = _replay.Notes[i];
                if (note.EventType == NoteEventType.Good)
                {
                    items.Add(new Scheduled { Time = note.EventTime, Kind = Kind.NoteCut, Index = i });
                    items.Add(new Scheduled { Time = note.EventTime + SwingRatingDelay, Kind = Kind.NoteFinal, Index = i });
                }
                else
                {
                    items.Add(new Scheduled { Time = note.EventTime, Kind = Kind.NoteFinal, Index = i });
                }
            }

            for (var i = 0; i < _replay.Walls.Count; i++)
            {
                items.Add(new Scheduled { Time = _replay.Walls[i].Time, Kind = Kind.Wall, Index = i });
            }

            for (var i = 0; i < _replay.Heights.Count; i++)
            {
                items.Add(new Scheduled { Time = _replay.Heights[i].Time, Kind = Kind.Height, Index = i });
            }

            for (var i = 0; i < _replay.Pauses.Count; i++)
            {
                items.Add(new Scheduled { Time = _replay.Pauses[i].Time, Kind = Kind.Pause, Index = i });
            }

            for (var i = 0; i < _noteSpawns.Count; i++)
            {
                items.Add(new Scheduled { Time = _noteSpawns[i].Time - SpawnLead, Kind = Kind.NoteSpawn, Index = i });
            }

            for (var i = 0; i < _wallSpawns.Count; i++)
            {
                items.Add(new Scheduled { Time = _wallSpawns[i].Time - SpawnLead, Kind = Kind.WallSpawn, Index = i });
            }

            for (var i = 0; i < _sliderSpawns.Count; i++)
            {
                // Like the game's recorder: arcs and chains go out ahead of the notes.
                items.Add(new Scheduled { Time = _sliderSpawns[i].Time - Math.Max(SpawnLead, 3f), Kind = Kind.SliderSpawn, Index = i });
            }

            // Stable order: events at the same time keep their kind order (pose first).
            return items.Select((item, order) => (item, order))
                .OrderBy(x => x.item.Time).ThenBy(x => x.order)
                .Select(x => x.item).ToList();
        }

        private static bool IsSpawn(Kind kind) => kind == Kind.NoteSpawn || kind == Kind.WallSpawn || kind == Kind.SliderSpawn;

        /// <summary>Sleeps until shortly before the deadline, then spins, for sub-millisecond release times.</summary>
        private static bool WaitUntil(Stopwatch clock, double seconds, CancellationToken token)
        {
            while (true)
            {
                if (token.IsCancellationRequested)
                {
                    return false;
                }

                var remaining = seconds - clock.Elapsed.TotalSeconds;
                if (remaining <= 0)
                {
                    return true;
                }

                if (remaining > 0.002)
                {
                    Thread.Sleep(TimeSpan.FromSeconds(Math.Min(remaining - 0.0015, 0.1)));
                }
                else
                {
                    Thread.SpinWait(50);
                }
            }
        }
    }
}
