using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using LiveViewer.Server.Protocol;

namespace LiveViewer.Host
{
    /// <summary>A decoded BeatLeader replay (.bsor). Mirrors the web viewer's open-replay-decoder.js.</summary>
    public sealed class BsorReplay
    {
        public sealed class InfoSection
        {
            public string Version = "", GameVersion = "", Timestamp = "";
            public string PlayerId = "", PlayerName = "", Platform = "";
            public string TrackingSystem = "", Hmd = "", Controller = "";
            public string Hash = "", SongName = "", Mapper = "", Difficulty = "";
            public int Score;
            public string Mode = "", Environment = "", Modifiers = "";
            public float JumpDistance;
            public bool LeftHanded;
            public float Height;
            public float StartTime, FailTime, Speed;
        }

        public struct Frame
        {
            public float Time;
            public int Fps;
            public Pose Head, Left, Right;
        }

        public struct HeightEvent
        {
            public float Height, Time;
        }

        public struct PauseEvent
        {
            public long Duration;
            public float Time;
        }

        public InfoSection Info = new InfoSection();
        public List<Frame> Frames = new List<Frame>();
        public List<NoteEvent> Notes = new List<NoteEvent>();
        public List<WallEvent> Walls = new List<WallEvent>();
        public List<HeightEvent> Heights = new List<HeightEvent>();
        public List<PauseEvent> Pauses = new List<PauseEvent>();

        public static BsorReplay Decode(byte[] data)
        {
            var r = new Reader(data);
            if (r.I32() != 0x442d3d69 || r.U8() != 1)
            {
                throw new InvalidDataException("Not a BSOR v1 file.");
            }

            var replay = new BsorReplay();
            for (var section = 0; section <= 7 && r.Remaining > 0; section++)
            {
                switch (r.U8())
                {
                    case 0:
                        replay.Info = DecodeInfo(r);
                        break;
                    case 1:
                        DecodeFrames(r, replay.Frames);
                        break;
                    case 2:
                        for (int i = 0, n = r.I32(); i < n; i++)
                        {
                            replay.Notes.Add(DecodeNote(r));
                        }

                        break;
                    case 3:
                        for (int i = 0, n = r.I32(); i < n; i++)
                        {
                            replay.Walls.Add(new WallEvent { WallId = r.I32(), Energy = r.F32(), Time = r.F32(), SpawnTime = r.F32() });
                        }

                        break;
                    case 4:
                        for (int i = 0, n = r.I32(); i < n; i++)
                        {
                            replay.Heights.Add(new HeightEvent { Height = r.F32(), Time = r.F32() });
                        }

                        break;
                    case 5:
                        for (int i = 0, n = r.I32(); i < n; i++)
                        {
                            replay.Pauses.Add(new PauseEvent { Duration = r.I64(), Time = r.F32() });
                        }

                        break;
                    default:
                        // Saber offsets and custom data aren't needed for live playback.
                        return replay;
                }
            }

            return replay;
        }

        private static InfoSection DecodeInfo(Reader r) => new InfoSection
        {
            Version = r.Str(),
            GameVersion = r.Str(),
            Timestamp = r.Str(),
            PlayerId = r.Str(),
            PlayerName = r.Name(),
            Platform = r.Str(),
            TrackingSystem = r.Str(),
            Hmd = r.Str(),
            Controller = r.Str(),
            Hash = r.Str(),
            SongName = r.Str(),
            Mapper = r.Str(),
            Difficulty = r.Str(),
            Score = r.I32(),
            Mode = r.Str(),
            Environment = r.Str(),
            Modifiers = r.Str(),
            JumpDistance = r.F32(),
            LeftHanded = r.U8() != 0,
            Height = r.F32(),
            StartTime = r.F32(),
            FailTime = r.F32(),
            Speed = r.F32(),
        };

        private static void DecodeFrames(Reader r, List<Frame> frames)
        {
            for (int i = 0, n = r.I32(); i < n; i++)
            {
                var frame = new Frame { Time = r.F32(), Fps = r.I32(), Head = r.Pose(), Left = r.Pose(), Right = r.Pose() };

                // Same filtering as the web viewer: drop zero and duplicate timestamps.
                if (frame.Time != 0 && (frames.Count == 0 || frame.Time != frames[frames.Count - 1].Time))
                {
                    frames.Add(frame);
                }
            }
        }

        private static NoteEvent DecodeNote(Reader r)
        {
            var e = new NoteEvent { NoteId = r.I32(), EventTime = r.F32(), SpawnTime = r.F32(), EventType = (NoteEventType) r.I32() };
            if (e.HasCutInfo)
            {
                e.CutInfo = new NoteCutInfo
                {
                    SpeedOk = r.U8() != 0,
                    DirectionOk = r.U8() != 0,
                    SaberTypeOk = r.U8() != 0,
                    WasCutTooSoon = r.U8() != 0,
                    SaberSpeed = r.F32(),
                    SaberDirection = r.Vec3(),
                    SaberType = r.I32(),
                    TimeDeviation = r.F32(),
                    CutDirectionDeviation = r.F32(),
                    CutPoint = r.Vec3(),
                    CutNormal = r.Vec3(),
                    CutDistanceToCenter = r.F32(),
                    CutAngle = r.F32(),
                    BeforeCutRating = r.F32(),
                    AfterCutRating = r.F32(),
                };
            }

            return e;
        }

        private sealed class Reader
        {
            private readonly byte[] _data;
            private int _pos;

            public Reader(byte[] data)
            {
                _data = data;
            }

            public int Remaining => _data.Length - _pos;

            public byte U8() => _data[_pos++];

            public int I32()
            {
                var v = BitConverter.ToInt32(_data, _pos);
                _pos += 4;
                return v;
            }

            public long I64()
            {
                var v = BitConverter.ToInt64(_data, _pos);
                _pos += 8;
                return v;
            }

            public float F32()
            {
                var v = BitConverter.ToSingle(_data, _pos);
                _pos += 4;
                return v;
            }

            public Vec3 Vec3() => new Vec3(F32(), F32(), F32());

            public Pose Pose() => new Pose(Vec3(), new Quat(F32(), F32(), F32(), F32()));

            // Like the viewer: a corrupt length makes it skip a byte and retry.
            public string Str()
            {
                while (true)
                {
                    var length = BitConverter.ToInt32(_data, _pos);
                    if (length < 0 || length > 300)
                    {
                        _pos++;
                        continue;
                    }

                    var s = Encoding.UTF8.GetString(_data, _pos + 4, length);
                    _pos += 4 + length;
                    return s;
                }
            }

            // Old recorders wrote the player name's character count instead of its byte count; like the viewer, extend
            // the string until the next field (the platform string, length 5, 6 or 8) lines up.
            public string Name()
            {
                var length = BitConverter.ToInt32(_data, _pos);
                var extra = 0;
                if (length > 0)
                {
                    while (true)
                    {
                        var next = BitConverter.ToInt32(_data, _pos + 4 + length + extra);
                        if (next == 5 || next == 6 || next == 8)
                        {
                            break;
                        }

                        extra++;
                    }
                }

                var s = Encoding.UTF8.GetString(_data, _pos + 4, length + extra);
                _pos += 4 + length + extra;
                return s;
            }
        }
    }
}
