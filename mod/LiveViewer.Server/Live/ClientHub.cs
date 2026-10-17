using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using EmbedIO.WebSockets;
using LiveViewer.Server.Protocol;
using LiveViewer.Server.Security;

namespace LiveViewer.Server.Live
{
    /// <summary>
    /// Owns all client connections and the network-side session state. A dedicated thread drains the
    /// <see cref="LiveFeed"/>, encodes each event once and fans it out to approved clients.
    /// Everything a late joiner needs (session start plus every non-pose event since) is kept as a backlog.
    /// </summary>
    internal sealed class ClientHub : IDisposable
    {
        public const int MaxConnections = 16;
        public const int MaxConnectionsPerAddress = 4;
        public const int MaxBacklog = 200_000;

        private readonly object _lock = new object();
        private readonly Dictionary<string, ClientConnection> _byContext = new Dictionary<string, ClientConnection>();
        private readonly List<byte[]> _backlog = new List<byte[]>();
        private readonly LiveFeed _feed;
        private readonly WaitingRoom _waitingRoom;
        private readonly DeviceStore _devices;
        private readonly ILiveLog _log;
        private readonly string _serverName;
        private readonly Thread _pump;
        private readonly Timer _expiry;
        private volatile bool _stopping;

        private uint _sessionId;
        private bool _inSession;
        private IMapFileSource? _map;

        public ClientHub(LiveFeed feed, WaitingRoom waitingRoom, DeviceStore devices, string serverName, ILiveLog log)
        {
            _feed = feed;
            _waitingRoom = waitingRoom;
            _devices = devices;
            _serverName = serverName;
            _log = log;
            _waitingRoom.Decided += OnDecided;
            _devices.Revoked += OnRevoked;
            _pump = new Thread(PumpLoop) { IsBackground = true, Name = "LiveViewer feed pump" };
            _expiry = new Timer(_ => SafeExpire(), null, Timeout.Infinite, Timeout.Infinite);
        }

        public int ApprovedCount
        {
            get
            {
                lock (_lock)
                {
                    return _byContext.Values.Count(c => c.State == ClientState.Approved);
                }
            }
        }

        public void Start()
        {
            _pump.Start();
            _expiry.Change(TimeSpan.FromSeconds(5), TimeSpan.FromSeconds(5));
        }

        public void Dispose()
        {
            _stopping = true;
            _feed.Signal.Release();
            _expiry.Dispose();
            _waitingRoom.Decided -= OnDecided;
            _devices.Revoked -= OnRevoked;
            List<ClientConnection> all;
            lock (_lock)
            {
                all = _byContext.Values.ToList();
                _byContext.Clear();
            }

            foreach (var c in all)
            {
                _ = c.AbortAsync();
            }

            _pump.Join(TimeSpan.FromSeconds(2));
        }

        // ---- Connection lifecycle (called from the WebSocket module) ----

        public void OnConnected(IWebSocketContext context, string userAgent)
        {
            var connection = new ClientConnection(context, DescribeUserAgent(userAgent), _log);
            lock (_lock)
            {
                var total = _byContext.Count;
                var sameAddress = _byContext.Values.Count(c => c.Address.Equals(connection.Address));
                if (total >= MaxConnections || sameAddress >= MaxConnectionsPerAddress)
                {
                    _log.Warn($"Refusing connection from {connection.Address}: too many connections.");
                    _ = connection.AbortAsync();
                    return;
                }

                _byContext[context.Id] = connection;
            }

            _ = connection.RunSendLoopAsync(() => Volatile.Read(ref _sessionId));
            connection.EnqueueReliable(Messages.Welcome(LiveClock.NowUs(), _serverName));
        }

        public void OnDisconnected(IWebSocketContext context)
        {
            ClientConnection? connection;
            lock (_lock)
            {
                if (_byContext.TryGetValue(context.Id, out connection))
                {
                    _byContext.Remove(context.Id);
                }
            }

            if (connection == null)
            {
                return;
            }

            connection.MarkClosed();
            _waitingRoom.Leave(connection.Id);
        }

        public void OnMessage(IWebSocketContext context, byte[] data, bool isText)
        {
            ClientConnection? connection;
            lock (_lock)
            {
                _byContext.TryGetValue(context.Id, out connection);
            }

            if (connection == null || connection.IsClosed)
            {
                return;
            }

            try
            {
                if (isText || data.Length == 0)
                {
                    throw new ProtocolException("Expected a binary message.");
                }

                if (!connection.TryConsumeInboundToken())
                {
                    throw new ProtocolException("Too many messages.");
                }

                var reader = new MessageReader(data);
                switch (reader.U8())
                {
                    case MessageType.Hello:
                        HandleHello(connection, ClientMessages.ParseHello(reader));
                        break;
                    case MessageType.Ping:
                        var clientTime = ClientMessages.ParsePing(reader);
                        var received = LiveClock.NowUs();
                        connection.EnqueueReliable(Messages.Pong(clientTime, received, LiveClock.NowUs()));
                        break;
                    case MessageType.MapRequest:
                        HandleMapRequest(connection, ClientMessages.ParseMapRequest(reader));
                        break;
                    default:
                        throw new ProtocolException("Unknown message type.");
                }
            }
            catch (ProtocolException e)
            {
                _log.Warn($"Client {connection.Id} ({connection.Address}) violated the protocol: {e.Message}");
                _ = connection.AbortAsync();
            }
        }

        private void HandleHello(ClientConnection connection, ClientMessages.Hello hello)
        {
            if (hello.ProtocolVersion != MessageType.ProtocolVersion)
            {
                throw new ProtocolException("Unsupported protocol version " + hello.ProtocolVersion + ".");
            }

            lock (_lock)
            {
                if (connection.State != ClientState.Connected)
                {
                    throw new ProtocolException("Duplicate hello.");
                }

                connection.State = ClientState.Pending;
            }

            var device = hello.Credential != null ? _devices.Match(hello.Credential) : null;
            if (device != null)
            {
                connection.DeviceId = device.Id;
                _log.Info($"Client {connection.Id} ({connection.Address}) authenticated as remembered device \"{device.Label}\".");
                Subscribe(connection, null);
                return;
            }

            var result = _waitingRoom.Join(connection.Id, connection.Address, connection.Label, code =>
            {
                _log.Info($"Client {connection.Id} ({connection.Address}, {connection.Label}) is waiting for approval, code {code}.");
                connection.EnqueueReliable(Messages.Waiting(code));
            });
            if (result == JoinResult.Pending)
            {
                return;
            }

            _log.Info($"Client {connection.Id} ({connection.Address}) can't join the waiting room: {result}.");
            Reject(connection, Messages.Denied());
        }

        private void HandleMapRequest(ClientConnection connection, ClientMessages.MapRequest request)
        {
            IMapFileSource? map;
            uint sessionId;
            lock (_lock)
            {
                if (connection.State != ClientState.Approved)
                {
                    throw new ProtocolException("Map request before approval.");
                }

                map = _inSession ? _map : null;
                sessionId = _sessionId;
            }

            if (map == null || request.SessionId != sessionId)
            {
                connection.EnqueueReliable(Messages.MapError(request.RequestId, MapErrorCode.NoSession));
                return;
            }

            if (!map.TryOpen(request.FileName, out var stream))
            {
                connection.EnqueueReliable(Messages.MapError(request.RequestId, MapErrorCode.NotAvailable));
                return;
            }

            var transfer = new MapTransfer(stream, request.RequestId, sessionId);
            if (!connection.TryEnqueueTransfer(transfer))
            {
                transfer.Dispose();
                connection.EnqueueReliable(Messages.MapError(request.RequestId, MapErrorCode.TooManyRequests));
            }
        }

        // ---- Approval ----

        private void OnDecided(Decision decision)
        {
            ClientConnection? connection;
            lock (_lock)
            {
                connection = _byContext.Values.FirstOrDefault(c => c.Id == decision.ConnectionId);
            }

            if (connection == null)
            {
                return;
            }

            if (decision.Kind == DecisionKind.Approved)
            {
                connection.DeviceId = decision.Device?.Id;
                _log.Info($"Client {connection.Id} ({connection.Address}) approved{(decision.Device != null ? " and remembered" : "")}.");
                Subscribe(connection, decision.Credential);
            }
            else
            {
                _log.Info($"Client {connection.Id} ({connection.Address}) {decision.Kind.ToString().ToLowerInvariant()}.");
                Reject(connection, Messages.Denied());
            }
        }

        private void OnRevoked(string deviceId)
        {
            List<ClientConnection> affected;
            lock (_lock)
            {
                affected = _byContext.Values.Where(c => c.DeviceId == deviceId).ToList();
                foreach (var c in affected)
                {
                    c.State = ClientState.Closing;
                }
            }

            foreach (var c in affected)
            {
                _log.Info($"Client {c.Id} ({c.Address}) revoked.");
                c.EnqueueReliable(Messages.Revoked());
                c.CloseAfterFlush();
            }
        }

        /// <summary>Marks a client approved and queues the current state; from then on it receives broadcasts.</summary>
        private void Subscribe(ClientConnection connection, byte[]? credential)
        {
            lock (_lock)
            {
                if (connection.State != ClientState.Pending)
                {
                    return;
                }

                connection.State = ClientState.Approved;
                connection.EnqueueReliable(Messages.Approved(credential));
                if (_inSession)
                {
                    foreach (var message in _backlog)
                    {
                        connection.EnqueueReliable(message);
                    }
                }
                else
                {
                    connection.EnqueueReliable(Messages.Idle());
                }
            }
        }

        private void Reject(ClientConnection connection, byte[] message)
        {
            lock (_lock)
            {
                connection.State = ClientState.Closing;
            }

            connection.EnqueueReliable(message);
            connection.CloseAfterFlush();
        }

        private void SafeExpire()
        {
            try
            {
                _waitingRoom.Expire();
            }
            catch (Exception e)
            {
                _log.Error("Waiting room expiry failed", e);
            }
        }

        // ---- Feed pump ----

        private void PumpLoop()
        {
            var writer = new MessageWriter(256);
            while (!_stopping)
            {
                try
                {
                    _feed.Signal.Wait(500);
                    while (!_stopping && _feed.TryTake(out var entry))
                    {
                        Dispatch(ref entry, writer);
                    }
                }
                catch (Exception e)
                {
                    _log.Error("Feed pump error", e);
                }
            }
        }

        private void Dispatch(ref LiveFeed.Entry e, MessageWriter w)
        {
            switch (e.Kind)
            {
                case LiveFeed.Kind.SessionStart:
                    lock (_lock)
                    {
                        _sessionId++;
                        _inSession = true;
                        _map = e.Map;
                        _backlog.Clear();
                        var message = Messages.SessionStart(_sessionId, e.Session!);
                        _backlog.Add(message);
                        foreach (var c in Approved())
                        {
                            c.ClearPoses();
                            c.EnqueueReliable(message);
                        }
                    }

                    _log.Info($"Session {_sessionId} started: {e.Session!.SongName} ({e.Session.Difficulty}).");
                    return;

                case LiveFeed.Kind.SessionEnd:
                    lock (_lock)
                    {
                        if (!_inSession)
                        {
                            return;
                        }

                        _inSession = false;
                        _map = null;
                        _backlog.Clear();
                        var message = Messages.SessionEnd(_sessionId, e.EndReason, e.SongTime);
                        foreach (var c in Approved())
                        {
                            c.ClearPoses();
                            c.EnqueueReliable(message);
                        }
                    }

                    return;

                case LiveFeed.Kind.Pose:
                    Messages.Pose(w, e.CaptureUs, e.SongTime, e.Head, e.Left, e.Right);
                    BroadcastPose(w.ToArray());
                    return;

                case LiveFeed.Kind.NoteCut:
                case LiveFeed.Kind.NoteFinal:
                    Messages.Note(w, e.Kind == LiveFeed.Kind.NoteFinal, e.CaptureUs, e.Note);
                    break;
                case LiveFeed.Kind.Wall:
                    Messages.Wall(w, e.CaptureUs, e.Wall);
                    break;
                case LiveFeed.Kind.Height:
                    Messages.Height(w, e.CaptureUs, e.Height, e.SongTime);
                    break;
                case LiveFeed.Kind.Pause:
                case LiveFeed.Kind.Resume:
                    Messages.PauseResume(w, e.Kind == LiveFeed.Kind.Pause, e.CaptureUs, e.SongTime);
                    break;
                default:
                    return;
            }

            BroadcastEvent(w.ToArray());
        }

        private void BroadcastPose(byte[] message)
        {
            lock (_lock)
            {
                if (!_inSession)
                {
                    return;
                }

                foreach (var c in Approved())
                {
                    c.EnqueuePose(message);
                }
            }
        }

        private void BroadcastEvent(byte[] message)
        {
            lock (_lock)
            {
                if (!_inSession)
                {
                    return;
                }

                if (_backlog.Count < MaxBacklog)
                {
                    _backlog.Add(message);
                }

                foreach (var c in Approved())
                {
                    c.EnqueueReliable(message);
                }
            }
        }

        private IEnumerable<ClientConnection> Approved() => _byContext.Values.Where(c => c.State == ClientState.Approved);

        /// <summary>A short, human-readable device description for the approval screen. Display only.</summary>
        internal static string DescribeUserAgent(string? ua)
        {
            if (string.IsNullOrEmpty(ua))
            {
                return "Unknown browser";
            }

            string browser = ua!.Contains("Edg/") ? "Edge"
                : ua.Contains("OPR/") ? "Opera"
                : ua.Contains("SamsungBrowser/") ? "Samsung Internet"
                : ua.Contains("Firefox/") ? "Firefox"
                : ua.Contains("Chrome/") || ua.Contains("CriOS/") ? "Chrome"
                : ua.Contains("Safari/") ? "Safari"
                : "Browser";
            string os = ua.Contains("Android") ? "Android"
                : ua.Contains("iPhone") ? "iPhone"
                : ua.Contains("iPad") ? "iPad"
                : ua.Contains("Windows") ? "Windows"
                : ua.Contains("Mac OS X") || ua.Contains("Macintosh") ? "macOS"
                : ua.Contains("CrOS") ? "ChromeOS"
                : ua.Contains("Linux") ? "Linux"
                : "unknown OS";
            return browser + " on " + os;
        }
    }
}
