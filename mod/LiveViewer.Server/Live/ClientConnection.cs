using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Threading;
using System.Threading.Tasks;
using EmbedIO.WebSockets;
using LiveViewer.Server.Protocol;

namespace LiveViewer.Server.Live
{
    internal enum ClientState
    {
        Connected, // waiting for Hello
        Pending,   // in the waiting room
        Approved,
        Closing,
    }

    /// <summary>
    /// One browser connection: its approval state and its outbound queues, drained by a dedicated send loop.
    /// Queues are prioritized: reliable messages (session, notes, waiting room) first, then the newest poses,
    /// then one map chunk at a time, so a map download never delays live data by more than one chunk.
    /// </summary>
    internal sealed class ClientConnection
    {
        public const int MaxQueuedPoses = 4;
        public const int MaxQueuedReliable = 20000;
        public const int MaxQueuedTransfers = 16;
        public const int MaxPendingLookups = 8;
        public const int MapChunkBytes = 16 * 1024 - 16; // one TLS record with the message header

        private static readonly TimeSpan SendTimeout = TimeSpan.FromSeconds(5);
        private static long _nextId;

        private readonly object _lock = new object();
        private readonly Queue<byte[]> _reliable = new Queue<byte[]>();
        private readonly Queue<byte[]> _poses = new Queue<byte[]>();
        private readonly Queue<MapTransfer> _transfers = new Queue<MapTransfer>();
        private readonly SemaphoreSlim _wake = new SemaphoreSlim(0, int.MaxValue);
        private readonly IWebSocketContext _context;
        private readonly ILiveLog _log;

        // Inbound rate limit (token bucket).
        private const double TokensPerSecond = 20;
        private const double MaxTokens = 40;
        private double _tokens = MaxTokens;
        private long _tokensUpdatedUs = LiveClock.NowUs();

        // Suggestion changes: a few in a row, then one every two seconds.
        private const double SuggestionsPerSecond = 0.5;
        private const double MaxSuggestionTokens = 10;
        private double _suggestionTokens = MaxSuggestionTokens;
        private long _suggestionTokensUpdatedUs = LiveClock.NowUs();

        private bool _closeAfterFlush;
        private int _closed;
        private int _pendingLookups;

        public ClientConnection(IWebSocketContext context, string label, ILiveLog log)
        {
            Id = Interlocked.Increment(ref _nextId);
            _context = context;
            _log = log;
            Address = context.RemoteEndPoint.Address.IsIPv4MappedToIPv6
                ? context.RemoteEndPoint.Address.MapToIPv4()
                : context.RemoteEndPoint.Address;
            Label = label;
        }

        public long Id { get; }

        public IPAddress Address { get; }

        public string Label { get; }

        public string ContextId => _context.Id;

        /// <summary>Guarded by the hub's lock.</summary>
        public ClientState State { get; set; } = ClientState.Connected;

        /// <summary>Remembered device this connection authenticated as, if any.</summary>
        public string? DeviceId { get; set; }

        public bool IsClosed => Volatile.Read(ref _closed) != 0;

        public void EnqueueReliable(byte[] message)
        {
            lock (_lock)
            {
                if (_closeAfterFlush)
                {
                    return;
                }

                if (_reliable.Count >= MaxQueuedReliable)
                {
                    _log.Warn($"Client {Id} can't keep up; disconnecting.");
                    _ = AbortAsync();
                    return;
                }

                _reliable.Enqueue(message);
            }

            _wake.Release();
        }

        public void EnqueuePose(byte[] message)
        {
            lock (_lock)
            {
                if (_closeAfterFlush)
                {
                    return;
                }

                if (_poses.Count >= MaxQueuedPoses)
                {
                    _poses.Dequeue();
                }

                _poses.Enqueue(message);
            }

            _wake.Release();
        }

        public void ClearPoses()
        {
            lock (_lock)
            {
                _poses.Clear();
            }
        }

        public bool TryEnqueueTransfer(MapTransfer transfer)
        {
            lock (_lock)
            {
                if (_closeAfterFlush || _transfers.Count >= MaxQueuedTransfers)
                {
                    return false;
                }

                _transfers.Enqueue(transfer);
            }

            _wake.Release();
            return true;
        }

        /// <summary>
        /// Reserves a slot for a request answered asynchronously (level list, level file, stats). Bounded per
        /// connection so a client can't pile up work; release with <see cref="EndLookup"/>.
        /// </summary>
        public bool TryBeginLookup()
        {
            if (Interlocked.Increment(ref _pendingLookups) <= MaxPendingLookups)
            {
                return true;
            }

            Interlocked.Decrement(ref _pendingLookups);
            return false;
        }

        public void EndLookup() => Interlocked.Decrement(ref _pendingLookups);

        /// <summary>Sends what's queued (dropping poses and transfers), then closes.</summary>
        public void CloseAfterFlush()
        {
            lock (_lock)
            {
                _closeAfterFlush = true;
                _poses.Clear();
                foreach (var t in _transfers)
                {
                    t.Dispose();
                }

                _transfers.Clear();
            }

            _wake.Release();
        }

        /// <summary>Token-bucket check for inbound messages.</summary>
        public bool TryConsumeInboundToken()
        {
            lock (_lock)
            {
                return TryConsume(ref _tokens, ref _tokensUpdatedUs, TokensPerSecond, MaxTokens);
            }
        }

        /// <summary>Token-bucket check for adding or removing a suggestion.</summary>
        public bool TryConsumeSuggestionToken()
        {
            lock (_lock)
            {
                return TryConsume(ref _suggestionTokens, ref _suggestionTokensUpdatedUs, SuggestionsPerSecond, MaxSuggestionTokens);
            }
        }

        private static bool TryConsume(ref double tokens, ref long updatedUs, double perSecond, double max)
        {
            var now = LiveClock.NowUs();
            tokens = Math.Min(max, tokens + (now - updatedUs) / 1e6 * perSecond);
            updatedUs = now;
            if (tokens < 1)
            {
                return false;
            }

            tokens -= 1;
            return true;
        }

        public async Task RunSendLoopAsync(Func<uint> currentSessionId)
        {
            var chunk = new byte[MapChunkBytes];
            try
            {
                while (!IsClosed)
                {
                    await _wake.WaitAsync().ConfigureAwait(false);
                    while (!IsClosed)
                    {
                        byte[]? message = null;
                        MapTransfer? transfer = null;
                        bool close;
                        lock (_lock)
                        {
                            if (_reliable.Count > 0)
                            {
                                message = _reliable.Dequeue();
                            }
                            else if (_poses.Count > 0)
                            {
                                message = _poses.Dequeue();
                            }
                            else if (_transfers.Count > 0)
                            {
                                transfer = _transfers.Peek();
                            }

                            close = message == null && transfer == null && _closeAfterFlush;
                        }

                        if (close)
                        {
                            await CloseAsync().ConfigureAwait(false);
                            return;
                        }

                        if (message != null)
                        {
                            await SendAsync(message).ConfigureAwait(false);
                            continue;
                        }

                        if (transfer == null)
                        {
                            break;
                        }

                        var (next, done) = await transfer.NextMessageAsync(chunk, currentSessionId()).ConfigureAwait(false);
                        if (done)
                        {
                            lock (_lock)
                            {
                                if (_transfers.Count > 0 && _transfers.Peek() == transfer)
                                {
                                    _transfers.Dequeue();
                                }
                            }

                            transfer.Dispose();
                        }

                        if (next != null)
                        {
                            await SendAsync(next).ConfigureAwait(false);
                        }
                    }
                }
            }
            catch (Exception e)
            {
                if (!IsClosed)
                {
                    _log.Info($"Client {Id} send loop ended: {e.Message}");
                }

                await AbortAsync().ConfigureAwait(false);
            }
        }

        public void MarkClosed()
        {
            if (Interlocked.Exchange(ref _closed, 1) != 0)
            {
                return;
            }

            _wake.Release();
            lock (_lock)
            {
                foreach (var t in _transfers)
                {
                    t.Dispose();
                }

                _transfers.Clear();
                _reliable.Clear();
                _poses.Clear();
            }
        }

        public async Task AbortAsync()
        {
            MarkClosed();
            try
            {
                var close = _context.WebSocket.CloseAsync();
                await Task.WhenAny(close, Task.Delay(1000)).ConfigureAwait(false);
            }
            catch
            {
                // already gone
            }

            try
            {
                _context.WebSocket.Dispose();
            }
            catch
            {
                // already gone
            }
        }

        private async Task CloseAsync()
        {
            await AbortAsync().ConfigureAwait(false);
        }

        private async Task SendAsync(byte[] message)
        {
            var send = _context.WebSocket.SendAsync(message, false, CancellationToken.None);
            if (await Task.WhenAny(send, Task.Delay(SendTimeout)).ConfigureAwait(false) != send)
            {
                throw new TimeoutException("Send timed out.");
            }

            await send.ConfigureAwait(false);
        }
    }

    /// <summary>
    /// A file being streamed to one client in chunks. Map files are bound to their session and abort when it
    /// ends; level library files and generated documents are not.
    /// </summary>
    internal sealed class MapTransfer : IDisposable
    {
        private readonly Stream _stream;
        private readonly ushort _requestId;
        private readonly uint? _sessionId;
        private readonly uint _length;
        private uint _offset;
        private bool _sentEmpty;

        public MapTransfer(Stream stream, ushort requestId, uint? sessionId)
        {
            _stream = stream;
            _requestId = requestId;
            _sessionId = sessionId;
            _length = (uint) Math.Min(stream.Length, MapDirectory.MaxFileBytes);
        }

        /// <summary>Reads the next chunk. Returns the message to send (if any) and whether the transfer is finished.</summary>
        public async Task<(byte[]? message, bool done)> NextMessageAsync(byte[] buffer, uint currentSessionId)
        {
            if (_sessionId.HasValue && currentSessionId != _sessionId.Value)
            {
                return (Messages.MapError(_requestId, MapErrorCode.NoSession), true);
            }

            if (_length == 0)
            {
                // Zero-length file: one empty chunk tells the client it's complete.
                var first = !_sentEmpty;
                _sentEmpty = true;
                return (first ? Messages.MapChunk(_requestId, 0, 0, buffer, 0) : null, true);
            }

            try
            {
                var want = (int) Math.Min(buffer.Length, _length - _offset);
                var read = await _stream.ReadAsync(buffer, 0, want).ConfigureAwait(false);
                if (read <= 0)
                {
                    return (Messages.MapError(_requestId, MapErrorCode.ReadFailed), true);
                }

                var message = Messages.MapChunk(_requestId, _length, _offset, buffer, read);
                _offset += (uint) read;
                return (message, _offset >= _length);
            }
            catch (IOException)
            {
                return (Messages.MapError(_requestId, MapErrorCode.ReadFailed), true);
            }
        }

        public void Dispose() => _stream.Dispose();
    }
}
