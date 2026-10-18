using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using LiveViewer.Server.Security;
using Newtonsoft.Json;

namespace LiveViewer.Server.Levels
{
    public sealed class Suggestion
    {
        /// <summary>The level's hash, as in the level list.</summary>
        public string Id = "";

        /// <summary>The device that suggested it (its browser description). Display only.</summary>
        public string By = "";

        public DateTime AddedUtc;
    }

    /// <summary>
    /// Levels viewers suggest for the player, shown in the game as a level pack. Any approved viewer may add or remove
    /// entries; the caller checks that a level is installed before adding it. Persisted next to the devices file.
    /// Thread-safe.
    /// </summary>
    public sealed class Suggestions
    {
        public const int MaxSuggestions = 100;

        private readonly object _lock = new object();
        private readonly string? _path;
        private readonly List<Suggestion> _entries = new List<Suggestion>();
        private byte[]? _json;

        /// <param name="path">File to persist to, or <c>null</c> to keep suggestions in memory only.</param>
        public Suggestions(string? path)
        {
            _path = path;
            if (path != null && File.Exists(path))
            {
                Load(path);
            }
        }

        /// <summary>Raised after an entry is added or removed (on the calling thread).</summary>
        public event Action? Changed;

        /// <summary>Oldest first.</summary>
        public IReadOnlyList<Suggestion> List()
        {
            lock (_lock)
            {
                return _entries.ToList();
            }
        }

        /// <summary>False if the level is already suggested or the list is full.</summary>
        public bool Add(string id, string by)
        {
            lock (_lock)
            {
                if (_entries.Count >= MaxSuggestions || _entries.Any(e => e.Id == id))
                {
                    return false;
                }

                _entries.Add(new Suggestion { Id = id, By = DeviceStore.Sanitize(by), AddedUtc = DateTime.UtcNow });
                Save();
            }

            Changed?.Invoke();
            return true;
        }

        public bool Remove(string id)
        {
            lock (_lock)
            {
                if (_entries.RemoveAll(e => e.Id == id) == 0)
                {
                    return false;
                }

                Save();
            }

            Changed?.Invoke();
            return true;
        }

        /// <summary>The list as sent to viewers (see "Suggestions" in PROTOCOL.md), HTML-escaped like the level list.</summary>
        public byte[] Json()
        {
            lock (_lock)
            {
                if (_json != null)
                {
                    return _json;
                }

                using var sw = new StringWriter(CultureInfo.InvariantCulture);
                using (var w = new JsonTextWriter(sw) { StringEscapeHandling = StringEscapeHandling.EscapeHtml })
                {
                    w.WriteStartObject();
                    w.WritePropertyName("levels");
                    w.WriteStartArray();
                    foreach (var e in _entries)
                    {
                        w.WriteStartObject();
                        w.WritePropertyName("id");
                        w.WriteValue(e.Id);
                        w.WritePropertyName("by");
                        w.WriteValue(e.By);
                        w.WritePropertyName("added");
                        w.WriteValue(new DateTimeOffset(e.AddedUtc).ToUnixTimeSeconds());
                        w.WriteEndObject();
                    }

                    w.WriteEndArray();
                    w.WritePropertyName("max");
                    w.WriteValue(MaxSuggestions);
                    w.WriteEndObject();
                }

                return _json = Encoding.UTF8.GetBytes(sw.ToString());
            }
        }

        private void Load(string path)
        {
            foreach (var line in File.ReadAllLines(path, Encoding.UTF8))
            {
                var parts = line.Split('\t');
                if (parts.Length != 3 || !LevelLibrary.IsLevelId(parts[0]) || _entries.Count >= MaxSuggestions
                    || _entries.Any(e => e.Id == parts[0]))
                {
                    continue;
                }

                try
                {
                    _entries.Add(new Suggestion
                    {
                        Id = parts[0],
                        AddedUtc = DateTime.Parse(parts[1], CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind),
                        By = DeviceStore.Sanitize(Encoding.UTF8.GetString(Convert.FromBase64String(parts[2]))),
                    });
                }
                catch (FormatException)
                {
                    // Skip damaged lines rather than refusing to start.
                }
            }
        }

        // Called with the lock held.
        private void Save()
        {
            _json = null;
            if (_path == null)
            {
                return;
            }

            var lines = _entries.Select(e => string.Join("\t",
                e.Id,
                e.AddedUtc.ToString("o", CultureInfo.InvariantCulture),
                Convert.ToBase64String(Encoding.UTF8.GetBytes(e.By))));
            var tmp = _path + ".tmp";
            File.WriteAllLines(tmp, lines, new UTF8Encoding(false));
            if (File.Exists(_path))
            {
                File.Delete(_path);
            }

            File.Move(tmp, _path);
        }
    }
}
