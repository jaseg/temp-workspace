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
        public static SessionInfo? TryDescribe(GameplayCoreSceneSetupData setup, string playerName, out IMapFileSource? map, out string reason)
        {
            map = null;
            var key = setup.beatmapKey;
            var level = setup.beatmapLevel;
            if (level == null || !key.levelId.StartsWith(CustomLevelPrefix, StringComparison.Ordinal))
            {
                reason = "not a custom level";
                return null;
            }

            var loader = SongCore.Loader.CustomLevelLoader;
            var saveData = loader != null
                ? loader.GetField<Dictionary<string, CustomLevelLoader.LoadedSaveData>, CustomLevelLoader>("_loadedBeatmapSaveData")
                : null;
            var folder = saveData != null && saveData.TryGetValue(key.levelId, out var loaded)
                ? loaded.customLevelFolderInfo.folderPath
                : null;
            if (string.IsNullOrEmpty(folder))
            {
                reason = "SongCore doesn't know the level's folder";
                return null;
            }

            var mode = key.beatmapCharacteristic.serializedName;
            var difficulty = key.difficulty.ToString();
            MapDescription description;
            try
            {
                description = MapDescription.Read(folder!, mode, difficulty);
            }
            catch (Exception e)
            {
                reason = "couldn't read its Info.dat: " + e.Message;
                return null;
            }

            if (!description.Files.ContainsKey("difficulty"))
            {
                reason = $"Info.dat has no {mode} {difficulty} file";
                return null;
            }

            map = description.Source;
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
                NoteJumpSpeed = description.NoteJumpSpeed,
                StartTime = practice?.startSongTime ?? 0,
                SongSpeed = practice != null && practice.songSpeedMul > 0
                    ? practice.songSpeedMul
                    : setup.gameplayModifiers.songSpeedMul,
                GameVersion = Application.version.Split('_')[0],
                Files = description.Files,
            };
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
