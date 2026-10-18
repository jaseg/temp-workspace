using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace LiveViewer.Server.Levels
{
    /// <summary>One installed custom level, as listed to viewers.</summary>
    public sealed class LevelInfo
    {
        /// <summary>SongCore-style level hash (lowercase hex SHA-1). Also the level's id in the protocol.</summary>
        public string Hash = "";

        public string Directory = "";
        public string SongName = "";
        public string SongSubName = "";
        public string SongAuthor = "";
        public string Mapper = "";
        public string Environment = "";
        public double Bpm;

        /// <summary>Song length in seconds; 0 if unknown.</summary>
        public double Duration;

        public double PreviewStart;
        public double PreviewDuration;

        /// <summary>Real on-disk names, or null if the file is missing. Only these two files are served for a level.</summary>
        public string? CoverFile;
        public string? AudioFile;

        /// <summary>Last write time of Info.dat, as Unix seconds (for "recently added").</summary>
        public long Added;

        public List<DifficultyInfo> Difficulties = new List<DifficultyInfo>();
    }

    public sealed class DifficultyInfo
    {
        public string Mode = "";
        public string Difficulty = "";
        public string Label = "";
        public double NoteJumpSpeed;
        public double Offset;

        /// <summary>Object counts; -1 when the difficulty file couldn't be read.</summary>
        public int Notes = -1;
        public int Bombs = -1;
        public int Walls = -1;
    }

    /// <summary>
    /// What the game already knows about a level folder (in the game: SongCore's hash and the game's object counts),
    /// so reading the folder needs only Info.dat. Hashing and counting otherwise read every difficulty file, which in
    /// the game's garbage collector grows the heap by gigabytes over a large library.
    /// </summary>
    public sealed class KnownLevel
    {
        public string Hash = "";

        /// <summary>Song length in seconds, 0 if unknown.</summary>
        public double Duration;

        /// <summary>Object counts by "Mode/Difficulty" (as named in Info.dat), compared ignoring case.</summary>
        public Dictionary<string, (int notes, int bombs, int walls)> Counts =
            new Dictionary<string, (int, int, int)>(StringComparer.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Reads a level folder: Info.dat (v2, v3 or v4), object counts from each difficulty file, the SongCore hash and
    /// the song length. Everything here is untrusted input from downloaded maps, so sizes are capped and every
    /// field is optional.
    /// </summary>
    public static class LevelReader
    {
        public const long MaxInfoBytes = 1024 * 1024;
        public const long MaxDifficultyBytes = 64L * 1024 * 1024;

        /// <summary>
        /// Returns null if the folder has no readable Info.dat. With <paramref name="known"/>, takes the hash, counts
        /// and length from it instead of reading the difficulty and audio files.
        /// </summary>
        public static LevelInfo? Read(string directory, KnownLevel? known = null)
        {
            // Difficulty and audio files are files the game's level loader may guard (see GameFileAccess).
            using (GameFileAccess.Enter())
            {
                return ReadLevel(directory, known);
            }
        }

        private static LevelInfo? ReadLevel(string directory, KnownLevel? known)
        {
            var files = System.IO.Directory.EnumerateFiles(directory).Select(Path.GetFileName).ToList();
            var infoName = files.FirstOrDefault(n => string.Equals(n, "info.dat", StringComparison.OrdinalIgnoreCase));
            if (infoName == null)
            {
                return null;
            }

            var infoPath = Path.Combine(directory, infoName);
            var infoFile = new FileInfo(infoPath);
            if (infoFile.Length > MaxInfoBytes)
            {
                return null;
            }

            // SongCore hashes the text as the game read it (File.ReadAllText: BOM stripped, invalid UTF-8 replaced),
            // re-encoded as UTF-8, not the raw file.
            var infoText = File.ReadAllText(infoPath);
            var infoBytes = System.Text.Encoding.UTF8.GetBytes(infoText);
            JObject root;
            try
            {
                root = JObject.Parse(infoText);
            }
            catch (JsonException)
            {
                return null;
            }

            string? Actual(string? name) => string.IsNullOrEmpty(name)
                ? null
                : files.FirstOrDefault(n => string.Equals(n, name, StringComparison.OrdinalIgnoreCase));

            var level = new LevelInfo
            {
                Directory = directory,
                Added = new DateTimeOffset(infoFile.LastWriteTimeUtc).ToUnixTimeSeconds(),
            };

            // Files hashed after Info.dat, in SongCore's order. A file listed twice is hashed twice, as SongCore does.
            var hashed = new List<string>();
            var difficultyFiles = new List<(DifficultyInfo info, string? file)>();

            if (root["_difficultyBeatmapSets"] is JArray sets)
            {
                // v2 / v3 Info.dat
                level.SongName = Str(root, "_songName");
                level.SongSubName = Str(root, "_songSubName");
                level.SongAuthor = Str(root, "_songAuthorName");
                level.Mapper = Str(root, "_levelAuthorName");
                level.Environment = Str(root, "_environmentName");
                level.Bpm = Num(root, "_beatsPerMinute");
                level.PreviewStart = Num(root, "_previewStartTime");
                level.PreviewDuration = Num(root, "_previewDuration");
                level.CoverFile = Actual(Str(root, "_coverImageFilename"));
                level.AudioFile = Actual(Str(root, "_songFilename"));
                foreach (var set in sets.OfType<JObject>())
                {
                    var mode = Str(set, "_beatmapCharacteristicName");
                    if (!(set["_difficultyBeatmaps"] is JArray beatmaps))
                    {
                        continue;
                    }

                    foreach (var d in beatmaps.OfType<JObject>())
                    {
                        var file = Actual(Str(d, "_beatmapFilename"));
                        if (file != null)
                        {
                            hashed.Add(file);
                        }

                        difficultyFiles.Add((new DifficultyInfo
                        {
                            Mode = mode,
                            Difficulty = Str(d, "_difficulty"),
                            Label = d["_customData"] is JObject custom ? Str(custom, "_difficultyLabel") : "",
                            NoteJumpSpeed = Num(d, "_noteJumpMovementSpeed"),
                            Offset = Num(d, "_noteJumpStartBeatOffset"),
                        }, file));
                    }
                }
            }
            else if (root["difficultyBeatmaps"] is JArray beatmaps)
            {
                // v4 Info.dat
                var song = root["song"] as JObject;
                var audio = root["audio"] as JObject;
                level.SongName = song != null ? Str(song, "title") : "";
                level.SongSubName = song != null ? Str(song, "subTitle") : "";
                level.SongAuthor = song != null ? Str(song, "author") : "";
                level.Bpm = audio != null ? Num(audio, "bpm") : 0;
                level.Duration = audio != null ? Num(audio, "songDuration") : 0;
                level.PreviewStart = audio != null ? Num(audio, "previewStartTime") : 0;
                level.PreviewDuration = audio != null ? Num(audio, "previewDuration") : 0;
                level.CoverFile = Actual(Str(root, "coverImageFilename"));
                level.AudioFile = Actual(audio != null ? Str(audio, "songFilename") : null);
                if (root["environmentNames"] is JArray environments && environments.Count > 0)
                {
                    level.Environment = environments[0].Type == JTokenType.String ? (string) environments[0]! : "";
                }

                var audioData = Actual(audio != null ? Str(audio, "audioDataFilename") : null);
                if (audioData != null)
                {
                    hashed.Add(audioData);
                }

                var mappers = new List<string>();
                foreach (var d in beatmaps.OfType<JObject>())
                {
                    var file = Actual(Str(d, "beatmapDataFilename"));
                    var lightshow = Actual(Str(d, "lightshowDataFilename"));
                    hashed.AddRange(new[] { file, lightshow }.Where(f => f != null)!);

                    if (d["beatmapAuthors"] is JObject authors && authors["mappers"] is JArray names)
                    {
                        mappers.AddRange(names.Where(n => n.Type == JTokenType.String).Select(n => (string) n!).Where(n => !mappers.Contains(n)));
                    }

                    difficultyFiles.Add((new DifficultyInfo
                    {
                        Mode = Str(d, "characteristic"),
                        Difficulty = Str(d, "difficulty"),
                        Label = d["customData"] is JObject custom ? Str(custom, "difficultyLabel") : "",
                        NoteJumpSpeed = Num(d, "noteJumpMovementSpeed"),
                        Offset = Num(d, "noteJumpStartBeatOffset"),
                    }, file));
                }

                level.Mapper = string.Join(", ", mappers);
            }
            else
            {
                return null;
            }

            if (known != null)
            {
                level.Hash = known.Hash;
                foreach (var (info, _) in difficultyFiles)
                {
                    if (known.Counts.TryGetValue(info.Mode + "/" + info.Difficulty, out var counts))
                    {
                        (info.Notes, info.Bombs, info.Walls) = counts;
                    }

                    level.Difficulties.Add(info);
                }

                if (known.Duration > 0)
                {
                    level.Duration = known.Duration;
                }

                return level;
            }

            using (var sha = SHA1.Create())
            {
                sha.TransformBlock(infoBytes, 0, infoBytes.Length, null, 0);
                foreach (var name in hashed)
                {
                    var path = Path.Combine(directory, name);
                    if (new FileInfo(path).Length > MaxDifficultyBytes)
                    {
                        continue;
                    }

                    var bytes = File.ReadAllBytes(path);
                    sha.TransformBlock(bytes, 0, bytes.Length, null, 0);
                }

                sha.TransformFinalBlock(new byte[0], 0, 0);
                level.Hash = string.Concat(sha.Hash.Select(b => b.ToString("x2")));
            }

            foreach (var (info, file) in difficultyFiles)
            {
                if (file != null)
                {
                    CountObjects(Path.Combine(directory, file), info);
                }

                level.Difficulties.Add(info);
            }

            if (level.Duration <= 0 && level.AudioFile != null)
            {
                level.Duration = AudioDuration.TryRead(Path.Combine(directory, level.AudioFile));
            }

            return level;
        }

        /// <summary>Counts notes, bombs and walls in a v2, v3 or v4 difficulty file, streaming (outside the game only).</summary>
        internal static void CountObjects(string path, DifficultyInfo info)
        {
            try
            {
                if (new FileInfo(path).Length > MaxDifficultyBytes)
                {
                    return;
                }

                int notes = 0, bombs = 0, walls = 0;
                using (var reader = new JsonTextReader(new StreamReader(path)))
                {
                    if (!reader.Read() || reader.TokenType != JsonToken.StartObject)
                    {
                        return;
                    }

                    while (reader.Read() && reader.TokenType == JsonToken.PropertyName)
                    {
                        var name = (string) reader.Value!;
                        if (!reader.Read())
                        {
                            return;
                        }

                        if (reader.TokenType != JsonToken.StartArray)
                        {
                            reader.Skip();
                            continue;
                        }

                        switch (name)
                        {
                            case "_notes":
                                // v2: one array, the type tells notes (0, 1) from bombs (3).
                                while (reader.Read() && reader.TokenType == JsonToken.StartObject)
                                {
                                    var note = JObject.Load(reader);
                                    var type = note["_type"]?.Type == JTokenType.Integer ? (int) note["_type"]! : -1;
                                    if (type == 0 || type == 1)
                                    {
                                        notes++;
                                    }
                                    else if (type == 3)
                                    {
                                        bombs++;
                                    }
                                }

                                break;
                            case "colorNotes":
                                notes += CountElements(reader);
                                break;
                            case "bombNotes":
                                bombs += CountElements(reader);
                                break;
                            case "_obstacles":
                            case "obstacles":
                                walls += CountElements(reader);
                                break;
                            default:
                                reader.Skip();
                                break;
                        }
                    }
                }

                info.Notes = notes;
                info.Bombs = bombs;
                info.Walls = walls;
            }
            catch (Exception e) when (e is IOException || e is JsonException || e is UnauthorizedAccessException)
            {
                // Counts stay unknown.
            }
        }

        /// <summary>Counts the elements of the array the reader is at the start of, and moves past it.</summary>
        private static int CountElements(JsonReader reader)
        {
            var count = 0;
            while (reader.Read() && reader.TokenType != JsonToken.EndArray)
            {
                count++;
                if (reader.TokenType == JsonToken.StartObject || reader.TokenType == JsonToken.StartArray)
                {
                    reader.Skip();
                }
            }

            return count;
        }

        private static string Str(JObject o, string name) =>
            o[name]?.Type == JTokenType.String ? (string) o[name]! : "";

        private static double Num(JObject o, string name)
        {
            var t = o[name];
            if (t == null || (t.Type != JTokenType.Float && t.Type != JTokenType.Integer))
            {
                return 0;
            }

            var value = (double) t;
            return double.IsNaN(value) || double.IsInfinity(value) ? 0 : value;
        }
    }

    /// <summary>Song length of an Ogg Vorbis file (.ogg / .egg) from its headers, without decoding.</summary>
    /// <summary>Song length from an Ogg Vorbis (.ogg/.egg) or WAV file's headers, without decoding.</summary>
    internal static class AudioDuration
    {
        public static double TryRead(string path)
        {
            try
            {
                using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
                {
                    var head = new byte[Math.Min(stream.Length, 4096)];
                    ReadFully(stream, head);
                    if (head.Length >= 12 && System.Text.Encoding.ASCII.GetString(head, 0, 4) == "RIFF"
                        && System.Text.Encoding.ASCII.GetString(head, 8, 4) == "WAVE")
                    {
                        return WavDuration(head, stream.Length);
                    }

                    var rate = SampleRate(head);
                    if (rate <= 0)
                    {
                        return 0;
                    }

                    // The last page's granule position is the total number of samples.
                    var tailLength = (int) Math.Min(stream.Length, 64 * 1024);
                    var tail = new byte[tailLength];
                    stream.Seek(-tailLength, SeekOrigin.End);
                    ReadFully(stream, tail);
                    for (var i = tail.Length - 14; i >= 0; i--)
                    {
                        if (tail[i] == 'O' && tail[i + 1] == 'g' && tail[i + 2] == 'g' && tail[i + 3] == 'S')
                        {
                            var granule = BitConverter.ToInt64(tail, i + 6);
                            return granule > 0 ? granule / (double) rate : 0;
                        }
                    }
                }
            }
            catch (Exception e) when (e is IOException || e is UnauthorizedAccessException || e is ArgumentException)
            {
            }

            return 0;
        }

        private static double WavDuration(byte[] head, long fileLength)
        {
            // Chunks after "RIFF<size>WAVE": "fmt " holds the byte rate; the "data" chunk's size gives the length.
            long byteRate = 0;
            for (var at = 12; at + 8 <= head.Length;)
            {
                var id = System.Text.Encoding.ASCII.GetString(head, at, 4);
                var size = BitConverter.ToUInt32(head, at + 4);
                if (id == "fmt " && at + 20 <= head.Length)
                {
                    byteRate = BitConverter.ToUInt32(head, at + 16);
                }
                else if (id == "data")
                {
                    // Some writers leave the size at 0 or 0xFFFFFFFF; then the data runs to the end of the file.
                    var bytes = size == 0 || size == uint.MaxValue ? fileLength - at - 8 : Math.Min(size, fileLength - at - 8);
                    return byteRate > 0 ? bytes / (double) byteRate : 0;
                }

                at += 8 + (int) Math.Min(size + (size & 1), int.MaxValue - at - 8);
            }

            return 0;
        }

        private static int SampleRate(byte[] head)
        {
            // First page: "OggS" header, segment table, then the identification packet "\x01vorbis".
            if (head.Length < 58 || head[0] != 'O' || head[1] != 'g' || head[2] != 'g' || head[3] != 'S')
            {
                return 0;
            }

            var packet = 27 + head[26];
            if (packet + 16 > head.Length || head[packet] != 1 || System.Text.Encoding.ASCII.GetString(head, packet + 1, 6) != "vorbis")
            {
                return 0;
            }

            return BitConverter.ToInt32(head, packet + 12);
        }

        private static void ReadFully(Stream stream, byte[] buffer)
        {
            var read = 0;
            while (read < buffer.Length)
            {
                var n = stream.Read(buffer, read, buffer.Length - read);
                if (n <= 0)
                {
                    throw new IOException("Unexpected end of file.");
                }

                read += n;
            }
        }
    }
}
