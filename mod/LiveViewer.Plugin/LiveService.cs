using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using IPA.Utilities;
using LiveViewer.Server;
using LiveViewer.Server.Levels;
using LiveViewer.Server.Web;
using IPALogger = IPA.Logging.Logger;

namespace LiveViewer.Plugin
{
    /// <summary>
    /// Owns the web server for the lifetime of the game. Starting it (certificate generation, binding) happens on a
    /// background thread so the game's startup isn't delayed; <see cref="Running"/> tells whether it succeeded.
    /// </summary>
    public sealed class LiveService : IDisposable
    {
        private readonly PluginConfig _config;
        private readonly IPALogger _logger;
        private readonly object _lock = new object();
        private LiveServer? _server;
        private BeatLeaderHttpApi? _beatLeader;
        private volatile bool _running;
        private bool _disposed;

        public LiveService(PluginConfig config, IPALogger logger)
        {
            _config = config;
            _logger = logger;
        }

        public PluginConfig Config => _config;

        /// <summary>The player's platform (Steam) name, once the menu has read it; empty before.</summary>
        public string PlatformPlayerName { get; set; } = "";

        /// <summary>Set once the server listens; read from the game thread before feeding it.</summary>
        public bool Running => _running;

        /// <summary>Why the server isn't running, for the menu; null while starting or when running.</summary>
        public string? Problem { get; private set; }

        /// <summary>Raised on a background thread once the server is listening or has failed to start.</summary>
        public event Action? StateChanged;

        public LiveServer? Server => _running ? _server : null;

        public void StartInBackground()
        {
            if (!_config.Enabled)
            {
                Problem = "Turned off in the settings.";
                return;
            }

            new Thread(Start) { IsBackground = true, Name = "LiveViewer start" }.Start();
        }

        private void Start()
        {
            try
            {
                var gameData = Path.Combine(UnityGame.InstallPath, "Beat Saber_Data");
                var options = new LiveServerOptions
                {
                    DataDirectory = Path.Combine(UnityGame.UserDataPath, "LiveViewer"),
                    Site = LoadSite(),
                    LevelFolders = new List<string>
                    {
                        Path.Combine(gameData, "CustomLevels"),
                        Path.Combine(gameData, "CustomWIPLevels"),
                    },
                };

                // Wine reports the Linux host name, which avahi already announces as <name>.local.
                var machine = Environment.MachineName.ToLowerInvariant();
                if (machine.Length > 0 && !options.HostNames.Contains(machine + ".local"))
                {
                    options.HostNames.Insert(0, machine + ".local");
                }

                if (_config.BeatLeaderStats)
                {
                    _beatLeader = new BeatLeaderHttpApi();
                    options.BeatLeader = _beatLeader;
                }

                var server = new LiveServer(options, new IpaLiveLog(_logger));
                // Read when a device waits, not here: BSIPA may still be loading the config file at this point.
                server.WaitingRoom.Changed += () =>
                {
                    if (!_config.DevAutoApprove)
                    {
                        return;
                    }

                    foreach (var pending in server.WaitingRoom.Pending)
                    {
                        _logger.Warn($"DevAutoApprove is on: letting in \"{pending.Label}\" from {pending.Address} without asking.");
                        server.WaitingRoom.Approve(pending.ConnectionId, false);
                    }
                };

                server.Levels.Known = SongCoreLevels.Describe;
                server.Start();
                lock (_lock)
                {
                    if (_disposed)
                    {
                        server.Dispose();
                        return;
                    }

                    _server = server;
                    _running = true;
                }

                foreach (var url in server.Urls)
                {
                    _logger.Info("Watch at " + url);
                }

                _logger.Info("BeatLeader star ratings in the level browser: " + (_beatLeader != null ? "on" : "off"));
            }
            catch (Exception e)
            {
                Problem = e.Message;
                _logger.Error("Couldn't start the live viewer server: " + e);
            }

            StateChanged?.Invoke();
        }

        private StaticSite? LoadSite()
        {
            using var zip = typeof(LiveService).Assembly.GetManifestResourceStream("viewer.zip");
            if (zip == null)
            {
                _logger.Warn("This build has no viewer bundle; serving the test page.");
                return null;
            }

            return StaticSite.FromZip(zip);
        }

        public void Dispose()
        {
            lock (_lock)
            {
                _disposed = true;
                _running = false;
                _server?.Dispose();
                _server = null;
            }

            _beatLeader?.Dispose();
        }

        private sealed class IpaLiveLog : ILiveLog
        {
            private readonly IPALogger _logger;

            public IpaLiveLog(IPALogger logger) => _logger = logger;

            public void Info(string message) => _logger.Info(message);

            public void Warn(string message) => _logger.Warn(message);

            public void Error(string message, Exception? exception = null) =>
                _logger.Error(exception == null ? message : message + ": " + exception);
        }
    }
}
