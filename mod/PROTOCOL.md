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
- **Map requests:** `MapRequest` is only valid once approved.
- **Violations:** anything unexpected closes the connection. That includes an
  unknown type, trailing bytes, a second `Hello`, a map request before approval,
  or more than about 20 messages per second.

## Server → client

| Type | Name | Payload |
|---|---|---|
| `0x01` | Welcome | `u16 protocolVersion, us serverTime, str serverName` |
| `0x02` | Waiting | `str matchCode`. The browser shows the code; the player matches it in the game menu. |
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
| `0x30` | MapChunk | `u16 requestId, u32 totalLength, u32 offset, bytes...` (the rest of the message). Chunks arrive in order; a zero-length file is one chunk with `totalLength` 0. |
| `0x31` | MapError | `u16 requestId, u8 code (1 not available, 2 no or other session, 3 read failed, 4 too many requests)` |

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
  "noteJumpSpeed": 18, "startTime": 0, "songSpeed": 1,
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

The maximum inbound message size is 1 KB.

## Clock sync

The client sends `Ping{t0}` and gets `Pong{t0, sr, ss}` back at `t1`. Then:

- `rtt = (t1 - t0) - (ss - sr)`
- `offset = ((sr + ss) / 2) - (t0 + t1) / 2`, in µs after unit conversion

Keep the sample with the lowest `rtt` from a sliding window. A server
timestamp `us` maps to client time as `us - offset`.
