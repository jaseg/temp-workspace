using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using LiveViewer.Server.Levels;
using Newtonsoft.Json.Linq;
using Xunit;

namespace LiveViewer.Server.Tests
{
    public class LevelTests : IDisposable
    {
        private readonly string _root = Directory.CreateTempSubdirectory().FullName;

        public void Dispose() => Directory.Delete(_root, true);

        private string Level(string name, params (string file, string content)[] files)
        {
            var dir = Path.Combine(_root, name);
            Directory.CreateDirectory(dir);
            foreach (var (file, content) in files)
            {
                File.WriteAllText(Path.Combine(dir, file), content);
            }

            return dir;
        }

        private static string Sha1(params string[] parts) =>
            string.Concat(SHA1.HashData(Encoding.UTF8.GetBytes(string.Concat(parts))).Select(b => b.ToString("x2")));

        private const string V2Info = @"{""_version"":""2.0.0"",""_songName"":""Song"",""_songSubName"":""Sub"",""_songAuthorName"":""Artist"",
            ""_levelAuthorName"":""Mapper"",""_beatsPerMinute"":128,""_previewStartTime"":12.5,""_previewDuration"":10,
            ""_songFilename"":""song.egg"",""_coverImageFilename"":""Cover.JPG"",""_environmentName"":""DefaultEnvironment"",
            ""_difficultyBeatmapSets"":[{""_beatmapCharacteristicName"":""Standard"",""_difficultyBeatmaps"":[
              {""_difficulty"":""Expert"",""_beatmapFilename"":""Expert.dat"",""_noteJumpMovementSpeed"":16,""_noteJumpStartBeatOffset"":-0.5,
               ""_customData"":{""_difficultyLabel"":""Hard one""}},
              {""_difficulty"":""ExpertPlus"",""_beatmapFilename"":""ExpertPlus.dat"",""_noteJumpMovementSpeed"":18}]}]}";

        private const string V2Difficulty = @"{""_version"":""2.2.0"",""_events"":[{""_time"":1,""_type"":0,""_value"":1}],
            ""_notes"":[{""_time"":1,""_type"":0},{""_time"":2,""_type"":1},{""_time"":3,""_type"":3},{""_time"":4,""_type"":0}],
            ""_obstacles"":[{""_time"":1}],""_sliders"":[{""_colorType"":0}]}";

        private const string V3Difficulty = @"{""version"":""3.3.0"",""bpmEvents"":[],""colorNotes"":[{""b"":1},{""b"":2}],
            ""bombNotes"":[{""b"":1}],""obstacles"":[{""b"":1},{""b"":2},{""b"":3}],""sliders"":[],""burstSliders"":[{""b"":4}],
            ""customData"":{""fakeColorNotes"":[{""b"":5}]}}";

        [Fact]
        public void ReadsV2InfoWithCountsAndSongCoreHash()
        {
            var dir = Level("a", ("Info.dat", V2Info), ("Expert.dat", V2Difficulty), ("ExpertPlus.dat", V3Difficulty),
                ("song.egg", "not really ogg"), ("cover.jpg", "jpg"));
            var level = LevelReader.Read(dir)!;

            Assert.Equal(Sha1(V2Info, V2Difficulty, V3Difficulty), level.Hash);
            Assert.Equal("Song", level.SongName);
            Assert.Equal("Mapper", level.Mapper);
            Assert.Equal(128, level.Bpm);
            Assert.Equal(12.5, level.PreviewStart);
            Assert.Equal("song.egg", level.AudioFile);
            Assert.Equal("cover.jpg", level.CoverFile); // matched case-insensitively, served under the real name
            Assert.Equal(0, level.Duration);

            var expert = level.Difficulties[0];
            Assert.Equal(("Standard", "Expert", "Hard one", 16.0, -0.5), (expert.Mode, expert.Difficulty, expert.Label, expert.NoteJumpSpeed, expert.Offset));
            Assert.Equal((3, 1, 1, 1, 0), (expert.Notes, expert.Bombs, expert.Walls, expert.Arcs, expert.Chains));
            var plus = level.Difficulties[1];
            Assert.Equal((2, 1, 3, 0, 1), (plus.Notes, plus.Bombs, plus.Walls, plus.Arcs, plus.Chains));
        }

        [Fact]
        public void HashesInfoDatTextWithoutByteOrderMark()
        {
            var dir = Level("bom", ("Info.dat", V2Info), ("Expert.dat", V2Difficulty), ("ExpertPlus.dat", V3Difficulty));
            var info = Path.Combine(dir, "Info.dat");
            File.WriteAllBytes(info, new byte[] { 0xEF, 0xBB, 0xBF }.Concat(File.ReadAllBytes(info)).ToArray());

            Assert.Equal(Sha1(V2Info, V2Difficulty, V3Difficulty), LevelReader.Read(dir)!.Hash);
        }

        [Fact]
        public void ReadsV4Info()
        {
            const string info = @"{""version"":""4.0.0"",""song"":{""title"":""Four"",""subTitle"":""S"",""author"":""A""},
                ""audio"":{""songFilename"":""song.ogg"",""songDuration"":201.5,""audioDataFilename"":""BPMInfo.dat"",""bpm"":200,
                  ""previewStartTime"":30,""previewDuration"":12},
                ""coverImageFilename"":""cover.png"",""environmentNames"":[""WeaveEnvironment""],
                ""difficultyBeatmaps"":[
                  {""characteristic"":""Standard"",""difficulty"":""Hard"",""beatmapAuthors"":{""mappers"":[""One"",""Two""]},
                   ""noteJumpMovementSpeed"":15,""beatmapDataFilename"":""Hard.dat"",""lightshowDataFilename"":""Lights.dat""},
                  {""characteristic"":""Standard"",""difficulty"":""Expert"",""beatmapAuthors"":{""mappers"":[""Two""]},
                   ""noteJumpMovementSpeed"":17,""beatmapDataFilename"":""Expert.dat"",""lightshowDataFilename"":""Lights.dat""}]}";
            const string v4 = @"{""version"":""4.0.0"",""colorNotes"":[{""b"":1}],""colorNotesData"":[{}],""bombNotes"":[],
                ""obstacles"":[{""b"":1}],""arcs"":[{""ai"":0},{""ai"":1}],""chains"":[{""ci"":0}]}";
            var dir = Level("v4", ("Info.dat", info), ("BPMInfo.dat", "bpm"), ("Hard.dat", v4), ("Expert.dat", "{}"),
                ("Lights.dat", "lights"), ("song.ogg", "x"));
            var level = LevelReader.Read(dir)!;

            // Like SongCore: audio data, then each difficulty's beatmap and lightshow, a shared lightshow twice.
            Assert.Equal(Sha1(info, "bpm", v4, "lights", "{}", "lights"), level.Hash);
            Assert.Equal(("Four", "One, Two", "WeaveEnvironment", 200.0, 201.5), (level.SongName, level.Mapper, level.Environment, level.Bpm, level.Duration));
            Assert.Null(level.CoverFile); // listed but missing
            Assert.Equal((1, 0, 1, 2, 1), (level.Difficulties[0].Notes, level.Difficulties[0].Bombs, level.Difficulties[0].Walls, level.Difficulties[0].Arcs, level.Difficulties[0].Chains));
            Assert.Equal(0, level.Difficulties[1].Notes);
        }

        [Fact]
        public void BrokenFilesDontBreakTheLevel()
        {
            Assert.Null(LevelReader.Read(Level("noinfo", ("song.egg", "x"))));
            Assert.Null(LevelReader.Read(Level("badinfo", ("info.dat", "{nope"))));

            var level = LevelReader.Read(Level("baddiff", ("info.dat", V2Info), ("Expert.dat", "[1,2"), ("song.egg", "x")))!;
            Assert.Equal(-1, level.Difficulties[0].Notes);
            Assert.Equal(-1, level.Difficulties[1].Notes); // file missing
        }

        [Fact]
        public void FileNamesFromInfoNeverLeaveTheFolder()
        {
            File.WriteAllText(Path.Combine(_root, "outside.egg"), "secret");
            var info = V2Info.Replace("\"song.egg\"", "\"../outside.egg\"").Replace("\"Cover.JPG\"", "\"Expert.dat\"");
            Level("evil", ("Info.dat", info), ("Expert.dat", V2Difficulty));
            var snapshot = new LevelLibrary(new[] { _root }, new ConsoleLiveLog()).GetAsync().Result;
            var level = snapshot.Levels.Single();

            Assert.Null(level.AudioFile);
            Assert.False(LevelLibrary.TryOpen(snapshot, level.Hash, LevelFileKind.Audio, out _));

            // A cover pointing at a difficulty file is served: it's what Info.dat calls the cover, and all of a
            // level's own files are public map data anyway. Nothing outside the folder is reachable.
            Assert.True(LevelLibrary.TryOpen(snapshot, level.Hash, LevelFileKind.Cover, out var s));
            s.Dispose();
            Assert.False(LevelLibrary.TryOpen(snapshot, "0000", LevelFileKind.Cover, out _));
            Assert.False(LevelLibrary.TryOpen(snapshot, level.Hash, (LevelFileKind) 7, out _));
        }

        [Fact]
        public void LibraryListsEachHashOnceAsJson()
        {
            Level("one", ("Info.dat", V2Info.Replace("Song", "<b>Song</b>")), ("Expert.dat", V2Difficulty));
            Level("copy", ("Info.dat", V2Info.Replace("Song", "<b>Song</b>")), ("Expert.dat", V2Difficulty));
            Level("two", ("Info.dat", V2Info.Replace("Song", "Other")));
            var snapshot = new LevelLibrary(new[] { _root, Path.Combine(_root, "missing") }, new ConsoleLiveLog()).GetAsync().Result;

            Assert.Equal(3, snapshot.Levels.Count);
            Assert.Equal(2, snapshot.ByHash.Count);
            var json = Encoding.UTF8.GetString(snapshot.Json);
            Assert.DoesNotContain("<b>", json); // HTML-significant characters are escaped
            var levels = (JArray) JObject.Parse(json)["levels"]!;
            Assert.Equal(2, levels.Count);
            var song = levels.Single(l => (string) l["songName"]! == "<b>Song</b>");
            Assert.Equal(3, (int) song["difficulties"]![0]!["notes"]!);
            Assert.Equal(JTokenType.Null, song["difficulties"]![1]!["notes"]!.Type);
            Assert.True((bool) song["hasCover"]! == false);
        }

        [Fact]
        public void ReadsOggDuration()
        {
            var path = Path.Combine(_root, "song.egg");
            var bytes = new List<byte>();
            void Page(long granule, byte[] packet)
            {
                bytes.AddRange(Encoding.ASCII.GetBytes("OggS"));
                bytes.Add(0);
                bytes.Add(0);
                bytes.AddRange(BitConverter.GetBytes(granule));
                bytes.AddRange(new byte[12]);
                bytes.Add(1);
                bytes.Add((byte) packet.Length);
                bytes.AddRange(packet);
            }

            var id = new List<byte> { 1 };
            id.AddRange(Encoding.ASCII.GetBytes("vorbis"));
            id.AddRange(BitConverter.GetBytes(0));
            id.Add(2);
            id.AddRange(BitConverter.GetBytes(44100));
            id.AddRange(new byte[15]);
            Page(0, id.ToArray());
            Page(44100 * 3 / 2, new byte[100]);
            Page(44100 * 3, new byte[100]);
            File.WriteAllBytes(path, bytes.ToArray());

            Assert.Equal(3.0, AudioDuration.TryRead(path), 3);
            File.WriteAllText(path, "RIFF....WAVE");
            Assert.Equal(0, AudioDuration.TryRead(path));
        }

        [Fact]
        public void SuggestionsPersistAndAreBounded()
        {
            var path = Path.Combine(_root, "suggestions.tsv");
            var store = new Suggestions(path);
            var ids = Enumerable.Range(0, Suggestions.MaxSuggestions + 1).Select(i => i.ToString("x40")).ToList();
            Assert.True(store.Add(ids[0], "Firefox\ton <Linux>"));
            Assert.False(store.Add(ids[0], "again"));
            foreach (var id in ids.Skip(1).Take(Suggestions.MaxSuggestions - 1))
            {
                Assert.True(store.Add(id, "x"));
            }

            Assert.False(store.Add(ids[Suggestions.MaxSuggestions], "x"));
            Assert.True(store.Remove(ids[1]));
            Assert.False(store.Remove(ids[1]));

            var reloaded = new Suggestions(path).List();
            Assert.Equal(Suggestions.MaxSuggestions - 1, reloaded.Count);
            Assert.Equal((ids[0], "Firefoxon <Linux>"), (reloaded[0].Id, reloaded[0].By)); // control characters dropped
            Assert.Contains("\\u003cLinux\\u003e", Encoding.UTF8.GetString(new Suggestions(path).Json()));
        }

        [Fact]
        public void SuggestionsMove()
        {
            var store = new Suggestions(Path.Combine(_root, "order.tsv"));
            var ids = Enumerable.Range(1, 4).Select(i => i.ToString("x40")).ToArray();
            foreach (var id in ids)
            {
                store.Add(id, "x");
            }

            string Order() => string.Concat(store.List().Select(e => e.Id.Substring(39)));
            Assert.True(store.Move(ids[3], 0));
            Assert.Equal("4123", Order());
            Assert.True(store.Move(ids[3], 99)); // clamped: to the bottom
            Assert.Equal("1234", Order());
            Assert.True(store.Move(ids[0], 2));
            Assert.Equal("2314", Order());
            Assert.False(store.Move(ids[0], 2)); // already there
            Assert.False(store.Move(new string('f', 40), 0));
            Assert.Equal("2314", string.Concat(new Suggestions(Path.Combine(_root, "order.tsv")).List().Select(e => e.Id.Substring(39))));
        }

        [Fact]
        public void ReadsWavDuration()
        {
            var path = Path.Combine(_root, "song.wav");
            var wav = new List<byte>();
            wav.AddRange(Encoding.ASCII.GetBytes("RIFF"));
            wav.AddRange(BitConverter.GetBytes(0));
            wav.AddRange(Encoding.ASCII.GetBytes("WAVEfmt "));
            wav.AddRange(BitConverter.GetBytes(16));
            wav.AddRange(new byte[] { 1, 0, 2, 0 });
            wav.AddRange(BitConverter.GetBytes(44100));
            wav.AddRange(BitConverter.GetBytes(44100 * 4));
            wav.AddRange(new byte[] { 4, 0, 16, 0 });
            wav.AddRange(Encoding.ASCII.GetBytes("LIST"));
            wav.AddRange(BitConverter.GetBytes(3));
            wav.AddRange(new byte[4]); // odd chunk plus its pad byte
            wav.AddRange(Encoding.ASCII.GetBytes("data"));
            wav.AddRange(BitConverter.GetBytes(44100 * 4 * 2));
            wav.AddRange(new byte[44100 * 4 * 2]);
            File.WriteAllBytes(path, wav.ToArray());

            Assert.Equal(2.0, AudioDuration.TryRead(path), 3);
        }

        private sealed class FakeApi : IBeatLeaderApi
        {
            public int Calls;
            public Func<string, string?> Respond = _ => null;

            public Task<string?> GetMapByHashAsync(string hash, CancellationToken cancellation)
            {
                Calls++;
                return Task.FromResult(Respond(hash));
            }
        }

        [Fact]
        public void StatsKeepOnlyKnownFields()
        {
            var json = Encoding.UTF8.GetString(BeatLeaderStats.Summarize(@"{""id"":""4adb"",""secret"":""x"",""difficulties"":[
                {""modeName"":""Standard"",""difficultyName"":""Expert"",""status"":3,""stars"":5.74639,""passRating"":2.7,
                 ""accRating"":7.5,""techRating"":6.1,""predictedAcc"":0.983,""maxScore"":344195,""njs"":15},
                {""modeName"":""<script>"",""difficultyName"":""Easy"",""status"":0,""stars"":null}, 42]}"));
            var o = JObject.Parse(json);
            Assert.True((bool) o["found"]!);
            Assert.Equal("4adb", (string) o["key"]!);
            Assert.Null(o["secret"]);
            var d = (JArray) o["difficulties"]!;
            Assert.Equal(2, d.Count);
            Assert.Equal(5.7464, (double) d[0]!["stars"]!);
            Assert.Null(d[0]!["njs"]);
            Assert.Equal(JTokenType.Null, d[1]!["stars"]!.Type);
            Assert.DoesNotContain("<script>", json);

            Assert.Equal("{\"found\":false}", Encoding.UTF8.GetString(BeatLeaderStats.Summarize(null)));
            Assert.ThrowsAny<Exception>(() => BeatLeaderStats.Summarize("<html>"));
        }

        [Fact]
        public async Task StatsAreCachedAndFailuresRetriedLater()
        {
            var now = new DateTime(2026, 1, 1, 0, 0, 0, DateTimeKind.Utc);
            var api = new FakeApi();
            var stats = new BeatLeaderStats(api, new ConsoleLiveLog(), () => now);

            await stats.GetAsync("aa");
            await stats.GetAsync("aa");
            Assert.Equal(1, api.Calls);

            api.Respond = _ => throw new InvalidOperationException("offline");
            await Assert.ThrowsAsync<InvalidOperationException>(() => stats.GetAsync("bb"));
            await Assert.ThrowsAsync<InvalidOperationException>(() => stats.GetAsync("bb"));
            Assert.Equal(2, api.Calls);

            now += BeatLeaderStats.RetryAfter;
            api.Respond = _ => "{\"id\":\"k\"}";
            Assert.Contains("\"k\"", Encoding.UTF8.GetString(await stats.GetAsync("bb")));
            Assert.Equal(3, api.Calls);

            now += BeatLeaderStats.CacheFor;
            await stats.GetAsync("aa");
            Assert.Equal(4, api.Calls);
        }
    }
}
