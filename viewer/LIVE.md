# Live mode

This copy of BeatLeader's web replay viewer has a second build flavor: the live
viewer that the Beat Saber mod serves on the local network. It renders a song
while it is being played, from the mod's WebSocket stream. The protocol is
described in [`../mod/PROTOCOL.md`](../mod/PROTOCOL.md).

```sh
npm ci
npm run build:live      # LIVE=1 production webpack build, then scripts/package-live.js
```

The output is `dist-live/`, about 8 MB. It contains:
- `index.html`
- the bundle
- A-Frame
- the assets the scene needs
- Font Awesome

It includes no CDN references. To try it without the game, see the fake-live
host in `../mod/README.md`.

## How it works

Everything is in `src/live/`; the rest of the viewer is reused.

| File | Role |
|---|---|
| `session.js` | `LiveSession`: the stream becomes the same `replay`, `allStructs`, `bombs`, `walls` data the `replay-loader` component normally builds from a `.bsor`. |
| `connection.js` | WebSocket, waiting room, remembered-device credential (localStorage), clock-sync pings, map file downloads. |
| `clock.js` | `ServerClock` maps the mod's microsecond clock to `performance.now()` (lowest-RTT pong of the last 16). `SongClock` turns pose timestamps into a smoothed song time. |
| `audio.js` | Re-seeks the song audio whenever what is heard drifts more than 40 ms from the live song time. |
| `overlay.js` | Connecting / waiting-for-approval (with the match code) / song-ended card. Press `l` for the latency readout. |

### Session start

1. `SessionStart` resets the scene, like loading a new replay.
2. The page downloads Info.dat, the played difficulty, the cover and the audio
   over the WebSocket.
3. It hands them to the normal `zip-loader` processing as virtual files.

### Notes

- **Cut:** a `NoteCut` matches its map note immediately, so the beat is cut at
  once with a provisional score.
- **Final:** `NoteFinal` completes the score. The note goes into the
  time-ordered list and the running totals are recomputed with the same
  `computeTotals` the replay path uses.
- **Spawned before the outcome is known:** beats look up their outcome every
  frame until it exists.

### Time

- **Song time** comes from the clock-synced pose timestamps, not from the
  audio.
- **Prediction:** the frame rendered at `t` shows song time `t + predict`,
  16 ms by default (`?predict=<ms>`, 0 disables it). This covers the display
  pipeline.
- **Extrapolation:** poses are extrapolated from the last two samples, by at
  most 50 ms past the newest pose. When the stream stalls, the picture freezes
  instead of drifting.

### Disabled in live mode

Seeking, speed changes, pausing, random replays and BeatLeader API calls. The
page talks to the mod only.

### Content Security Policy

The mod serves the page with `script-src 'self' 'unsafe-eval'`. A-Frame needs
`new Function`; inline scripts stay forbidden. `scripts/package-live.js` does
two things:
- It moves the templates' inline `<script>` blocks into `live-inline.js`.
- It turns their `onclick`/`oninput`/... attributes into `data-live-on*`
  attributes. `live-inline.js` binds those once at load.

Only handlers present in the shipped `index.html` are ever bound.

## Changes to upstream files

All of these are gated on `LIVE_MODE`, so the regular build behaves as before:

- **`replay-loader.js`:**
  - Starts `LiveSession` in live mode.
  - Score bookkeeping is factored into the exported `computeTotals` and
    `noteStructFromEvent`; the replay path calls the same code.
- **`zip-loader.js`:** no CDN fetch, and only the provided difficulty is
  loaded.
- **`song.js`:** `getCurrentTime` returns the live clock when one is set.
- **`replay-player.js`:** open-ended frame list with bounded extrapolation.
- **`beat.js`:** outcome looked up lazily; the score text updates when the
  final score arrives.
- **`wall.js`:** wall hits looked up lazily.
- **`pauser.js`, `random-replay.js`, `colors.js`:** disabled or offline.
- **State (`state/index.js`):**
  - `hasReceivedUserGesture` starts out true.
  - New `livesessionstart` handler.
  - `scoreChanged` accepts `force`.
- **`index.html`:** a live variant without inline scripts or third-party
  resources.
- **Build:** `webpack.config.js` defines `LIVE_MODE`. New devDependency
  `@fortawesome/fontawesome-free`, so the icons are served locally.

Upstream updates come in with:

```sh
git subtree pull --prefix viewer https://github.com/BeatLeader/BeatSaber-Web-Replays.git master --squash
```
