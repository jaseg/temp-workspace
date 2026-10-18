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
| `mod/LiveViewer.Server/` | Web server the mod hosts (netstandard2.0, no game references). Contains the waiting room, protocol, live feed, level library, suggestions and an embedded test page. |
| `mod/LiveViewer.Plugin/` | The BSIPA plugin (net472): runs the server in the game, streams gameplay, menu screen, in-game suggestion pack. Builds against `mod/refs/` (game assemblies, not in git; see `mod/README.md`). |
| `mod/LiveViewer.Host/` | Development host: runs the server outside the game and streams a `.bsor` replay in real time ("fake live"). |
| `mod/LiveViewer.Server.Tests/` | xunit unit and integration tests (TLS on loopback). |
| `mod/vendor/EmbedIO/` | Vendored EmbedIO with hardening patches (`VENDORED.md`). |
| `mod/PROTOCOL.md` | WebSocket protocol. |
| `mod/tools/` | Headless-Chromium smoke tests (test page, live viewer, song transitions, level browser, suggestions). |
| `viewer/` | Live viewer: a fork of BeatLeader/BeatSaber-Web-Replays (imported as a git subtree), cut down to live play only (`viewer/README.md`). |

## The Frame

- **Target:** the BSManager instance `~/.local/share/BSManager/BSInstances/1.44.1` (native ARM64 via bs-arm64
  v0.3.2, Proton 11.0 ARM64, BSIPA, SiraUtil, BSML, SongCore). The Steam folder itself holds an unmodded x64 1.45.3.
  Changes on the Frame outside the instance folder need the owner's explicit approval.
- **Deploy:** copy `package/Plugins` and `package/Libs` into the instance, then start it with
  `bs-arm64.sh launch <instance>` (from `~/.local/share/BSManager/cache/bs-arm64/bs-arm64-v0.3.2-proton-11.0-2c`).
  Logs: `<instance>/Logs/`. Started over SSH with nobody in the headset, the game stops at the health-warning
  screen, so the main menu (menu screen, suggestion pack, DevAutoPlayLevel) needs someone to put the headset on.
- **Network:** the firewall allows TCP/UDP 1024–65535 on wlan0; avahi already announces `frame.local`, so
  `https://frame.local:4280/` works without our own mDNS.
- **Levels:** this instance has its own `CustomLevels` (19 levels). BSManager's shared maps
  (`SharedContent/SharedMaps`, 73 levels) are linked only into the Steam install; turning on map sharing for the
  1.44.1 instance in BSManager would make them playable and listed.

## Status

| Milestone | State |
|---|---|
| 1. Server core: TLS, waiting room, device approvals, protocol, limits, tests, fake-live host | Done |
| 2. Viewer live mode, driven by the fake-live host | Done |
| 2b. Self-contained demo build (`npm run build:demo`), published as a claude.ai artifact | Done |
| 2c. Viewer made live-only: replay-mode code removed, "Request to watch" button before the waiting room | Done |
| 2d. Viewers enter a name on the start screen (two random words suggested); the player approves by name | Done |
| 2e. Level browser: installed custom levels, map and BeatLeader stats, audio preview | Done, checked on the Frame |
| 2f. Top bar (Live / Levels / Playlist), shared, reorderable playlist of suggestions, "Suggested by viewers" pack in the game | Web side checked on the Frame; in-game pack untested |
| 0. On-device spike: server in the game under Proton (TLS, wss, binding) | Done |
| 3. BSIPA plugin on the Frame | Server and level browser work in the game; recorder and menu screen built, untested in game |
| 4. Latency tuning on the real device | Open |
| 5. Polish | Open |

## Outstanding tasks

### On the Frame (needs someone in the headset)

- **Recorder:** play a custom level and watch it live (or set `DevAutoPlayLevel` and put the headset on). Check
  poses, cuts, misses, walls, pause/resume, end reasons, the player's name and late join.
- **Menu screen:** the Live Viewer button, waiting room approval (allow once / always / deny), remembered devices,
  the BeatLeader toggle. Then turn `DevAutoApprove` off in `UserData/LiveViewer.json`.
- **Suggestion pack:** check that "Suggested by viewers" appears in Custom Levels, updates when viewers change
  the list, and doesn't disturb level selection (it calls SongCore's `RefreshLevelPacks`).
- **SongCore folders:** check the level browser picks up the folders SongCore loads (log line "Level folders: …").
- **Latency:**
  - Pose capture point: now Zenject `LateTick`, like BeatLeader. Compare with `Application.onBeforeRender`.
  - Measure Wi-Fi latency and the game-thread cost (CPU, GC) at 120 Hz.
  - Tune the viewer's prediction (default 16 ms, `?predict=`).

### Decisions and setup for the owner

- **Shared maps:** turn on map sharing for the 1.44.1 instance in BSManager (or approve doing it), so the 73
  shared levels are playable and listed. It changes files outside the instance folder.
- **Upstream BeatLeader mod:** replaced the 1.40.2 build with `BeatLeader-0.10.0-bs1.42+.zip` and an ARM64
  `yoga.dll` (`frame/yoga-arm64/`). It now starts. Check in the headset that its UI shows and a score uploads.
- **CI:** tier 1 (every push: C# tests, viewer build, dev host + browser smoke tests with checked-in fixtures);
  tier 2 (build against each game version's assemblies, check reflected field names); tier 3 (self-hosted runner
  playing a replay in each game version without VR and comparing the stream); tier 4 (the same nightly on the
  Frame). Not started.

### Software

- **Not needed after all:** our own mDNS responder (avahi announces `frame.local`). A DNS-SD service record would
  only help apps that browse for services, not browsers.
- **Certificate regeneration** from the menu.
- **Playlist:** maybe remove a level automatically once the player has played it; the in-game pack could
  also be a `.bplist` playlist if PlaylistManager is installed. Older entries keep the name their viewer had then.
- **Map colors** (estimate below, option 1 recommended): not started.
- **Reconnect handling.** After a dropped connection the viewer re-downloads the whole map. Keep the files when the
  session id and hash are unchanged.
- **Scan cost:** 19 levels take 1.9 s on the Frame on first scan. A persistent cache keyed by the folder stamp
  would help large libraries.
- **QR handoff mode** (later; see `PLAN.md`).

### Map colors and environments: estimate

What the viewer does today:

- **Colors:** fixed defaults from BeatLeader's viewer (red/blue notes and sabers, pink/blue lights), changeable in
  the viewer's settings panel. Map color schemes (v2 `_customData` colors, `_colorSchemes`, v4 `colorSchemes`) are
  parsed for v4 Info.dat but never applied, and the player's own color override in the game isn't sent.
- **Environment:** one generic stage for every map (floor, two laser columns, rings, background, tunnel). The map's
  environment name is ignored.
- **Lighting:** v2 basic events (types 0–4, 8, 9, 12, 13) flash, fade and spin the generic stage; v3 basic events
  are converted to those. v3 group lighting (`lightColorEventBoxGroups` etc.) is ignored, and v4 lightshow files are
  not loaded at all, so most recent maps show a static stage.

Options, cheapest first:

1. **Correct colors, about 1–2 days.** The mod sends the game's resolved color scheme
   (`GameplayCoreSceneSetupData.colorScheme`: sabers, lights 0/1 and boost, walls) in SessionStart. It is
   what the player actually sees: their override, else the map's scheme, else the environment's. The viewer
   applies it to notes, sabers, trails, walls and lights; its color code already updates at runtime. The level
   browser could show each map's own scheme as swatches (half a day, optional).
2. **Lighting for recent maps on the generic stage, about 1–2 weeks.** Load v4 lightshow files (already in the
   session's file list) and v3 event boxes, and map group lighting (filters, distributions, easing) onto the
   stage's few light groups. Right colors and rhythm, not the real layout. Chroma per-light colors: 2–3 more days.
3. **Real environments: weeks, and a licensing problem.** The game's environment models are Beat Games' assets in
   Unity bundles; they can't be shipped with the viewer, and converting them from the game files inside the mod
   is heavy and fragile. The realistic route is hand-built look-alikes with the right light groups and IDs, about
   3–5 days each once option 2 exists, starting with the few environments most custom maps use. Vivify and other
   custom environments are out of reach.

Recommendation: option 1 now, option 2 if lightshows matter, option 3 only for the two or three most used
environments.

## Known issues

- **Flaky test, fixed.** `RememberedDeviceReconnectsWithoutWaitingAndCanBeRevoked` timed out under CPU load
  (3 failures in 30 runs). The cause was in EmbedIO: a client's first message could be dropped before the module
  subscribed to it, and the dispatcher could leave a message queued until the next frame (see `VENDORED.md`).
  After the fix: 0 failures in 45 runs under the same load. Real browsers were affected too: an unlucky page stayed
  at "Connecting".
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
