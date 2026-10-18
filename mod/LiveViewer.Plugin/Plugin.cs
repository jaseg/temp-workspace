using System.Runtime.CompilerServices;
using IPA;
using IPA.Config.Stores;
using LiveViewer.Plugin.Recording;
using LiveViewer.Plugin.UI;
using SiraUtil.Zenject;
using IPALogger = IPA.Logging.Logger;
using IPAConfig = IPA.Config.Config;

[assembly: InternalsVisibleTo(GeneratedStore.AssemblyVisibilityTarget)]

namespace LiveViewer.Plugin
{
    [Plugin(RuntimeOptions.SingleStartInit)]
    public sealed class Plugin
    {
        private readonly LiveService _service;
        private readonly MemoryProbe _memory;

        internal static IPALogger? Log { get; private set; }

        [Init]
        public Plugin(IPALogger logger, [IPAConfig.Name("LiveViewer")] IPAConfig config, Zenjector zenjector)
        {
            Log = logger;
            SongCoreFileAccess.Install(logger);
            var settings = config.Generated<PluginConfig>();
            _service = new LiveService(settings, logger);
            _memory = new MemoryProbe(logger);
            zenjector.UseLogger(logger);
            zenjector.Install(Location.App, container => container.BindInstance(_service).AsSingle());
            zenjector.Install<MenuInstaller>(Location.Menu);
            zenjector.Install(Location.StandardPlayer, container =>
            {
                if (_service.Running)
                {
                    container.BindInterfacesAndSelfTo<LiveRecorder>().AsSingle();
                }
            });
        }

        [OnStart]
        public void OnStart() => _service.StartInBackground();

        [OnExit]
        public void OnExit()
        {
            _memory.Dispose();
            _service.Dispose();
        }
    }
}
