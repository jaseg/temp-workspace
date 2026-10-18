using System;
using BeatSaberMarkupLanguage;
using BeatSaberMarkupLanguage.MenuButtons;
using HMUI;
using Zenject;

namespace LiveViewer.Plugin.UI
{
    internal sealed class MenuInstaller : Installer
    {
        public override void InstallBindings()
        {
            Container.Bind<LiveViewController>().FromNewComponentAsViewController().AsSingle();
            Container.Bind<LiveFlowCoordinator>().FromNewComponentOnNewGameObject().AsSingle();
            Container.BindInterfacesTo<MenuButtonManager>().AsSingle();
            Container.BindInterfacesTo<SuggestionPack>().AsSingle();
            Container.BindInterfacesTo<DevAutoPlay>().AsSingle();
        }
    }

    internal sealed class LiveFlowCoordinator : FlowCoordinator
    {
        [Inject]
        private readonly MainFlowCoordinator _mainFlowCoordinator = null!;

        [Inject]
        private readonly LiveViewController _view = null!;

        protected override void DidActivate(bool firstActivation, bool addedToHierarchy, bool screenSystemEnabling)
        {
            if (firstActivation)
            {
                SetTitle("Live Viewer");
                showBackButton = true;
                ProvideInitialViewControllers(_view);
            }
        }

        protected override void BackButtonWasPressed(ViewController topViewController) =>
            _mainFlowCoordinator.DismissFlowCoordinator(this);
    }

    /// <summary>
    /// The "Live Viewer" main-menu button. Its label shows how many devices are waiting, so the player notices them
    /// without opening the screen. Server events arrive on network threads and are applied on the next frame.
    /// </summary>
    internal sealed class MenuButtonManager : IInitializable, IDisposable, ITickable
    {
        private readonly LiveService _service;
        private readonly MainFlowCoordinator _mainFlowCoordinator;
        private readonly LiveFlowCoordinator _flowCoordinator;
        private readonly LiveViewController _view;
        private readonly MenuButtons _menuButtons;
        private readonly MenuButton _button;
        private volatile bool _dirty = true;
        private Server.LiveServer? _subscribed;

        public MenuButtonManager(LiveService service, MainFlowCoordinator mainFlowCoordinator, LiveFlowCoordinator flowCoordinator,
            LiveViewController view, MenuButtons menuButtons)
        {
            _service = service;
            _mainFlowCoordinator = mainFlowCoordinator;
            _flowCoordinator = flowCoordinator;
            _view = view;
            _menuButtons = menuButtons;
            _button = new MenuButton("Live Viewer", "Who may watch you play, and where", Open);
        }

        public void Initialize()
        {
            _menuButtons.RegisterButton(_button);
            _service.StateChanged += MarkDirty;
        }

        public void Dispose()
        {
            _service.StateChanged -= MarkDirty;
            if (_subscribed != null)
            {
                _subscribed.WaitingRoom.Changed -= MarkDirty;
                _subscribed.Devices.Changed -= MarkDirty;
            }

            _menuButtons.UnregisterButton(_button);
        }

        public void Tick()
        {
            if (!_dirty)
            {
                return;
            }

            _dirty = false;
            var server = _service.Server;
            if (server != null && _subscribed == null)
            {
                _subscribed = server;
                server.WaitingRoom.Changed += MarkDirty;
                server.Devices.Changed += MarkDirty;
            }

            var waiting = server?.WaitingRoom.Pending.Count ?? 0;
            _button.Text = waiting > 0 ? $"Live Viewer ({waiting} waiting)" : "Live Viewer";
            _view.Refresh();
        }

        private void MarkDirty() => _dirty = true;

        private void Open() => _mainFlowCoordinator.PresentFlowCoordinator(_flowCoordinator);
    }
}
