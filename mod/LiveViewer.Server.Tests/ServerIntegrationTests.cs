using System;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Threading;
using System.Threading.Tasks;
using LiveViewer.Server.Levels;
using LiveViewer.Server.Live;
using LiveViewer.Server.Protocol;
using Xunit;

namespace LiveViewer.Server.Tests
{
    /// <summary>Runs the real server over TLS on loopback and talks to it like a browser would.</summary>
    public sealed class ServerIntegrationTests : IDisposable
    {
        private readonly string _data = Directory.CreateTempSubdirectory().FullName;
        private readonly int _port = FreePort();
        private readonly LiveServer _server;
        private readonly string _mapDir;
        private readonly string _levelsDir = Directory.CreateTempSubdirectory().FullName;
        private readonly FakeBeatLeader _beatLeader = new FakeBeatLeader();

        private sealed class FakeBeatLeader : IBeatLeaderApi
        {
            public readonly System.Collections.Concurrent.ConcurrentBag<string> Asked = new System.Collections.Concurrent.ConcurrentBag<string>();

            public Task<string?> GetMapByHashAsync(string hash, CancellationToken cancellation)
            {
                Asked.Add(hash);
                return Task.FromResult<string?>("{\"id\":\"abc\",\"difficulties\":[{\"modeName\":\"Standard\",\"difficultyName\":\"Expert\",\"stars\":6.5}]}");
            }
        }

        public ServerIntegrationTests()
        {
            var level = Path.Combine(_levelsDir, "level");
            Directory.CreateDirectory(level);
            File.WriteAllText(Path.Combine(level, "Info.dat"), "{\"_songName\":\"Library song\",\"_songFilename\":\"song.ogg\",\"_coverImageFilename\":\"cover.jpg\","
                + "\"_difficultyBeatmapSets\":[{\"_beatmapCharacteristicName\":\"Standard\",\"_difficultyBeatmaps\":[{\"_difficulty\":\"Expert\",\"_beatmapFilename\":\"Expert.dat\"}]}]}");
            File.WriteAllText(Path.Combine(level, "Expert.dat"), "{\"_notes\":[]}");
            File.WriteAllBytes(Path.Combine(level, "song.ogg"), new byte[40_000]);
            File.WriteAllText(Path.Combine(level, "cover.jpg"), "cover");

            _server = new LiveServer(new LiveServerOptions
            {
                Port = _port,
                DataDirectory = _data,
                LevelFolders = { _levelsDir },
                BeatLeader = _beatLeader,
            }, new ConsoleLiveLog());
            _server.Start();

            _mapDir = Directory.CreateTempSubdirectory().FullName;
            File.WriteAllText(Path.Combine(_mapDir, "Info.dat"), "{\"_version\":\"2.0.0\"}");
            File.WriteAllBytes(Path.Combine(_mapDir, "song.egg"), Enumerable.Range(0, 100_000).Select(i => (byte) i).ToArray());
            File.WriteAllText(Path.Combine(_mapDir, "secret.txt"), "nope");
        }

        public void Dispose() => _server.Dispose();

        private static int FreePort()
        {
            var l = new TcpListener(IPAddress.Loopback, 0);
            l.Start();
            var port = ((IPEndPoint) l.LocalEndpoint).Port;
            l.Stop();
            return port;
        }

        private async Task<ClientWebSocket> ConnectAsync(string? origin = "default")
        {
            var ws = new ClientWebSocket();
            ws.Options.RemoteCertificateValidationCallback = (_, _, _, _) => true;
            ws.Options.AddSubProtocol("bslive.v1");
            if (origin != null)
            {
                ws.Options.SetRequestHeader("Origin", origin == "default" ? $"https://localhost:{_port}" : origin);
            }

            await ws.ConnectAsync(new Uri($"wss://localhost:{_port}/ws"), CancellationToken.None);
            return ws;
        }

        private static Task SendAsync(ClientWebSocket ws, byte[] data) =>
            ws.SendAsync(data, WebSocketMessageType.Binary, true, CancellationToken.None);

        private static async Task<byte[]?> ReceiveAsync(ClientWebSocket ws, int timeoutMs = 5000)
        {
            var buffer = new byte[1 << 16];
            using var ms = new MemoryStream();
            using var cts = new CancellationTokenSource(timeoutMs);
            try
            {
                while (true)
                {
                    var result = await ws.ReceiveAsync(buffer, cts.Token);
                    if (result.MessageType == WebSocketMessageType.Close)
                    {
                        return null;
                    }

                    ms.Write(buffer, 0, result.Count);
                    if (result.EndOfMessage)
                    {
                        return ms.ToArray();
                    }
                }
            }
            catch (WebSocketException)
            {
                return null;
            }
        }

        /// <summary>Receives until a message of the given type arrives; fails on close.</summary>
        private static async Task<byte[]> ExpectAsync(ClientWebSocket ws, byte type)
        {
            while (true)
            {
                var message = await ReceiveAsync(ws);
                Assert.True(message != null, $"Connection closed while waiting for 0x{type:x2}.");
                if (message![0] == type)
                {
                    return message;
                }
            }
        }

        private static async Task ExpectClosedAsync(ClientWebSocket ws)
        {
            for (var i = 0; i < 500; i++)
            {
                if (await ReceiveAsync(ws) == null)
                {
                    return;
                }
            }

            Assert.Fail("Connection stayed open.");
        }

        private static byte[] Hello(byte[]? credential = null, string name = "Test Viewer")
        {
            var w = new MessageWriter().U8(MessageType.Hello).U16(MessageType.ProtocolVersion).Bool(credential != null);
            if (credential != null)
            {
                w.Bytes(credential);
            }

            return w.String(name).ToArray();
        }

        private async Task<string> WaitForNameAsync(ClientWebSocket ws)
        {
            await SendAsync(ws, Hello());
            return await WaitingNameAsync(ws);
        }

        private static async Task<string> WaitingNameAsync(ClientWebSocket ws)
        {
            var waiting = await ExpectAsync(ws, MessageType.Waiting);
            var r = new MessageReader(waiting);
            r.U8();
            return r.String(64);
        }

        private long PendingId(string name) => _server.WaitingRoom.Pending.Single(p => p.Name == name).ConnectionId;

        [Fact]
        public async Task RejectsWebSocketFromForeignOrMissingOrigin()
        {
            await Assert.ThrowsAnyAsync<WebSocketException>(() => ConnectAsync("https://evil.example"));
            await Assert.ThrowsAnyAsync<WebSocketException>(() => ConnectAsync(null));
        }

        [Fact]
        public async Task RejectsForeignHostOverHttp()
        {
            using var handler = new HttpClientHandler { ServerCertificateCustomValidationCallback = (_, _, _, _) => true, UseProxy = false };
            using var http = new HttpClient(handler);
            var ok = await http.GetAsync($"https://localhost:{_port}/");
            Assert.Equal(HttpStatusCode.OK, ok.StatusCode);
            Assert.Contains("default-src 'self'", ok.Headers.GetValues("Content-Security-Policy").Single());

            var request = new HttpRequestMessage(HttpMethod.Get, $"https://localhost:{_port}/");
            request.Headers.Host = "evil.example:" + _port;
            Assert.Equal((HttpStatusCode) 421, (await http.SendAsync(request)).StatusCode);

            Assert.Equal(HttpStatusCode.MethodNotAllowed, (await http.PostAsync($"https://localhost:{_port}/", new StringContent("x"))).StatusCode);
        }

        [Fact]
        public async Task WaitingRoomApprovalThenLiveData()
        {
            using var ws = await ConnectAsync();
            await ExpectAsync(ws, MessageType.Welcome);
            var name = await WaitForNameAsync(ws);

            // Nothing live is sent before approval.
            _server.Feed.BeginSession(new SessionInfo { SongName = "Test", Files = { ["audio"] = "song.egg" } },
                new MapDirectory(_mapDir, new[] { "Info.dat", "song.egg" }));
            var pose = new Pose(new Vec3(0, 1.7f, 0), new Quat(0, 0, 0, 1));
            _server.Feed.Pose(LiveClock.NowUs(), 1f, pose, pose, pose);
            _server.Feed.Note(true, LiveClock.NowUs(), new NoteEvent { NoteId = 7, EventType = NoteEventType.Miss });
            await Task.Delay(200);

            Assert.True(_server.WaitingRoom.Approve(PendingId(name), remember: true));
            var approved = await ExpectAsync(ws, MessageType.Approved);
            Assert.Equal(1, approved[1]);
            Assert.Equal(34, approved.Length);

            // The name in effect, the suggestion list, then the backlog: session start and the earlier note event
            // (poses aren't backlogged).
            Assert.Equal(MessageType.Name, (await ReceiveAsync(ws))![0]);
            Assert.Equal(MessageType.Suggestions, (await ReceiveAsync(ws))![0]);
            Assert.Equal(MessageType.SessionStart, (await ReceiveAsync(ws))![0]);
            Assert.Equal(MessageType.NoteFinal, (await ReceiveAsync(ws))![0]);

            _server.Feed.Pose(LiveClock.NowUs(), 2f, pose, pose, pose);
            var live = await ExpectAsync(ws, MessageType.Pose);
            Assert.Equal(1 + 8 + 4 + 3 * 28, live.Length);

            // Ping/pong.
            await SendAsync(ws, new MessageWriter().U8(MessageType.Ping).F64(123.5).ToArray());
            var pong = new MessageReader(await ExpectAsync(ws, MessageType.Pong));
            pong.U8();
            Assert.Equal(123.5, pong.F64());

            // Map transfer: allowed file, unlisted file.
            await SendAsync(ws, new MessageWriter().U8(MessageType.MapRequest).U16(5).U32(1).String("song.egg").ToArray());
            var received = 0;
            while (received < 100_000)
            {
                var chunk = new MessageReader(await ExpectAsync(ws, MessageType.MapChunk));
                chunk.U8();
                Assert.Equal(5, chunk.U16());
                Assert.Equal(100_000u, chunk.U32());
                Assert.Equal((uint) received, chunk.U32());
                received += chunk.Remaining;
            }

            await SendAsync(ws, new MessageWriter().U8(MessageType.MapRequest).U16(6).U32(1).String("secret.txt").ToArray());
            var error = await ExpectAsync(ws, MessageType.MapError);
            Assert.Equal((byte) MapErrorCode.NotAvailable, error[3]);
        }

        /// <summary>Receives a complete file transfer for one request id, or returns the error code.</summary>
        private static async Task<(byte[]? data, byte error)> ReceiveFileAsync(ClientWebSocket ws, ushort requestId)
        {
            byte[]? data = null;
            var received = 0;
            while (true)
            {
                var message = await ReceiveAsync(ws);
                Assert.True(message != null, "Connection closed during transfer.");
                var r = new MessageReader(message!);
                var type = r.U8();
                if (type != MessageType.MapChunk && type != MessageType.MapError)
                {
                    continue;
                }

                Assert.Equal(requestId, r.U16());
                if (type == MessageType.MapError)
                {
                    return (null, r.U8());
                }

                var total = r.U32();
                var offset = r.U32();
                data ??= new byte[total];
                Assert.Equal((uint) received, offset);
                var chunk = r.Bytes(r.Remaining);
                chunk.CopyTo(data, offset);
                received += chunk.Length;
                if (received >= total)
                {
                    return (data, 0);
                }
            }
        }

        private async Task<ClientWebSocket> ApprovedClientAsync()
        {
            var ws = await ConnectAsync();
            var name = await WaitForNameAsync(ws);
            _server.WaitingRoom.Approve(PendingId(name), remember: false);
            await ExpectAsync(ws, MessageType.Idle);
            return ws;
        }

        private static byte[] LevelFileRequest(ushort id, byte kind, string level) =>
            new MessageWriter().U8(MessageType.LevelFileRequest).U16(id).U8(kind).String(level).ToArray();

        [Fact]
        public async Task LevelLibraryListFilesAndStats()
        {
            using var ws = await ApprovedClientAsync();

            await SendAsync(ws, new MessageWriter().U8(MessageType.LevelListRequest).U16(1).ToArray());
            var (list, _) = await ReceiveFileAsync(ws, 1);
            var level = Newtonsoft.Json.Linq.JObject.Parse(System.Text.Encoding.UTF8.GetString(list!))["levels"]![0]!;
            Assert.Equal("Library song", (string) level["songName"]!);
            var id = (string) level["id"]!;

            await SendAsync(ws, LevelFileRequest(2, (byte) LevelFileKind.Audio, id));
            Assert.Equal(40_000, (await ReceiveFileAsync(ws, 2)).data!.Length);
            await SendAsync(ws, LevelFileRequest(3, (byte) LevelFileKind.Cover, id));
            Assert.Equal("cover", System.Text.Encoding.UTF8.GetString((await ReceiveFileAsync(ws, 3)).data!));

            await SendAsync(ws, new MessageWriter().U8(MessageType.LevelStatsRequest).U16(4).String(id).ToArray());
            var stats = System.Text.Encoding.UTF8.GetString((await ReceiveFileAsync(ws, 4)).data!);
            Assert.Contains("\"stars\":6.5", stats);
            Assert.Equal(new[] { id }, _beatLeader.Asked.ToArray());

            // Unknown levels: no file, and BeatLeader is never asked about them.
            var unknown = new string('0', 40);
            await SendAsync(ws, LevelFileRequest(5, (byte) LevelFileKind.Audio, unknown));
            Assert.Equal((byte) MapErrorCode.NotAvailable, (await ReceiveFileAsync(ws, 5)).error);
            await SendAsync(ws, new MessageWriter().U8(MessageType.LevelStatsRequest).U16(6).String(unknown).ToArray());
            Assert.Equal((byte) MapErrorCode.NotAvailable, (await ReceiveFileAsync(ws, 6)).error);
            Assert.Single(_beatLeader.Asked);

            // Level files are addressed by kind only; anything else is a violation.
            await SendAsync(ws, LevelFileRequest(7, 3, id));
            await ExpectClosedAsync(ws);
        }

        private static async Task<string[]> ExpectSuggestionsAsync(ClientWebSocket ws)
        {
            var message = await ExpectAsync(ws, MessageType.Suggestions);
            var json = Newtonsoft.Json.Linq.JObject.Parse(System.Text.Encoding.UTF8.GetString(message, 5, message.Length - 5));
            return json["levels"]!.Select(l => (string) l["id"]!).ToArray();
        }

        private static byte[] Suggestion(bool add, string id) =>
            new MessageWriter().U8(add ? MessageType.SuggestionAdd : MessageType.SuggestionRemove).String(id).ToArray();

        [Fact]
        public async Task SuggestionsAreSharedBetweenViewers()
        {
            using var a = await ApprovedClientAsync();
            using var b = await ApprovedClientAsync();
            await SendAsync(a, new MessageWriter().U8(MessageType.LevelListRequest).U16(1).ToArray());
            var (list, _) = await ReceiveFileAsync(a, 1);
            var id = (string) Newtonsoft.Json.Linq.JObject.Parse(System.Text.Encoding.UTF8.GetString(list!))["levels"]![0]!["id"]!;

            await SendAsync(a, Suggestion(true, id));
            Assert.Equal(new[] { id }, await ExpectSuggestionsAsync(a));
            Assert.Equal(new[] { id }, await ExpectSuggestionsAsync(b));
            Assert.Equal(id, _server.Suggestions.List().Single().Id);

            // A level that isn't installed isn't added; the sender gets the real list back.
            await SendAsync(a, Suggestion(true, new string('0', 40)));
            Assert.Equal(new[] { id }, await ExpectSuggestionsAsync(a));

            await SendAsync(b, Suggestion(false, id));
            Assert.Empty(await ExpectSuggestionsAsync(a));
            Assert.Empty(await ExpectSuggestionsAsync(b));

            // A new viewer gets the list right after approval.
            await SendAsync(a, Suggestion(true, id));
            await ExpectSuggestionsAsync(a);
            using var c = await ConnectAsync();
            var name = await WaitForNameAsync(c);
            _server.WaitingRoom.Approve(PendingId(name), remember: false);
            Assert.Equal(new[] { id }, await ExpectSuggestionsAsync(c));

            // Moving: a second suggestion, moved to the top, reaches everyone; a move to where it is already
            // answers the sender with the current order.
            var other = new string('1', 40);
            _server.Suggestions.Add(other, "test"); // directly: the level needn't be installed for this
            Assert.Equal(new[] { id, other }, await ExpectSuggestionsAsync(a));
            Assert.Equal(new[] { id, other }, await ExpectSuggestionsAsync(c));
            await SendAsync(c, new MessageWriter().U8(MessageType.SuggestionMove).String(other).U16(0).ToArray());
            Assert.Equal(new[] { other, id }, await ExpectSuggestionsAsync(a));
            Assert.Equal(new[] { other, id }, await ExpectSuggestionsAsync(c));
            await SendAsync(c, new MessageWriter().U8(MessageType.SuggestionMove).String(other).U16(0).ToArray());
            Assert.Equal(new[] { other, id }, await ExpectSuggestionsAsync(c));

            // Ids must look like level hashes.
            await SendAsync(b, Suggestion(true, "../../etc"));
            await ExpectClosedAsync(b);
        }

        private static async Task<string> ExpectNameAsync(ClientWebSocket ws)
        {
            var r = new MessageReader(await ExpectAsync(ws, MessageType.Name));
            r.U8();
            return r.String(128);
        }

        [Fact]
        public async Task ViewersCanRenameThemselves()
        {
            using var ws = await ConnectAsync();
            await SendAsync(ws, Hello(name: "  Ada \t Lovelace "));
            Assert.Equal("Ada Lovelace", await WaitingNameAsync(ws));
            _server.WaitingRoom.Approve(PendingId("Ada Lovelace"), remember: false);
            Assert.Equal("Ada Lovelace", await ExpectNameAsync(ws));

            await SendAsync(ws, new MessageWriter().U8(MessageType.Rename).String("Grace\u0000 Hopper").ToArray());
            Assert.Equal("Grace Hopper", await ExpectNameAsync(ws));

            // New suggestions carry the new name.
            await SendAsync(ws, new MessageWriter().U8(MessageType.LevelListRequest).U16(1).ToArray());
            var (list, _) = await ReceiveFileAsync(ws, 1);
            var id = (string) Newtonsoft.Json.Linq.JObject.Parse(System.Text.Encoding.UTF8.GetString(list!))["levels"]![0]!["id"]!;
            await SendAsync(ws, Suggestion(true, id));
            await ExpectSuggestionsAsync(ws);
            Assert.Equal("Grace Hopper", _server.Suggestions.List().Single().By);
        }

        [Fact]
        public async Task RenameNeedsApproval()
        {
            using var ws = await ConnectAsync();
            await WaitForNameAsync(ws);
            await SendAsync(ws, new MessageWriter().U8(MessageType.Rename).String("x").ToArray());
            await ExpectClosedAsync(ws);
        }

        [Fact]
        public async Task LevelRequestsNeedApproval()
        {
            using var ws = await ConnectAsync();
            await WaitForNameAsync(ws);
            await SendAsync(ws, new MessageWriter().U8(MessageType.LevelListRequest).U16(1).ToArray());
            await ExpectClosedAsync(ws);
        }

        [Fact]
        public async Task RememberedDeviceReconnectsWithoutWaitingAndCanBeRevoked()
        {
            byte[] credential;
            using (var first = await ConnectAsync())
            {
                var name = await WaitForNameAsync(first);
                _server.WaitingRoom.Approve(PendingId(name), remember: true);
                credential = (await ExpectAsync(first, MessageType.Approved)).Skip(2).ToArray();
            }

            using var second = await ConnectAsync();
            await SendAsync(second, Hello(credential));
            await ExpectAsync(second, MessageType.Approved);
            await ExpectAsync(second, MessageType.Idle);
            Assert.Empty(_server.WaitingRoom.Pending);

            _server.Devices.Remove(_server.Devices.List().Single().Id);
            await ExpectAsync(second, MessageType.Revoked);
            await ExpectClosedAsync(second);

            // The revoked credential no longer works.
            using var third = await ConnectAsync();
            await SendAsync(third, Hello(credential));
            await ExpectAsync(third, MessageType.Waiting);
        }

        [Fact]
        public async Task DeniedClientIsClosed()
        {
            using var ws = await ConnectAsync();
            var name = await WaitForNameAsync(ws);
            _server.WaitingRoom.Deny(PendingId(name));
            await ExpectAsync(ws, MessageType.Denied);
            await ExpectClosedAsync(ws);
        }

        [Theory]
        [InlineData("map request before approval")]
        [InlineData("text frame")]
        [InlineData("unknown type")]
        [InlineData("duplicate hello")]
        [InlineData("oversized")]
        [InlineData("flood")]
        public async Task ProtocolViolationsCloseTheConnection(string violation)
        {
            using var ws = await ConnectAsync();
            await ExpectAsync(ws, MessageType.Welcome);
            switch (violation)
            {
                case "map request before approval":
                    await SendAsync(ws, Hello());
                    await SendAsync(ws, new MessageWriter().U8(MessageType.MapRequest).U16(1).U32(1).String("Info.dat").ToArray());
                    break;
                case "text frame":
                    await ws.SendAsync(new byte[] { 0x82 }, WebSocketMessageType.Text, true, CancellationToken.None);
                    break;
                case "unknown type":
                    await SendAsync(ws, new byte[] { 0x99 });
                    break;
                case "duplicate hello":
                    await SendAsync(ws, Hello());
                    await SendAsync(ws, Hello());
                    break;
                case "oversized":
                    try
                    {
                        await SendAsync(ws, new byte[64 * 1024]);
                    }
                    catch (WebSocketException)
                    {
                        // The server refuses the frame by its header and may close before the client has written it all.
                    }

                    break;
                case "flood":
                    for (var i = 0; i < 200 && ws.State == WebSocketState.Open; i++)
                    {
                        try
                        {
                            await SendAsync(ws, new MessageWriter().U8(MessageType.Ping).F64(i).ToArray());
                        }
                        catch (WebSocketException)
                        {
                            break;
                        }
                    }

                    break;
            }

            await ExpectClosedAsync(ws);
        }
    }
}
