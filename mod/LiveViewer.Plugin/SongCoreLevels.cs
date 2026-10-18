using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using LiveViewer.Server.Levels;

namespace LiveViewer.Plugin
{
    /// <summary>
    /// Describes level folders from what SongCore and the game already loaded: SongCore's hash (cached across
    /// restarts) and the game's per-difficulty object counts. The level browser then reads only Info.dat; hashing and
    /// counting every difficulty file of a large library made the game's heap grow by gigabytes.
    /// </summary>
    internal static class SongCoreLevels
    {
        private const string CustomLevelPrefix = "custom_level_";

        /// <summary>Null for folders SongCore hasn't loaded (yet); the game can't play those either.</summary>
        public static KnownLevel? Describe(string folder)
        {
            if (!SongCore.Loader.AreSongsLoaded || SongCore.Loader.AreSongsLoading)
            {
                return null;
            }

            var level = Find(folder);
            if (level == null)
            {
                return null;
            }

            var id = level.levelID;
            if (!id.StartsWith(CustomLevelPrefix, StringComparison.Ordinal))
            {
                return null;
            }

            // Duplicate copies get a suffix after the hash ("custom_level_<hash> <folder>").
            var hash = id.Substring(CustomLevelPrefix.Length);
            var space = hash.IndexOf(' ');
            var known = new KnownLevel
            {
                Hash = (space > 0 ? hash.Substring(0, space) : hash).ToLowerInvariant(),
                Duration = level.songDuration,
            };
            foreach (var pair in level.beatmapBasicData)
            {
                var data = pair.Value;
                known.Counts[pair.Key.Item1.serializedName + "/" + pair.Key.Item2] = (data.notesCount, data.bombsCount, data.obstaclesCount);
            }

            return LevelLibrary.IsLevelId(known.Hash) ? known : null;
        }

        private static readonly object IndexLock = new object();
        private static Dictionary<string, BeatmapLevel> _index = new Dictionary<string, BeatmapLevel>();
        private static int _indexedCount = -1;

        // SongCore keys its levels by folder path as it found them (custom levels, WIP levels and extra folders);
        // the library's paths may differ in form, so both are normalized. Rebuilt when SongCore's counts change.
        private static BeatmapLevel? Find(string folder)
        {
            var count = SongCore.Loader.CustomLevels.Count + SongCore.Loader.CustomWIPLevels.Count
                        + SongCore.Loader.SeparateSongFolders.Sum(f => f.Levels.Count);
            lock (IndexLock)
            {
                if (count != _indexedCount)
                {
                    var index = new Dictionary<string, BeatmapLevel>(StringComparer.OrdinalIgnoreCase);
                    var all = SongCore.Loader.CustomLevels
                        .Concat(SongCore.Loader.CustomWIPLevels)
                        .Concat(SongCore.Loader.SeparateSongFolders.SelectMany(f => f.Levels));
                    foreach (var pair in all)
                    {
                        index[Normalize(pair.Key)] = pair.Value;
                    }

                    _index = index;
                    _indexedCount = count;
                }

                return _index.TryGetValue(Normalize(folder), out var level) ? level : null;
            }
        }

        private static string Normalize(string path)
        {
            try
            {
                path = Path.GetFullPath(path);
            }
            catch (Exception e) when (e is ArgumentException || e is NotSupportedException || e is PathTooLongException)
            {
                // Keep it as it is.
            }

            return path.Replace(Path.AltDirectorySeparatorChar, Path.DirectorySeparatorChar).TrimEnd(Path.DirectorySeparatorChar);
        }
    }
}
