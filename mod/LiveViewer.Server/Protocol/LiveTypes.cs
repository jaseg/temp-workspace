using System.Collections.Generic;

namespace LiveViewer.Server.Protocol
{
    public struct Vec3
    {
        public float X, Y, Z;

        public Vec3(float x, float y, float z)
        {
            X = x;
            Y = y;
            Z = z;
        }
    }

    public struct Quat
    {
        public float X, Y, Z, W;

        public Quat(float x, float y, float z, float w)
        {
            X = x;
            Y = y;
            Z = z;
            W = w;
        }
    }

    public struct Pose
    {
        public Vec3 Position;
        public Quat Rotation;

        public Pose(Vec3 position, Quat rotation)
        {
            Position = position;
            Rotation = rotation;
        }
    }

    /// <summary>BSOR note event type.</summary>
    public enum NoteEventType
    {
        Good = 0,
        Bad = 1,
        Miss = 2,
        Bomb = 3,
    }

    /// <summary>Same fields and order as BSOR's NoteCutInfo.</summary>
    public struct NoteCutInfo
    {
        public bool SpeedOk;
        public bool DirectionOk;
        public bool SaberTypeOk;
        public bool WasCutTooSoon;
        public float SaberSpeed;
        public Vec3 SaberDirection;
        public int SaberType;
        public float TimeDeviation;
        public float CutDirectionDeviation;
        public Vec3 CutPoint;
        public Vec3 CutNormal;
        public float CutDistanceToCenter;
        public float CutAngle;
        public float BeforeCutRating;
        public float AfterCutRating;
    }

    /// <summary>Same fields and order as a BSOR note event.</summary>
    public struct NoteEvent
    {
        public int NoteId;
        public float EventTime;
        public float SpawnTime;
        public NoteEventType EventType;
        public NoteCutInfo CutInfo;

        public bool HasCutInfo => EventType == NoteEventType.Good || EventType == NoteEventType.Bad;
    }

    /// <summary>Same fields and order as a BSOR wall event.</summary>
    public struct WallEvent
    {
        public int WallId;
        public float Energy;
        public float Time;
        public float SpawnTime;
    }

    /// <summary>
    /// What a viewer needs to set up a song. Serialized as JSON in the SessionStart message.
    /// </summary>
    public sealed class SessionInfo
    {
        public string Hash = "";
        public string SongName = "";
        public string SongSubName = "";
        public string SongAuthor = "";
        public string Mapper = "";
        public string Difficulty = "";
        public string Mode = "";
        public string Environment = "";
        public string Modifiers = "";
        public string PlayerName = "";
        public bool LeftHanded;
        public float PlayerHeight;
        public float JumpDistance;
        public float NoteJumpSpeed;
        public float StartTime;
        public float SongSpeed = 1f;

        /// <summary>The game version, e.g. "1.44.1". The viewer matches chain notes differently from 1.29 on.</summary>
        public string GameVersion = "";

        /// <summary>Map file roles ("info", "difficulty", "audio", "cover", ...) to file names.</summary>
        public Dictionary<string, string> Files = new Dictionary<string, string>();
    }
}
