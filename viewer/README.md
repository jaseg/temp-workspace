# Beat Saber live viewer

This is the browser side of the live viewer. The Beat Saber mod serves it on the local network, and it renders
the song being played, in 3D, from the mod's WebSocket stream. The protocol is in
[`../mod/PROTOCOL.md`](../mod/PROTOCOL.md).

It started as a fork of BeatLeader's [web replay viewer](https://github.com/BeatLeader/BeatSaber-Web-Replays)
(MIT, A-Frame), imported as a git subtree. It has since been cut down to live play only:
- No replay or ScoreSaber loading.
- No BeatLeader API calls.
- No timeline, seeking, speed or pause.
- No random replays and no local-file lookup.

Upstream changes can no longer be merged wholesale; port the ones we want by hand.

```sh
npm ci
npm run build     # production webpack build, then scripts/package.js -> dist/
```

`dist/` (about 7 MB) is what the mod serves. It contains:
- `index.html`
- the bundle
- A-Frame
- the scene assets
- Font Awesome

There are no CDN references. To try it without the game, use the fake-live host in `../mod/README.md` with
`--www ../viewer/dist`.

## Demo build

```sh
npm run build:demo -- <map folder> <replay.bsor>    # -> dist-demo/
```

`dist-demo/` is a static page that needs no game or mod. An in-page source (`src/live/demo.js`) plays the given
BeatLeader replay through the same live protocol path, waiting room included.

## How it works

The live code is in `src/live/`. The rest is the replay viewer's scene, reused.

| File | Role |
|---|---|
| `session.js` | `LiveSession`: the stream becomes the `replay`, `allStructs`, `bombs`, `walls` data on the `replay-loader` component, which the scene reads. |
| `connection.js` | WebSocket, waiting room, remembered-device credential (localStorage), clock-sync pings, map file downloads. |
| `clock.js` | `ServerClock` maps the mod's microsecond clock to `performance.now()` (lowest-RTT pong of the last 16). `SongClock` turns pose timestamps into a smoothed song time. |
| `audio.js` | Re-seeks the song audio whenever what is heard drifts more than 40 ms from the live song time. |
| `overlay.js` | "Request to watch" (the click also unlocks audio), waiting for approval with the match code, song ended. `l` toggles the latency readout. |
| `demo.js` | In-page replay source for the demo build. |
| `bsor.js` | BSOR decoder (demo only). |

**Song start.**
1. `SessionStart` resets the scene.
2. The page downloads Info.dat, the played difficulty, the cover and the audio over the WebSocket.
3. `map-loader` turns them into the challenge.

**Notes.**
- **Cut:** a `NoteCut` is matched to its map note immediately, so the beat is cut at once with a provisional
  score.
- **Final:** `NoteFinal` completes the score. The note goes into the time-ordered list, and the running totals
  are recomputed (`computeTotals` in `replay-loader.js`).
- **Spawned early:** beats spawned before their outcome is known look it up every frame.

**Time.**
- **Song time** comes from the clock-synced pose timestamps, not from the audio (`song.getCurrentTime()`).
- **Prediction:** the frame rendered at `t` shows song time `t + predict`, 16 ms by default (`?predict=<ms>`,
  0 disables it). This covers the display pipeline.
- **Extrapolation:** poses are extrapolated from the last two samples, by at most 50 ms past the newest pose.

**Content Security Policy.**
- The mod serves the page with `script-src 'self'`: no inline scripts, no event-handler attributes, no eval.
  `scripts/package.js` fails the build if `index.html` has inline script.
- Bind expressions in the templates are compiled by a small parser in `state-component.js`, not
  `new Function`.
- A-Frame's one eval use (a getter factory) is replaced when packaging.
