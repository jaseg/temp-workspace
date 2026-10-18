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

    /// <summary>A note as it is spawned by the game, in the game's already-modified beatmap.</summary>
    public struct NoteSpawn
    {
        public int NoteId;
        public float Time;
        public int LineIndex;
        public int LineLayer;
        public int BeforeJumpLineLayer;
        public int ColorType;
        public int CutDirection;
        public int ScoringType;
        public float CutDirectionAngleOffset;
        public int FlipLineIndex;
        public float FlipYSide;
        public bool HasFlip;
    }

    /// <summary>An obstacle as it is spawned by the game.</summary>
    public struct WallSpawn
    {
        public int WallId;
        public float Time;
        public float Duration;
        public int LineIndex;
        public int LineLayer;
        public int Width;
        public int Height;
    }

    public enum SliderKind : byte
    {
        Arc = 0,
        Chain = 1,
    }

    /// <summary>An arc or chain, as in the game's level data (after modifiers and mirroring). Times in seconds.</summary>
    public struct SliderSpawn
    {
        public SliderKind Kind;
        public int ColorType;
        public float Time;
        public int LineIndex;
        public int LineLayer;
        public int CutDirection;
        public float TailTime;
        public int TailLineIndex;
        public int TailLineLayer;
        public int TailCutDirection;

        /// <summary>Arcs only.</summary>
        public float HeadControlPointLengthMultiplier;
        public float TailControlPointLengthMultiplier;
        public int MidAnchorMode;
        public bool HasTailNote;

        /// <summary>Chains only: the number of segments including the head, and how squished they are.</summary>
        public int SliceCount;
        public float SquishAmount;
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
        public float BeatsPerMinute;
        public float StartTime;
        public float SongSpeed = 1f;

        /// <summary>The game version, e.g. "1.44.1". The viewer matches chain notes differently from 1.29 on.</summary>
        public string GameVersion = "";

        /// <summary>Tokenized, same-origin URL of the progressively streamed song audio.</summary>
        public string AudioUrl = "";

        /// <summary>Host-side compatibility metadata; never serialized to viewers.</summary>
        public Dictionary<string, string> Files = new Dictionary<string, string>();
    }
}
