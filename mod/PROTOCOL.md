# Live protocol (v1)

There is one WebSocket at `wss://<host>:4280/ws`, with subprotocol `bslive.v1`.

Every message is a **binary** frame. Text frames are a protocol violation and
close the connection.

- **Byte 0 is the message type.** Server→client types are below `0x80`;
  client→server types are `0x80` and up.
- **Encoding:** little-endian. `str` is an `i32` byte length followed by that
  many bytes of UTF-8, as in BSOR.
- **Timestamps:**
  - `us` is an `i64` on the server's monotonic clock, in microseconds.
  - `songTime` is an `f32`, in seconds of song time.

Composite types:

- `vec3` = `f32 x, y, z`
- `quat` = `f32 x, y, z, w`
- `pose` = `vec3 position, quat rotation`

These are the coordinates the game reports. They use BSOR's conventions, so the
viewer's existing BSOR conversion applies.

## Connection flow

```
client                         server
  ── connect ──────────────────►
  ◄──────────────────── Welcome
  ── Hello{credential?} ───────►
       credential valid → Approved{} + current state
       otherwise        → Waiting{code} ... (player decides in game) ...
                          → Approved{credential?} + current state | Denied + close
```

- **Pinging:** `Ping` may be sent at any time after `Hello`.
- **Map and level requests:** `MapRequest` and the level library requests are
  only valid once approved.
- **Violations:** anything unexpected closes the connection. That includes an
  unknown type, trailing bytes, a second `Hello`, a map request before approval,
  or more than about 20 messages per second.

## Server → client

| Type | Name | Payload |
|---|---|---|
| `0x01` | Welcome | `u16 protocolVersion, us serverTime, str serverName` |
| `0x02` | Waiting | `str matchCode`: three words from the PGP word list separated by single spaces (even, odd, even list; e.g. `Aztec Istanbul Yucatan`, at most 31 bytes). The browser shows the code; the player matches it in the game menu. |
| `0x03` | Approved | `u8 hasCredential, [32 bytes credential]`. Store the credential (if present) and send it in later `Hello`s. |
| `0x04` | Denied | none. Also sent when the waiting room is full, the request expired, or the address is cooling down after a deny. |
| `0x05` | Revoked | none. The remembered device was revoked: forget the credential. |
| `0x06` | Pong | `f64 clientTime (echoed), us serverReceive, us serverSend` |
| `0x10` | SessionStart | `u32 sessionId, str json`. The JSON fields are below. |
| `0x11` | SessionEnd | `u32 sessionId, u8 reason (1 cleared, 2 failed, 3 quit, 4 restarted), f32 songTime` |
| `0x12` | Idle | none. Sent after approval when no song is being played. |
| `0x20` | Pose | `us capture, f32 songTime, pose head, pose left, pose right`. Sent once per rendered game frame. |
| `0x21` | NoteCut | `us capture` + BSOR note event. Sent immediately when a note is cut, missed or a bomb is hit; for cuts, `afterCutRating` is still incomplete. |
| `0x22` | NoteFinal | `us capture` + BSOR note event, final. Sent once the swing rating completes (cuts) or immediately (misses, bombs). |
| `0x23` | Wall | `us capture` + BSOR wall event (`i32 wallId, f32 energy, f32 time, f32 spawnTime`) |
| `0x24` | Height | `us capture, f32 height, f32 songTime` |
| `0x25` | Pause | `us capture, f32 songTime` |
| `0x26` | Resume | `us capture, f32 songTime` |
| `0x30` | MapChunk | `u16 requestId, u32 totalLength, u32 offset, bytes...` (the rest of the message). Chunks arrive in order; a zero-length file is one chunk with `totalLength` 0. Answers `MapRequest` and the level library requests. |
| `0x31` | MapError | `u16 requestId, u8 code (1 not available, 2 no or other session, 3 read failed or BeatLeader unreachable, 4 too many requests)` |
| `0x40` | Suggestions | `str json`: the whole suggestion list (see "Suggestions"). Sent right after `Approved`, to everyone whenever it changes, and to a sender whose change wasn't applied. |

A **BSOR note event** is laid out as:

```
i32 noteId, f32 eventTime, f32 spawnTime, i32 eventType (0 good, 1 bad, 2 miss, 3 bomb)
then, only for good and bad cuts, the cut info:
u8 speedOK, u8 directionOK, u8 saberTypeOK, u8 wasCutTooSoon,
f32 saberSpeed, vec3 saberDirection, i32 saberType,
f32 timeDeviation, f32 cutDirDeviation, vec3 cutPoint, vec3 cutNormal,
f32 cutDistanceToCenter, f32 cutAngle, f32 beforeCutRating, f32 afterCutRating
```

### SessionStart JSON

```json
{
  "hash": "…", "songName": "…", "songSubName": "…", "songAuthor": "…", "mapper": "…",
  "difficulty": "ExpertPlus", "mode": "Standard", "environment": "…", "modifiers": "FS,NF",
  "playerName": "…", "leftHanded": false, "playerHeight": 1.75, "jumpDistance": 18.6,
  "noteJumpSpeed": 18, "startTime": 0, "songSpeed": 1, "gameVersion": "1.44.1",
  "files": { "info": "Info.dat", "difficulty": "ExpertPlus.dat", "audio": "song.egg", "cover": "cover.jpg" }
}
```

`files` maps roles to the exact names to use in `MapRequest`. Other names are
refused.

### Late join

On approval during a song, the client receives `Approved`, then `SessionStart`,
then every non-pose event of the session so far, in order. After that it gets
live data. Poses are never backlogged.

### Prioritization

- Order of priority, per client: waiting-room and session messages and events
  first, then poses (only the newest 4 are kept when a client falls behind),
  then map chunks (16 KB each).
- A slow map download never delays live data by more than one chunk.

## Client → server

| Type | Name | Payload |
|---|---|---|
| `0x81` | Hello | `u16 protocolVersion (1), u8 hasCredential, [32 bytes credential]` |
| `0x82` | Ping | `f64 clientTime` (e.g. `performance.now()`) |
| `0x83` | MapRequest | `u16 requestId, u32 sessionId, str fileName (≤ 256 bytes)` |
| `0x84` | LevelListRequest | `u16 requestId`. Answered with the level list JSON as a file. |
| `0x85` | LevelFileRequest | `u16 requestId, u8 kind (1 cover, 2 song), str levelId (≤ 64 bytes)` |
| `0x86` | LevelStatsRequest | `u16 requestId, str levelId (≤ 64 bytes)`. Answered with the stats JSON as a file. |
| `0x87` | SuggestionAdd | `str levelId`: 40 lowercase hex digits, else a protocol violation. |
| `0x88` | SuggestionRemove | `str levelId`, as above. |

The maximum inbound message size is 1 KB.

## Level library

The page can list the custom levels installed on the Frame, show their stats and
play their songs as previews. Level requests are answered asynchronously, as
file transfers (`MapChunk` / `MapError`), and are not tied to a session. A
connection may have at most 8 of them in progress.

- **Ids:** a level's id is its hash, as SongCore computes it (lowercase hex
  SHA-1 of Info.dat and the difficulty files). Duplicate copies of a level are
  listed once.
- **Boundary:** for any listed level, only its cover image and song file can be
  read, by kind, as named by its Info.dat and resolved inside its folder.
  Difficulty files are available only for the level being played, through
  `MapRequest`.
- **BeatLeader stats are fetched by the mod**, so the page never talks to
  anything but the mod. The mod asks BeatLeader only about hashes of installed
  levels, at most two requests at a time, and caches the answers for 12 hours
  (failures for 2 minutes). Stats are off unless the mod enables them.
- **Rescans:** the list is re-scanned when it's requested and the last scan is
  more than 30 seconds old; unchanged level folders are not re-read.
- **Errors:** an unknown id gives `MapError` 1. Level requests when the library
  or stats are disabled also give 1. Stats when BeatLeader can't be reached give 3.

Level list JSON (strings are escaped so the JSON is inert in HTML; still, the
page must treat every string as text):

```json
{"levels": [{
  "id": "c9c15d3f…", "songName": "…", "songSubName": "…", "songAuthor": "…", "mapper": "…",
  "environment": "…", "bpm": 154, "duration": 105.43, "previewStart": 60, "previewDuration": 10,
  "hasCover": true, "hasAudio": true, "added": 1700000000,
  "difficulties": [{"mode": "Standard", "difficulty": "ExpertPlus", "label": "", "njs": 18, "offset": 0,
                    "notes": 446, "bombs": 0, "walls": 11, "arcs": 0, "chains": 0}]
}]}
```

- `duration` is in seconds; 0 if unknown.
- `added` is the Unix time Info.dat was last written.
- Counts are `null` when a difficulty file couldn't be read.

Stats JSON, a subset of BeatLeader's map data, re-encoded by the mod:

```json
{"found": true, "key": "4adb", "difficulties": [{"mode": "Standard", "difficulty": "ExpertPlus", "status": 3,
  "stars": 7.5131, "pass": 4.3924, "acc": 8.821, "tech": 7.9199, "predictedAcc": 0.9799, "maxScore": 403075}]}
```

- `found` is false if BeatLeader doesn't know the map.
- `status` is BeatLeader's: 0 unranked, 1 nominated, 2 qualified, 3 ranked,
  4 unrankable, 5 outdated, 6 event, 7 OST.
- Ratings are `null` when BeatLeader has none.

## Suggestions

Approved viewers share one list of levels they suggest to the player. The mod shows it in the game as a level
pack ("Suggested by viewers") and keeps it across restarts.

- Any approved viewer can add or remove any entry. Only installed levels can be added; at most 100 entries.
- Changes are rate-limited per connection (10 in a row, then one every 2 s). A change that isn't applied (not
  installed, already there, list full, rate limit) is answered with the unchanged list.
- `by` is the suggesting browser's description ("Firefox on Linux"), for display only.

```json
{"levels": [{"id": "c9c15d3f…", "by": "Firefox on Linux", "added": 1700000000}], "max": 100}
```

Entries stay listed if their level is deleted; the page should show them as unavailable.

## Clock sync

The client sends `Ping{t0}` and gets `Pong{t0, sr, ss}` back at `t1`. Then:

- `rtt = (t1 - t0) - (ss - sr)`
- `offset = ((sr + ss) / 2) - (t0 + t1) / 2`, in µs after unit conversion

Keep the sample with the lowest `rtt` from a sliding window. A server
timestamp `us` maps to client time as `us - offset`.
