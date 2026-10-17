# Live viewer: mod side

| Path | What |
|---|---|
| `LiveViewer.Server/` | The web server the mod hosts. `netstandard2.0` with **no Unity or game references**. Includes the waiting room, protocol, live feed and an embedded test page (`www/`). |
| `LiveViewer.Host/` | Development host (`net8.0`). Runs the server outside the game and plays a BeatLeader replay into it in real time ("fake live"). |
| `LiveViewer.Server.Tests/` | Unit and integration tests (xunit). The integration tests run the real server over TLS on loopback. |
| `vendor/EmbedIO/` | Vendored EmbedIO with local hardening patches; see `VENDORED.md`. |
| `tools/browser-smoke.cjs` | Opens the test page in headless Chromium against a running host and reports latency stats. |
| `tools/viewer-smoke.cjs` | Same for the real viewer (`--www ../viewer/dist`): screenshots, errors, score state, extrapolation horizon. |
| `tools/viewer-transitions.cjs` | Follows the viewer across several songs (`--loop --start 166`); can approve through the host console via a FIFO. |

Both viewer scripts press "Request to watch" first.
| `PROTOCOL.md` | The WebSocket protocol. |

The BSIPA plugin (`LiveViewer.Plugin`) comes in milestone 3. It needs the game's
assemblies to build.

## Build and test

You need the .NET 8 SDK.

```sh
dotnet build LiveViewer.sln -c Release
dotnet test LiveViewer.Server.Tests
```

## Fake live

```sh
dotnet run --project LiveViewer.Host -c Release -- --replay 8931530 --loop
```

- `--replay` takes a BeatLeader score id, a `.bsor` URL or a local file.
- The map is downloaded by hash into `./livedata/maps` unless you pass `--map`.

Open `https://localhost:4280/` and accept the certificate warning. The page
shows a code; type `a <code>` in the host's console to allow it once, or
`r <code>` to remember the device. `--auto-approve` skips that, for tests.

To serve the real viewer instead of the test page, build it (`cd ../viewer && npm ci && npm run build`) and
add `--www ../viewer/dist`. The host loads the files once at startup, so restart it after rebuilding.

Smoke test from another shell:

```sh
dotnet run --project LiveViewer.Host -c Release -- --replay 8931530 --loop --auto-approve &
NODE_PATH=$(npm root -g) node tools/browser-smoke.cjs https://localhost:4280/ 10
```

## Security boundary, in short

- **Before TLS:** peers outside private, link-local and loopback ranges are
  dropped right after accept. The TLS handshake has a 10 s timeout, and the
  request header a 10 s deadline and an 8 KB limit.
- **HTTP:** `Host` must be one of our names or the literal address the client
  connected to; this blocks DNS rebinding. Only GET and HEAD are allowed. Static
  files come from an in-memory table, never from the filesystem by request path.
  Strict CSP on every response.
- **WebSocket:**
  - `Origin` must be our own origin, and the subprotocol `bslive.v1` is
    required.
  - Inbound frames are capped at 1 KB, and clients get about 20 messages per
    second.
  - Every message is parsed strictly; anything unexpected closes the
    connection.
  - At most 16 connections in total, 4 per address.
- **Access:** nothing beyond the static page and the waiting room until the
  player approves the device in game.
  - Remembered devices hold a random 256-bit credential, and only its SHA-256 is
    stored. Revoking a device drops its live connections.
  - Map files: only names listed by the current map, resolved inside the map
    folder, at most 64 MB.
- **The game thread** only writes into a preallocated ring buffer. A slow client
  only loses its own pose frames; a client that can't keep up with events is
  disconnected.
