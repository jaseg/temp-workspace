using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using LiveViewer.Server.Live;
using Newtonsoft.Json;

namespace LiveViewer.Server.Levels
{
    public enum LevelFileKind : byte
    {
        Cover = 1,
        Audio = 2,
    }

    /// <summary>
    /// The installed custom levels, scanned from level folders (e.g. Beat Saber_Data/CustomLevels).
    /// <para>
    /// Security boundary: viewers address levels only by hash and files only by kind. For any level, only its cover
    /// image and song file (as named by its Info.dat, resolved inside its folder) can be read. Difficulty files
    /// are served only for the level being played, through the session's map files.
    /// </para>
    /// Scans run on the thread pool. Unchanged folders are not re-read; a scan older than
    /// <see cref="RescanAfter"/> is refreshed on the next request.
    /// </summary>
    public sealed class LevelLibrary
    {
        public const int MaxLevels = 10000;
        public static readonly TimeSpan RescanAfter = TimeSpan.FromSeconds(30);

        private readonly object _lock = new object();
        private volatile IReadOnlyList<string> _roots;
        private readonly ILiveLog _log;
        private readonly Dictionary<string, (string stamp, LevelInfo? level)> _byFolder = new Dictionary<string, (string, LevelInfo?)>();
        private Task<Snapshot>? _scan;
        private DateTime _scannedUtc;

        public LevelLibrary(IEnumerable<string> roots, ILiveLog log)
        {
            _roots = roots.Select(Path.GetFullPath).ToList();
            _log = log;
        }

        public bool Enabled => _roots.Count > 0;

        /// <summary>
        /// When set, describes level folders from what the game already loaded (see <see cref="KnownLevel"/>); a
        /// folder it returns null for isn't listed, and is looked at again on the next scan. Called on a scan thread.
        /// </summary>
        public Func<string, KnownLevel?>? Known { get; set; }

        /// <summary>
        /// When set and false, the game hasn't loaded its levels yet: the list is empty and says it's loading, and the
        /// next request scans again.
        /// </summary>
        public Func<bool>? Ready { get; set; }

        /// <summary>A level id as the protocol uses it: the lowercase hex SHA-1 SongCore computes.</summary>
        public static bool IsLevelId(string? id) =>
            id != null && id.Length == 40 && id.All(c => (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'));

        /// <summary>
        /// Replaces the level folders (e.g. once the game's level loader has read its folder list). The next request
        /// rescans; levels in folders that stay are not re-read.
        /// </summary>
        public void SetRoots(IEnumerable<string> roots)
        {
            var list = roots.Select(Path.GetFullPath).Distinct(StringComparer.OrdinalIgnoreCase).ToList();
            lock (_lock)
            {
                if (list.SequenceEqual(_roots, StringComparer.OrdinalIgnoreCase))
                {
                    return;
                }

                _roots = list;
                _scannedUtc = DateTime.MinValue; // stale, also if a scan is running now

            }

            _log.Info("Level folders: " + string.Join(", ", list));
        }

        public sealed class Snapshot
        {
            public IReadOnlyList<LevelInfo> Levels = Array.Empty<LevelInfo>();
            public Dictionary<string, LevelInfo> ByHash = new Dictionary<string, LevelInfo>();

            /// <summary>The list as sent to viewers (UTF-8 JSON).</summary>
            public byte[] Json = Array.Empty<byte>();
        }

        /// <summary>The current level list, scanning first if there is none or it's stale.</summary>
        public Task<Snapshot> GetAsync()
        {
            lock (_lock)
            {
                var stale = _scan == null || _scan.IsFaulted || (_scan.IsCompleted && DateTime.UtcNow - _scannedUtc > RescanAfter);
                if (stale)
                {
                    _scan = Task.Run(Scan);
                }

                return _scan!;
            }
        }

        /// <summary>Opens a level's cover or song file. Returns false if the level or file isn't known.</summary>
        public static bool TryOpen(Snapshot snapshot, string hash, LevelFileKind kind, out Stream stream)
        {
            stream = Stream.Null;
            if (!snapshot.ByHash.TryGetValue(hash, out var level))
            {
                return false;
            }

            var name = kind == LevelFileKind.Cover ? level.CoverFile : kind == LevelFileKind.Audio ? level.AudioFile : null;
            return name != null && new MapDirectory(level.Directory, new[] { name }).TryOpen(name, out stream);
        }

        private Snapshot Scan()
        {
            if (Ready != null && !Ready())
            {
                lock (_lock)
                {
                    _scannedUtc = DateTime.MinValue;
                }

                return new Snapshot { Json = ToJson(Array.Empty<LevelInfo>(), loading: true) };
            }

            var started = DateTime.UtcNow;
            var levels = new List<LevelInfo>();
            var seen = new HashSet<string>();
            var roots = _roots;
            foreach (var root in roots)
            {
                IEnumerable<string> folders;
                try
                {
                    folders = Directory.EnumerateDirectories(root).ToList();
                }
                catch (Exception e) when (e is IOException || e is UnauthorizedAccessException)
                {
                    _log.Warn($"Can't list levels in {root}: {e.Message}");
                    continue;
                }

                foreach (var folder in folders)
                {
                    if (levels.Count >= MaxLevels)
                    {
                        break;
                    }

                    seen.Add(folder);
                    var level = ReadCached(folder);
                    if (level != null)
                    {
                        levels.Add(level);
                    }
                }
            }

            lock (_lock)
            {
                foreach (var gone in _byFolder.Keys.Where(k => !seen.Contains(k)).ToList())
                {
                    _byFolder.Remove(gone);
                }

                // If the folders changed during the scan, the next request scans again.
                _scannedUtc = ReferenceEquals(roots, _roots) ? DateTime.UtcNow : DateTime.MinValue;
            }

            var snapshot = new Snapshot { Levels = levels };
            foreach (var level in levels)
            {
                // Duplicate copies of a level share a hash; the first one wins.
                if (!snapshot.ByHash.ContainsKey(level.Hash))
                {
                    snapshot.ByHash[level.Hash] = level;
                }
            }

            snapshot.Json = ToJson(snapshot.ByHash.Values);
            _log.Info($"Level library: {snapshot.ByHash.Count} levels in {(DateTime.UtcNow - started).TotalSeconds:0.0} s.");
            return snapshot;
        }

        private LevelInfo? ReadCached(string folder)
        {
            string stamp;
            try
            {
                // Any change to a file's size or write time re-reads the folder.
                var sb = new StringBuilder();
                foreach (var f in new DirectoryInfo(folder).EnumerateFiles().OrderBy(f => f.Name, StringComparer.Ordinal))
                {
                    sb.Append(f.Name).Append('|').Append(f.Length).Append('|').Append(f.LastWriteTimeUtc.Ticks).Append('\n');
                }

                stamp = sb.ToString();
            }
            catch (Exception e) when (e is IOException || e is UnauthorizedAccessException)
            {
                return null;
            }

            lock (_lock)
            {
                if (_byFolder.TryGetValue(folder, out var cached) && cached.stamp == stamp)
                {
                    return cached.level;
                }
            }

            var describe = Known;
            KnownLevel? known = null;
            if (describe != null)
            {
                known = describe(folder);
                if (known == null)
                {
                    return null;
                }
            }

            LevelInfo? level = null;
            try
            {
                level = LevelReader.Read(folder, known);
            }
            catch (Exception e)
            {
                // Level folders are downloaded content: one broken level must not break the list.
                _log.Warn($"Can't read level {Path.GetFileName(folder)}: {e.Message}");
            }

            lock (_lock)
            {
                _byFolder[folder] = (stamp, level);
            }

            return level;
        }

        internal static byte[] ToJson(IEnumerable<LevelInfo> levels, bool loading = false)
        {
            var sw = new StringWriter();
            using (var w = new JsonTextWriter(sw) { StringEscapeHandling = StringEscapeHandling.EscapeHtml })
            {
                w.WriteStartObject();
                w.WritePropertyName("levels");
                w.WriteStartArray();
                foreach (var l in levels)
                {
                    w.WriteStartObject();
                    Field(w, "id", l.Hash);
                    Field(w, "songName", l.SongName);
                    Field(w, "songSubName", l.SongSubName);
                    Field(w, "songAuthor", l.SongAuthor);
                    Field(w, "mapper", l.Mapper);
                    Field(w, "environment", l.Environment);
                    Field(w, "bpm", l.Bpm);
                    Field(w, "duration", l.Duration);
                    Field(w, "previewStart", l.PreviewStart);
                    Field(w, "previewDuration", l.PreviewDuration);
                    w.WritePropertyName("hasCover");
                    w.WriteValue(l.CoverFile != null);
                    w.WritePropertyName("hasAudio");
                    w.WriteValue(l.AudioFile != null);
                    w.WritePropertyName("added");
                    w.WriteValue(l.Added);
                    w.WritePropertyName("difficulties");
                    w.WriteStartArray();
                    foreach (var d in l.Difficulties)
                    {
                        w.WriteStartObject();
                        Field(w, "mode", d.Mode);
                        Field(w, "difficulty", d.Difficulty);
                        Field(w, "label", d.Label);
                        Field(w, "njs", d.NoteJumpSpeed);
                        Field(w, "offset", d.Offset);
                        Count(w, "notes", d.Notes);
                        Count(w, "bombs", d.Bombs);
                        Count(w, "walls", d.Walls);
                        w.WriteEndObject();
                    }

                    w.WriteEndArray();
                    w.WriteEndObject();
                }

                w.WriteEndArray();
                if (loading)
                {
                    w.WritePropertyName("loading");
                    w.WriteValue(true);
                }

                w.WriteEndObject();
            }

            return Encoding.UTF8.GetBytes(sw.ToString());
        }

        private static void Field(JsonWriter w, string name, string value)
        {
            w.WritePropertyName(name);
            w.WriteValue(value);
        }

        private static void Field(JsonWriter w, string name, double value)
        {
            w.WritePropertyName(name);
            w.WriteValue(Math.Round(value, 3));
        }

        private static void Count(JsonWriter w, string name, int value)
        {
            w.WritePropertyName(name);
            if (value < 0)
            {
                w.WriteNull();
            }
            else
            {
                w.WriteValue(value);
            }
        }
    }
}
