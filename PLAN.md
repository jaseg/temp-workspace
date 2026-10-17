# Beat Saber live 3D viewer — plan (rev 2)

Goal: watch a Beat Saber session live, in 3D, in a browser on the **local network**.
The game is the native ARM64 build on a Steam Frame. Everything is hosted by the
mod itself; there is no cloud infrastructure. Rendering reuses BeatLeader's web
replay viewer. The latency target is real time: well under one 60 fps frame
(16.7 ms) of added latency.

Out of scope for now:
- Non-Frame and x64 builds of Beat Saber. They may happen to work, but nothing
  is done for them.
- Public access. A later "QR handoff" mode is planned (see the end).

## What we're building on

| Piece | Source | Notes |
|---|---|---|
| Game | [bs-arm64](https://github.com/DaVarga/bs-arm64) | Windows ARM64 Unity player (6000.0.40f1, **Mono**) under Proton on ARM64 SteamOS. BSIPA 4.3.7 + Harmony on 1.41.1+, so the mod is an ordinary C# `net48` BSIPA plugin. |
| Recorder logic | [BeatLeader/beatleader-mod](https://github.com/BeatLeader/beatleader-mod) `ReplayRecorder` (MIT) | **Copied and adapted** into our mod, with no dependency on BeatLeader. We keep the capture points: poses, note cut/miss, swing-rating completion, walls, height, pauses. We drop file writing, upload and the replay manager. |
| Renderer | [BeatLeader/BeatSaber-Web-Replays](https://github.com/BeatLeader/BeatSaber-Web-Replays) (MIT, A-Frame) | Forked. Today it assumes a complete replay with audio as the master clock. We add a live mode driven by the stream. |

## Architecture

```
Steam Frame — Beat Saber process (Proton)                        LAN browser(s)
┌─────────────────────────────────────────────────────┐        ┌──────────────────────┐
│ Unity main thread                                   │        │ forked BL viewer     │
│  LiveRecorder (port of BL ReplayRecorder)           │        │  live-loader          │
│   └─ fixed-size structs → lock-free SPSC ring ──┐   │        │  clock sync           │
│                                                 ▼   │  HTTP  │  pose prediction      │
│ Network thread: LiveServer (no Unity refs)          │ ◄────► │  scoring (all in JS)  │
│   • minimal HTTP/1.1: embedded static viewer        │   WS   │  map parsing (all JS) │
│     + current map files                             │ ─────► │                       │
│   • WebSocket: per-frame binary push, TCP_NODELAY   │        └──────────────────────┘
└─────────────────────────────────────────────────────┘
```

### 1. Mod, split into two assemblies
- **`LiveViewer.Server`** (pure `net48`, **no Unity or game references**). It
  contains the HTTP/WebSocket server, the auth, the protocol encoder and the
  ring buffer.
  - It can be built and unit-tested anywhere with `dotnet`, this container
    included.
  - It also ships as a small console host, which is used for development and
    the "fake live" source.
- **`LiveViewer.Plugin`** (BSIPA). It contains the recorder port, the
  lifecycle (menu, song start, song end) and a small BSML panel showing the
  URL, the pairing QR code, and on/off.
- The game thread only copies poses and events into preallocated structs in a
  ring buffer, with no allocations, no I/O and no locks on the hot path. The
  network thread encodes and sends.

### 2. Server: kept small and auditable
We hand-roll the server on `TcpListener`, which is roughly 500–800 lines. We
don't use `HttpListener`, for three reasons:
- We get full control of `NoDelay`, limits and parsing.
- It behaves the same under Mono and Wine.
- It's less surface to audit.

Endpoints, which are the whole API:

| Route | Purpose |
|---|---|
| `GET /` and `/assets/*` | Viewer bundle, embedded in the DLL as resources. A fixed lookup table, never a filesystem path. |
| `GET /map/{sessionMapId}/{file}` | Files of the **currently loaded** map only (info.dat, the difficulty .dat, audio), looked up from SongCore's level path. `{file}` must match names listed in that map's info.dat. |
| `GET /ws` → WebSocket | Server→client stream. The only client→server messages are `hello{token}` and `ping` for clock sync, each a fixed size with a maximum length. |

### 3. Security boundary
The browser and the LAN are untrusted. The mod trusts nothing it receives
except that the token matches.
- **Pairing token.** A random 128-bit token, created once and stored in the
  mod config. It's shown in game as a URL and QR code
  (`http://<frame-ip>:<port>/#t=<token>`). Because it sits in the fragment, it
  never appears in request lines or logs. The page sends it as the WS
  `hello` (and in a header for `/map`), and the server compares it in
  constant time. There is a "regenerate token" button in the panel.
- **Read-only API.** Nothing a client sends can change game state, the
  filesystem or the mod config. There's no upload, no command channel and no
  reflection.
- **DNS rebinding and CSRF.** `Host` must be an IP literal of one of our
  interfaces, or a configured name. WS `Origin` must equal our own origin.
- **Network scope.** Bind to all interfaces, but reject peers outside the
  private, link-local and loopback ranges. Configurable.
- **Resource limits.**
  - Max header size of 8 KB, max request line length, max WS frame size of
    256 B inbound.
  - Read and handshake timeouts, and at most N concurrent clients (8 by
    default).
  - Per-client send queues with drop-oldest pose frames, so a slow client can
    never stall the game or other clients.
- **Response headers.** Strict CSP (`default-src 'self'`; `connect-src` only
  our WS), `X-Content-Type-Options`, no caching of the map.
- **Error handling.** The server runs on its own threads and every exception is
  contained. A server failure disables the feature and never crashes or stalls
  the game.
- **Testing.** Fuzz the HTTP/WS parser with the console host here.

### 4. Wire protocol: binary, one WS message per event
| Msg | When | Payload (≈ bytes) |
|---|---|---|
| `session` | On connect and on song start | Map id/hash, difficulty, mode, modifiers, player settings (height, left-handed), color scheme, NJS/JD, and game clock info |
| `pose` | **Every rendered game frame** (Frame refresh rate, 90–120 Hz) | Game timestamp (µs), song time, head, left and right (pos + quat): about 100 B |
| `cut` | Immediately at `NoteWasCut` / `NoteWasMissed` | Note id, cut info (as in BSOR). The viewer shows the cut at once. |
| `score` | When the swing rating finishes (about 0.3 s later) | Note id, final pre/post/acc |
| `wall`, `bomb`, `height`, `pause`, `resume`, `end` | As they happen | Small |
| `pong` | Reply to `ping` | Client t0, server time |

Field layouts reuse BSOR's encodings (Vec3/Quat/NoteCutInfo), so the viewer's
decoder helpers still apply. The bandwidth is about 12 KB/s per viewer.

### 5. Latency budget (target: < 16 ms added; aim for about 5–10 ms)
- **Capture.** Read poses as late as possible in the frame:
  `Application.onBeforeRender`, or right after `PlayerTransforms` updates as BL
  does. Measure which is later.
- **Send.** No batching. The game thread signals the network thread, which
  writes immediately with `NoDelay`. Expect less than 0.5 ms in process.
- **LAN.** Wi-Fi typically takes 1–5 ms one way, but the Frame's Wi-Fi may also
  be busy with PC streaming. We'll measure it.
- **Browser.** Up to one display frame (16.7 ms at 60 Hz) between WS receipt
  and the next rAF. This alone breaks the budget unless we **predict**:
  - Keep a clock-offset estimate (NTP-style ping/pong, min-RTT filter).
  - At each rAF, compute the game time that this frame *will be displayed*
    and extrapolate the latest pose to it using velocity and angular velocity
    from the last few samples.
  - Prediction horizons are a few ms to about 20 ms, which is benign for head
    and saber motion.
- **Song clock.** The viewer's song time comes from the stream's clock-synced
  song time, not from local audio. Audio is optional: when it's on, it's
  scheduled via WebAudio with `outputLatency` compensation and resynced on
  drift greater than about 20 ms.
- **Instrumentation from day 1.** A debug overlay shows clock offset, RTT,
  sample age at display and prediction horizon, and the server logs its send
  latency.

### 6. Viewer: fork of BeatSaber-Web-Replays, most processing here
- A new `live-loader` component, used instead of `replay-loader` when the page
  is served by the mod. It does the following:
  - It loads the map from `/map/...` through the existing `zip-loader` parsing
    path, fed from files instead of a zip. That parsing path already
    post-processes v2, v3 and v4 maps.
  - It keeps a rolling `replay` object: a short ring of recent pose frames, plus
    all note events.
  - It makes `processScores()` **incremental**: each `cut` or `score` event is
    matched to its map note on arrival, and the running score, combo,
    multiplier and accuracy are updated.
- Every 3D, scoring and UI calculation runs in the browser. The mod sends raw
  observations only.
- **Live UI.** Remove seek, speed, random replay, the BeatLeader API, external
  CDNs and analytics. All existing camera modes stay.
- **Build output.** One static bundle, embedded into the plugin DLL at build
  time.
- **Repo layout.**
  - `viewer/` is a git subtree of BeatLeader's repo, so we can pull upstream
    fixes.
  - `mod/` holds the Server, the Plugin and the console host.
  - `tools/` holds the fake-live source and the protocol fixtures.

## Milestones
1. **Server core (in this container).** `LiveViewer.Server` with HTTP, WS,
   token auth, limits and unit plus fuzz tests. A console host streams a
   `.bsor` through the live protocol in real time ("fake live"), and a test
   page shows pose and latency stats.
2. **Viewer live mode (in this container).** Fork, `live-loader`, incremental
   scoring, the clock sync and prediction loop, and the stripped UI, developed
   end to end against the fake-live host. Playwright tests measure sample age
   at display.
3. **Plugin on the Frame (needs SSH).** The recorder port, the lifecycle, map
   serving and the BSML panel with QR code. Pull the game's reference DLLs from
   the Frame to build, and verify Proton networking and firewall reachability.
4. **Latency tuning on the real device.** Choose the capture point, measure the
   Wi-Fi, tune prediction, and check the CPU and GC cost in game. We need to
   stay well under the frame budget on the Frame's GPU-bound setup.
5. **Polish.** Song transitions, reconnects, multiple viewers, and token
   regeneration.

## Open questions
- **Beat Saber version:** which version runs on your Frame (1.41.1–1.44.1)?
  I'll target exactly that one.
- **OST/DLC maps:** their notes and audio aren't files on disk. v1 supports
  custom levels only. Later the mod could serialize the beatmap from game
  memory instead.
- **Port:** a fixed default (e.g. 4280), configurable.
- **Firewall:** is SteamOS's firewall open for inbound LAN TCP on the Frame?
  To be checked over SSH.

## Later: QR handoff
- A public static page on another computer shows a QR code, and the Frame's
  cameras scan it. The mod then tells that page where to go, and the page
  redirects to `http://<frame-ip>:<port>/#t=<token>`.
- This is a top-level navigation from HTTPS to plain HTTP, which browsers
  allow.
- The return channel (how the mod reaches the waiting page) needs design
  later. One option is the page polling a rendezvous id encoded in the QR,
  which needs only a tiny public endpoint.
- A plain-HTTP origin limits some browser APIs, but nothing we need.
