using System;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Threading;
using System.Threading.Tasks;
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

        public ServerIntegrationTests()
        {
            _server = new LiveServer(new LiveServerOptions { Port = _port, DataDirectory = _data }, new ConsoleLiveLog());
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

        private static byte[] Hello(byte[]? credential = null)
        {
            var w = new MessageWriter().U8(MessageType.Hello).U16(1).Bool(credential != null);
            if (credential != null)
            {
                w.Bytes(credential);
            }

            return w.ToArray();
        }

        private async Task<string> WaitForCodeAsync(ClientWebSocket ws)
        {
            await SendAsync(ws, Hello());
            var waiting = await ExpectAsync(ws, MessageType.Waiting);
            var r = new MessageReader(waiting);
            r.U8();
            return r.String(64);
        }

        private long PendingId(string code) => _server.WaitingRoom.Pending.Single(p => p.MatchCode == code).ConnectionId;

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
            var code = await WaitForCodeAsync(ws);

            // Nothing live is sent before approval.
            _server.Feed.BeginSession(new SessionInfo { SongName = "Test", Files = { ["audio"] = "song.egg" } },
                new MapDirectory(_mapDir, new[] { "Info.dat", "song.egg" }));
            var pose = new Pose(new Vec3(0, 1.7f, 0), new Quat(0, 0, 0, 1));
            _server.Feed.Pose(LiveClock.NowUs(), 1f, pose, pose, pose);
            _server.Feed.Note(true, LiveClock.NowUs(), new NoteEvent { NoteId = 7, EventType = NoteEventType.Miss });
            await Task.Delay(200);

            Assert.True(_server.WaitingRoom.Approve(PendingId(code), remember: true));
            var approved = await ExpectAsync(ws, MessageType.Approved);
            Assert.Equal(1, approved[1]);
            Assert.Equal(34, approved.Length);

            // Backlog: session start, then the earlier note event (poses aren't backlogged).
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

        [Fact]
        public async Task RememberedDeviceReconnectsWithoutWaitingAndCanBeRevoked()
        {
            byte[] credential;
            using (var first = await ConnectAsync())
            {
                var code = await WaitForCodeAsync(first);
                _server.WaitingRoom.Approve(PendingId(code), remember: true);
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
            var code = await WaitForCodeAsync(ws);
            _server.WaitingRoom.Deny(PendingId(code));
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
                    await SendAsync(ws, new byte[64 * 1024]);
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
