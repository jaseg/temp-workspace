using System.Threading;
using LiveViewer.Server.Protocol;

namespace LiveViewer.Server.Live
{
    /// <summary>
    /// Entry point for the game (or the fake-live source). Must be called from a single thread.
    /// Each call copies its data into a preallocated ring slot and wakes the network thread: no allocation,
    /// no I/O and no locks on the caller's side. If the ring is full the event is dropped and counted.
    /// </summary>
    public sealed class LiveFeed
    {
        internal enum Kind : byte
        {
            None,
            SessionStart,
            SessionEnd,
            SongSelected,
            Pose,
            NoteSpawn,
            WallSpawn,
            NoteCut,
            NoteFinal,
            Wall,
            Height,
            Pause,
            Resume,
        }

        internal struct Entry
        {
            public Kind Kind;
            public long CaptureUs;
            public float SongTime;
            public Pose Head, Left, Right;
            public NoteEvent Note;
            public NoteSpawn NoteSpawn;
            public WallEvent Wall;
            public WallSpawn WallSpawn;
            public float Height;
            public SessionEndReason EndReason;
            public SessionInfo? Session;
            public SongSelection? Selection;
        }

        private const int Capacity = 4096; // power of two; about 40 s of poses at 100 Hz

        private readonly Entry[] _ring = new Entry[Capacity];
        private readonly SemaphoreSlim _signal = new SemaphoreSlim(0, int.MaxValue);
        private long _head; // next slot to write (producer)
        private long _tail; // next slot to read (consumer)
        private long _dropped;

        public long Dropped => Interlocked.Read(ref _dropped);

        internal SemaphoreSlim Signal => _signal;

        public void BeginSession(SessionInfo info)
        {
            if (!TryClaim(Kind.SessionStart, out var index))
            {
                return;
            }

            ref var e = ref _ring[index];
            e.Session = info;
            Publish();
        }

        /// <summary>Compatibility helper for non-game hosts: publishes the map's audio, but no map data.</summary>
        public void BeginSession(SessionInfo info, IMapFileSource map)
        {
            if (info.Files.TryGetValue("audio", out var audio))
            {
                SelectSong(new SongSelection
                {
                    Hash = info.Hash,
                    SongName = info.SongName,
                    SongSubName = info.SongSubName,
                    SongAuthor = info.SongAuthor,
                    BeatsPerMinute = info.BeatsPerMinute,
                    Audio = new MapAudioFile(map, audio),
                });
            }
            BeginSession(info);
        }

        /// <summary>Makes a selected song available to approved browsers immediately, before gameplay starts.</summary>
        public void SelectSong(SongSelection selection)
        {
            if (!TryClaim(Kind.SongSelected, out var index)) return;
            _ring[index].Selection = selection;
            Publish();
        }

        public void EndSession(SessionEndReason reason, float songTime)
        {
            if (!TryClaim(Kind.SessionEnd, out var index))
            {
                return;
            }

            ref var e = ref _ring[index];
            e.EndReason = reason;
            e.SongTime = songTime;
            Publish();
        }

        /// <param name="captureUs">When the poses were sampled, from <see cref="LiveClock.NowUs"/>.</param>
        public void Pose(long captureUs, float songTime, in Pose head, in Pose left, in Pose right)
        {
            if (!TryClaim(Kind.Pose, out var index))
            {
                return;
            }

            ref var e = ref _ring[index];
            e.CaptureUs = captureUs;
            e.SongTime = songTime;
            e.Head = head;
            e.Left = left;
            e.Right = right;
            Publish();
        }

        /// <summary>
        /// A note was cut, missed or a bomb was hit. <paramref name="final"/> is false for the immediate cut event,
        /// whose after-cut rating is still incomplete; the final event for the same note follows later.
        /// </summary>
        public void Note(bool final, long captureUs, in NoteEvent note)
        {
            if (!TryClaim(final ? Kind.NoteFinal : Kind.NoteCut, out var index))
            {
                return;
            }

            ref var e = ref _ring[index];
            e.CaptureUs = captureUs;
            e.Note = note;
            Publish();
        }

        public void SpawnNote(long captureUs, in NoteSpawn note)
        {
            if (!TryClaim(Kind.NoteSpawn, out var index)) return;
            ref var e = ref _ring[index];
            e.CaptureUs = captureUs;
            e.NoteSpawn = note;
            Publish();
        }

        public void SpawnWall(long captureUs, in WallSpawn wall)
        {
            if (!TryClaim(Kind.WallSpawn, out var index)) return;
            ref var e = ref _ring[index];
            e.CaptureUs = captureUs;
            e.WallSpawn = wall;
            Publish();
        }

        public void Wall(long captureUs, in WallEvent wall)
        {
            if (!TryClaim(Kind.Wall, out var index))
            {
                return;
            }

            ref var e = ref _ring[index];
            e.CaptureUs = captureUs;
            e.Wall = wall;
            Publish();
        }

        public void Height(long captureUs, float height, float songTime)
        {
            if (!TryClaim(Kind.Height, out var index))
            {
                return;
            }

            ref var e = ref _ring[index];
            e.CaptureUs = captureUs;
            e.Height = height;
            e.SongTime = songTime;
            Publish();
        }

        public void Pause(long captureUs, float songTime) => PauseResume(Kind.Pause, captureUs, songTime);

        public void Resume(long captureUs, float songTime) => PauseResume(Kind.Resume, captureUs, songTime);

        private void PauseResume(Kind kind, long captureUs, float songTime)
        {
            if (!TryClaim(kind, out var index))
            {
                return;
            }

            ref var e = ref _ring[index];
            e.CaptureUs = captureUs;
            e.SongTime = songTime;
            Publish();
        }

        private bool TryClaim(Kind kind, out long index)
        {
            var head = _head;
            if (head - Volatile.Read(ref _tail) >= Capacity)
            {
                Interlocked.Increment(ref _dropped);
                index = 0;
                return false;
            }

            index = head & (Capacity - 1);
            _ring[index].Kind = kind;
            return true;
        }

        private void Publish()
        {
            Volatile.Write(ref _head, _head + 1);
            _signal.Release();
        }

        /// <summary>Consumer side: copies the next entry out, or returns false if the ring is empty.</summary>
        internal bool TryTake(out Entry entry)
        {
            var tail = _tail;
            if (tail >= Volatile.Read(ref _head))
            {
                entry = default;
                return false;
            }

            ref var slot = ref _ring[tail & (Capacity - 1)];
            entry = slot;
            slot.Session = null;
            slot.Selection = null;
            Volatile.Write(ref _tail, tail + 1);
            return true;
        }
    }
}
