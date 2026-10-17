# Vendored EmbedIO

Upstream: https://github.com/unosquare/embedio, commit `6a6bb41` (2026-03-08), `src/EmbedIO` only.
License: MIT (see `LICENSE`).

The upstream code is imported unmodified in one commit; every local change is a
separate, later commit touching only this directory. `git log -- mod/vendor/EmbedIO`
lists them. Local changes are documented below.

## Local changes

All marked with a `LiveViewer patch` comment.

- `EmbedIO.csproj`: standalone build file (no central package management, no analyzers).
- `Net/HttpListener.cs`: new public knobs: `AcceptFilter`, `TlsStreamFactory`, `TlsHandshakeTimeout`,
  `FirstRequestTimeout`, `KeepAliveTimeout`, `MaxRequestHeaderBytes`, `MaxWebSocketMessageBytes`, `NoDelay`.
- `Net/Internal/EndPointListener.cs`, `Net/Internal/HttpConnection.cs`:
  - Peers are filtered right after accept, before anything is read.
  - `TCP_NODELAY` is set on accepted sockets. Small per-frame WebSocket messages otherwise wait on Nagle and
    delayed ACKs.
  - The TLS handshake is asynchronous and has a timeout. Upstream ran it synchronously with no timeout, so a
    silent client held a thread pool thread forever. The TLS implementation is pluggable.
  - The request timeout now covers the whole request header. Upstream stopped it after the first chunk, which
    allowed slowloris-style trickling.
  - The header size limit is configurable.
- `WebSockets/Internal/WebSocket.cs`, `WebSockets/Internal/WebSocketFrameStream.cs`:
  - Oversized inbound frames and fragmented messages are rejected before their payload is allocated. Upstream
    accepted up to `long.MaxValue`.
  - Frame writes are serialized. `SslStream` doesn't allow concurrent writes, and pong and close frames are
    written from the receive loop.
- `Net/Internal/ListenerPrefix.cs`: wildcard prefixes (`https://*:port/`) parse again. Newer `System.Uri` rejects `*`
  as a host name.
