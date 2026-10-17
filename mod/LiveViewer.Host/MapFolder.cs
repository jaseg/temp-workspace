using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;

namespace LiveViewer.Host
{
    /// <summary>A custom map on disk, with the file roles the SessionStart message advertises.</summary>
    public sealed class MapFolder
    {
        public string Directory = "";
        public Dictionary<string, string> Files = new Dictionary<string, string>();
        public float NoteJumpSpeed;
        public string SongSubName = "";
        public string SongAuthor = "";

        /// <summary>Uses a folder or zip if given, otherwise downloads the map by hash into the cache.</summary>
        public static async Task<MapFolder> ResolveAsync(string? mapArgument, string hash, string cacheDirectory, string mode, string difficulty)
        {
            string directory;
            if (mapArgument != null && System.IO.Directory.Exists(mapArgument))
            {
                directory = mapArgument;
            }
            else
            {
                directory = Path.Combine(cacheDirectory, "maps", hash.ToLowerInvariant());
                if (!System.IO.Directory.Exists(directory))
                {
                    var zip = mapArgument != null && File.Exists(mapArgument)
                        ? await File.ReadAllBytesAsync(mapArgument)
                        : await DownloadAsync(hash);
                    var tmp = directory + ".tmp";
                    if (System.IO.Directory.Exists(tmp))
                    {
                        System.IO.Directory.Delete(tmp, true);
                    }

                    System.IO.Directory.CreateDirectory(tmp);
                    using (var archive = new ZipArchive(new MemoryStream(zip)))
                    {
                        // Flat maps only: entries with directories are ignored, which also rules out path traversal.
                        foreach (var entry in archive.Entries.Where(e => e.FullName == e.Name && e.Name.Length > 0))
                        {
                            entry.ExtractToFile(Path.Combine(tmp, entry.Name));
                        }
                    }

                    System.IO.Directory.Move(tmp, directory);
                }
            }

            return Describe(directory, mode, difficulty);
        }

        private static async Task<byte[]> DownloadAsync(string hash)
        {
            using var http = new HttpClient();
            http.DefaultRequestHeaders.UserAgent.ParseAdd("BeatSaberLiveViewer-DevHost/0.1");
            try
            {
                Console.WriteLine($"Downloading map {hash} from BeatLeader's CDN...");
                return await http.GetByteArrayAsync($"https://cdn.songs.beatleader.xyz/{hash}.zip");
            }
            catch (HttpRequestException)
            {
                Console.WriteLine("Not on BeatLeader's CDN; asking BeatSaver...");
                using var doc = JsonDocument.Parse(await http.GetStringAsync($"https://api.beatsaver.com/maps/hash/{hash}"));
                var url = doc.RootElement.GetProperty("versions").EnumerateArray()
                    .First(v => string.Equals(v.GetProperty("hash").GetString(), hash, StringComparison.OrdinalIgnoreCase))
                    .GetProperty("downloadURL").GetString()!;
                return await http.GetByteArrayAsync(url);
            }
        }

        /// <summary>Reads Info.dat (v2 or v4) and maps file roles to names.</summary>
        public static MapFolder Describe(string directory, string mode, string difficulty)
        {
            var infoName = System.IO.Directory.EnumerateFiles(directory)
                .Select(Path.GetFileName)
                .First(n => string.Equals(n, "info.dat", StringComparison.OrdinalIgnoreCase))!;
            var map = new MapFolder { Directory = directory };
            map.Files["info"] = infoName;

            using var doc = JsonDocument.Parse(File.ReadAllText(Path.Combine(directory, infoName)));
            var root = doc.RootElement;
            if (root.TryGetProperty("_difficultyBeatmapSets", out var sets))
            {
                // v2/v3 info
                Add(map, "audio", Str(root, "_songFilename"));
                Add(map, "cover", Str(root, "_coverImageFilename"));
                map.SongSubName = Str(root, "_songSubName") ?? "";
                map.SongAuthor = Str(root, "_songAuthorName") ?? "";
                foreach (var set in sets.EnumerateArray())
                {
                    var characteristic = Str(set, "_beatmapCharacteristicName") ?? "";
                    foreach (var diff in set.GetProperty("_difficultyBeatmaps").EnumerateArray())
                    {
                        var name = Str(diff, "_difficulty") ?? "";
                        var file = Str(diff, "_beatmapFilename");
                        Add(map, $"beatmap:{characteristic}:{name}", file);
                        if (Matches(characteristic, mode) && Matches(name, difficulty))
                        {
                            Add(map, "difficulty", file);
                            map.NoteJumpSpeed = diff.TryGetProperty("_noteJumpMovementSpeed", out var njs) ? njs.GetSingle() : 0;
                        }
                    }
                }
            }
            else
            {
                // v4 info
                if (root.TryGetProperty("audio", out var audio))
                {
                    Add(map, "audio", Str(audio, "songFilename"));
                    Add(map, "audioData", Str(audio, "audioDataFilename"));
                }

                Add(map, "cover", Str(root, "coverImageFilename"));
                if (root.TryGetProperty("song", out var song))
                {
                    map.SongSubName = Str(song, "subTitle") ?? "";
                    map.SongAuthor = Str(song, "author") ?? "";
                }

                foreach (var diff in root.GetProperty("difficultyBeatmaps").EnumerateArray())
                {
                    var characteristic = Str(diff, "characteristic") ?? "";
                    var name = Str(diff, "difficulty") ?? "";
                    var file = Str(diff, "beatmapDataFilename");
                    Add(map, $"beatmap:{characteristic}:{name}", file);
                    Add(map, $"lightshow:{characteristic}:{name}", Str(diff, "lightshowDataFilename"));
                    if (Matches(characteristic, mode) && Matches(name, difficulty))
                    {
                        Add(map, "difficulty", file);
                        Add(map, "lightshow", Str(diff, "lightshowDataFilename"));
                        map.NoteJumpSpeed = diff.TryGetProperty("noteJumpMovementSpeed", out var njs) ? njs.GetSingle() : 0;
                    }
                }
            }

            return map;
        }

        private static bool Matches(string a, string b) => string.Equals(a, b, StringComparison.OrdinalIgnoreCase);

        private static string? Str(JsonElement e, string name) =>
            e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;

        private static void Add(MapFolder map, string role, string? file)
        {
            if (string.IsNullOrEmpty(file))
            {
                return;
            }

            // Info.dat names files case-insensitively in practice; serve them under their real on-disk names.
            var actual = System.IO.Directory.EnumerateFiles(map.Directory)
                .Select(Path.GetFileName)
                .FirstOrDefault(n => string.Equals(n, file, StringComparison.OrdinalIgnoreCase));
            if (actual != null)
            {
                map.Files[role] = actual;
            }
        }
    }
}
