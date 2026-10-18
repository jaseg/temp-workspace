using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using LiveViewer.Server.Live;

namespace LiveViewer.Host
{
    /// <summary>Finds or downloads the custom map a replay was played on.</summary>
    public static class MapFolder
    {
        /// <summary>Uses a folder or zip if given, otherwise downloads the map by hash into the cache.</summary>
        public static async Task<MapDescription> ResolveAsync(string? mapArgument, string hash, string cacheDirectory, string mode, string difficulty)
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

            return MapDescription.Read(directory, mode, difficulty);
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
    }
}
