using System;

namespace LiveViewer.Server.Protocol
{
    /// <summary>Encoders for server-to-client messages. Layouts are documented in PROTOCOL.md.</summary>
    public static class Messages
    {
        public const int CredentialBytes = 32;
        public const int MaxFileNameBytes = 256;

        public static byte[] Welcome(long serverTimeUs, string serverName) =>
            new MessageWriter().U8(MessageType.Welcome).U16(MessageType.ProtocolVersion).I64(serverTimeUs)
                .String(serverName).ToArray();

        /// <summary>In the waiting room, under this name (the one the viewer asked for, made unique).</summary>
        public static byte[] Waiting(string name) =>
            new MessageWriter().U8(MessageType.Waiting).String(name).ToArray();

        /// <summary>The viewer's name as the server uses it (after approval and after Rename).</summary>
        public static byte[] Name(string name) =>
            new MessageWriter().U8(MessageType.Name).String(name).ToArray();

        public static byte[] Approved(byte[]? credential)
        {
            var w = new MessageWriter().U8(MessageType.Approved).Bool(credential != null);
            if (credential != null)
            {
                w.Bytes(credential);
            }

            return w.ToArray();
        }

        public static byte[] Denied() => new[] { MessageType.Denied };

        public static byte[] Revoked() => new[] { MessageType.Revoked };

        public static byte[] Pong(double clientTime, long serverReceiveUs, long serverSendUs) =>
            new MessageWriter(32).U8(MessageType.Pong).F64(clientTime).I64(serverReceiveUs).I64(serverSendUs).ToArray();

        public static byte[] SessionStart(uint sessionId, SessionInfo info)
        {
            var json = new JsonObjectWriter()
                .Field("hash", info.Hash)
                .Field("songName", info.SongName)
                .Field("songSubName", info.SongSubName)
                .Field("songAuthor", info.SongAuthor)
                .Field("mapper", info.Mapper)
                .Field("difficulty", info.Difficulty)
                .Field("mode", info.Mode)
                .Field("environment", info.Environment)
                .Field("modifiers", info.Modifiers)
                .Field("playerName", info.PlayerName)
                .Field("leftHanded", info.LeftHanded)
                .Field("playerHeight", info.PlayerHeight)
                .Field("jumpDistance", info.JumpDistance)
                .Field("noteJumpSpeed", info.NoteJumpSpeed)
                .Field("beatsPerMinute", info.BeatsPerMinute)
                .Field("startTime", info.StartTime)
                .Field("songSpeed", info.SongSpeed)
                .Field("gameVersion", info.GameVersion)
                .Field("audioUrl", info.AudioUrl)
                .ToString();
            return new MessageWriter(512).U8(MessageType.SessionStart).U32(sessionId).String(json).ToArray();
        }

        public static byte[] SessionEnd(uint sessionId, SessionEndReason reason, float songTime) =>
            new MessageWriter(16).U8(MessageType.SessionEnd).U32(sessionId).U8((byte) reason).F32(songTime).ToArray();

        public static byte[] Idle() => new[] { MessageType.Idle };

        public static byte[] SongSelected(string audioUrl, string hash, string songName, string songSubName,
            string songAuthor, float beatsPerMinute)
        {
            var json = new JsonObjectWriter()
                .Field("audioUrl", audioUrl)
                .Field("hash", hash)
                .Field("songName", songName)
                .Field("songSubName", songSubName)
                .Field("songAuthor", songAuthor)
                .Field("beatsPerMinute", beatsPerMinute)
                .ToString();
            return new MessageWriter(256).U8(MessageType.SongSelected).String(json).ToArray();
        }

        public static void Pose(MessageWriter w, long captureUs, float songTime, in Pose head, in Pose left, in Pose right) =>
            w.Reset().U8(MessageType.Pose).I64(captureUs).F32(songTime).Pose(head).Pose(left).Pose(right);

        public static void Note(MessageWriter w, bool final, long captureUs, in NoteEvent e)
        {
            w.Reset().U8(final ? MessageType.NoteFinal : MessageType.NoteCut).I64(captureUs)
                .I32(e.NoteId).F32(e.EventTime).F32(e.SpawnTime).I32((int) e.EventType);
            if (!e.HasCutInfo)
            {
                return;
            }

            var c = e.CutInfo;
            w.Bool(c.SpeedOk).Bool(c.DirectionOk).Bool(c.SaberTypeOk).Bool(c.WasCutTooSoon)
                .F32(c.SaberSpeed).Vec3(c.SaberDirection).I32(c.SaberType)
                .F32(c.TimeDeviation).F32(c.CutDirectionDeviation)
                .Vec3(c.CutPoint).Vec3(c.CutNormal)
                .F32(c.CutDistanceToCenter).F32(c.CutAngle)
                .F32(c.BeforeCutRating).F32(c.AfterCutRating);
        }

        public static void Wall(MessageWriter w, long captureUs, in WallEvent e) =>
            w.Reset().U8(MessageType.Wall).I64(captureUs).I32(e.WallId).F32(e.Energy).F32(e.Time).F32(e.SpawnTime);

        public static void NoteSpawn(MessageWriter w, long captureUs, in NoteSpawn e) =>
            w.Reset().U8(MessageType.NoteSpawn).I64(captureUs).I32(e.NoteId).F32(e.Time)
                .I32(e.LineIndex).I32(e.LineLayer).I32(e.BeforeJumpLineLayer)
                .I32(e.ColorType).I32(e.CutDirection).I32(e.ScoringType)
                .F32(e.CutDirectionAngleOffset).Bool(e.HasFlip).I32(e.FlipLineIndex).F32(e.FlipYSide);

        public static void WallSpawn(MessageWriter w, long captureUs, in WallSpawn e) =>
            w.Reset().U8(MessageType.WallSpawn).I64(captureUs).I32(e.WallId).F32(e.Time).F32(e.Duration)
                .I32(e.LineIndex).I32(e.LineLayer).I32(e.Width).I32(e.Height);

        public static void SliderSpawn(MessageWriter w, long captureUs, in SliderSpawn e) =>
            w.Reset().U8(MessageType.SliderSpawn).I64(captureUs).U8((byte) e.Kind).I32(e.ColorType)
                .F32(e.Time).I32(e.LineIndex).I32(e.LineLayer).I32(e.CutDirection)
                .F32(e.TailTime).I32(e.TailLineIndex).I32(e.TailLineLayer).I32(e.TailCutDirection)
                .F32(e.HeadControlPointLengthMultiplier).F32(e.TailControlPointLengthMultiplier).I32(e.MidAnchorMode)
                .Bool(e.HasTailNote).I32(e.SliceCount).F32(e.SquishAmount);

        public static void Height(MessageWriter w, long captureUs, float height, float songTime) =>
            w.Reset().U8(MessageType.Height).I64(captureUs).F32(height).F32(songTime);

        public static void PauseResume(MessageWriter w, bool pause, long captureUs, float songTime) =>
            w.Reset().U8(pause ? MessageType.Pause : MessageType.Resume).I64(captureUs).F32(songTime);

        /// <summary>Header for a map chunk; the payload bytes follow directly.</summary>
        public static byte[] MapChunk(ushort requestId, uint totalLength, uint offset, byte[] data, int count)
        {
            return new MessageWriter(13 + count).U8(MessageType.MapChunk).U16(requestId).U32(totalLength).U32(offset)
                .Bytes(data, 0, count).ToArray();
        }

        public static byte[] MapError(ushort requestId, MapErrorCode code) =>
            new MessageWriter(4).U8(MessageType.MapError).U16(requestId).U8((byte) code).ToArray();

        /// <summary>The whole suggestion list (UTF-8 JSON from <see cref="Levels.Suggestions.Json"/>).</summary>
        public static byte[] Suggestions(byte[] json) =>
            new MessageWriter(5 + json.Length).U8(MessageType.Suggestions).I32(json.Length).Bytes(json).ToArray();
    }

    /// <summary>Parsed client-to-server messages. Anything that doesn't parse exactly is a protocol violation.</summary>
    public static class ClientMessages
    {
        public struct Hello
        {
            public ushort ProtocolVersion;
            public byte[]? Credential;

            /// <summary>The name the viewer entered, as sent (unsanitized).</summary>
            public string Name;
        }

        public const int MaxNameBytes = 128;

        public struct LevelRequest
        {
            public ushort RequestId;
            public string LevelId;
            public Levels.LevelFileKind Kind;
        }

        public const int MaxLevelIdBytes = 64;

        public static ushort ParseLevelListRequest(MessageReader r)
        {
            var requestId = r.U16();
            r.End();
            return requestId;
        }

        public static LevelRequest ParseLevelFileRequest(MessageReader r)
        {
            var request = new LevelRequest { RequestId = r.U16() };
            var kind = r.U8();
            if (kind != (byte) Levels.LevelFileKind.Cover && kind != (byte) Levels.LevelFileKind.Audio)
            {
                throw new ProtocolException("Unknown level file kind.");
            }

            request.Kind = (Levels.LevelFileKind) kind;
            request.LevelId = r.String(MaxLevelIdBytes);
            r.End();
            return request;
        }

        /// <summary>SuggestionAdd and SuggestionRemove: a level id, which must look like one.</summary>
        public static string ParseSuggestionChange(MessageReader r)
        {
            var id = r.String(MaxLevelIdBytes);
            r.End();
            if (!Levels.LevelLibrary.IsLevelId(id))
            {
                throw new ProtocolException("Malformed level id.");
            }

            return id;
        }

        public static string ParseRename(MessageReader r)
        {
            var name = r.String(MaxNameBytes);
            r.End();
            return name;
        }

        /// <summary>SuggestionMove: a level id and the position it should end up at.</summary>
        public static (string id, int index) ParseSuggestionMove(MessageReader r)
        {
            var id = r.String(MaxLevelIdBytes);
            var index = r.U16();
            r.End();
            if (!Levels.LevelLibrary.IsLevelId(id))
            {
                throw new ProtocolException("Malformed level id.");
            }

            return (id, index);
        }

        public static LevelRequest ParseLevelStatsRequest(MessageReader r)
        {
            var request = new LevelRequest { RequestId = r.U16(), LevelId = r.String(MaxLevelIdBytes) };
            r.End();
            return request;
        }

        public static Hello ParseHello(MessageReader r)
        {
            var hello = new Hello { ProtocolVersion = r.U16() };
            var hasCredential = r.U8();
            if (hasCredential > 1)
            {
                throw new ProtocolException("Invalid flag.");
            }

            if (hasCredential == 1)
            {
                hello.Credential = r.Bytes(Messages.CredentialBytes);
            }

            hello.Name = r.String(MaxNameBytes);
            r.End();
            return hello;
        }

        public static double ParsePing(MessageReader r)
        {
            var t = r.F64();
            r.End();
            if (double.IsNaN(t) || double.IsInfinity(t))
            {
                throw new ProtocolException("Invalid time.");
            }

            return t;
        }


        /// <summary>Upper bound for any client message; the WebSocket layer rejects larger frames.</summary>
        public static readonly int MaxMessageBytes = Math.Max(1 + 2 + 1 + Messages.CredentialBytes, 1 + 2 + 4 + 4 + Messages.MaxFileNameBytes);
    }
}
