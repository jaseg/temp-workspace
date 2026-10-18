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
        private const int HashLength = 40;
        private const int MaxArchiveBytes = 256 * 1024 * 1024;
        private const int MaxExtractedBytes = 256 * 1024 * 1024;
        private const int MaxArchiveEntries = 2048;

        /// <summary>Uses a folder or zip if given, otherwise downloads the map by hash into the cache.</summary>
        public static async Task<MapDescription> ResolveAsync(string? mapArgument, string hash, string cacheDirectory, string mode, string difficulty)
        {
            ValidateHash(hash);

            string directory;
            if (mapArgument != null && System.IO.Directory.Exists(mapArgument))
            {
                directory = mapArgument;
            }
            else
            {
                var mapsDirectory = Path.GetFullPath(Path.Combine(cacheDirectory, "maps"));
                directory = Path.GetFullPath(Path.Combine(mapsDirectory, hash.ToLowerInvariant()));
                EnsureContained(directory, mapsDirectory);
                if (!System.IO.Directory.Exists(directory))
                {
                    var zip = mapArgument != null && File.Exists(mapArgument)
                        ? await ReadArchiveAsync(mapArgument)
                        : await DownloadAsync(hash);
                    System.IO.Directory.CreateDirectory(mapsDirectory);
                    var tmp = Path.Combine(mapsDirectory, $".{hash.ToLowerInvariant()}.{Guid.NewGuid():N}.tmp");
                    try
                    {
                        System.IO.Directory.CreateDirectory(tmp);
                        await ExtractAsync(zip, tmp);
                        System.IO.Directory.Move(tmp, directory);
                    }
                    finally
                    {
                        if (System.IO.Directory.Exists(tmp))
                        {
                            System.IO.Directory.Delete(tmp, true);
                        }
                    }
                }
            }

            return MapDescription.Read(directory, mode, difficulty);
        }

        private static void ValidateHash(string hash)
        {
            if (hash == null || hash.Length != HashLength || hash.Any(c =>
                    (c < '0' || c > '9') && (c < 'a' || c > 'f') && (c < 'A' || c > 'F')))
            {
                throw new ArgumentException("Map hash must be a 40-character SHA-1 hexadecimal value.", nameof(hash));
            }
        }

        private static async Task<byte[]> ReadArchiveAsync(string path)
        {
            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 81920, true);
            return await ReadBoundedAsync(stream, stream.Length);
        }

        private static async Task ExtractAsync(byte[] zip, string destinationDirectory)
        {
            using var archive = new ZipArchive(new MemoryStream(zip), ZipArchiveMode.Read);
            if (archive.Entries.Count > MaxArchiveEntries)
            {
                throw new InvalidDataException($"Map archive contains more than {MaxArchiveEntries} entries.");
            }

            var extractedBytes = 0L;
            var destinationRoot = Path.GetFullPath(destinationDirectory);
            foreach (var entry in archive.Entries)
            {
                // Beat Saber maps are flat. Ignore wrapper directories as before, but validate every flat name.
                if (entry.FullName != entry.Name || entry.Name.Length == 0)
                {
                    continue;
                }

                if (Path.IsPathRooted(entry.Name) || entry.Name == "." || entry.Name == ".." ||
                    entry.Name.IndexOf('/') >= 0 || entry.Name.IndexOf('\\') >= 0 ||
                    entry.Name.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
                {
                    throw new InvalidDataException("Map archive contains an invalid file name.");
                }

                if (entry.Length > MaxExtractedBytes || extractedBytes + entry.Length > MaxExtractedBytes)
                {
                    throw new InvalidDataException("Map archive expands beyond the permitted size.");
                }

                var path = Path.GetFullPath(Path.Combine(destinationRoot, entry.Name));
                EnsureContained(path, destinationRoot);
                using var input = entry.Open();
                using var output = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None, 81920, true);
                var buffer = new byte[81920];
                while (true)
                {
                    var read = await input.ReadAsync(buffer, 0, buffer.Length);
                    if (read == 0)
                    {
                        break;
                    }

                    extractedBytes += read;
                    if (extractedBytes > MaxExtractedBytes)
                    {
                        throw new InvalidDataException("Map archive expands beyond the permitted size.");
                    }

                    await output.WriteAsync(buffer, 0, read);
                }
            }
        }

        private static void EnsureContained(string path, string directory)
        {
            var root = Path.GetFullPath(directory).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                + Path.DirectorySeparatorChar;
            var candidate = Path.GetFullPath(path);
            var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
            if (!candidate.StartsWith(root, comparison))
            {
                throw new InvalidDataException("Map cache path escapes its designated directory.");
            }
        }

        private static async Task<byte[]> ReadBoundedAsync(Stream stream, long? contentLength = null)
        {
            if (contentLength > MaxArchiveBytes)
            {
                throw new InvalidDataException("Map archive is larger than the permitted size.");
            }

            using var output = new MemoryStream(contentLength is > 0 and <= MaxArchiveBytes ? (int)contentLength.Value : 0);
            var buffer = new byte[81920];
            while (true)
            {
                var read = await stream.ReadAsync(buffer, 0, buffer.Length);
                if (read == 0)
                {
                    return output.ToArray();
                }

                if (output.Length + read > MaxArchiveBytes)
                {
                    throw new InvalidDataException("Map archive is larger than the permitted size.");
                }

                await output.WriteAsync(buffer, 0, read);
            }
        }

        private static async Task<byte[]> DownloadAsync(string hash)
        {
            using var http = new HttpClient();
            http.DefaultRequestHeaders.UserAgent.ParseAdd("BeatSaberLiveViewer-DevHost/0.1");
            try
            {
                Console.WriteLine($"Downloading map {hash} from BeatLeader's CDN...");
                return await DownloadArchiveAsync(http, $"https://cdn.songs.beatleader.xyz/{hash}.zip");
            }
            catch (HttpRequestException)
            {
                Console.WriteLine("Not on BeatLeader's CDN; asking BeatSaver...");
                using var doc = JsonDocument.Parse(await http.GetStringAsync($"https://api.beatsaver.com/maps/hash/{hash}"));
                var url = doc.RootElement.GetProperty("versions").EnumerateArray()
                    .First(v => string.Equals(v.GetProperty("hash").GetString(), hash, StringComparison.OrdinalIgnoreCase))
                    .GetProperty("downloadURL").GetString()!;
                return await DownloadArchiveAsync(http, url);
            }
        }

        private static async Task<byte[]> DownloadArchiveAsync(HttpClient http, string url)
        {
            using var response = await http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead);
            response.EnsureSuccessStatusCode();
            using var stream = await response.Content.ReadAsStreamAsync();
            return await ReadBoundedAsync(stream, response.Content.Headers.ContentLength);
        }
    }
}
