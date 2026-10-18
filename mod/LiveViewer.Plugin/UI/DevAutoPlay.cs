using System;
using System.Linq;
using System.Threading.Tasks;
using Zenject;

namespace LiveViewer.Plugin.UI
{
    /// <summary>
    /// Testing only (<see cref="PluginConfig.DevAutoPlayLevel"/>): once per game start, plays a custom level from the
    /// main menu with No Fail on, so a whole session can be streamed on the device without anyone in the headset.
    /// </summary>
    internal sealed class DevAutoPlay : IInitializable
    {
        private static bool _played;

        private readonly LiveService _service;
        private readonly MenuTransitionsHelper _transitions;
        private readonly PlayerDataModel _playerData;
        private readonly EnvironmentsListModel _environments;

        public DevAutoPlay(LiveService service, MenuTransitionsHelper transitions, PlayerDataModel playerData, EnvironmentsListModel environments)
        {
            _service = service;
            _transitions = transitions;
            _playerData = playerData;
            _environments = environments;
        }

        public async void Initialize()
        {
            var spec = _service.Config.DevAutoPlayLevel;
            if (_played || string.IsNullOrEmpty(spec))
            {
                return;
            }

            _played = true;
            try
            {
                // "<hash>" or "<hash> <Difficulty>"; the hardest Standard difficulty by default.
                var parts = spec.Split(' ');
                for (var i = 0; i < 120 && (!SongCore.Loader.AreSongsLoaded || !_service.Running); i++)
                {
                    await Task.Delay(1000);
                }

                var level = SongCore.Loader.GetLevelByHash(parts[0]);
                if (level == null)
                {
                    Plugin.Log?.Warn("DevAutoPlayLevel: no installed level with hash " + parts[0]);
                    return;
                }

                var keys = level.GetBeatmapKeys().Where(k => k.beatmapCharacteristic.serializedName == "Standard").ToList();
                var key = parts.Length > 1
                    ? keys.FirstOrDefault(k => k.difficulty.ToString() == parts[1])
                    : keys.OrderByDescending(k => k.difficulty).FirstOrDefault();
                if (key.beatmapCharacteristic == null)
                {
                    Plugin.Log?.Warn("DevAutoPlayLevel: the level has no such Standard difficulty");
                    return;
                }

                await Task.Delay(3000);
                Plugin.Log?.Warn($"DevAutoPlayLevel: starting {level.songName} {key.difficulty} for a test.");
                var player = _playerData.playerData;
                _transitions.StartStandardLevel("Solo", in key, level, player.overrideEnvironmentSettings, null, false,
                    player.gameplayModifiers.CopyWith(noFailOn0Energy: true), player.playerSpecificSettings, null,
                    _environments, null, null, null, null, null, null, null);
            }
            catch (Exception e)
            {
                Plugin.Log?.Error("DevAutoPlayLevel failed: " + e);
            }
        }
    }
}
