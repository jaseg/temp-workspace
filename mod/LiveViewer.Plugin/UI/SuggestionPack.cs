using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using SongCore.OverrideClasses;
using UnityEngine;
using Zenject;

namespace LiveViewer.Plugin.UI
{
    /// <summary>
    /// Keeps the game and the web page in step on two things, from the main menu:
    /// the "Suggested by viewers" level pack in Custom Levels (the server's suggestion list), and the level browser's
    /// folders (whatever SongCore loads, including its folders.xml entries). Suggestions changed during a song are
    /// applied when the menu is back.
    /// </summary>
    internal sealed class SuggestionPack : IInitializable, IDisposable, ITickable
    {
        private const string PackId = "custom_levelPack_LiveViewerSuggestions";

        private static SongCoreCustomBeatmapLevelPack? _pack;

        private readonly LiveService _service;
        private Server.LiveServer? _subscribed;
        private volatile bool _dirty = true;
        private bool _foldersDirty = true;

        public SuggestionPack(LiveService service)
        {
            _service = service;
        }

        public void Initialize()
        {
            SongCore.Loader.SongsLoadedEvent += OnSongsLoaded;
        }

        public void Dispose()
        {
            SongCore.Loader.SongsLoadedEvent -= OnSongsLoaded;
            if (_subscribed != null)
            {
                _subscribed.Suggestions.Changed -= MarkDirty;
            }
        }

        public void Tick()
        {
            var server = _service.Server;
            if (server == null || !SongCore.Loader.AreSongsLoaded || SongCore.Loader.AreSongsLoading)
            {
                return;
            }

            if (_subscribed == null)
            {
                _subscribed = server;
                server.Suggestions.Changed += MarkDirty;
            }

            if (_foldersDirty)
            {
                _foldersDirty = false;
                server.Levels.SetRoots(SongCoreFolders());
            }

            if (_dirty)
            {
                _dirty = false;
                UpdatePack(server);
            }
        }

        private void OnSongsLoaded(SongCore.Loader loader, ConcurrentDictionary<string, BeatmapLevel> levels)
        {
            _foldersDirty = true;
            _dirty = true;
        }

        private void MarkDirty() => _dirty = true;

        private static IEnumerable<string> SongCoreFolders()
        {
            yield return CustomLevelPathHelper.customLevelsDirectoryPath;
            yield return Path.Combine(Application.dataPath, "CustomWIPLevels");
            foreach (var folder in SongCore.Loader.SeparateSongFolders)
            {
                if (!string.IsNullOrEmpty(folder.SongFolderEntry?.Path))
                {
                    yield return folder.SongFolderEntry!.Path;
                }
            }
        }

        /// <summary>The pack's cover (UI/SuggestedCover.svg, rendered to PNG). Game thread only.</summary>
        private static Sprite? LoadCover()
        {
            try
            {
                using var stream = typeof(SuggestionPack).Assembly.GetManifestResourceStream("LiveViewer.Plugin.UI.SuggestedCover.png");
                if (stream == null)
                {
                    return null;
                }

                var bytes = new byte[stream.Length];
                stream.Read(bytes, 0, bytes.Length);
                var texture = new Texture2D(2, 2);
                if (!texture.LoadImage(bytes))
                {
                    return null;
                }

                return Sprite.Create(texture, new Rect(0, 0, texture.width, texture.height), new Vector2(0.5f, 0.5f));
            }
            catch (Exception e)
            {
                Plugin.Log?.Warn("Can't load the suggestion pack's cover: " + e.Message);
                return null;
            }
        }

        private static void UpdatePack(Server.LiveServer server)
        {
            var repository = SongCore.Loader.CustomLevelsRepository;
            if (repository == null)
            {
                return;
            }

            // Oldest suggestion first, as the web page lists them. Levels no longer installed are left out.
            var levels = server.Suggestions.List()
                .Select(s => SongCore.Loader.GetLevelByHash(s.Id))
                .Where(l => l != null)
                .ToArray();
            if (_pack == null)
            {
                _pack = new SongCoreCustomBeatmapLevelPack(PackId, "Suggested by viewers", LoadCover() ?? SongCore.Loader.defaultCoverImage, levels, "Suggested");
            }
            else
            {
                _pack.UpdateBeatmapLevels(levels);
            }

            // Like SongCore's own folder packs: only listed while it has levels.
            var listed = repository.beatmapLevelPacks.Contains(_pack);
            if (levels.Length > 0 && !listed)
            {
                repository.AddLevelPack(_pack);
            }
            else if (levels.Length == 0 && listed)
            {
                repository.RemoveLevelPack(_pack);
            }

            SongCore.Loader.Instance?.RefreshLevelPacks();
            Plugin.Log?.Info($"Suggested by viewers: {levels.Length} level{(levels.Length == 1 ? "" : "s")}.");
        }
    }
}
