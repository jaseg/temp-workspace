# Live viewer: mod side

| Path | What |
|---|---|
| `LiveViewer.Server/` | The web server the mod hosts. `netstandard2.0` with **no Unity or game references**. Includes the waiting room, protocol, live feed and an embedded test page (`www/`). |
| `LiveViewer.Host/` | Development host (`net8.0`). Runs the server outside the game and plays a BeatLeader replay into it in real time ("fake live"). |
| `LiveViewer.Server.Tests/` | Unit and integration tests (xunit). The integration tests run the real server over TLS on loopback. |
| `LiveViewer.Plugin/` | The BSIPA plugin (`net472`): starts the server, streams gameplay (`Recording/`, adapted from BeatLeader's ReplayRecorder) and adds the "Live Viewer" menu screen (`UI/`). |
| `vendor/EmbedIO/` | Vendored EmbedIO with local hardening patches; see `VENDORED.md`. |
| `tools/browser-smoke.cjs` | Opens the test page in headless Chromium against a running host and reports latency stats. |
| `tools/viewer-smoke.cjs` | Same for the real viewer (`--www ../viewer/dist`): screenshots, errors, score state, extrapolation horizon. |
| `tools/levels-smoke.cjs` | Checks the level browser (list, covers, BeatLeader stars, details, audio preview) on desktop and phone sizes. |
| `tools/viewer-transitions.cjs` | Follows the viewer across several songs (`--loop --start 166`); can approve through the host console via a FIFO. |
| `PROTOCOL.md` | The WebSocket protocol. |

Both viewer scripts press "Request to watch" first.

## Build and test

You need the .NET 8 SDK.

```sh
dotnet build LiveViewer.sln -c Release
dotnet test LiveViewer.Server.Tests
```

## Plugin

The plugin builds against the game's own assemblies, which aren't in the repository. Copy them from a
Beat Saber 1.44.1 install with BSIPA, SiraUtil, SongCore and BSML into `refs/` (gitignored), for example from
the Frame's BSManager instance:

```sh
I=.local/share/BSManager/BSInstances/1.44.1
rsync -a --include='*.dll' --exclude='*' "steamos@frame:$I/Beat Saber_Data/Managed/" refs/Managed/
rsync -a --include='*.dll' --exclude='*' "steamos@frame:$I/Plugins/" refs/Plugins/
rsync -a "steamos@frame:$I/Libs/" refs/Libs/
```

Build the viewer first (`npm run build` in `../viewer`); the plugin embeds `viewer/dist` as a zip. Then
`dotnet build LiveViewer.Plugin -c Release` writes `LiveViewer.Plugin/bin/Release/net472/package/`, whose
`Plugins/` and `Libs/` go into the game folder.

Settings are in `UserData/LiveViewer.json`; the certificate and remembered devices in `UserData/LiveViewer/`.
`BeatLeaderStats` (on by default) can also be switched from the menu screen. Two settings exist for testing on the device
without anyone in the headset and must stay off otherwise:

- `DevAutoApprove`: lets every waiting browser in.
- `DevAutoPlayLevel`: `"<hash>"` or `"<hash> <Difficulty>"`; plays that level with No Fail once the main menu
  is up.

## Fake live

```sh
dotnet run --project LiveViewer.Host -c Release -- --replay 8931530 --loop
```

- `--replay` takes a BeatLeader score id, a `.bsor` URL or a local file.
- The map is downloaded by hash into `./livedata/maps` unless you pass `--map`.

Open `https://localhost:4280/` and accept the certificate warning. The page
shows a three-word code; type `a <code>` in the host's console to allow it once
(e.g. `a aztec istanbul yucatan`; case and separators don't matter), or
`r <code>` to remember the device. `--auto-approve` skips that, for tests.

The level browser lists the levels in `--levels <dir>` (repeatable; default
`./livedata/maps`, where downloaded maps go) and fetches their BeatLeader stats
unless you pass `--no-beatleader`.

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
  - Level library: other installed levels expose only their cover and song
    file, requested by kind and level hash, never by name. BeatLeader is asked
    only about installed levels' hashes, by the mod.
- **The game thread** only writes into a preallocated ring buffer. A slow client
  only loses its own pose frames; a client that can't keep up with events is
  disconnected.
