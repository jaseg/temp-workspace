using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using IPEndPoint = System.Net.IPEndPoint;
using System.Security.Cryptography.X509Certificates;
using System.Threading;
using System.Threading.Tasks;
using EmbedIO.Net.Internal;

namespace EmbedIO.Net
{
    /// <summary>
    /// The EmbedIO implementation of the standard HTTP Listener class.
    ///
    /// Based on MONO HttpListener class.
    /// </summary>
    /// <seealso cref="IDisposable" />
    public sealed class HttpListener : IHttpListener
    {
        private readonly SemaphoreSlim _ctxQueueSem = new (0);
        private readonly ConcurrentDictionary<string, HttpListenerContext> _ctxQueue;
        private readonly ConcurrentDictionary<HttpConnection, object> _connections;
        private readonly HttpListenerPrefixCollection _prefixes;
        private bool _disposed;

        /// <summary>
        /// Initializes a new instance of the <see cref="HttpListener" /> class.
        /// </summary>
        /// <param name="certificate">The certificate.</param>
        public HttpListener(X509Certificate? certificate = null)
        {
            Certificate = certificate;

            _prefixes = new HttpListenerPrefixCollection(this);
            _connections = new ConcurrentDictionary<HttpConnection, object>();
            _ctxQueue = new ConcurrentDictionary<string, HttpListenerContext>();
        }
        
        /// <inheritdoc />
        public bool IgnoreWriteExceptions { get; set; } = true;

        /// <inheritdoc />
        public bool IsListening { get; private set; }

        /// <inheritdoc />
        public string Name { get; } = "Unosquare HTTP Listener";

        /// <inheritdoc />
        public List<string> Prefixes => _prefixes.ToList();
        
        /// <summary>
        /// Gets the certificate.
        /// </summary>
        /// <value>
        /// The certificate.
        /// </value>
        internal X509Certificate? Certificate { get; }

        // LiveViewer patch: connection hardening and TLS hooks. See VENDORED.md.

        /// <summary>
        /// Called for every accepted socket before any byte is read; returning <c>false</c> closes the socket.
        /// </summary>
        public Func<IPEndPoint, bool>? AcceptFilter { get; set; }

        /// <summary>
        /// Performs the server side of the TLS handshake on the given network stream and returns the stream to use.
        /// When <c>null</c>, <see cref="System.Net.Security.SslStream"/> is used.
        /// </summary>
        public Func<Stream, X509Certificate, CancellationToken, Task<Stream>>? TlsStreamFactory { get; set; }

        /// <summary>
        /// Maximum time a client may take to complete the TLS handshake.
        /// </summary>
        public TimeSpan TlsHandshakeTimeout { get; set; } = TimeSpan.FromSeconds(10);

        /// <summary>
        /// Maximum time a client may take to send a complete request header (first request on a connection).
        /// </summary>
        public TimeSpan FirstRequestTimeout { get; set; } = TimeSpan.FromSeconds(90);

        /// <summary>
        /// Maximum time a keep-alive connection may stay idle, and to send the header of later requests.
        /// </summary>
        public TimeSpan KeepAliveTimeout { get; set; } = TimeSpan.FromSeconds(15);

        /// <summary>
        /// Maximum size of a request header in bytes.
        /// </summary>
        public int MaxRequestHeaderBytes { get; set; } = 32768;

        /// <summary>
        /// Maximum size of an inbound WebSocket frame or reassembled fragmented message, in bytes.
        /// </summary>
        public int MaxWebSocketMessageBytes { get; set; } = 1024 * 1024;

        /// <summary>
        /// Sets <see cref="System.Net.Sockets.Socket.NoDelay"/> on accepted sockets.
        /// </summary>
        public bool NoDelay { get; set; } = true;

        /// <inheritdoc />
        public void Start()
        {
            if (IsListening)
            {
                return;
            }

            EndPointManager.AddListener(this);
            IsListening = true;
        }

        /// <inheritdoc />
        public void Stop()
        {
            IsListening = false;
            Close(false);
        }

        /// <inheritdoc />
        public void AddPrefix(string urlPrefix) => _prefixes.Add(urlPrefix);

        /// <inheritdoc />
        public void Dispose()
        {
            if (_disposed)
            {
                return;
            }

            Close(true);
            _ctxQueueSem.Dispose();
            _disposed = true;
        }

        /// <inheritdoc />
        public async Task<IHttpContextImpl> GetContextAsync(CancellationToken cancellationToken)
        {
            while (true)
            {
                await _ctxQueueSem.WaitAsync(cancellationToken).ConfigureAwait(false);

                foreach (var key in _ctxQueue.Keys)
                {
                    if (_ctxQueue.TryRemove(key, out var context))
                    {
                        return context;
                    }

                    break;
                }
            }
        }

        internal void RegisterContext(HttpListenerContext context)
        {
            if (!_ctxQueue.TryAdd(context.Id, context))
            {
                throw new InvalidOperationException("Unable to register context");
            }

            _ = _ctxQueueSem.Release();
        }

        internal void UnregisterContext(HttpListenerContext context) => _ctxQueue.TryRemove(context.Id, out _);

        internal void AddConnection(HttpConnection cnc) => _connections[cnc] = cnc;

        internal void RemoveConnection(HttpConnection cnc) => _connections.TryRemove(cnc, out _);

        private void Close(bool closeExisting)
        {
            EndPointManager.RemoveListener(this);

            var keys = _connections.Keys;
            var connections = new HttpConnection[keys.Count];
            keys.CopyTo(connections, 0);
            _connections.Clear();
            var list = new List<HttpConnection>(connections);

            for (var i = list.Count - 1; i >= 0; i--)
            {
                list[i].Close(true);
            }

            if (!closeExisting)
            {
                return;
            }

            while (!_ctxQueue.IsEmpty)
            {
                foreach (var key in _ctxQueue.Keys.ToArray())
                {
                    if (_ctxQueue.TryGetValue(key, out var context))
                    {
                        context.Connection.Close(true);
                    }
                }
            }
        }
    }
}