using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.IO;
using System.Threading.Tasks;
using EmbedIO.WebSockets;
using LiveViewer.Server.Levels;
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
        public const int MaxApprovedConnections = 64;
        public const int MaxPreAdmissionConnections = 16;
        public const int MaxPreAdmissionConnectionsPerAddress = 4;
        public const int MaxBacklog = 200_000;

        private readonly object _lock = new object();
        private readonly Dictionary<string, ClientConnection> _byContext = new Dictionary<string, ClientConnection>();
        private readonly List<byte[]> _backlog = new List<byte[]>();
        private readonly LiveFeed _feed;
        private readonly WaitingRoom _waitingRoom;
        private readonly DeviceStore _devices;
        private readonly ILiveLog _log;
        private readonly LevelLibrary? _levels;
        private readonly BeatLeaderStats? _stats;
        private readonly Suggestions? _suggestions;
        private readonly string _serverName;
        private readonly AudioStreamState _audio;
        private readonly TimeSpan _helloTimeout;
        private readonly Thread _pump;
        private readonly Timer _expiry;
        private volatile bool _stopping;

        private uint _sessionId;
        private bool _inSession;
        private string _sessionHash = "";
        private byte[]? _selectedSongMessage;
        private string _selectedSongHash = "";
        private string _audioUrl = "";

        public ClientHub(LiveFeed feed, WaitingRoom waitingRoom, DeviceStore devices, string serverName, ILiveLog log,
            TimeSpan helloTimeout, AudioStreamState audio, LevelLibrary? levels = null, BeatLeaderStats? stats = null,
            Suggestions? suggestions = null)
        {
            if (helloTimeout <= TimeSpan.Zero)
            {
                throw new ArgumentOutOfRangeException(nameof(helloTimeout));
            }

            _feed = feed;
            _levels = levels;
            _stats = stats;
            _suggestions = suggestions;
            _waitingRoom = waitingRoom;
            _devices = devices;
            _serverName = serverName;
            _audio = audio;
            _helloTimeout = helloTimeout;
            _log = log;
            _waitingRoom.Decided += OnDecided;
            _devices.Revoked += OnRevoked;
            if (_suggestions != null)
            {
                _suggestions.Changed += OnSuggestionsChanged;
            }

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
            if (_suggestions != null)
            {
                _suggestions.Changed -= OnSuggestionsChanged;
            }

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
                var awaitingAdmission = _byContext.Values.Count(c => c.State != ClientState.Approved);
                var sameAddress = _byContext.Values.Count(c =>
                    c.State != ClientState.Approved && c.Address.Equals(connection.Address));
                if (awaitingAdmission >= MaxPreAdmissionConnections ||
                    sameAddress >= MaxPreAdmissionConnectionsPerAddress)
                {
                    _log.Warn($"Refusing pre-admission connection from {connection.Address}: too many connections.");
                    _ = connection.AbortAsync();
                    return;
                }

                _byContext[context.Id] = connection;
            }

            _ = connection.RunSendLoopAsync();
            connection.EnqueueReliable(Messages.Welcome(LiveClock.NowUs(), _serverName));
            _ = EnforceHelloDeadlineAsync(connection);
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
                        RequireHello(connection);
                        var clientTime = ClientMessages.ParsePing(reader);
                        var received = LiveClock.NowUs();
                        connection.EnqueueReliable(Messages.Pong(clientTime, received, LiveClock.NowUs()));
                        break;
                    case MessageType.LevelListRequest:
                        HandleLevelRequest(connection, ClientMessages.ParseLevelListRequest(reader), null, null);
                        break;
                    case MessageType.LevelFileRequest:
                        var file = ClientMessages.ParseLevelFileRequest(reader);
                        HandleLevelRequest(connection, file.RequestId, file.LevelId, file.Kind);
                        break;
                    case MessageType.LevelStatsRequest:
                        var stats = ClientMessages.ParseLevelStatsRequest(reader);
                        HandleLevelRequest(connection, stats.RequestId, stats.LevelId, null);
                        break;
                    case MessageType.SuggestionAdd:
                    case MessageType.SuggestionRemove:
                        HandleSuggestion(connection, data[0] == MessageType.SuggestionAdd, ClientMessages.ParseSuggestionChange(reader));
                        break;
                    case MessageType.Rename:
                        HandleRename(connection, ClientMessages.ParseRename(reader));
                        break;
                    case MessageType.SuggestionMove:
                        var (moveId, moveIndex) = ClientMessages.ParseSuggestionMove(reader);
                        HandleSuggestionMove(connection, moveId, moveIndex);
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

            connection.Name = WaitingRoom.CleanName(hello.Name, connection.Id);
            if (hello.Credential != null)
            {
                var admitted = _devices.TryAuthenticate(hello.Credential,
                    device => TrySubscribe(connection, null, device.Id), out var device);
                if (admitted)
                {
                    _log.Info($"Client {connection.Id} ({connection.Address}) authenticated as remembered device \"{device!.Label}\".");
                    return;
                }

                if (device != null)
                {
                    _log.Warn($"Client {connection.Id} ({connection.Address}) could not be admitted: viewer limit reached.");
                    Reject(connection, Messages.Denied());
                    return;
                }
            }

            var result = _waitingRoom.Join(connection.Id, connection.Address, connection.Name, connection.Label, name =>
            {
                connection.Name = name;
                _log.Info($"Client {connection.Id} ({connection.Address}, {connection.Label}) is waiting for approval as \"{name}\".");
                connection.EnqueueReliable(Messages.Waiting(name));
            });
            if (result == JoinResult.Pending)
            {
                return;
            }

            _log.Info($"Client {connection.Id} ({connection.Address}) can't join the waiting room: {result}.");
            Reject(connection, Messages.Denied());
        }

        /// <summary>
        /// Level library requests: the list (no level id), a level's cover or song (kind), or its BeatLeader stats
        /// (id, no kind). Answered asynchronously as a file transfer once the library scan is done.
        /// </summary>
        private void HandleLevelRequest(ClientConnection connection, ushort requestId, string? levelId, LevelFileKind? kind)
        {
            lock (_lock)
            {
                if (connection.State != ClientState.Approved)
                {
                    throw new ProtocolException("Level request before approval.");
                }
            }

            var wantsStats = levelId != null && kind == null;
            if (_levels == null || !_levels.Enabled || (wantsStats && _stats == null))
            {
                connection.EnqueueReliable(Messages.MapError(requestId, MapErrorCode.NotAvailable));
                return;
            }

            if (!connection.TryBeginLookup())
            {
                connection.EnqueueReliable(Messages.MapError(requestId, MapErrorCode.TooManyRequests));
                return;
            }

            _ = AnswerLevelRequestAsync(connection, requestId, levelId, kind);
        }

        private async Task AnswerLevelRequestAsync(ClientConnection connection, ushort requestId, string? levelId, LevelFileKind? kind)
        {
            try
            {
                var snapshot = await _levels!.GetAsync().ConfigureAwait(false);
                Stream stream;
                if (levelId == null)
                {
                    stream = new MemoryStream(snapshot.Json, false);
                }
                else if (!snapshot.ByHash.ContainsKey(levelId))
                {
                    connection.EnqueueReliable(Messages.MapError(requestId, MapErrorCode.NotAvailable));
                    return;
                }
                else if (kind == null)
                {
                    stream = new MemoryStream(await _stats!.GetAsync(levelId).ConfigureAwait(false), false);
                }
                else if (!LevelLibrary.TryOpen(snapshot, levelId, kind.Value, out stream))
                {
                    connection.EnqueueReliable(Messages.MapError(requestId, MapErrorCode.NotAvailable));
                    return;
                }

                var transfer = new MapTransfer(stream, requestId);
                if (!connection.TryEnqueueTransfer(transfer))
                {
                    transfer.Dispose();
                    connection.EnqueueReliable(Messages.MapError(requestId, MapErrorCode.TooManyRequests));
                }
            }
            catch (Exception e)
            {
                if (levelId == null)
                {
                    _log.Error("Level list failed", e);
                }

                connection.EnqueueReliable(Messages.MapError(requestId, MapErrorCode.ReadFailed));
            }
            finally
            {
                connection.EndLookup();
            }
        }

        // ---- Suggestions ----

        private void HandleSuggestion(ClientConnection connection, bool add, string levelId)
        {
            lock (_lock)
            {
                if (connection.State != ClientState.Approved)
                {
                    throw new ProtocolException("Suggestion before approval.");
                }
            }

            if (_suggestions == null || _levels == null || !_levels.Enabled || !connection.TryConsumeSuggestionToken())
            {
                // Not applied: the sender gets the unchanged list back so its page shows the real state.
                SendSuggestions(connection);
                return;
            }

            if (!add)
            {
                if (!_suggestions.Remove(levelId))
                {
                    SendSuggestions(connection);
                }

                return;
            }

            _ = AddSuggestionAsync(connection, levelId);
        }

        private void HandleRename(ClientConnection connection, string name)
        {
            lock (_lock)
            {
                if (connection.State != ClientState.Approved)
                {
                    throw new ProtocolException("Rename before approval.");
                }
            }

            // Same budget as suggestion changes; the viewer is told the name in effect either way.
            if (connection.TryConsumeSuggestionToken())
            {
                var clean = WaitingRoom.CleanName(name, connection.Id);
                if (clean != connection.Name)
                {
                    _log.Info($"Client {connection.Id} ({connection.Address}) renamed \"{connection.Name}\" to \"{clean}\".");
                    connection.Name = clean;
                }
            }

            connection.EnqueueReliable(Messages.Name(connection.Name));
        }

        private void HandleSuggestionMove(ClientConnection connection, string levelId, int index)
        {
            lock (_lock)
            {
                if (connection.State != ClientState.Approved)
                {
                    throw new ProtocolException("Suggestion before approval.");
                }
            }

            // Not applied (unknown level, already there, rate limit): the sender gets the real order back.
            if (_suggestions == null || !connection.TryConsumeSuggestionToken() || !_suggestions.Move(levelId, index))
            {
                SendSuggestions(connection);
            }
        }

        private async Task AddSuggestionAsync(ClientConnection connection, string levelId)
        {
            try
            {
                // Only installed levels can be suggested: the game can't show anything else.
                var snapshot = await _levels!.GetAsync().ConfigureAwait(false);
                if (snapshot.ByHash.ContainsKey(levelId) && _suggestions!.Add(levelId, connection.Name))
                {
                    _log.Info($"Client {connection.Id} ({connection.Address}) suggested level {levelId}.");
                    return;
                }
            }
            catch (Exception e)
            {
                _log.Error("Adding a suggestion failed", e);
            }

            SendSuggestions(connection);
        }

        private void SendSuggestions(ClientConnection connection)
        {
            if (_suggestions != null)
            {
                connection.EnqueueReliable(Messages.Suggestions(_suggestions.Json()));
            }
        }

        private void OnSuggestionsChanged()
        {
            var message = Messages.Suggestions(_suggestions!.Json());
            lock (_lock)
            {
                foreach (var c in Approved())
                {
                    c.EnqueueReliable(message);
                }
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
                if (TrySubscribe(connection, decision.Credential, decision.Device?.Id))
                {
                    _log.Info($"Client {connection.Id} ({connection.Address}) approved{(decision.Device != null ? " and remembered" : "")}.");
                }
                else
                {
                    if (decision.Device != null)
                    {
                        _devices.Remove(decision.Device.Id);
                    }

                    _log.Warn($"Client {connection.Id} ({connection.Address}) could not be admitted: viewer limit reached.");
                    Reject(connection, Messages.Denied());
                }
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
        private bool TrySubscribe(ClientConnection connection, byte[]? credential, string? deviceId)
        {
            lock (_lock)
            {
                if (connection.State != ClientState.Pending)
                {
                    return false;
                }

                if (_byContext.Values.Count(c => c.State == ClientState.Approved) >= MaxApprovedConnections)
                {
                    return false;
                }

                connection.DeviceId = deviceId;
                connection.State = ClientState.Approved;
                connection.EnqueueReliable(Messages.Approved(credential));
                connection.EnqueueReliable(Messages.Name(connection.Name));
                SendSuggestions(connection);
                if (_selectedSongMessage != null)
                {
                    connection.EnqueueReliable(_selectedSongMessage);
                }
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

                return true;
            }
        }

        private void RequireHello(ClientConnection connection)
        {
            lock (_lock)
            {
                if (connection.State == ClientState.Connected || connection.State == ClientState.Closing)
                {
                    throw new ProtocolException("Message before hello.");
                }
            }
        }

        private async Task EnforceHelloDeadlineAsync(ClientConnection connection)
        {
            await Task.Delay(_helloTimeout).ConfigureAwait(false);
            lock (_lock)
            {
                if (!_byContext.TryGetValue(connection.ContextId, out var current) ||
                    !ReferenceEquals(current, connection) || connection.State != ClientState.Connected)
                {
                    return;
                }

                connection.State = ClientState.Closing;
            }

            _log.Warn($"Client {connection.Id} ({connection.Address}) did not send hello within {_helloTimeout.TotalSeconds:g} seconds.");
            await connection.AbortAsync().ConfigureAwait(false);
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
                case LiveFeed.Kind.SongSelected:
                    lock (_lock)
                    {
                        var selected = e.Selection!;
                        // Gameplay setup repeats the menu selection. Keep the existing capability alive so a
                        // browser which is already preloading it cannot race a token replacement at song start.
                        if (_audioUrl.Length == 0 || !string.Equals(_selectedSongHash, selected.Hash, StringComparison.OrdinalIgnoreCase))
                        {
                            _audioUrl = _audio.Select(selected.Audio);
                            _selectedSongHash = selected.Hash;
                        }
                        _selectedSongMessage = Messages.SongSelected(_audioUrl, selected.Hash, selected.SongName,
                            selected.SongSubName, selected.SongAuthor, selected.BeatsPerMinute);
                        foreach (var c in Approved()) c.EnqueueReliable(_selectedSongMessage);
                    }
                    return;

                case LiveFeed.Kind.SessionStart:
                    lock (_lock)
                    {
                        _sessionId++;
                        _inSession = true;
                        _sessionHash = e.Session!.Hash;
                        e.Session!.AudioUrl = _audioUrl;
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
                    string hash;
                    lock (_lock)
                    {
                        if (!_inSession)
                        {
                            return;
                        }

                        hash = _sessionHash;
                        _inSession = false;
                        _backlog.Clear();
                        var message = Messages.SessionEnd(_sessionId, e.EndReason, e.SongTime);
                        foreach (var c in Approved())
                        {
                            c.ClearPoses();
                            c.EnqueueReliable(message);
                        }
                    }

                    // A played level leaves the playlist: finished, whether cleared or failed. Quitting or restarting
                    // keeps it. The game's ids are upper-case hashes; the playlist's are lower case.
                    if ((e.EndReason == SessionEndReason.Cleared || e.EndReason == SessionEndReason.Failed)
                        && _suggestions != null && _suggestions.Remove(hash.ToLowerInvariant()))
                    {
                        _log.Info($"Played level {hash} removed from the playlist.");
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
                case LiveFeed.Kind.NoteSpawn:
                    Messages.NoteSpawn(w, e.CaptureUs, e.NoteSpawn);
                    break;
                case LiveFeed.Kind.WallSpawn:
                    Messages.WallSpawn(w, e.CaptureUs, e.WallSpawn);
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
