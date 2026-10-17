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

        public static byte[] Waiting(string matchCode) =>
            new MessageWriter().U8(MessageType.Waiting).String(matchCode).ToArray();

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
                .Field("startTime", info.StartTime)
                .Field("songSpeed", info.SongSpeed)
                .Field("files", info.Files)
                .ToString();
            return new MessageWriter(512).U8(MessageType.SessionStart).U32(sessionId).String(json).ToArray();
        }

        public static byte[] SessionEnd(uint sessionId, SessionEndReason reason, float songTime) =>
            new MessageWriter(16).U8(MessageType.SessionEnd).U32(sessionId).U8((byte) reason).F32(songTime).ToArray();

        public static byte[] Idle() => new[] { MessageType.Idle };

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
    }

    /// <summary>Parsed client-to-server messages. Anything that doesn't parse exactly is a protocol violation.</summary>
    public static class ClientMessages
    {
        public struct Hello
        {
            public ushort ProtocolVersion;
            public byte[]? Credential;
        }

        public struct MapRequest
        {
            public ushort RequestId;
            public uint SessionId;
            public string FileName;
        }

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

        public static MapRequest ParseMapRequest(MessageReader r)
        {
            var request = new MapRequest
            {
                RequestId = r.U16(),
                SessionId = r.U32(),
                FileName = r.String(Messages.MaxFileNameBytes),
            };
            r.End();
            return request;
        }

        /// <summary>Upper bound for any client message; the WebSocket layer rejects larger frames.</summary>
        public static readonly int MaxMessageBytes = Math.Max(1 + 2 + 1 + Messages.CredentialBytes, 1 + 2 + 4 + 4 + Messages.MaxFileNameBytes);
    }
}
