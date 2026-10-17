# Beat Saber live 3D viewer — task and status

## Task

Watch a Beat Saber session live, in 3D, in a browser on the local network.
- **Source:** the native ARM64 Beat Saber build ([bs-arm64](https://github.com/DaVarga/bs-arm64), BS 1.44.1, under
  Proton on the Steam Frame).
- **Hosting:** everything is hosted by a BSIPA mod running inside the game. There is no cloud infrastructure.
- **Renderer:** BeatLeader's web replay viewer, used in a live mode.

Requirements, as agreed:

- **Real-time.** Added latency should be well under one 60 fps frame. Poses are streamed every game frame, with
  no batching.
- **Recording logic** is copied and adapted from the BeatLeader mod, with no dependency on it.
- **Backend:** lightweight C#, using libraries for HTTP/WebSocket (EmbedIO) and certificates (BouncyCastle). The
  frontend does most of the processing.
- **A clean security boundary.**
  - TLS with a self-signed certificate generated on first start.
  - No pairing tokens: new browsers wait in a waiting room until the player approves them from a menu screen.
    Devices can be remembered and revoked.
- **Address:** mDNS announces the server so people can type a readable name: `https://beatsaber.local:4280`. The
  port is fixed at 4280.
- **Scope:**
  - Custom maps only.
  - Compatibility with non-Frame or x64 Beat Saber is not required.
  - The Frame has no screen others can see, so the in-game menu shows no QR codes.
- **Later:** a public page shows a QR code; the Frame's cameras scan it, and the page redirects the viewer to the
  Frame.

See `PLAN.md` for the design. Some details there predate later decisions; this file is the current status.

## Layout

| Path | What |
|---|---|
| `mod/LiveViewer.Server/` | Web server the mod hosts (netstandard2.0, no game references). Contains the waiting room, protocol, live feed and an embedded test page. |
| `mod/LiveViewer.Host/` | Development host: runs the server outside the game and streams a `.bsor` replay in real time ("fake live"). |
| `mod/LiveViewer.Server.Tests/` | xunit unit and integration tests (TLS on loopback). |
| `mod/vendor/EmbedIO/` | Vendored EmbedIO with hardening patches (`VENDORED.md`). |
| `mod/PROTOCOL.md` | WebSocket protocol. |
| `mod/tools/` | Headless-Chromium smoke tests (test page, live viewer, song transitions). |
| `viewer/` | Live viewer: a fork of BeatLeader/BeatSaber-Web-Replays (imported as a git subtree), cut down to live play only (`viewer/README.md`). |

## Status

| Milestone | State |
|---|---|
| 1. Server core: TLS, waiting room, device approvals, protocol, limits, tests, fake-live host | Done |
| 2. Viewer live mode, driven by the fake-live host | Done |
| 2b. Self-contained demo build (`npm run build:demo`), published as a claude.ai artifact | Done |
| 2c. Viewer made live-only: replay-mode code removed, "Request to watch" button before the waiting room | Done |
| 2d. Waiting-room codes are three words from the PGP word list | Done |
| 2e. Level browser: installed custom levels, map and BeatLeader stats, audio preview (dev host and demo) | Done |
| 0. On-device spike (needs SSH to a Frame) | Open |
| 3. BSIPA plugin on the Frame | Open |
| 4. Latency tuning on the real device | Open |
| 5. Polish | Open |

## Outstanding tasks

### Needs the Frame (milestones 0, 3, 4)

- **Spike inside the game's Mono under Proton:**
  - `SslStream` server mode with our certificate. Fallback: BouncyCastle TLS through EmbedIO's
    `TlsStreamFactory` hook.
  - EmbedIO serving wss.
  - Wine networking and binding.
  - mDNS coexisting with SteamOS's avahi on UDP 5353.
  - Firewall for TCP 4280 and UDP 5353.
- **mDNS / DNS-SD announcement** (Makaretu.Dns.Multicast). Not implemented yet.
- **`LiveViewer.Plugin` (BSIPA):**
  - Port of BeatLeader's `ReplayRecorder`: poses every frame, note cut (immediate) and final (after the swing
    rating), walls, height, pause/resume, session start/end.
  - Map file allow-list from the level's info.dat.
  - BSML screens: status and URLs, waiting room (allow once / allow and remember / deny), approved devices with
    revoke.
  - Embedding `viewer/dist` (as a zip resource).
  - Build against the game's reference assemblies from the Frame.
- **Latency on the device:**
  - Choose the pose capture point (`Application.onBeforeRender` vs after `PlayerTransforms`).
  - Measure Wi-Fi latency.
  - Tune the viewer's prediction (default 16 ms, `?predict=`).
  - Check the game-thread CPU and GC cost.

### Level browser follow-ups

- **In the plugin:** point `LiveServerOptions.LevelFolders` at `Beat Saber_Data/CustomLevels` (and
  `CustomWIPLevels` if wanted; SongCore's extra folders from its config). Add a menu toggle for BeatLeader
  stats, which sets `LiveServerOptions.BeatLeader`. It's off unless enabled, since it tells BeatLeader which
  levels viewers look at.
- **Scan cost on the Frame.** The first scan reads every Info.dat and difficulty file to count notes and compute
  hashes (8 levels: about 1 s on the dev container). It runs off the game thread, but a large library on the Frame
  may take a while. Measure it there, and consider a persistent cache keyed by the folder stamp.
- **v4 hashes.** For v2/v3 Info.dat the hash matches BeatSaver's (checked on 8 real maps). For v4 it hashes
  Info.dat, the audio data file and each beatmap and lightshow file once, in order; this has not been checked
  against SongCore with a real v4 map.
- **Safari / iOS** may not play Ogg Vorbis in `<audio>`. The preview then says the browser can't play the file.
  The live viewer has the same limitation.
- **More from BeatLeader**, if wanted: play counts and top scores need more API calls per level.

### Software

- **`gameVersion` in the session.** Add it to the server's `SessionInfo` and the SessionStart JSON. The viewer's
  note-id matching depends on it for chains on game versions ≥ 1.29; the fake-live host passes nothing today.
- **Certificate regeneration** from the menu, and showing its fingerprint there.
- **Reconnect handling.** After a dropped connection the viewer re-downloads the whole map. Keep the files when the
  session id and hash are unchanged.
- **Audio sync.** It re-seeks when the drift exceeds 40 ms, which is audible. Consider small playback-rate
  adjustments instead. It is also untested with the `<audio>` element path used at speeds other than 1.
- **Late join:** check the score and combo shown when joining mid-song against the game's own numbers.
- **QR handoff mode** (later; see `PLAN.md`).

## Known issues

- **Flaky test.** `ServerIntegrationTests.RememberedDeviceReconnectsWithoutWaitingAndCanBeRevoked` sometimes times
  out (5 s receive) under heavy CPU load. It passes otherwise; not investigated yet.
- **Stuck "processing audio" flag.** Rarely, the viewer's `isSongBufferProcessing` stayed set after a song loaded,
  which stops playback. It was seen in a few headless test runs and couldn't be reproduced on demand. A watchdog in
  `LiveSession.checkStuckProcessing` clears it after 3 s; the cause is not known.
- **Latency numbers are from headless Chromium with software rendering.** Real browsers and the real network are
  unmeasured.
  - In the container, the server-side path measured a median 0.6 ms from capture to receipt in the browser.
  - The viewer extrapolates about 26 ms (median) past the newest pose at 60 fps: the 16 ms prediction, 5 ms
    simulated latency, and up to one pose interval.
- **Map file allow-list.** The fake-live host allows every file listed in info.dat, all difficulties included. The
  viewer only requests what it needs. (The level library is narrower: cover and song only, by kind.)
- **The level page also receives the live stream** (poses every frame), since it shares the viewer's connection.
  That's about 12 KB/s per viewer.
- **The waiting room approves by match code only.** The approval screen shows IP and browser to help, but anyone
  on the LAN can ask, and denial cooldowns are per IP.
- **The dev host loads `--www` files once at startup.** Restart it after rebuilding the viewer.
- **Saber colors chosen in the settings are not saved.** The replay viewer synced them to the BeatLeader profile;
  that is gone. Better: the session should carry the player's color scheme from the game.
