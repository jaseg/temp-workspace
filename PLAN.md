# Beat Saber live 3D viewer — plan

Goal: watch a Beat Saber session live, in 3D, in a web browser. The game is the
native ARM64 build on a Steam Frame. Rendering reuses BeatLeader's web replay
viewer (replay.beatleader.xyz).

## What we're building on

| Piece | Source | Notes |
|---|---|---|
| Game | [bs-arm64](https://github.com/DaVarga/bs-arm64) | Windows ARM64 Unity player (6000.0.40f1, **Mono**), run under Proton on ARM64 SteamOS. BSIPA 4.3.7 + Harmony work on 1.41.1+, so mods are ordinary C# `net48` BSIPA plugins. |
| Recorder | [BeatLeader/beatleader-mod](https://github.com/BeatLeader/beatleader-mod) (MIT) | `ReplayRecorder` builds a BSOR `Replay` in memory while you play. Pose frames are added in `LateTick`, note events in `_replay.notes.Add` once the swing rating finishes (about 0.3 s after the cut), and walls, heights and pauses are added in the same way. |
| Renderer | [BeatLeader/BeatSaber-Web-Replays](https://github.com/BeatLeader/BeatSaber-Web-Replays) (MIT, A-Frame) | It assumes a **complete** replay. `replay-loader` fetches the whole BSOR and `processScores()` matches every note event to map notes once. `replay-player` interpolates `replay.frames` by song time. `zip-loader` fetches the map zip by hash from `cdn.songs.beatleader.xyz`, and the audio comes from that zip. |

No existing tool streams BeatLeader-format data live. Status-socket mods such as
HttpStatus and AnotherStatusSocket send only score and game events, with no poses.

## Architecture

```
Steam Frame (Proton, ARM64)            Relay (one small server)              Browsers
┌──────────────────────────┐   WS    ┌──────────────────────────┐   WS    ┌───────────────────┐
│ BSIPA mod "LiveLeader"   │ ──────► │ session fan-out, keeps   │ ──────► │ forked BL viewer  │
│ taps BeatLeader recorder │  push   │ current song header and  │  sub    │ with a live-loader│
│ batches deltas every     │         │ buffer so late joiners   │         │ component         │
│ ~100 ms                  │         │ catch up                 │         │                   │
└──────────────────────────┘         └──────────────────────────┘         └───────────────────┘
```

### 1. Mod (C#, BSIPA, `net48`)
- **Data source:** depend on the BeatLeader mod and use reflection or Harmony to read its in-progress `_replay` each tick. Send only what's new: frames, notes, walls, heights and pauses since the last send. This avoids duplicating its recording logic, and the data matches BSOR exactly. Fallback if that proves fragile: copy the relevant parts of `ReplayRecorder` (MIT) into our own recorder.
- **Wire format:** BSOR's own binary encoding, cut into messages: `start` (BSOR info section plus map hash, difficulty and mode), `frames[]`, `notes[]`, `walls[]`, `heights[]`, `pauses[]`, and `end` (finished, failed or quit). The viewer's existing BSOR decoder functions can then decode each message unchanged.
- **Transport:** an outbound WebSocket client (`System.Net.WebSockets.ClientWebSocket`, or a tiny hand-rolled one if Mono or Wine misbehaves). The client connects to the relay with a stream key and reconnects on drop. All sending happens on a background thread, so the game loop never blocks.
- A small BSML settings page for relay URL, stream key and on/off.

### 2. Relay (TypeScript)
- Two WebSocket endpoints: `/ingest/:key` (the mod) and `/watch/:id` (viewers).
- Holds the current song's `start` message and every delta since it, so a viewer who joins mid-song gets the backlog and then live data.
- Target: a Cloudflare Worker with a Durable Object (the viewer is already deployed as a Worker). A plain Node or Deno server works as a LAN or self-host alternative.

### 3. Viewer (fork of BeatSaber-Web-Replays, kept as a git subtree or submodule)
- New `?live=<id>` mode with a `live-loader` component that replaces `replay-loader`'s fetch:
  - `start` → load the map by hash (existing `zip-loader` path), create an empty `replay` object, and emit `replayfetched`.
  - Deltas → append to `replay.frames`, `notes` and the other arrays. Make `processScores()` incremental, so it matches only new note events and keeps running score, combo and accuracy state.
  - `end` → stop, show results, and wait for the next `start`.
- **Clock:** play the song audio locally a fixed **latency buffer** (around 1.5 s, adjustable) behind the newest received frame. Resync on drift. Pauses in the game pause playback.
- Remove or disable the seek and speed UI in live mode. All the existing camera modes (first person, third person, orbit) stay.

## Milestones
1. **Spike, desktop x64:** a mod that dumps live deltas to a local file or socket, and a Node relay. Proves the recorder tap works. The Frame isn't needed yet.
2. **Viewer live mode** fed by a "fake live" script that replays a `.bsor` from BeatLeader's CDN through the relay in real time. All viewer work can happen here, with no game.
3. **End-to-end on the Frame:** mod on bs-arm64 → relay → browser. Check networking under Proton, CPU cost and latency.
4. **Polish:** late join, reconnects, song transitions, settings UI, and deploy (Worker plus static site).

## Risks and open questions
- **Building the mod** needs Beat Saber's managed DLLs, which aren't in this container. Builds must run on your machine, or in CI with stripped reference assemblies. I can write the code here and keep it compiling against stubs.
- **Map availability:** the viewer fetches maps by hash from BeatLeader or BeatSaver. OST/DLC and unpublished WIP maps won't load. Possible fix: the mod uploads the map zip to the relay. Not in scope for v1?
- **BeatLeader mod on ARM64:** probably fine because it's managed code, but not yet verified on bs-arm64. If it fails, use the standalone-recorder fallback.
- **Proton networking:** an outbound WebSocket from Mono under Wine should work. Verify in milestone 3.
- **Bandwidth:** about 90 fps × 3 poses × 28 B ≈ 7.5 KB/s, which is negligible. We could downsample to 60 fps if needed.
