using System;
using System.Collections.Generic;
using IPA.Utilities;
using LiveViewer.Server.Live;
using LiveViewer.Server.Protocol;
using UnityEngine;

namespace LiveViewer.Plugin.Recording
{
    /// <summary>What viewers are told about the level being played (adapted from BeatLeader's MapEnhancer).</summary>
    internal static class SessionBuilder
    {
        private const string CustomLevelPrefix = "custom_level_";

        /// <summary>Returns null for anything but a SongCore custom level with a readable Info.dat.</summary>
        public static SessionInfo? TryDescribe(GameplayCoreSceneSetupData setup, string playerName, out SongSelection? selection, out string reason)
        {
            selection = null;
            var key = setup.beatmapKey;
            var level = setup.beatmapLevel;
            if (level == null || !key.levelId.StartsWith(CustomLevelPrefix, StringComparison.Ordinal))
            {
                reason = "not a custom level";
                return null;
            }

            var mode = key.beatmapCharacteristic.serializedName;
            var difficulty = key.difficulty.ToString();
            if (!TryRead(key.levelId, mode, difficulty, out var description, out reason))
            {
                return null;
            }

            selection = Selection(key.levelId, level, description!);
            var settings = setup.playerSpecificSettings;
            var practice = setup.practiceSettings;
            var hash = key.levelId.Substring(CustomLevelPrefix.Length);
            // WIP and duplicate levels get a suffix after the hash ("<hash> WIP"); viewers only need the hash.
            var space = hash.IndexOf(' ');
            reason = "";
            return new SessionInfo
            {
                Hash = space > 0 ? hash.Substring(0, space) : hash,
                SongName = level.songName ?? "",
                SongSubName = level.songSubName ?? "",
                SongAuthor = level.songAuthorName ?? "",
                Mapper = string.Join(", ", level.allMappers ?? Array.Empty<string>()),
                Difficulty = difficulty,
                Mode = mode,
                Environment = setup.targetEnvironmentInfo != null ? setup.targetEnvironmentInfo.serializedName : "",
                Modifiers = string.Join(",", Modifiers(setup.gameplayModifiers)),
                PlayerName = playerName,
                LeftHanded = settings.leftHanded,
                PlayerHeight = settings.automaticPlayerHeight ? 0 : settings.playerHeight,
                NoteJumpSpeed = description!.NoteJumpSpeed,
                BeatsPerMinute = level.beatsPerMinute,
                StartTime = practice?.startSongTime ?? 0,
                SongSpeed = practice != null && practice.songSpeedMul > 0
                    ? practice.songSpeedMul
                    : setup.gameplayModifiers.songSpeedMul,
                GameVersion = Application.version.Split('_')[0],
            };
        }

        public static bool TryDescribeSelection(BeatmapKey key, BeatmapLevel level, out SongSelection? selection)
        {
            selection = null;
            if (level == null || !key.levelId.StartsWith(CustomLevelPrefix, StringComparison.Ordinal)) return false;
            if (!TryRead(key.levelId, key.beatmapCharacteristic.serializedName, key.difficulty.ToString(),
                    out var description, out _)) return false;
            selection = Selection(key.levelId, level, description!);
            return true;
        }

        private static SongSelection Selection(string levelId, BeatmapLevel level, MapDescription description)
        {
            var hash = levelId.Substring(CustomLevelPrefix.Length);
            var space = hash.IndexOf(' ');
            var source = description.Source;
            return new SongSelection
            {
                Hash = space > 0 ? hash.Substring(0, space) : hash,
                SongName = level.songName ?? "",
                SongSubName = level.songSubName ?? "",
                SongAuthor = level.songAuthorName ?? "",
                BeatsPerMinute = level.beatsPerMinute,
                Audio = new MapAudioFile(source, description.Files["audio"]),
            };
        }

        private static bool TryRead(string levelId, string mode, string difficulty,
            out MapDescription? description, out string reason)
        {
            description = null;
            var loader = SongCore.Loader.CustomLevelLoader;
            var saveData = loader != null
                ? loader.GetField<Dictionary<string, CustomLevelLoader.LoadedSaveData>, CustomLevelLoader>("_loadedBeatmapSaveData")
                : null;
            var folder = saveData != null && saveData.TryGetValue(levelId, out var loaded)
                ? loaded.customLevelFolderInfo.folderPath
                : null;
            if (string.IsNullOrEmpty(folder))
            {
                reason = "SongCore doesn't know the level's folder";
                return false;
            }

            try
            {
                description = MapDescription.Read(folder!, mode, difficulty);
            }
            catch (Exception e)
            {
                reason = "couldn't read its Info.dat: " + e.Message;
                return false;
            }

            if (!description.Files.ContainsKey("difficulty") || !description.Files.ContainsKey("audio"))
            {
                reason = $"Info.dat has no {mode} {difficulty} map or song audio";
                description = null;
                return false;
            }

            reason = "";
            return true;
        }

        private static IEnumerable<string> Modifiers(GameplayModifiers m)
        {
            if (m.disappearingArrows) yield return "DA";
            if (m.songSpeed == GameplayModifiers.SongSpeed.Faster) yield return "FS";
            if (m.songSpeed == GameplayModifiers.SongSpeed.Slower) yield return "SS";
            if (m.songSpeed == GameplayModifiers.SongSpeed.SuperFast) yield return "SF";
            if (m.ghostNotes) yield return "GN";
            if (m.noArrows) yield return "NA";
            if (m.noBombs) yield return "NB";
            if (m.noFailOn0Energy) yield return "NF";
            if (m.enabledObstacleType == GameplayModifiers.EnabledObstacleType.NoObstacles) yield return "NO";
            if (m.strictAngles) yield return "SA";
            if (m.smallCubes) yield return "SC";
            if (m.proMode) yield return "PM";
            if (m.failOnSaberClash) yield return "CS";
            if (m.instaFail) yield return "IF";
            if (m.energyType == GameplayModifiers.EnergyType.Battery) yield return "BE";
        }
    }
}
