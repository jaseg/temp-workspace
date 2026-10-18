using System;
using System.IO;
using System.IO.Compression;
using System.Threading.Tasks;
using LiveViewer.Host;
using Xunit;

namespace LiveViewer.Server.Tests
{
    public sealed class MapFolderTests : IDisposable
    {
        private readonly string _root = Directory.CreateTempSubdirectory().FullName;

        public void Dispose() => Directory.Delete(_root, true);

        [Theory]
        [InlineData("../../victim")]
        [InlineData("abc")]
        [InlineData("000000000000000000000000000000000000000g")]
        public async Task RejectsAnythingExceptASha1Hash(string hash)
        {
            var cache = Path.Combine(_root, "cache");
            var victim = Path.Combine(_root, "victim.tmp");
            Directory.CreateDirectory(victim);
            File.WriteAllText(Path.Combine(victim, "marker"), "keep");

            await Assert.ThrowsAsync<ArgumentException>(() =>
                MapFolder.ResolveAsync(null, hash, cache, "Standard", "Expert"));

            Assert.Equal("keep", File.ReadAllText(Path.Combine(victim, "marker")));
        }

        [Fact]
        public async Task ExtractsAValidFlatArchiveIntoTheHashDirectory()
        {
            var archivePath = Path.Combine(_root, "map.zip");
            using (var file = File.Create(archivePath))
            using (var archive = new ZipArchive(file, ZipArchiveMode.Create))
            using (var writer = new StreamWriter(archive.CreateEntry("Info.dat").Open()))
            {
                writer.Write("{}");
            }

            var hash = new string('a', 40);
            var cache = Path.Combine(_root, "cache");
            var map = await MapFolder.ResolveAsync(archivePath, hash, cache, "Standard", "Expert");

            Assert.Equal(Path.GetFullPath(Path.Combine(cache, "maps", hash)), map.Directory);
            Assert.Equal("{}", File.ReadAllText(Path.Combine(map.Directory, "Info.dat")));
            Assert.Empty(Directory.GetDirectories(Path.Combine(cache, "maps"), ".*.tmp"));
        }
    }
}
