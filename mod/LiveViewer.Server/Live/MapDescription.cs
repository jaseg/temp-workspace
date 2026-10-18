using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using LiveViewer.Server.Levels;

namespace LiveViewer.Server.Live
{
    /// <summary>
    /// The files of a custom level folder that viewers of a session may download, by role ("info", "audio",
    /// "difficulty", ...), read from its Info.dat (v2, v3 or v4). Names are the real on-disk names.
    /// </summary>
    public sealed class MapDescription
    {
        public string Directory = "";
        public Dictionary<string, string> Files = new Dictionary<string, string>();
        public float NoteJumpSpeed;
        public float BeatsPerMinute;
        public string SongSubName = "";
        public string SongAuthor = "";

        public IMapFileSource Source => new MapDirectory(Directory, Files.Values);

        /// <summary>
        /// Describes the level in <paramref name="directory"/> for one difficulty. Throws if Info.dat is missing,
        /// too large or not JSON.
        /// </summary>
        public static MapDescription Read(string directory, string mode, string difficulty)
        {
            var names = System.IO.Directory.EnumerateFiles(directory).Select(Path.GetFileName).ToList();
            var infoName = names.FirstOrDefault(n => string.Equals(n, "info.dat", StringComparison.OrdinalIgnoreCase))
                           ?? throw new FileNotFoundException("No Info.dat in " + directory);
            var infoPath = Path.Combine(directory, infoName);
            if (new FileInfo(infoPath).Length > LevelReader.MaxInfoBytes)
            {
                throw new InvalidDataException("Info.dat is too large.");
            }

            var map = new MapDescription { Directory = directory };
            map.Files["info"] = infoName;
            void Add(string role, string? file)
            {
                // Info.dat names files case-insensitively in practice; serve them under their real names.
                var actual = string.IsNullOrEmpty(file)
                    ? null
                    : names.FirstOrDefault(n => string.Equals(n, file, StringComparison.OrdinalIgnoreCase));
                if (actual != null)
                {
                    map.Files[role] = actual;
                }
            }

            var root = JObject.Parse(File.ReadAllText(infoPath));
            if (root["_difficultyBeatmapSets"] is JArray sets)
            {
                // v2/v3 info
                Add("audio", Str(root, "_songFilename"));
                Add("cover", Str(root, "_coverImageFilename"));
                map.SongSubName = Str(root, "_songSubName") ?? "";
                map.SongAuthor = Str(root, "_songAuthorName") ?? "";
                map.BeatsPerMinute = Num(root, "_beatsPerMinute");
                foreach (var set in sets.OfType<JObject>())
                {
                    var characteristic = Str(set, "_beatmapCharacteristicName") ?? "";
                    foreach (var diff in (set["_difficultyBeatmaps"] as JArray ?? new JArray()).OfType<JObject>())
                    {
                        var name = Str(diff, "_difficulty") ?? "";
                        var file = Str(diff, "_beatmapFilename");
                        Add($"beatmap:{characteristic}:{name}", file);
                        if (Matches(characteristic, mode) && Matches(name, difficulty))
                        {
                            Add("difficulty", file);
                            map.NoteJumpSpeed = Num(diff, "_noteJumpMovementSpeed");
                        }
                    }
                }
            }
            else
            {
                // v4 info
                if (root["audio"] is JObject audio)
                {
                    Add("audio", Str(audio, "songFilename"));
                    Add("audioData", Str(audio, "audioDataFilename"));
                    map.BeatsPerMinute = Num(audio, "bpm");
                }

                Add("cover", Str(root, "coverImageFilename"));
                if (root["song"] is JObject song)
                {
                    map.SongSubName = Str(song, "subTitle") ?? "";
                    map.SongAuthor = Str(song, "author") ?? "";
                }

                foreach (var diff in (root["difficultyBeatmaps"] as JArray ?? new JArray()).OfType<JObject>())
                {
                    var characteristic = Str(diff, "characteristic") ?? "";
                    var name = Str(diff, "difficulty") ?? "";
                    var file = Str(diff, "beatmapDataFilename");
                    Add($"beatmap:{characteristic}:{name}", file);
                    Add($"lightshow:{characteristic}:{name}", Str(diff, "lightshowDataFilename"));
                    if (Matches(characteristic, mode) && Matches(name, difficulty))
                    {
                        Add("difficulty", file);
                        Add("lightshow", Str(diff, "lightshowDataFilename"));
                        map.NoteJumpSpeed = Num(diff, "noteJumpMovementSpeed");
                    }
                }
            }

            return map;
        }

        private static bool Matches(string a, string b) => string.Equals(a, b, StringComparison.OrdinalIgnoreCase);

        private static string? Str(JObject o, string name) => o[name] is JValue { Type: JTokenType.String } v ? (string?) v : null;

        private static float Num(JObject o, string name) =>
            o[name] is JValue { Type: JTokenType.Float or JTokenType.Integer } v ? (float) v : 0;
    }
}
