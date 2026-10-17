# Beat Saber live 3D viewer — plan (rev 3)

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
- **`LiveViewer.Server`** (pure `net48`/netstandard2.0, **no Unity or game
  references**). It contains:
  - the web server setup (on libraries; see below)
  - the waiting room and device approvals
  - the protocol encoder
  - the ring buffer

  It builds and tests anywhere with `dotnet`, this container included. A small
  console host is used for development and for the "fake live" source.
- **`LiveViewer.Plugin`** (BSIPA). It contains:
  - the recorder port
  - the lifecycle (menu, song start, song end)
  - the BSML menu screens: status and URLs, waiting room, approved
    devices
- The game thread only copies poses and events into preallocated structs in a
  lock-free ring buffer, with no allocations, no I/O and no locks on the hot
  path. The network thread encodes and sends.
- **Dependencies** ship in `Libs/` next to the plugin, as BSIPA does for other
  mods:

| Need | Library | Notes |
|---|---|---|
| HTTP(S) + WebSocket | [EmbedIO](https://github.com/unosquare/embedio) (MIT, netstandard2.0, maintained) | Fully managed listener, so it doesn't depend on Mono's or Wine's `HttpListener`. It has a built-in WebSocket module, serves static files from embedded resources, and supports TLS via `X509Certificate2`. We vendor it with two small patches: setting `Socket.NoDelay` on accepted sockets (it doesn't today, and Nagle plus delayed ACK can add about 40 ms), and a hook to supply our own TLS stream (see the TLS risk). |
| Certificate generation (and TLS fallback) | [BouncyCastle.Cryptography](https://github.com/bcgit/bc-csharp) (MIT, netstandard2.0) | Fully managed, so it doesn't depend on whether Unity's Mono has `CertificateRequest`. |
| mDNS / DNS-SD | [Makaretu.Dns.Multicast](https://github.com/richardschneider/net-mdns) (MIT, netstandard2.0) | Announces the host name and the service (see §7). |

### 2. Web surface: everything sensitive goes over one authenticated WebSocket
The whole API:

| Route | Who | Purpose |
|---|---|---|
| `GET /`, `/assets/*` | Anyone on the LAN | The viewer bundle, embedded in the DLL as resources. It's public code and holds no data. Served from a fixed lookup table, never from the filesystem. |
| `GET /ws` → WSS | Anyone can *connect*; only approved devices get data | The waiting-room handshake, then the live stream and the current map's files. |

There are no other HTTP endpoints. Map files (info.dat, difficulty .dat, audio)
are sent over the authenticated WebSocket as chunked binary messages. This
means no request-level authentication logic is needed in HTTP handlers.

### 3. Security boundary
The browser and the LAN are untrusted. The only thing that grants access is the
player approving a device in game.

- **TLS everywhere.**
  - On first start the mod generates an ECDSA P-256 self-signed certificate
    with BouncyCastle and stores it in `UserData/LiveViewer/`.
  - Its SANs are the mDNS name and the current LAN IPs. It's regenerated only
    on request from the menu, so the browser warning appears only once per
    device.
  - The menu shows the certificate's SHA-256 fingerprint, short form, so
    careful users can compare it to what the browser shows.
  - Plain HTTP on the port gets no content: we only listen with TLS.
- **Waiting room instead of tokens.**
  1. A browser opens the page and connects to `/ws`. It receives a random
     **match code** of three words from the PGP word list (e.g. `Aztec
     Istanbul Yucatan`) and shows it while waiting for approval.
  2. The menu's **Waiting room** screen lists pending devices: the match code,
     IP, browser and OS (parsed from the User-Agent, for display only) and age.
     The buttons are **Allow once**, **Allow & remember** and **Deny**.
  3. On approval, the server sends that WS session a random 256-bit **device
     credential**. The page keeps it in `localStorage` and presents it in the
     `hello` of later connections. The server stores only a hash, plus a label
     and last-seen time.
  4. An **Approved devices** screen lists remembered devices with **Revoke**.
     Revoking also drops live sessions immediately.
  5. Pending requests made during a song wait until you're back in the menu. A
     small "N waiting" badge shows on the main menu button.
- **Abuse limits in the waiting room.**
  - At most 4 pending devices in total, and 1 per IP.
  - Pending entries expire after 2 minutes.
  - After a Deny, the IP has a cooldown. Excess connections are closed without
    being listed, so the menu can't be spammed.
- **Read-only.** Nothing a client sends can change game state, the filesystem
  or the mod config. Client→server messages are only `hello`, `ping` (clock
  sync) and `mapRequest(file)` for the current map's files. `file` must be a
  name listed in that map's info.dat. Each message type has a fixed or small
  maximum size, and anything else closes the connection.
- **DNS rebinding and CSRF.**
  - `Host` must be our mDNS name or an IP literal of one of our interfaces.
  - The WS `Origin` must equal our own origin.
- **Network scope.** We bind on all interfaces but reject peers outside the
  private, link-local and loopback ranges (configurable).
- **Resource limits.**
  - Header size, inbound WS frame size and handshake and read timeouts are
    capped (the EmbedIO options, plus checks in our module).
  - At most 8 concurrent clients.
  - Each client has its own send queue. When it backs up, the oldest pose
    frames are dropped, so a slow client never stalls the game or other
    clients.
- **Headers.** Strict CSP (`default-src 'self'`; `connect-src` only our own
  wss origin), `X-Content-Type-Options`, `Referrer-Policy: no-referrer`.
- **Error handling.** The server runs on its own threads and every exception is
  contained. A server failure disables the feature and never crashes or stalls
  the game.
- **Testing.** Unit tests for the waiting-room state machine and the message
  validation. Fuzzing of the WS message parser with the console host.

### 4. Wire protocol: binary, one WS message per event
| Msg | When | Payload (≈ bytes) |
|---|---|---|
| `session` | After approval and on song start | Map id/hash, difficulty, mode, modifiers, player settings (height, left-handed), color scheme, NJS/JD, and game clock info |
| `pose` | **Every rendered game frame** (Frame refresh rate, 90–120 Hz) | Game timestamp (µs), song time, head, left and right (pos + quat): about 100 B |
| `cut` | Immediately at `NoteWasCut` / `NoteWasMissed` | Note id, cut info (as in BSOR). The viewer shows the cut at once. |
| `score` | When the swing rating finishes (about 0.3 s later) | Note id, final pre/post/acc |
| `wall`, `bomb`, `height`, `pause`, `resume`, `end` | As they happen | Small |
| `pong` | Reply to `ping` | Client t0, server time |
| `waiting`, `approved{credential}`, `denied`, `revoked` | Waiting-room lifecycle | Small |
| `mapChunk` | Reply to `mapRequest` | Up to 64 KB chunks. Sent on a lower priority than pose frames, so a map download never delays live data. |

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
  is served by the mod. It includes a waiting-room screen that shows the match
  code. It does the following:
  - It loads the map over the WebSocket through the existing `zip-loader`
    parsing path, fed from files instead of a zip. That parsing path already
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

### 7. Discovery: a human-readable address
- The mod answers mDNS for **`beatsaber.local`** (configurable). If that name
  is taken, it falls back to `beatsaber-2.local`, and so on.
- It also announces a DNS-SD service `_https._tcp`, named "Beat Saber Live
  (<player>)", with `path=/`.
- **People type `https://beatsaber.local:4280`.** The port is fixed at 4280.
  - Browsers ignore the port in DNS-SD SRV records, so a URL without a port
    would need 443.
  - Wine runs unprivileged and can't bind 443, so we don't try.
  - A URL without a port is left to the later QR handoff.
- **Where `.local` names resolve:**
  - out of the box on Windows 10+, macOS, iOS and iPadOS
  - on most desktop Linux distributions, via nss-mdns
  - on Android, it depends on the version and browser
- **Fallback, always shown in the menu:** the IP URL. The player reads it out.
  The Frame has no screen anyone else can see, so the menu doesn't show QR
  codes.
- **On-device risk:** SteamOS probably already runs avahi on UDP 5353. Two
  responders can share the port when both use `SO_REUSEADDR`, but this needs
  checking under Wine. If it fails, we fall back to the Frame's existing avahi
  host name (`<hostname>.local`), which avahi likely already announces.

## Milestones
0. **On-device spike (as soon as SSH is available).** A tiny BSIPA plugin
   exercising the three unknowns inside the game's Mono under Proton:
   - `SslStream` in server mode with our certificate. Unity's TLS provider has a
     history of client-side quirks, and server mode is unverified. If it fails,
     switch to BouncyCastle TLS through the EmbedIO patch.
   - EmbedIO serving wss.
   - mDNS coexisting with avahi.
1. **Server core (in this container).**
   - `LiveViewer.Server` on EmbedIO: TLS with a generated certificate, the
     waiting room and device approvals, limits, and tests.
   - A console host that streams a `.bsor` through the live protocol in real
     time ("fake live"), with approvals auto-accepted or done from the console.
   - A test page that shows pose and latency stats.
2. **Viewer live mode (in this container).** Fork, `live-loader`, incremental
   scoring, the clock sync and prediction loop, and the stripped UI, developed
   end to end against the fake-live host. Playwright tests measure sample age
   at display.
3. **Plugin on the Frame (needs SSH).**
   - The recorder port, the lifecycle and map serving.
   - The BSML screens: status and URLs, waiting room, approved devices.
   - Building against the reference DLLs pulled from the Frame, and checking
     Proton networking and firewall reachability.
4. **Latency tuning on the real device.** Choose the capture point, measure the
   Wi-Fi, tune prediction, and check the CPU and GC cost in game. We need to
   stay well under the frame budget on the Frame's GPU-bound setup.
5. **Polish.** Song transitions, reconnects, multiple viewers, and
   certificate regeneration.

## Decisions
- Target **Beat Saber 1.44.1** only, on bs-arm64.
- **Custom maps only.**
- **Port 4280**, HTTPS only.

## Open questions
- **Firewall:** is SteamOS's firewall open for inbound LAN TCP 4280 and UDP 5353
  on the Frame? To be checked over SSH.

## Later: QR handoff
- A public static page on another computer shows a QR code, and the Frame's
  cameras scan it. The mod then tells that page where to go, and the page
  redirects to `https://<frame-ip>:4280/`, where the device goes through the
  normal waiting room.
- The certificate warning appears on the first visit, as usual.
- The return channel (how the mod reaches the waiting page) needs design
  later. One option is the page polling a rendezvous id encoded in the QR,
  which needs only a tiny public endpoint.
