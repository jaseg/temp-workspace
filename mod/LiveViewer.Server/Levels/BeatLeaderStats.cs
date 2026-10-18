using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace LiveViewer.Server.Levels
{
    /// <summary>Fetches BeatLeader's map data for one hash. Returns null if BeatLeader doesn't know the map.</summary>
    public interface IBeatLeaderApi
    {
        Task<string?> GetMapByHashAsync(string hash, CancellationToken cancellation);
    }

    /// <summary>
    /// BeatLeader's public API (https://api.beatleader.com/map/hash/{hash}). Only ever called with the hash of an
    /// installed level, never with anything a viewer typed.
    /// </summary>
    public sealed class BeatLeaderHttpApi : IBeatLeaderApi, IDisposable
    {
        public const long MaxResponseBytes = 4 * 1024 * 1024;

        private readonly HttpClient _http;

        public BeatLeaderHttpApi(string baseUrl = "https://api.beatleader.com/")
        {
            _http = new HttpClient
            {
                BaseAddress = new Uri(baseUrl),
                Timeout = TimeSpan.FromSeconds(10),
                MaxResponseContentBufferSize = MaxResponseBytes,
            };
            _http.DefaultRequestHeaders.UserAgent.ParseAdd("BeatSaberLiveViewer/0.1");
        }

        public async Task<string?> GetMapByHashAsync(string hash, CancellationToken cancellation)
        {
            using (var response = await _http.GetAsync("map/hash/" + hash, cancellation).ConfigureAwait(false))
            {
                if (response.StatusCode == HttpStatusCode.NotFound)
                {
                    return null;
                }

                response.EnsureSuccessStatusCode();
                return await response.Content.ReadAsStringAsync().ConfigureAwait(false);
            }
        }

        public void Dispose() => _http.Dispose();
    }

    /// <summary>
    /// Per-level BeatLeader stats (star ratings, ranked status), fetched by the mod so the page only ever talks to
    /// the mod. Results are cached: successes for <see cref="CacheFor"/>, failures for <see cref="RetryAfter"/>.
    /// With a cache file, successes survive restarts: they're written a few seconds after they arrive and on
    /// <see cref="Flush"/>. At most two requests run at once.
    /// </summary>
    public sealed class BeatLeaderStats : IDisposable
    {
        public static readonly TimeSpan CacheFor = TimeSpan.FromDays(3.1);
        public static readonly TimeSpan RetryAfter = TimeSpan.FromMinutes(2);
        public static readonly TimeSpan SaveDelay = TimeSpan.FromSeconds(5);

        /// <summary>Larger entries in the cache file are ignored (a summary is well under 1 KB).</summary>
        public const int MaxEntryBytes = 64 * 1024;

        private readonly object _lock = new object();
        private readonly Dictionary<string, (DateTime fetchedUtc, Task<byte[]> result)> _cache = new Dictionary<string, (DateTime, Task<byte[]>)>();
        private readonly SemaphoreSlim _concurrency = new SemaphoreSlim(2);
        private readonly IBeatLeaderApi _api;
        private readonly ILiveLog _log;
        private readonly Func<DateTime> _utcNow;
        private readonly string? _path;
        private readonly Timer _saveTimer;
        private bool _dirty;

        /// <param name="cachePath">File to keep successful lookups in across restarts, or <c>null</c>.</param>
        public BeatLeaderStats(IBeatLeaderApi api, ILiveLog log, Func<DateTime>? utcNow = null, string? cachePath = null)
        {
            _api = api;
            _log = log;
            _utcNow = utcNow ?? (() => DateTime.UtcNow);
            _path = cachePath;
            _saveTimer = new Timer(_ => Flush(), null, Timeout.Infinite, Timeout.Infinite);
            if (_path != null && File.Exists(_path))
            {
                Load(_path);
            }
        }

        public void Dispose()
        {
            _saveTimer.Dispose();
            Flush();
        }

        /// <summary>Writes the cache file now if anything changed. Thread-safe.</summary>
        public void Flush()
        {
            if (_path == null)
            {
                return;
            }

            List<string> lines;
            lock (_lock)
            {
                if (!_dirty)
                {
                    return;
                }

                _dirty = false;
                var now = _utcNow();
                lines = _cache
                    .Where(e => e.Value.result.Status == TaskStatus.RanToCompletion && now - e.Value.fetchedUtc < CacheFor)
                    .Select(e => string.Join("\t", e.Key, e.Value.fetchedUtc.ToString("o", CultureInfo.InvariantCulture),
                        Convert.ToBase64String(e.Value.result.Result)))
                    .ToList();
            }

            try
            {
                var tmp = _path + ".tmp";
                File.WriteAllLines(tmp, lines, new UTF8Encoding(false));
                if (File.Exists(_path))
                {
                    File.Delete(_path);
                }

                File.Move(tmp, _path);
            }
            catch (Exception e) when (e is IOException || e is UnauthorizedAccessException)
            {
                _log.Warn("Couldn't save the BeatLeader stats cache: " + e.Message);
            }
        }

        private void Load(string path)
        {
            var now = _utcNow();
            try
            {
                foreach (var line in File.ReadAllLines(path, Encoding.UTF8))
                {
                    var parts = line.Split('\t');
                    if (parts.Length != 3 || !LevelLibrary.IsLevelId(parts[0]) || parts[2].Length > MaxEntryBytes * 4 / 3 + 4
                        || !DateTime.TryParse(parts[1], CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind, out var fetched)
                        || fetched > now || now - fetched >= CacheFor)
                    {
                        continue;
                    }

                    byte[] summary;
                    try
                    {
                        summary = Convert.FromBase64String(parts[2]);
                    }
                    catch (FormatException)
                    {
                        continue;
                    }

                    _cache[parts[0]] = (fetched, Task.FromResult(summary));
                }
            }
            catch (Exception e) when (e is IOException || e is UnauthorizedAccessException)
            {
                _log.Warn("Couldn't read the BeatLeader stats cache: " + e.Message);
            }
        }

        /// <summary>
        /// The stats document for a level hash (UTF-8 JSON, see PROTOCOL.md). Faults if BeatLeader can't be
        /// reached. The caller must only pass hashes of installed levels.
        /// </summary>
        public Task<byte[]> GetAsync(string hash)
        {
            var now = _utcNow();
            lock (_lock)
            {
                if (_cache.TryGetValue(hash, out var entry))
                {
                    var age = now - entry.fetchedUtc;
                    var keep = !entry.result.IsCompleted
                               || (entry.result.Status == TaskStatus.RanToCompletion ? age < CacheFor : age < RetryAfter);
                    if (keep)
                    {
                        return entry.result;
                    }
                }

                var task = FetchAsync(hash);
                _cache[hash] = (now, task);
                _ = task.ContinueWith(t => ScheduleSave(), TaskContinuationOptions.OnlyOnRanToCompletion);
                return task;
            }
        }

        private void ScheduleSave()
        {
            if (_path == null)
            {
                return;
            }

            lock (_lock)
            {
                _dirty = true;
            }

            _saveTimer.Change(SaveDelay, Timeout.InfiniteTimeSpan);
        }

        private async Task<byte[]> FetchAsync(string hash)
        {
            await _concurrency.WaitAsync().ConfigureAwait(false);
            try
            {
                using (var cancel = new CancellationTokenSource(TimeSpan.FromSeconds(15)))
                {
                    var json = await _api.GetMapByHashAsync(hash, cancel.Token).ConfigureAwait(false);
                    return Summarize(json);
                }
            }
            catch (Exception e)
            {
                _log.Warn($"BeatLeader stats for {hash} unavailable: {e.Message}");
                throw;
            }
            finally
            {
                _concurrency.Release();
            }
        }

        /// <summary>Keeps only the fields the page shows, re-encoded by us (BeatLeader's response is not passed through).</summary>
        internal static byte[] Summarize(string? json)
        {
            var sw = new StringWriter();
            using (var w = new JsonTextWriter(sw) { StringEscapeHandling = StringEscapeHandling.EscapeHtml })
            {
                w.WriteStartObject();
                JObject? map = null;
                if (json != null)
                {
                    try
                    {
                        map = JObject.Parse(json);
                    }
                    catch (JsonException)
                    {
                        throw new InvalidDataException("BeatLeader sent invalid JSON.");
                    }
                }

                w.WritePropertyName("found");
                w.WriteValue(map != null);
                if (map != null)
                {
                    w.WritePropertyName("key");
                    w.WriteValue(Str(map, "id"));
                    w.WritePropertyName("difficulties");
                    w.WriteStartArray();
                    if (map["difficulties"] is JArray difficulties)
                    {
                        foreach (var d in difficulties)
                        {
                            if (!(d is JObject o))
                            {
                                continue;
                            }

                            w.WriteStartObject();
                            w.WritePropertyName("mode");
                            w.WriteValue(Str(o, "modeName"));
                            w.WritePropertyName("difficulty");
                            w.WriteValue(Str(o, "difficultyName"));
                            w.WritePropertyName("status");
                            w.WriteValue(o["status"]?.Type == JTokenType.Integer ? (int) o["status"]! : 0);
                            Number(w, o, "stars", "stars");
                            Number(w, o, "passRating", "pass");
                            Number(w, o, "accRating", "acc");
                            Number(w, o, "techRating", "tech");
                            Number(w, o, "predictedAcc", "predictedAcc");
                            Number(w, o, "maxScore", "maxScore");
                            w.WriteEndObject();
                        }
                    }

                    w.WriteEndArray();
                }

                w.WriteEndObject();
            }

            return Encoding.UTF8.GetBytes(sw.ToString());
        }

        private static string Str(JObject o, string name) =>
            o[name]?.Type == JTokenType.String ? (string) o[name]! : "";

        private static void Number(JsonWriter w, JObject o, string from, string to)
        {
            w.WritePropertyName(to);
            var t = o[from];
            if (t != null && (t.Type == JTokenType.Float || t.Type == JTokenType.Integer))
            {
                var value = (double) t;
                if (!double.IsNaN(value) && !double.IsInfinity(value))
                {
                    w.WriteValue(Math.Round(value, 4));
                    return;
                }
            }

            w.WriteNull();
        }
    }
}
