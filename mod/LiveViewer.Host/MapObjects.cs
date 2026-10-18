using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using LiveViewer.Server.Live;
using LiveViewer.Server.Protocol;
using Newtonsoft.Json.Linq;

namespace LiveViewer.Host
{
    /// <summary>
    /// Notes, walls, arcs and chains of the replayed difficulty, as the game would send them. The game sends what it
    /// spawns; the fake-live host has only the map, so it reads the difficulty file (v2, v3 or v4) at the map's base
    /// BPM. Every note gets the normal scoring type, and chain links aren't sent as notes.
    /// </summary>
    public static class MapObjects
    {
        private const int ScoringNoScore = 0, ScoringNormal = 1;
        private const int ColorNone = -1;
        private const int CutAny = 8;

        public static (List<NoteSpawn> notes, List<WallSpawn> walls, List<SliderSpawn> sliders) Read(MapDescription map)
        {
            var notes = new List<NoteSpawn>();
            var walls = new List<WallSpawn>();
            var sliders = new List<SliderSpawn>();
            if (!map.Files.TryGetValue("difficulty", out var file) || map.BeatsPerMinute <= 0)
            {
                return (notes, walls, sliders);
            }

            var root = JObject.Parse(File.ReadAllText(Path.Combine(map.Directory, file)));
            var secondsPerBeat = 60f / map.BeatsPerMinute;
            float Seconds(JToken? beats) => (beats?.Value<float>() ?? 0) * secondsPerBeat;
            int Int(JToken? t) => t?.Value<int>() ?? 0;
            float Float(JToken? t) => t?.Value<float>() ?? 0;
            JArray Array(string name) => root[name] as JArray ?? new JArray();

            if (root["_notes"] != null || root["_obstacles"] != null)
            {
                foreach (var n in Array("_notes").OfType<JObject>())
                {
                    var bomb = Int(n["_type"]) == 3;
                    notes.Add(Note(Seconds(n["_time"]), Int(n["_lineIndex"]), Int(n["_lineLayer"]),
                        bomb ? ColorNone : Int(n["_type"]), bomb ? CutAny : Int(n["_cutDirection"]), 0, bomb));
                }

                foreach (var o in Array("_obstacles").OfType<JObject>())
                {
                    var crouch = Int(o["_type"]) == 1;
                    walls.Add(Wall(Seconds(o["_time"]), Seconds(o["_duration"]), Int(o["_lineIndex"]),
                        crouch ? 2 : 0, Int(o["_width"]), crouch ? 3 : 5));
                }
            }
            else if (root["colorNotesData"] != null)
            {
                // v4: objects point into shared data arrays.
                JObject Data(string name, JObject o) => Array(name).ElementAtOrDefault(Int(o["i"])) as JObject ?? new JObject();
                foreach (var n in Array("colorNotes").OfType<JObject>())
                {
                    var d = Data("colorNotesData", n);
                    notes.Add(Note(Seconds(n["b"]), Int(d["x"]), Int(d["y"]), Int(d["c"]), Int(d["d"]), Int(d["a"]), false));
                }

                foreach (var n in Array("bombNotes").OfType<JObject>())
                {
                    var d = Data("bombNotesData", n);
                    notes.Add(Note(Seconds(n["b"]), Int(d["x"]), Int(d["y"]), ColorNone, CutAny, 0, true));
                }

                foreach (var o in Array("obstacles").OfType<JObject>())
                {
                    var d = Data("obstaclesData", o);
                    walls.Add(Wall(Seconds(o["b"]), Seconds(d["d"]), Int(d["x"]), Int(d["y"]), Int(d["w"]), Int(d["h"])));
                }

                // Arcs and chains point at color note data for their head (and an arc's tail).
                JObject At(string name, JToken? index) => Array(name).ElementAtOrDefault(Int(index)) as JObject ?? new JObject();
                foreach (var a in Array("arcs").OfType<JObject>())
                {
                    var head = At("colorNotesData", a["hi"]);
                    var tail = At("colorNotesData", a["ti"]);
                    var arc = At("arcsData", a["ai"]);
                    sliders.Add(new SliderSpawn
                    {
                        Kind = SliderKind.Arc, ColorType = Int(head["c"]),
                        Time = Seconds(a["hb"]), LineIndex = Int(head["x"]), LineLayer = Int(head["y"]), CutDirection = Int(head["d"]),
                        TailTime = Seconds(a["tb"]), TailLineIndex = Int(tail["x"]), TailLineLayer = Int(tail["y"]), TailCutDirection = Int(tail["d"]),
                        HeadControlPointLengthMultiplier = Float(arc["m"]), TailControlPointLengthMultiplier = Float(arc["tm"]),
                        MidAnchorMode = Int(arc["a"]), HasTailNote = true,
                    });
                }

                foreach (var c in Array("chains").OfType<JObject>())
                {
                    var head = At("colorNotesData", c["i"]);
                    var chain = At("chainsData", c["ci"]);
                    sliders.Add(new SliderSpawn
                    {
                        Kind = SliderKind.Chain, ColorType = Int(head["c"]),
                        Time = Seconds(c["hb"]), LineIndex = Int(head["x"]), LineLayer = Int(head["y"]), CutDirection = Int(head["d"]),
                        TailTime = Seconds(c["tb"]), TailLineIndex = Int(chain["tx"]), TailLineLayer = Int(chain["ty"]),
                        SliceCount = Int(chain["c"]), SquishAmount = Float(chain["s"]),
                    });
                }
            }
            else
            {
                foreach (var n in Array("colorNotes").OfType<JObject>())
                {
                    notes.Add(Note(Seconds(n["b"]), Int(n["x"]), Int(n["y"]), Int(n["c"]), Int(n["d"]), Int(n["a"]), false));
                }

                foreach (var n in Array("bombNotes").OfType<JObject>())
                {
                    notes.Add(Note(Seconds(n["b"]), Int(n["x"]), Int(n["y"]), ColorNone, CutAny, 0, true));
                }

                foreach (var o in Array("obstacles").OfType<JObject>())
                {
                    walls.Add(Wall(Seconds(o["b"]), Seconds(o["d"]), Int(o["x"]), Int(o["y"]), Int(o["w"]), Int(o["h"])));
                }

                foreach (var a in Array("sliders").OfType<JObject>())
                {
                    sliders.Add(new SliderSpawn
                    {
                        Kind = SliderKind.Arc, ColorType = Int(a["c"]),
                        Time = Seconds(a["b"]), LineIndex = Int(a["x"]), LineLayer = Int(a["y"]), CutDirection = Int(a["d"]),
                        TailTime = Seconds(a["tb"]), TailLineIndex = Int(a["tx"]), TailLineLayer = Int(a["ty"]), TailCutDirection = Int(a["tc"]),
                        HeadControlPointLengthMultiplier = Float(a["mu"]), TailControlPointLengthMultiplier = Float(a["tmu"]),
                        MidAnchorMode = Int(a["m"]), HasTailNote = true,
                    });
                }

                foreach (var c in Array("burstSliders").OfType<JObject>())
                {
                    sliders.Add(new SliderSpawn
                    {
                        Kind = SliderKind.Chain, ColorType = Int(c["c"]),
                        Time = Seconds(c["b"]), LineIndex = Int(c["x"]), LineLayer = Int(c["y"]), CutDirection = Int(c["d"]),
                        TailTime = Seconds(c["tb"]), TailLineIndex = Int(c["tx"]), TailLineLayer = Int(c["ty"]),
                        SliceCount = Int(c["sc"]), SquishAmount = Float(c["s"]),
                    });
                }
            }

            notes.Sort((a, b) => a.Time.CompareTo(b.Time));
            walls.Sort((a, b) => a.Time.CompareTo(b.Time));
            sliders.Sort((a, b) => a.Time.CompareTo(b.Time));
            return (notes, walls, sliders);
        }

        private static NoteSpawn Note(float time, int line, int layer, int color, int direction, int angle, bool bomb)
        {
            var scoring = bomb ? ScoringNoScore : ScoringNormal;
            return new NoteSpawn
            {
                // BeatLeader's note id, as the recorder computes it.
                NoteId = (scoring + 2) * 10000 + line * 1000 + layer * 100 + color * 10 + direction,
                Time = time,
                LineIndex = line,
                LineLayer = layer,
                BeforeJumpLineLayer = layer,
                ColorType = color,
                CutDirection = direction,
                ScoringType = scoring,
                CutDirectionAngleOffset = angle,
            };
        }

        private static WallSpawn Wall(float time, float duration, int line, int layer, int width, int height) => new WallSpawn
        {
            WallId = line * 100 + (layer == 0 ? 0 : 1) * 10 + width,
            Time = time,
            Duration = duration,
            LineIndex = line,
            LineLayer = layer,
            Width = width,
            Height = height,
        };
    }
}
